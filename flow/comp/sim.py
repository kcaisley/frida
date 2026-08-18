"""HDL21 comparator testbench and named TSMC65 Spectre campaign runner."""

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, MosType, R, Vdc, Vpulse, Vpwl

from flow.circuit.netlist import pwl_points_to_wave, write_spectre_input
from flow.circuit.params import (
    PvtParams,
    build_uniform_sweep_values,
    supply_voltage,
    temperature_c,
    validate_uniform_sweep,
)
from flow.pdks import set_pdk

from .subckt import Bias, Comp, CompParams, Stages, State, is_valid_comp_params

# ``python -m flow.comp.sim`` executes this file as ``__main__``. Register that
# module under its canonical import name before the typed H5 layer imports
# ``CompTbParams``; otherwise Python creates a second class object and strict
# dataclass type validation rejects an otherwise identical parameter instance.
if __name__ == "__main__":
    sys.modules["flow.comp.sim"] = sys.modules[__name__]

BASE_PATH = Path(__file__).resolve().parents[2]
MODEL_LIBRARY = Path("/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs")
MAX_PARALLEL_SIMULATIONS = 18
SPECTRE_THREADS_PER_SIMULATION = 1
RAW_STROBE_PERIOD_S = 500e-12
TRANSIENT_NOISE_MAX_HZ = 25e9
TRANSIENT_NOISE_SEED = 1
TSMC65_WMIN_UM = 0.12
TSMC65_LMIN_UM = 0.06
TSMC65_AREA_UNIT_UM2 = TSMC65_WMIN_UM * TSMC65_LMIN_UM

# The generated output decision latch is not the standard-cell latch used on
# FRIDA65A. Its sizes are held near the existing generated implementation while
# the comparator core dimensions reproduce the fabricated schematic.
FRIDA65_WIDTH_UNITS = {
    "diffpair_w": 37,  # 4.4 um effective / 120 nm
    "tail_w": 5,  # 550 nm / 120 nm
    "rst_w": 8,  # 1.0 um effective / 120 nm
    "latch_on_w": 25,  # 3.0 um effective / 120 nm
    "latch_init_w": 33,  # 4.0 um effective / 120 nm
    "srlatch_n_w": 4,
    "srlatch_p_w": 8,
}
FRIDA65_LENGTH_UNITS = {
    "diffpair_l": 5,  # 300 nm / 60 nm
    "tail_l": 13,  # 800 nm / 60 nm
    "rst_l": 1,  # 60 nm / 60 nm
    "latch_on_l": 6,  # 350 nm / 60 nm
    "latch_init_l": 17,  # 1.0 um / 60 nm
}


@h.paramclass
class CompTbParams:
    """Typed comparator campaign and testbench parameters."""

    pvt = h.Param(dtype=PvtParams, desc="PVT conditions", default=PvtParams())
    comp = h.Param(dtype=CompParams, desc="Comparator parameters", default=CompParams())
    vin_cm_values_v = h.Param(
        dtype=tuple[h.Scalar, ...],
        desc="Comparator input common-mode values",
        default=(0.8,),
    )
    sweep_min_v = h.Param(dtype=h.Scalar, desc="Inclusive differential-input minimum", default=-3.0e-3)
    sweep_max_v = h.Param(dtype=h.Scalar, desc="Inclusive differential-input maximum", default=3.0e-3)
    sweep_step_v = h.Param(dtype=h.Scalar, desc="Differential-input grid step", default=100.0e-6)
    conversions = h.Param(dtype=int, desc="Repeated decisions per differential-input point", default=100)
    reset_time_s = h.Param(dtype=h.Scalar, desc="Reset interval before each evaluation", default=10.0e-9)
    evaluation_time_s = h.Param(dtype=h.Scalar, desc="Comparator evaluation interval", default=30.0e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Clock and input transition time", default=100.0e-12)
    source_resistance_ohm = h.Param(dtype=h.Scalar, desc="Input source resistance", default=1_000.0)
    source_capacitance_f = h.Param(dtype=h.Scalar, desc="Input source capacitance", default=100.0e-15)
    output_load_f = h.Param(dtype=h.Scalar, desc="Load capacitance on each output", default=10.0e-15)


if __name__ == "__main__":
    CompTbParams.__module__ = "flow.comp.sim"


@dataclass(frozen=True, slots=True)
class CompCandidate:
    """One stable comparator campaign candidate."""

    candidate_id: str
    label: str
    comp: CompParams
    topology_index: int
    size_profile: str
    device_width_signature: tuple[tuple[str, int], ...]
    device_geometry_signature: tuple[tuple[str, int, int], ...]
    total_width_units: int
    total_active_area_units: int
    total_active_area_um2: float


def validate_comp_tb_params(params: CompTbParams) -> None:
    """Validate standalone comparator campaign conditions."""

    validate_uniform_sweep(params.sweep_min_v, params.sweep_max_v, params.sweep_step_v)
    common_modes = tuple(float(value) for value in params.vin_cm_values_v)
    if not common_modes or not all(math.isfinite(value) for value in common_modes):
        raise ValueError("comparator common modes must be a non-empty finite sequence")
    if len(set(common_modes)) != len(common_modes):
        raise ValueError("comparator common modes must be unique")
    if isinstance(params.conversions, bool) or params.conversions <= 0:
        raise ValueError("comparator conversions must be a positive integer")
    positive_fields = (
        "reset_time_s",
        "evaluation_time_s",
        "transition_time_s",
        "source_resistance_ohm",
        "source_capacitance_f",
        "output_load_f",
    )
    for name in positive_fields:
        value = float(getattr(params, name))
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"comparator {name} must be finite and positive")
    if float(params.transition_time_s) >= min(float(params.reset_time_s), float(params.evaluation_time_s)):
        raise ValueError("comparator transition time must be shorter than reset and evaluation")


def cycle_time_s(params: CompTbParams) -> float:
    """Return one reset-plus-evaluation decision-cycle duration."""

    return float(params.reset_time_s) + float(params.evaluation_time_s)


def differential_values_v(params: CompTbParams) -> tuple[float, ...]:
    """Return the exact nominal differential-input grid."""

    return build_uniform_sweep_values(params.sweep_min_v, params.sweep_max_v, params.sweep_step_v)


def trial_count(params: CompTbParams) -> int:
    """Return the complete number of comparator decisions in one case."""

    return len(params.vin_cm_values_v) * len(differential_values_v(params)) * params.conversions


def simulation_stop_s(params: CompTbParams) -> float:
    """Return the transient stop time for all scheduled trials."""

    return trial_count(params) * cycle_time_s(params)


def _input_pwl_points(values: Sequence[float], dwell_s: float, transition_s: float) -> list[tuple[float, float]]:
    """Build point changes during the reset interval at each grid boundary."""

    if not values:
        raise ValueError("comparator PWL requires at least one value")
    points = [(0.0, float(values[0]))]
    for index, value in enumerate(values[1:], start=1):
        boundary_s = index * dwell_s
        points.append((boundary_s, float(values[index - 1])))
        points.append((boundary_s + transition_s, float(value)))
    return points


@h.generator
def CompTb(params: CompTbParams) -> h.Module:
    """Generate a complete comparator testbench from typed parameters."""

    validate_comp_tb_params(params)
    vdd = supply_voltage(params.pvt.v, tech_name="tsmc65")
    cycle_s = cycle_time_s(params)

    @h.module
    class CompTb:
        vss = h.Port(desc="Simulator ground")
        vdd = h.Signal()
        vin_p_src = h.Signal()
        vin_n_src = h.Signal()
        in_p = h.Signal()
        in_n = h.Signal()
        clk = h.Signal()
        clk_b = h.Signal()
        out_p = h.Signal()
        out_n = h.Signal()

    CompTb.vvdd = Vdc(dc=vdd)(p=CompTb.vdd, n=CompTb.vss)
    CompTb.rsrc_p = R(r=params.source_resistance_ohm)(p=CompTb.vin_p_src, n=CompTb.in_p)
    CompTb.rsrc_n = R(r=params.source_resistance_ohm)(p=CompTb.vin_n_src, n=CompTb.in_n)
    CompTb.csrc_p = C(c=params.source_capacitance_f)(p=CompTb.in_p, n=CompTb.vss)
    CompTb.csrc_n = C(c=params.source_capacitance_f)(p=CompTb.in_n, n=CompTb.vss)

    # Every cycle begins with a 10 ns reset and then provides the full 30 ns
    # evaluation interval requested for near-metastable decisions.
    CompTb.vclk = Vpulse(
        v1=0.0,
        v2=vdd,
        period=cycle_s,
        width=params.evaluation_time_s,
        rise=params.transition_time_s,
        fall=params.transition_time_s,
        delay=params.reset_time_s,
    )(p=CompTb.clk, n=CompTb.vss)
    CompTb.vclkb = Vpulse(
        v1=vdd,
        v2=0.0,
        period=cycle_s,
        width=params.evaluation_time_s,
        rise=params.transition_time_s,
        fall=params.transition_time_s,
        delay=params.reset_time_s,
    )(p=CompTb.clk_b, n=CompTb.vss)
    CompTb.cload_p = C(c=params.output_load_f)(p=CompTb.out_p, n=CompTb.vss)
    CompTb.cload_n = C(c=params.output_load_f)(p=CompTb.out_n, n=CompTb.vss)
    CompTb.dut = Comp(params.comp)(
        inp=CompTb.in_p,
        inn=CompTb.in_n,
        outp=CompTb.out_p,
        outn=CompTb.out_n,
        clk=CompTb.clk,
        clkb=CompTb.clk_b,
        vdd=CompTb.vdd,
        vss=CompTb.vss,
    )

    vin_p_values: list[float] = []
    vin_n_values: list[float] = []
    for vcm in params.vin_cm_values_v:
        for vdiff in differential_values_v(params):
            vin_p_values.append(float(vcm) + vdiff / 2.0)
            vin_n_values.append(float(vcm) - vdiff / 2.0)
    dwell_s = params.conversions * cycle_s
    CompTb.vvin_p = Vpwl(
        wave=pwl_points_to_wave(_input_pwl_points(vin_p_values, dwell_s, float(params.transition_time_s)))
    )(p=CompTb.vin_p_src, n=CompTb.vss)
    CompTb.vvin_n = Vpwl(
        wave=pwl_points_to_wave(_input_pwl_points(vin_n_values, dwell_s, float(params.transition_time_s)))
    )(p=CompTb.vin_n_src, n=CompTb.vss)
    return CompTb


COMP_SIGNAL_NAMES = {
    "time_s": "time",
    "vin_p_v": "xtop.in_p",
    "vin_n_v": "xtop.in_n",
    "clock_v": "xtop.clk",
    "vout_p_v": "xtop.out_p",
    "vout_n_v": "xtop.out_n",
    "comp_p_v": "xtop.dut.innerp",
    "comp_n_v": "xtop.dut.innern",
    "vdd_i": "xtop.vvdd:p",
}


def sim_input(
    params: CompTbParams,
    *,
    transient_noise: bool = True,
    strobe_period_s: float = RAW_STROBE_PERIOD_S,
    noise_seed: int = TRANSIENT_NOISE_SEED,
) -> hs.Sim:
    """Build one selected-signal Spectre simulation input."""

    validate_comp_tb_params(params)
    if not math.isfinite(strobe_period_s) or strobe_period_s <= 0.0:
        raise ValueError("Spectre strobe period must be finite and positive")
    if noise_seed <= 0:
        raise ValueError("Spectre transient-noise seed must be positive")
    tb = CompTb(params)
    attrs: list[hs.SimAttr] = [
        hs.Lib(path=MODEL_LIBRARY, section="tt_lib"),
        hs.Lib(path=MODEL_LIBRARY, section="pre_simu"),
        hs.Options(name="temp", value=temperature_c(params.pvt.t)),
        h.Literal("saveOptions options save=selected rawfmt=nutascii"),
        h.Literal(
            "save \\\n    "
            + " \\\n    ".join(raw_name for name, raw_name in COMP_SIGNAL_NAMES.items() if name != "time_s")
        ),
    ]
    tstop_s = simulation_stop_s(params)
    tran = f"tran tran stop={tstop_s:.12g} strobeperiod={strobe_period_s:.12g} strobeoutput=strobeonly"
    if transient_noise:
        tran += f" noisefmin={1.0 / tstop_s:.12g} noisefmax={TRANSIENT_NOISE_MAX_HZ:.12g} noiseseed={noise_seed}"
    attrs.append(h.Literal(tran))
    return hs.Sim(tb=tb, attrs=attrs)


def frida65_fabricated_params(**topology) -> CompParams:
    """Return the nearest integer-unit representation of the FRIDA65A core."""

    return CompParams(**FRIDA65_WIDTH_UNITS, **FRIDA65_LENGTH_UNITS, **topology)


def _scaled_widths(scale: float) -> dict[str, int]:
    return {name: max(1, math.floor(value * scale + 0.5)) for name, value in FRIDA65_WIDTH_UNITS.items()}


def _topology_params() -> tuple[dict[str, object], ...]:
    """Enumerate all 148 valid topology configurations without sizing."""

    topologies: list[dict[str, object]] = []
    for diff_type in (MosType.NMOS, MosType.PMOS):
        for bias in Bias:
            for stages in Stages:
                for inner_on in State:
                    for outer_on in State:
                        for inner_init in (State.CLOCK, State.SIGNAL):
                            for outer_init in (State.OMIT, State.CLOCK, State.SIGNAL):
                                topology = {
                                    "comp_stages": stages,
                                    "preamp_diff_xtors": diff_type,
                                    "preamp_bias": bias,
                                    "latch_inner_on_xtors": inner_on,
                                    "latch_outer_on_xtors": outer_on,
                                    "latch_inner_init_xtors": inner_init,
                                    "latch_outer_init_xtors": outer_init,
                                }
                                if is_valid_comp_params(frida65_fabricated_params(**topology)):
                                    topologies.append(topology)
    return tuple(topologies)


def device_geometry_signature(params: CompParams) -> tuple[tuple[str, int, int], ...]:
    """Return MOS names, widths, and lengths in stable insertion order."""

    module = Comp(params)
    signature = []
    for name, value in module.namespace.items():
        primitive_call = getattr(value, "of", None)
        primitive = getattr(primitive_call, "prim", None)
        if getattr(primitive, "name", None) != "Mos":
            continue
        width = getattr(getattr(primitive_call, "params", None), "w", None)
        length = getattr(getattr(primitive_call, "params", None), "l", None)
        if width is None or length is None:
            raise RuntimeError(f"comparator MOS {name!r} is missing explicit width or length")
        signature.append((name, int(float(width)), int(float(length))))
    return tuple(signature)


def device_width_signature(params: CompParams) -> tuple[tuple[str, int], ...]:
    """Return MOS widths in the generator's stable device insertion order."""

    return tuple((name, width) for name, width, _length in device_geometry_signature(params))


def _candidate(
    comp: CompParams,
    *,
    topology_index: int,
    size_profile: str,
    label: str | None = None,
) -> CompCandidate:
    geometry_signature = device_geometry_signature(comp)
    width_signature = tuple((name, width) for name, width, _length in geometry_signature)
    total_active_area_units = sum(width * length for _name, width, length in geometry_signature)
    digest = hashlib.sha256(repr(comp).encode()).hexdigest()[:8]
    candidate_id = "frida65_fabricated_baseline" if label else f"c{topology_index:03d}_{size_profile}_{digest}"
    topology_label = "-".join(
        (
            comp.preamp_diff_xtors.name.lower(),
            comp.preamp_bias.name.lower(),
            comp.comp_stages.name.lower(),
            f"inner-on-{comp.latch_inner_on_xtors.name.lower()}",
            f"outer-on-{comp.latch_outer_on_xtors.name.lower()}",
            f"inner-init-{comp.latch_inner_init_xtors.name.lower()}",
            f"outer-init-{comp.latch_outer_init_xtors.name.lower()}",
        )
    )
    return CompCandidate(
        candidate_id=candidate_id,
        label=label or f"{topology_label}, {size_profile}",
        comp=comp,
        topology_index=topology_index,
        size_profile=size_profile,
        device_width_signature=width_signature,
        device_geometry_signature=geometry_signature,
        total_width_units=sum(width for _name, width in width_signature),
        total_active_area_units=total_active_area_units,
        total_active_area_um2=total_active_area_units * TSMC65_AREA_UNIT_UM2,
    )


def build_candidates() -> tuple[CompCandidate, ...]:
    """Build 297 candidates: all topologies at half/double size plus FRIDA."""

    candidates = []
    topologies = _topology_params()
    for topology_index, topology in enumerate(topologies):
        for size_profile, scale in (("half", 0.5), ("double", 2.0)):
            comp = CompParams(
                **topology,
                **_scaled_widths(scale),
                **FRIDA65_LENGTH_UNITS,
            )
            candidates.append(
                _candidate(
                    comp,
                    topology_index=topology_index,
                    size_profile=size_profile,
                )
            )
    baseline = frida65_fabricated_params()
    candidates.append(
        _candidate(
            baseline,
            topology_index=topologies.index(
                {
                    "comp_stages": baseline.comp_stages,
                    "preamp_diff_xtors": baseline.preamp_diff_xtors,
                    "preamp_bias": baseline.preamp_bias,
                    "latch_inner_on_xtors": baseline.latch_inner_on_xtors,
                    "latch_outer_on_xtors": baseline.latch_outer_on_xtors,
                    "latch_inner_init_xtors": baseline.latch_inner_init_xtors,
                    "latch_outer_init_xtors": baseline.latch_outer_init_xtors,
                }
            ),
            size_profile="fabricated",
            label="FRIDA65A fabricated comparator dimensions",
        )
    )
    if len(candidates) != 297 or len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise RuntimeError("comparator candidate campaign must contain 297 unique designs")
    return tuple(candidates)


@dataclass(frozen=True, slots=True)
class _CompSpectreCase:
    """One prepared comparator Spectre case and its conversion metadata."""

    candidate: CompCandidate
    params: CompTbParams
    case_dir: Path
    deck_path: Path
    raw_path: Path
    h5_path: Path
    log_path: Path


def _case_paths(run_dir: Path, candidate: CompCandidate) -> tuple[Path, Path, Path, Path, Path]:
    case_dir = run_dir / "candidates" / candidate.candidate_id
    return (
        case_dir,
        case_dir / "input.scs",
        case_dir / "result.raw",
        case_dir / "result.h5",
        case_dir / "spectre.log",
    )


def _prepare_case(
    run_dir: Path,
    candidate: CompCandidate,
    *,
    params: CompTbParams | None = None,
    transient_noise: bool = True,
) -> _CompSpectreCase:
    case_dir, deck_path, raw_path, h5_path, log_path = _case_paths(run_dir, candidate)
    case_dir.mkdir(parents=True, exist_ok=True)
    params = CompTbParams(comp=candidate.comp) if params is None else params
    if params.comp != candidate.comp:
        raise ValueError("comparator case parameters must contain the selected candidate")
    sim = sim_input(params, transient_noise=transient_noise)
    h.pdk.compile(sim.tb)
    write_spectre_input(sim, deck_path)
    return _CompSpectreCase(
        candidate=candidate,
        params=params,
        case_dir=case_dir,
        deck_path=deck_path,
        raw_path=raw_path,
        h5_path=h5_path,
        log_path=log_path,
    )


def _execute_case(case: _CompSpectreCase) -> Path:
    from flow.spice.io import convert_spectre_comp_raw_to_h5

    if case.raw_path.is_dir():
        shutil.rmtree(case.raw_path)
    elif case.raw_path.exists():
        case.raw_path.unlink()
    command = [
        "spectre",
        case.deck_path.name,
        "+preset=mx",
        f"+mt={SPECTRE_THREADS_PER_SIMULATION}",
        "+lqtimeout",
        "3600",
        "+escchars",
        "-raw",
        case.raw_path.name,
        "+log",
        case.log_path.name,
    ]
    started = time.perf_counter()
    subprocess.run(command, cwd=case.case_dir, check=True)
    spectre_runtime_s = time.perf_counter() - started
    convert_spectre_comp_raw_to_h5(
        case.raw_path,
        case.h5_path,
        params=case.params,
        signal_names=COMP_SIGNAL_NAMES,
        candidate_id=case.candidate.candidate_id,
        candidate_label=case.candidate.label,
        topology_index=case.candidate.topology_index,
        size_profile=case.candidate.size_profile,
        total_width_units=case.candidate.total_width_units,
        device_width_signature=case.candidate.device_width_signature,
        total_active_area_units=case.candidate.total_active_area_units,
        total_active_area_um2=case.candidate.total_active_area_um2,
        device_geometry_signature=case.candidate.device_geometry_signature,
        spectre_runtime_s=spectre_runtime_s,
    )
    print(
        f"{case.candidate.candidate_id}: simulated and converted in {time.perf_counter() - started:.1f} s",
        flush=True,
    )
    return case.h5_path


def _run_candidates(
    run_dir: Path,
    candidates: Sequence[CompCandidate],
    *,
    execute: bool,
    params: CompTbParams | None = None,
    transient_noise: bool = True,
) -> Path:
    """Prepare one complete comparator run and optionally execute it."""

    set_pdk("tsmc65")
    prepared = tuple(
        _prepare_case(
            run_dir,
            candidate,
            params=params,
            transient_noise=transient_noise,
        )
        for candidate in candidates
    )
    if not execute:
        print(f"Prepared {len(prepared)} comparator netlists beneath {run_dir}")
        return run_dir
    if shutil.which("spectre") is None:
        raise RuntimeError("spectre is not on PATH; source design/spice/workspace.sh")

    failures = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SIMULATIONS) as executor:
        futures = {executor.submit(_execute_case, case): case for case in prepared}
        for future in as_completed(futures):
            case = futures[future]
            try:
                future.result()
            except (OSError, RuntimeError, TypeError, ValueError, subprocess.CalledProcessError) as error:
                failures.append((case.candidate.candidate_id, repr(error)))
                print(f"{case.candidate.candidate_id}: FAILED: {error}", flush=True)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(dict(failures), indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} comparator cases failed; see {failure_path}")
    print(f"Completed {len(prepared)} comparator simulations beneath {run_dir}")
    return run_dir


def frida65_baseline_netlist() -> Path:
    """Write one fabricated-size comparator core netlist."""

    set_pdk("tsmc65")
    # TODO: Change every target in this module to build/sim_comp/<short-datetime>.
    run_dir = BASE_PATH / "build/sim/comp" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    module = Comp(frida65_fabricated_params())
    h.pdk.compile(module)
    with (run_dir / "frida65_fabricated_baseline.scs").open("w") as output:
        h.netlist(module, dest=output, fmt="spectre")
    return run_dir


def frida65_candidate_netlists() -> Path:
    """Write all reviewed candidate simulation netlists without running them."""

    run_dir = BASE_PATH / "build/sim/comp" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_candidates(run_dir, build_candidates(), execute=False)


def frida65_candidate_smoke() -> Path:
    """Run one deterministic 40 ns baseline case to verify Spectre execution."""

    run_dir = BASE_PATH / "build/sim/comp" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    baseline = next(candidate for candidate in build_candidates() if candidate.size_profile == "fabricated")
    params = CompTbParams(
        comp=baseline.comp,
        vin_cm_values_v=(0.8,),
        sweep_min_v=0.0,
        sweep_max_v=0.0,
        sweep_step_v=100.0e-6,
        conversions=1,
    )
    return _run_candidates(
        run_dir,
        (baseline,),
        execute=True,
        params=params,
        transient_noise=False,
    )


def frida65_baseline_noise() -> Path:
    """Run the complete 61-point transient-noise S-curve for the baseline."""

    run_dir = BASE_PATH / "build/sim/comp" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    baseline = next(candidate for candidate in build_candidates() if candidate.size_profile == "fabricated")
    return _run_candidates(run_dir, (baseline,), execute=True)


def frida65_candidates() -> Path:
    """Run all 297 reviewed comparator candidates as one complete campaign."""

    run_dir = BASE_PATH / "build/sim/comp" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_candidates(run_dir, build_candidates(), execute=True)


TARGETS: dict[str, Callable[[], Path]] = {
    target.__name__: target
    for target in (
        frida65_baseline_netlist,
        frida65_candidate_netlists,
        frida65_candidate_smoke,
        frida65_baseline_noise,
        frida65_candidates,
    )
}


def main() -> None:
    """Run one explicitly named comparator artifact or simulation target."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(TARGETS))
    args = parser.parse_args()
    if args.target is None:
        print("Available comparator targets:")
        for target in sorted(TARGETS):
            print(f"  {target}")
        return
    run_dir = TARGETS[args.target]()
    print(f"Simulation output: {run_dir}")


if __name__ == "__main__":
    main()
