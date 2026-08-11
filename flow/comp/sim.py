"""HDL21 comparator testbench and named TSMC65 Spectre campaign runner."""

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, MosType, R, Vdc, Vpulse, Vpwl

from flow.circuit.netlist import pwl_points_to_wave, write_sim_netlist
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
OUTPUT_BASE = BASE_PATH / "build" / "comp"
CAMPAIGN_NAME = "frida65_candidate_scurve_power"
CAMPAIGN_DIR = OUTPUT_BASE / CAMPAIGN_NAME
MODEL_LIBRARY = Path("/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs")
MAX_PARALLEL_SPECTRE = 18
SPECTRE_THREADS_PER_CASE = 1
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


def _manifest_entry(candidate: CompCandidate) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "label": candidate.label,
        "topology_index": candidate.topology_index,
        "size_profile": candidate.size_profile,
        "total_width_units": candidate.total_width_units,
        "total_active_area_units": candidate.total_active_area_units,
        "total_active_area_um2": candidate.total_active_area_um2,
        "device_width_signature": candidate.device_width_signature,
        "device_geometry_signature": candidate.device_geometry_signature,
        "comp_params": repr(candidate.comp),
    }


def _write_manifest(candidates: Sequence[CompCandidate]) -> Path:
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = CAMPAIGN_DIR / "manifest.json"
    payload = {
        "campaign": CAMPAIGN_NAME,
        "pdk": "tsmc65",
        "candidate_count": len(candidates),
        "testbench": {
            "vin_cm_v": 0.8,
            "vin_diff_min_v": -3e-3,
            "vin_diff_max_v": 3e-3,
            "vin_diff_step_v": 100e-6,
            "decisions_per_point": 100,
            "reset_time_s": 10e-9,
            "evaluation_time_s": 30e-9,
            "transient_noise_max_hz": TRANSIENT_NOISE_MAX_HZ,
        },
        "candidates": [_manifest_entry(candidate) for candidate in candidates],
    }
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(manifest_path)
    return manifest_path


def _case_paths(candidate: CompCandidate) -> tuple[Path, Path, Path, Path, Path]:
    case_dir = CAMPAIGN_DIR / "candidates" / candidate.candidate_id
    return (
        case_dir,
        case_dir / "input.scs",
        case_dir / "result.raw",
        case_dir / "result.h5",
        case_dir / "spectre.log",
    )


def _prepare_case(candidate: CompCandidate, *, transient_noise: bool = True) -> tuple[Path, Path, Path, Path, Path]:
    case_dir, deck_path, raw_path, h5_path, log_path = _case_paths(candidate)
    case_dir.mkdir(parents=True, exist_ok=True)
    params = CompTbParams(comp=candidate.comp)
    sim = sim_input(params, transient_noise=transient_noise)
    h.pdk.compile(sim.tb)
    write_sim_netlist(sim, deck_path, compact=True)
    return case_dir, deck_path, raw_path, h5_path, log_path


def _completed_case(candidate: CompCandidate) -> bool:
    from flow.analysis.io import read_measurement
    from flow.analysis.types import MeasCompInt

    h5_path = _case_paths(candidate)[3]
    if not h5_path.is_file():
        return False
    try:
        measurement = read_measurement(h5_path)
    except (OSError, TypeError, ValueError):
        return False
    return (
        isinstance(measurement, MeasCompInt)
        and measurement.info.readbacks.get("candidate_id") == candidate.candidate_id
    )


def _execute_case(candidate: CompCandidate) -> Path:
    from flow.spice.io import convert_spectre_comp_raw_to_h5

    case_dir, deck_path, raw_path, h5_path, log_path = _case_paths(candidate)
    if raw_path.is_dir():
        shutil.rmtree(raw_path)
    elif raw_path.exists():
        raw_path.unlink()
    command = [
        "spectre",
        deck_path.name,
        "+preset=mx",
        f"+mt={SPECTRE_THREADS_PER_CASE}",
        "+lqtimeout",
        "3600",
        "+escchars",
        "-raw",
        raw_path.name,
        "+log",
        log_path.name,
    ]
    started = time.perf_counter()
    subprocess.run(command, cwd=case_dir, check=True)
    spectre_runtime_s = time.perf_counter() - started
    params = CompTbParams(comp=candidate.comp)
    convert_spectre_comp_raw_to_h5(
        raw_path,
        h5_path,
        params=params,
        signal_names=COMP_SIGNAL_NAMES,
        candidate_id=candidate.candidate_id,
        candidate_label=candidate.label,
        topology_index=candidate.topology_index,
        size_profile=candidate.size_profile,
        total_width_units=candidate.total_width_units,
        device_width_signature=candidate.device_width_signature,
        total_active_area_units=candidate.total_active_area_units,
        total_active_area_um2=candidate.total_active_area_um2,
        device_geometry_signature=candidate.device_geometry_signature,
        spectre_runtime_s=spectre_runtime_s,
    )
    print(f"{candidate.candidate_id}: simulated and converted in {time.perf_counter() - started:.1f} s", flush=True)
    return h5_path


def _convert_existing_case(candidate: CompCandidate) -> Path:
    """Regenerate one typed H5 result from its retained production raw file."""

    from flow.spice.io import convert_spectre_comp_raw_to_h5

    _case_dir, _deck_path, raw_path, h5_path, log_path = _case_paths(candidate)
    if not raw_path.is_file():
        raise FileNotFoundError(2, "comparator candidate raw result not found", raw_path)
    params = CompTbParams(comp=candidate.comp)
    spectre_runtime_s = _spectre_elapsed_seconds(log_path) if log_path.is_file() else None
    return convert_spectre_comp_raw_to_h5(
        raw_path,
        h5_path,
        params=params,
        signal_names=COMP_SIGNAL_NAMES,
        candidate_id=candidate.candidate_id,
        candidate_label=candidate.label,
        topology_index=candidate.topology_index,
        size_profile=candidate.size_profile,
        total_width_units=candidate.total_width_units,
        device_width_signature=candidate.device_width_signature,
        total_active_area_units=candidate.total_active_area_units,
        total_active_area_um2=candidate.total_active_area_um2,
        device_geometry_signature=candidate.device_geometry_signature,
        spectre_runtime_s=spectre_runtime_s,
    )


def _spectre_elapsed_seconds(log_path: Path) -> float | None:
    """Read Spectre's elapsed transient runtime, including SI-prefixed units."""

    match = re.search(
        r"Intrinsic tran analysis time:.*?elapsed\s*=\s*([0-9.eE+-]+)\s*([fpnumkMGT]?s)\b",
        log_path.read_text(errors="replace"),
    )
    if match is None:
        return None
    prefix_scale = {
        "f": 1e-15,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        "": 1.0,
        "k": 1e3,
        "M": 1e6,
        "G": 1e9,
        "T": 1e12,
    }
    return float(match.group(1)) * prefix_scale[match.group(2)[:-1]]


def _run_candidates(candidates: Sequence[CompCandidate], *, execute: bool) -> tuple[Path, ...]:
    """Prepare, resume, and optionally execute a deterministic candidate set."""

    set_pdk("tsmc65")
    _write_manifest(build_candidates())
    pending = []
    completed = []
    for candidate in candidates:
        if execute and _completed_case(candidate):
            completed.append(_case_paths(candidate)[3])
            continue
        _prepare_case(candidate)
        pending.append(candidate)
    if not execute:
        print(f"Prepared {len(pending)} comparator decks beneath {CAMPAIGN_DIR}")
        return tuple(_case_paths(candidate)[1] for candidate in pending)
    if shutil.which("spectre") is None:
        raise RuntimeError("spectre is not on PATH; source /eda/local/scripts/cadence_2024-25.sh")

    failures = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SPECTRE) as executor:
        futures = {executor.submit(_execute_case, candidate): candidate for candidate in pending}
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                completed.append(future.result())
            except (OSError, RuntimeError, TypeError, ValueError, subprocess.CalledProcessError) as error:
                failures.append((candidate.candidate_id, repr(error)))
                print(f"{candidate.candidate_id}: FAILED: {error}", flush=True)
    if failures:
        failure_path = CAMPAIGN_DIR / "failures.json"
        failure_path.write_text(json.dumps(dict(failures), indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} comparator cases failed; see {failure_path}")
    (CAMPAIGN_DIR / "failures.json").unlink(missing_ok=True)
    print(f"Completed {len(completed)} comparator cases beneath {CAMPAIGN_DIR}")
    return tuple(sorted(completed))


def frida65_baseline_netlist() -> None:
    """Write the persistent fabricated-size comparator core netlist."""

    set_pdk("tsmc65")
    output_dir = CAMPAIGN_DIR / "netlist"
    output_dir.mkdir(parents=True, exist_ok=True)
    module = Comp(frida65_fabricated_params())
    h.pdk.compile(module)
    with (output_dir / "frida65_fabricated_baseline.scs").open("w") as output:
        h.netlist(module, dest=output, fmt="spectre")


def frida65_candidate_decks() -> None:
    """Write all reviewed candidate simulation decks without executing them."""

    _run_candidates(build_candidates(), execute=False)


def frida65_baseline_noise() -> None:
    """Run the complete 61-point transient-noise S-curve for the baseline."""

    candidates = build_candidates()
    baseline = next(candidate for candidate in candidates if candidate.size_profile == "fabricated")
    _run_candidates((baseline,), execute=True)


def frida65_reconvert_h5() -> None:
    """Rebuild every typed H5 result from the collected raw campaign data."""

    candidates = build_candidates()
    _write_manifest(candidates)
    with ThreadPoolExecutor(max_workers=4) as executor:
        paths = tuple(executor.map(_convert_existing_case, candidates))
    (CAMPAIGN_DIR / "failures.json").unlink(missing_ok=True)
    print(f"Reconverted {len(paths)} comparator H5 results beneath {CAMPAIGN_DIR}")


def frida65_candidates_shard0() -> None:
    """Run the even-index half of the reviewed candidate campaign."""

    _run_candidates(build_candidates()[0::2], execute=True)


def frida65_candidates_shard1() -> None:
    """Run the odd-index half of the reviewed candidate campaign."""

    _run_candidates(build_candidates()[1::2], execute=True)


def frida65_candidates_all() -> None:
    """Run all reviewed comparator candidates on one host."""

    _run_candidates(build_candidates(), execute=True)


TARGETS: dict[str, Callable[[], None]] = {
    target.__name__: target
    for target in (
        frida65_baseline_netlist,
        frida65_candidate_decks,
        frida65_baseline_noise,
        frida65_reconvert_h5,
        frida65_candidates_shard0,
        frida65_candidates_shard1,
        frida65_candidates_all,
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
    TARGETS[args.target]()


if __name__ == "__main__":
    main()
