"""Comparator testbench and named TSMC65 Spectre simulation targets."""

import argparse
import hashlib
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from multiprocessing import get_context
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, MosType, R, Vdc, Vpulse, Vpwl
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.analysis.io import write_measurement
from flow.circuit.ports import testbench_from_ports

from .subckt import Bias, Comp, CompNets, CompParams, Stages, State, is_valid_comp_params


def comp_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in CompNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        elif net.props.get("save"):
            names[f"xtop.dut.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class CompTbParams:
    """Parameters which determine one generated comparator testbench."""

    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=10e-12
    )
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    comp = h.Param(dtype=CompParams, desc="Comparator parameters", default=CompParams())
    vin_cm_values_v = h.Param(dtype=tuple[h.Scalar, ...], desc="Input common-mode values", default=(0.8,))
    vin_diff_values_v = h.Param(
        dtype=tuple[h.Scalar, ...],
        desc="Differential-input values",
        default=tuple(step * 100e-6 for step in range(-30, 31)),
    )
    conversions = h.Param(dtype=int, desc="Decisions per input point", default=100)
    reset_time_s = h.Param(dtype=h.Scalar, desc="Reset interval", default=10e-9)
    evaluation_time_s = h.Param(dtype=h.Scalar, desc="Evaluation interval", default=30e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Clock and input transition", default=100e-12)
    source_resistance_ohm = h.Param(dtype=h.Scalar, desc="Input source resistance", default=1_000.0)
    source_capacitance_f = h.Param(dtype=h.Scalar, desc="Input source capacitance", default=100e-15)
    output_load_f = h.Param(dtype=h.Scalar, desc="Output load per side", default=10e-15)


def _validate_comp_tb_params(params: CompTbParams) -> None:
    if not math.isfinite(float(params.vdd)) or float(params.vdd) <= 0.0:
        raise ValueError("comparator vdd must be finite and positive")
    common_modes = tuple(float(value) for value in params.vin_cm_values_v)
    differential_values = tuple(float(value) for value in params.vin_diff_values_v)
    if (
        not common_modes
        or not all(math.isfinite(value) for value in common_modes)
        or len(set(common_modes)) != len(common_modes)
    ):
        raise ValueError("comparator common modes must be finite and unique")
    if (
        not differential_values
        or not all(math.isfinite(value) for value in differential_values)
        or len(set(differential_values)) != len(differential_values)
    ):
        raise ValueError("comparator differential inputs must be finite and unique")
    if params.conversions <= 0:
        raise ValueError("comparator conversions must be positive")
    for name in (
        "waveform_sample_interval_s",
        "reset_time_s",
        "evaluation_time_s",
        "transition_time_s",
        "source_resistance_ohm",
        "source_capacitance_f",
        "output_load_f",
    ):
        if not math.isfinite(float(getattr(params, name))) or float(getattr(params, name)) <= 0.0:
            raise ValueError(f"comparator {name} must be finite and positive")
    if float(params.transition_time_s) >= min(float(params.reset_time_s), float(params.evaluation_time_s)):
        raise ValueError("comparator transition must be shorter than reset and evaluation")


@h.generator
def CompTb(params: CompTbParams) -> h.Module:
    """Generate a complete swept comparator testbench."""

    _validate_comp_tb_params(params)
    cycle_s = float(params.reset_time_s) + float(params.evaluation_time_s)

    CompTb, connections = testbench_from_ports(
        "CompTb", {net.name: net for net in CompNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    CompTb.vin_cm, CompTb.vin_diff = h.Signals(2)
    CompTb.vin = h.Diff()

    CompTb.vvdd = Vdc(dc=params.vdd)(p=CompTb.vdd, n=CompTb.vss)
    CompTb.rsrc_p = R(r=params.source_resistance_ohm)(p=CompTb.vin.p, n=CompTb.inp)
    CompTb.rsrc_n = R(r=params.source_resistance_ohm)(p=CompTb.vin.n, n=CompTb.inn)
    CompTb.csrc_p = C(c=params.source_capacitance_f)(p=CompTb.inp, n=CompTb.vss)
    CompTb.csrc_n = C(c=params.source_capacitance_f)(p=CompTb.inn, n=CompTb.vss)
    for port in CompNets.signals.values():
        if port.usage != h.Usage.CLOCK:
            continue
        complement = port is CompNets.clkb
        net = connections[port.name]
        CompTb.add(
            Vpulse(
                v1=params.vdd if complement else 0.0,
                v2=0.0 if complement else params.vdd,
                period=cycle_s,
                width=params.evaluation_time_s,
                rise=params.transition_time_s,
                fall=params.transition_time_s,
                delay=params.reset_time_s,
            )(p=net, n=CompTb.vss),
            name=f"v{net.name}",
        )
    CompTb.cload_p = C(c=params.output_load_f)(p=CompTb.outp, n=CompTb.vss)
    CompTb.cload_n = C(c=params.output_load_f)(p=CompTb.outn, n=CompTb.vss)
    CompTb.dut = Comp(params.comp)(**connections)

    common_mode_schedule = []
    differential_schedule = []
    for common_mode in params.vin_cm_values_v:
        for differential in params.vin_diff_values_v:
            common_mode_schedule.append(common_mode)
            differential_schedule.append(differential)
    dwell_s = params.conversions * cycle_s
    CompTb.vvin_cm = Vpwl(
        wave=h.Pwl.steps(
            values=common_mode_schedule, dwell=dwell_s, transition=params.transition_time_s, transition_at="start"
        )
    )(p=CompTb.vin_cm, n=CompTb.vss)
    CompTb.vvin_diff = Vpwl(
        wave=h.Pwl.steps(
            values=differential_schedule, dwell=dwell_s, transition=params.transition_time_s, transition_at="start"
        )
    )(p=CompTb.vin_diff, n=CompTb.vss)
    CompTb.evin_p = h.Vcvs(gain=0.5)(p=CompTb.vin.p, n=CompTb.vin_cm, cp=CompTb.vin_diff, cn=CompTb.vss)
    CompTb.evin_n = h.Vcvs(gain=-0.5)(p=CompTb.vin.n, n=CompTb.vin_cm, cp=CompTb.vin_diff, cn=CompTb.vss)
    return CompTb


def _run_comp_sim(
    run_dir: Path,
    params: CompTbParams,
    *,
    candidate_id: str,
    candidate_label: str,
    topology_index: int,
    size_profile: str,
    check: bool = False,
) -> tuple[Path, CompTbParams, dict[str, str | int | float | bool]]:
    """Execute one configured comparator case, not an entire campaign.

    Targets define experiments: topology, sizing, stimuli, and case concurrency.
    This executor owns compilation, the shared Spectre recipe, short diagnostic
    checks, and measurement output. Each campaign worker compiles in an isolated
    process and uses one Spectre thread; no compiled HDL21 graph crosses workers.
    """
    from pdk import tsmc65
    from pdk.tsmc65 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    if not is_valid_comp_params(params.comp):
        raise ValueError(f"invalid comparator case {candidate_id}")
    try:
        h.pdk.set_default(tsmc65.pdk_logic)
        tb = CompTb(params)
        h.pdk.compile(tb)
        tstop_s = (
            len(params.vin_cm_values_v)
            * len(params.vin_diff_values_v)
            * params.conversions
            * (float(params.reset_time_s) + float(params.evaluation_time_s))
        )
        attrs = [
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([raw for raw in comp_signal_names() if raw != "time"]),
        ]
        if check:
            attrs.append(
                h.Literal(
                    "check_caps static_capacitor type=distr\n"
                    "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top "
                    "gate2power=on gate2ground=on\n"
                    "check_highz static_highz node=[*] fanout=gate_has_driver_no_moscap\n"
                    "check_dcpath static_dcpath net=[xtop.vdd 0]\n"
                    "check_stack static_stack count=3\n"
                    "check_topology static_topology node=[*] pin2gnd=on\n"
                    "check_nodecap dyn_nodecap node=[xtop.inp xtop.inn xtop.outp xtop.outn] time=[10n 39n]\n"
                    "check_setuphold dyn_setuphold node=[xtop.outp xtop.outn] ref_node=xtop.clk "
                    "setup_time=50p hold_time=50p"
                )
            )
        tran_options = {
            "strobeperiod": params.waveform_sample_interval_s,
            "maxstep": params.waveform_sample_interval_s,
            "strobeoutput": "strobeonly",
        }
        if not check:
            tran_options.update(noisefmin=1.0 / tstop_s, noisefmax="25G", noiseseed=1)
        attrs.append(hs.Tran(tstop=tstop_s, name="tran", noise=not check, options=tran_options))
        simulation = hs.Sim(tb=tb, attrs=attrs)
        started = time.perf_counter()
        simulation.run(
            SimOptions(
                simulator=SupportedSimulators.SPECTRE,
                fmt=ResultFormat.NONE if check else ResultFormat.SIM_DATA,
                rundir=run_dir,
                simulator_args=(
                    "+preset=mx",
                    "+mt=1",
                    "+lqtimeout",
                    "3600",
                    "+escchars",
                    "+log",
                    "spectre.log",
                    *(("-ahdllint=warn", "-ahdllint_log", "ahdllint.log") if check else ()),
                ),
            )
        )
        runtime_s = time.perf_counter() - started
        geometry = tuple(
            (name, round(float(instance.of.params.w) / 120e-9), round(float(instance.of.params.l) / 60e-9))
            for name, instance in tb.dut.of.instances.items()
            if hasattr(instance.of.params, "w") and hasattr(instance.of.params, "l")
        )
        readbacks = {
            "candidate_id": candidate_id,
            "candidate_label": candidate_label,
            "topology_index": topology_index,
            "size_profile": size_profile,
            "spectre_runtime_s": runtime_s,
            "total_width_units": sum(w for _, w, _ in geometry),
            "total_active_area_units": sum(w * l for _, w, l in geometry),
            "total_active_area_um2": sum(w * l for _, w, l in geometry) * 0.12 * 0.06,
            "device_width_signature": ",".join(f"{name}:{w}" for name, w, _ in geometry),
            "device_geometry_signature": ",".join(f"{name}:{w}:{l}" for name, w, l in geometry),
            "transient_noise": not check,
            "transient_noise_seed": 1,
            "transient_noise_max_hz": 25e9,
        }
    finally:
        CompTb.Cache.reset()
        Comp.Cache.reset()
    return run_dir / "netlist.raw", params, readbacks


def hdl21_comp_perf_vs_size(run_dir: Path, *, check: bool = False) -> Path:
    """Run 296 generated sizes plus FRIDA-1; checks cover six representative cases."""

    from dataclasses import replace

    from flow.circuit.results import convert_raw_comp_to_measurement, read_raw_transient

    run_dir.mkdir(parents=True, exist_ok=True)
    if check:
        cases = (
            (
                "fabricated_single_nmos_switched",
                CompParams(
                    diffpair_w=37,
                    tail_w=5,
                    rst_w=8,
                    latch_on_w=25,
                    latch_init_w=33,
                    srlatch_n_w=4,
                    srlatch_p_w=8,
                    diffpair_l=5,
                    tail_l=13,
                    rst_l=1,
                    latch_on_l=6,
                    latch_init_l=17,
                    preamp_diff_xtors=MosType.NMOS,
                    preamp_bias=Bias.SWITCHED,
                    comp_stages=Stages.SINGLE,
                    latch_inner_init_xtors=State.CLOCK,
                ),
            ),
            (
                "half_single_pmos_dynamic",
                CompParams(
                    diffpair_w=19,
                    tail_w=3,
                    rst_w=4,
                    latch_on_w=13,
                    latch_init_w=17,
                    srlatch_n_w=2,
                    srlatch_p_w=4,
                    diffpair_l=5,
                    tail_l=13,
                    rst_l=1,
                    latch_on_l=6,
                    latch_init_l=17,
                    preamp_diff_xtors=MosType.PMOS,
                    preamp_bias=Bias.DYNAMIC,
                    comp_stages=Stages.SINGLE,
                    latch_inner_init_xtors=State.SIGNAL,
                ),
            ),
            (
                "double_double_nmos_switched",
                CompParams(
                    diffpair_w=74,
                    tail_w=10,
                    rst_w=16,
                    latch_on_w=50,
                    latch_init_w=66,
                    srlatch_n_w=8,
                    srlatch_p_w=16,
                    diffpair_l=5,
                    tail_l=13,
                    rst_l=1,
                    latch_on_l=6,
                    latch_init_l=17,
                    preamp_diff_xtors=MosType.NMOS,
                    preamp_bias=Bias.SWITCHED,
                    comp_stages=Stages.DOUBLE,
                    latch_inner_on_xtors=State.SIGNAL,
                    latch_outer_on_xtors=State.OMIT,
                    latch_inner_init_xtors=State.CLOCK,
                    latch_outer_init_xtors=State.OMIT,
                ),
            ),
            (
                "fabricated_double_pmos_dynamic",
                CompParams(
                    diffpair_w=37,
                    tail_w=5,
                    rst_w=8,
                    latch_on_w=25,
                    latch_init_w=33,
                    srlatch_n_w=4,
                    srlatch_p_w=8,
                    diffpair_l=5,
                    tail_l=13,
                    rst_l=1,
                    latch_on_l=6,
                    latch_init_l=17,
                    preamp_diff_xtors=MosType.PMOS,
                    preamp_bias=Bias.DYNAMIC,
                    comp_stages=Stages.DOUBLE,
                    latch_inner_on_xtors=State.CLOCK,
                    latch_outer_on_xtors=State.SIGNAL,
                    latch_inner_init_xtors=State.SIGNAL,
                    latch_outer_init_xtors=State.OMIT,
                ),
            ),
            (
                "half_double_nmos_dynamic",
                CompParams(
                    diffpair_w=19,
                    tail_w=3,
                    rst_w=4,
                    latch_on_w=13,
                    latch_init_w=17,
                    srlatch_n_w=2,
                    srlatch_p_w=4,
                    diffpair_l=5,
                    tail_l=13,
                    rst_l=1,
                    latch_on_l=6,
                    latch_init_l=17,
                    preamp_diff_xtors=MosType.NMOS,
                    preamp_bias=Bias.DYNAMIC,
                    comp_stages=Stages.DOUBLE,
                    latch_inner_on_xtors=State.SIGNAL,
                    latch_outer_on_xtors=State.CLOCK,
                    latch_inner_init_xtors=State.CLOCK,
                    latch_outer_init_xtors=State.CLOCK,
                ),
            ),
            (
                "double_double_pmos_switched",
                CompParams(
                    diffpair_w=74,
                    tail_w=10,
                    rst_w=16,
                    latch_on_w=50,
                    latch_init_w=66,
                    srlatch_n_w=8,
                    srlatch_p_w=16,
                    diffpair_l=5,
                    tail_l=13,
                    rst_l=1,
                    latch_on_l=6,
                    latch_init_l=17,
                    preamp_diff_xtors=MosType.PMOS,
                    preamp_bias=Bias.SWITCHED,
                    comp_stages=Stages.DOUBLE,
                    latch_inner_on_xtors=State.CLOCK,
                    latch_outer_on_xtors=State.CLOCK,
                    latch_inner_init_xtors=State.SIGNAL,
                    latch_outer_init_xtors=State.SIGNAL,
                ),
            ),
        )
        cases = [(name, name, 0, "diagnostic", comp) for name, comp in cases]
    else:
        topologies = []
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
                                    probe = CompParams(
                                        diffpair_w=37,
                                        tail_w=5,
                                        rst_w=8,
                                        latch_on_w=25,
                                        latch_init_w=33,
                                        srlatch_n_w=4,
                                        srlatch_p_w=8,
                                        diffpair_l=5,
                                        tail_l=13,
                                        rst_l=1,
                                        latch_on_l=6,
                                        latch_init_l=17,
                                        **topology,
                                    )
                                    if is_valid_comp_params(probe):
                                        topologies.append(topology)
        if len(topologies) != 148:
            raise RuntimeError(f"expected 148 valid comparator topologies, got {len(topologies)}")

        cases = []
        for topology_index, topology in enumerate(topologies):
            for size_profile, widths in (
                (
                    "half",
                    {
                        "diffpair_w": 19,
                        "tail_w": 3,
                        "rst_w": 4,
                        "latch_on_w": 13,
                        "latch_init_w": 17,
                        "srlatch_n_w": 2,
                        "srlatch_p_w": 4,
                    },
                ),
                (
                    "double",
                    {
                        "diffpair_w": 74,
                        "tail_w": 10,
                        "rst_w": 16,
                        "latch_on_w": 50,
                        "latch_init_w": 66,
                        "srlatch_n_w": 8,
                        "srlatch_p_w": 16,
                    },
                ),
            ):
                comp = CompParams(
                    **topology,
                    **widths,
                    diffpair_l=5,
                    tail_l=13,
                    rst_l=1,
                    latch_on_l=6,
                    latch_init_l=17,
                )
                digest = hashlib.sha256(repr(comp).encode()).hexdigest()[:8]
                candidate_id = f"c{topology_index:03d}_{size_profile}_{digest}"
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
                cases.append(
                    (
                        candidate_id,
                        f"{topology_label}, {size_profile}",
                        topology_index,
                        size_profile,
                        comp,
                    )
                )
        baseline = CompParams(
            diffpair_w=37,
            tail_w=5,
            rst_w=8,
            latch_on_w=25,
            latch_init_w=33,
            srlatch_n_w=4,
            srlatch_p_w=8,
            diffpair_l=5,
            tail_l=13,
            rst_l=1,
            latch_on_l=6,
            latch_init_l=17,
        )
        baseline_topology = {
            "comp_stages": baseline.comp_stages,
            "preamp_diff_xtors": baseline.preamp_diff_xtors,
            "preamp_bias": baseline.preamp_bias,
            "latch_inner_on_xtors": baseline.latch_inner_on_xtors,
            "latch_outer_on_xtors": baseline.latch_outer_on_xtors,
            "latch_inner_init_xtors": baseline.latch_inner_init_xtors,
            "latch_outer_init_xtors": baseline.latch_outer_init_xtors,
        }
        cases.append(
            (
                "frida1_fabricated_baseline",
                "FRIDA-1 fabricated comparator dimensions",
                topologies.index(baseline_topology),
                "fabricated",
                baseline,
            )
        )
        if len(cases) != 297 or len({case[0] for case in cases}) != 297:
            raise RuntimeError("comparator campaign must contain 297 unique cases")

    failures: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=24, mp_context=get_context("spawn")) as executor:
        futures = {
            executor.submit(
                _run_comp_sim,
                run_dir / candidate_id,
                CompTbParams(
                    comp=comp,
                    **({"vin_cm_values_v": (0.8,), "vin_diff_values_v": (0.0,), "conversions": 1} if check else {}),
                ),
                candidate_id=candidate_id,
                candidate_label=label,
                topology_index=topology_index,
                size_profile=size_profile,
                check=check,
            ): candidate_id
            for candidate_id, label, topology_index, size_profile, comp in cases
        }
        for future in as_completed(futures):
            candidate_id = futures[future]
            try:
                raw_path, params, readbacks = future.result()
                if not check:
                    measurement = convert_raw_comp_to_measurement(
                        read_raw_transient(raw_path),
                        params=params,
                        raw_path=raw_path,
                        signal_names=comp_signal_names(),
                    )
                    measurement = replace(
                        measurement,
                        info=replace(measurement.info, readbacks={**measurement.info.readbacks, **readbacks}),
                    )
                    write_measurement(raw_path.parent / "result.h5", measurement)
            except Exception as error:  # noqa: BLE001 - report every independent case failure
                failures[candidate_id] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} comparator cases failed; see {failure_path}")
    return run_dir


def frida1_fixed_input_noise(run_dir: Path, *, check: bool = False) -> Path:
    """Run the FRIDA-1 comparator S-curve, or one noise-free diagnostic decision."""

    from dataclasses import replace

    from flow.circuit.results import convert_raw_comp_to_measurement, read_raw_transient

    params = CompTbParams(
        comp=CompParams(
            diffpair_w=37,
            tail_w=5,
            rst_w=8,
            latch_on_w=25,
            latch_init_w=33,
            srlatch_n_w=4,
            srlatch_p_w=8,
            diffpair_l=5,
            tail_l=13,
            rst_l=1,
            latch_on_l=6,
            latch_init_l=17,
        ),
        **({"vin_cm_values_v": (0.8,), "vin_diff_values_v": (0.0,), "conversions": 1} if check else {}),
    )
    raw_path, params, readbacks = _run_comp_sim(
        run_dir,
        params,
        candidate_id="frida1_fabricated_baseline",
        candidate_label="FRIDA-1 fabricated comparator dimensions",
        topology_index=37,
        size_profile="fabricated",
        check=check,
    )

    if not check:
        measurement = convert_raw_comp_to_measurement(
            read_raw_transient(raw_path),
            params=params,
            raw_path=raw_path,
            signal_names=comp_signal_names(),
        )
        measurement = replace(
            measurement, info=replace(measurement.info, readbacks={**measurement.info.readbacks, **readbacks})
        )
        write_measurement(run_dir / "result.h5", measurement)
    return run_dir


def main() -> None:
    """Create one output directory and run one named comparator target."""

    targets = {
        target.__name__: target
        for target in (
            hdl21_comp_perf_vs_size,
            frida1_fixed_input_noise,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available comparator simulation targets:")
        for name in list(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "comp"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
