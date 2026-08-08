"""Comparator testbench, netlisting, and simulation runner for FRIDA."""

import math
from pathlib import Path
from typing import cast

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, MosType, R, Vdc, Vpulse, Vpwl

from ..circuit.commands import testbench_main
from ..circuit.netlist import (
    get_param_axes,
    print_netlist_summary,
    pwl_points_to_wave,
    run_netlist_variants,
    select_variants,
    wrap_monte_carlo,
)
from ..circuit.params import (
    PvtParams,
    build_uniform_sweep_values,
    supply_voltage,
    temperature_c,
    validate_uniform_sweep,
)
from .subckt import Comp, CompParams, is_valid_comp_params


@h.paramclass
class CompTbParams:
    """Comparator testbench parameters."""

    pvt = h.Param(dtype=PvtParams, desc="PVT conditions", default=PvtParams())
    comp = h.Param(dtype=CompParams, desc="Comparator parameters", default=CompParams())
    vin_cm_values_v = h.Param(
        dtype=tuple[h.Scalar, ...],
        desc="Comparator input common-mode values",
        default=(0.7, 0.8, 0.9, 1.0, 1.1, 1.2),
    )
    sweep_min_v = h.Param(dtype=h.Scalar, desc="Inclusive differential-input minimum", default=0.0)
    sweep_max_v = h.Param(dtype=h.Scalar, desc="Inclusive differential-input maximum", default=25.0e-3)
    sweep_step_v = h.Param(dtype=h.Scalar, desc="Differential-input grid step", default=100.0e-6)
    conversions = h.Param(dtype=int, desc="Repeated decisions per differential-input point", default=1_000)


def validate_comp_tb_params(params: CompTbParams) -> None:
    """Validate standalone comparator testbench conditions."""

    validate_uniform_sweep(params.sweep_min_v, params.sweep_max_v, params.sweep_step_v)
    common_modes = tuple(float(value) for value in params.vin_cm_values_v)
    if not common_modes or not all(math.isfinite(value) for value in common_modes):
        raise ValueError("comparator common modes must be a non-empty finite sequence")
    if len(set(common_modes)) != len(common_modes):
        raise ValueError("comparator common modes must be unique")
    if isinstance(params.conversions, bool) or params.conversions <= 0:
        raise ValueError("comparator conversions must be a positive integer")


@h.generator
def CompTb(params: CompTbParams) -> h.Module:
    """
    Comparator testbench generator.

    Creates a testbench with:
    - DC supplies
    - Symmetric differential inputs around CM (driven by sim PWL)
    - Source impedances (1kOhm + 100fF)
    - 10ns clock period, 40% duty cycle
    - 10fF output loading
    """
    vdd = supply_voltage(params.pvt.v)

    @h.module
    class CompTb:
        """Comparator testbench module."""

        vss = h.Port(desc="Ground")

        # Power supplies
        vdd = h.Signal()

        # Differential input sources (driven by sim PWL)
        vin_p_src = h.Signal()
        vin_n_src = h.Signal()

        # Source impedances (models DAC/SHA output impedance)
        in_p = h.Signal()
        in_n = h.Signal()

        # Clocks
        clk = h.Signal()
        clk_b = h.Signal()

        # Outputs
        out_p = h.Signal()
        out_n = h.Signal()

    CompTb.vvdd = Vdc(dc=vdd)(p=CompTb.vdd, n=CompTb.vss)

    CompTb.rsrc_p = R(r=1000)(p=CompTb.vin_p_src, n=CompTb.in_p)
    CompTb.rsrc_n = R(r=1000)(p=CompTb.vin_n_src, n=CompTb.in_n)
    CompTb.csrc_p = C(c=100 * f)(p=CompTb.in_p, n=CompTb.vss)
    CompTb.csrc_n = C(c=100 * f)(p=CompTb.in_n, n=CompTb.vss)

    # Clocks: 10ns period, 40% duty cycle (4ns high = evaluation phase)
    CompTb.vclk = Vpulse(
        v1=0 * m,
        v2=vdd,
        period=10 * n,
        width=4 * n,
        rise=100 * p,
        fall=100 * p,
        delay=500 * p,
    )(p=CompTb.clk, n=CompTb.vss)
    CompTb.vclkb = Vpulse(
        v1=vdd,
        v2=0 * m,
        period=10 * n,
        width=4 * n,
        rise=100 * p,
        fall=100 * p,
        delay=500 * p,
    )(p=CompTb.clk_b, n=CompTb.vss)

    # Output loading (10fF each)
    CompTb.cload_p = C(c=10 * f)(p=CompTb.out_p, n=CompTb.vss)
    CompTb.cload_n = C(c=10 * f)(p=CompTb.out_n, n=CompTb.vss)

    # DUT
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

    validate_comp_tb_params(params)
    cm_voltages = params.vin_cm_values_v
    diff_voltages = build_uniform_sweep_values(params.sweep_min_v, params.sweep_max_v, params.sweep_step_v)
    vin_p_values: list[h.Scalar] = []
    vin_n_values: list[h.Scalar] = []
    for vcm in cm_voltages:
        for vdiff in diff_voltages:
            vin_p_values.append(vcm + vdiff / 2)
            vin_n_values.append(vcm - vdiff / 2)

    t_step = 200 * n
    t_rise = 100 * p
    points_p, _ = _build_pwl_points(vin_p_values, t_step, t_rise)
    points_n, _ = _build_pwl_points(vin_n_values, t_step, t_rise)
    CompTb.vvin_p = Vpwl(wave=pwl_points_to_wave(points_p))(p=CompTb.vin_p_src, n=CompTb.vss)
    CompTb.vvin_n = Vpwl(wave=pwl_points_to_wave(points_n))(p=CompTb.vin_n_src, n=CompTb.vss)

    return CompTb


def _build_pwl_points(
    values: list[h.Scalar],
    t_step: h.Scalar,
    t_rise: h.Scalar,
    t_delay: h.Scalar = 0 * n,
) -> tuple[list[tuple[float, float]], float]:
    points: list[tuple[float, float]] = []
    t = float(t_delay)
    step = float(t_step)
    rise = float(t_rise)

    for i, value in enumerate(values):
        points.append((t, float(value)))
        t += step
        if i < len(values) - 1:
            points.append((t, float(value)))
            t += rise

    return points, t


def sim_input(params: CompTbParams) -> hs.Sim:
    """Create transient simulation with stepped vcm/vdiff inputs."""
    sim_temp = temperature_c(params.pvt.t)

    validate_comp_tb_params(params)
    cm_voltages = params.vin_cm_values_v
    diff_voltages = build_uniform_sweep_values(params.sweep_min_v, params.sweep_max_v, params.sweep_step_v)

    t_step = 200 * n
    t_rise = 100 * p
    n_points = len(cm_voltages) * len(diff_voltages)
    t_stop = n_points * t_step + (n_points - 1) * t_rise

    @hs.sim
    class CompSim:
        tb = CompTb(params)
        tr = hs.Tran(tstop=t_stop, tstep=1 * n)

        save_all = hs.Save(hs.SaveMode.ALL)
        save = hs.Save(["xtop.clk", "xtop.out_p"])
        temp = hs.Options(name="temp", value=sim_temp)

    return CompSim


def _build_variants():
    """Build the full comparator variant list."""
    from .subckt import Bias, Stages, State

    variants: list[CompParams] = []

    for diff_type in [MosType.NMOS, MosType.PMOS]:
        for bias in list(Bias):
            for stages in list(Stages):
                for dw in [40, 80]:
                    for inner_on in State:
                        for outer_on in State:
                            for inner_init in [State.CLOCK, State.SIGNAL]:
                                for outer_init in [State.OMIT, State.CLOCK, State.SIGNAL]:
                                    params = CompParams(
                                        comp_stages=stages,
                                        preamp_diff_xtors=diff_type,
                                        preamp_bias=bias,
                                        latch_inner_on_xtors=inner_on,
                                        latch_outer_on_xtors=outer_on,
                                        latch_inner_init_xtors=inner_init,
                                        latch_outer_init_xtors=outer_init,
                                        diffpair_w=dw,
                                    )
                                    if is_valid_comp_params(params):
                                        variants.append(params)
    return variants


def run_netlist(
    tech: str,
    mode: str,
    montecarlo: bool,
    fmt: str,
    outdir: Path,
    scope: str = "full",
    verbose: bool = False,
) -> None:
    """Run comparator netlist generation."""
    all_variants = _build_variants()
    variants = select_variants(all_variants, mode)

    def build_sim(comp_params: CompParams):
        tb_params = CompTbParams(comp=comp_params)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return CompTb(tb_params), sim

    def build_dut(comp_params: CompParams):
        return Comp(comp_params)

    # TODO: Replace this flag-driven helper with a direct, idiomatic HDL21 netlist target.
    wall_time = cast(
        float,
        run_netlist_variants(
            "comp",
            variants,
            build_sim,
            outdir,
            simulator=fmt,
            fmt=fmt,
            scope=scope,
            build_dut=build_dut,
        ),
    )
    if verbose:
        print_netlist_summary(
            block="comp",
            pdk_name=tech,
            count=len(variants),
            total=len(all_variants),
            param_axes=get_param_axes(all_variants),
            wall_time=wall_time,
            outdir=str(outdir),
        )


def run_simulate(
    tech: str,
    mode: str,
    montecarlo: bool,
    simulator: str,
    sim_options,
    outdir: Path,
    verbose: bool = False,
) -> None:
    """Run comparator simulation."""
    all_variants = _build_variants()
    variants = select_variants(all_variants, mode)

    def build_sim(comp_params: CompParams):
        tb_params = CompTbParams(comp=comp_params)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return CompTb(tb_params), sim

    # TODO: Replace this flag-driven helper with a direct, idiomatic HDL21 simulation target.
    wall_time, sims = cast(
        tuple[float, list[hs.Sim]],
        run_netlist_variants(
            "comp",
            variants,
            build_sim,
            outdir,
            return_sims=True,
            simulator=simulator,
            scope="full",
        ),
    )
    if verbose:
        print_netlist_summary(
            block="comp",
            pdk_name=tech,
            count=len(variants),
            total=len(all_variants),
            param_axes=get_param_axes(all_variants),
            wall_time=wall_time,
            outdir=str(outdir),
        )
    h.sim.run(sims, sim_options)


if __name__ == "__main__":
    testbench_main("flow.comp.sim", "comp", run_netlist, run_simulate)
