"""
ADC testbench and runner functions for FRIDA.
"""

from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import f, m, n, p
from hdl21.primitives import Vdc, Vpulse, Vpwl

from ..cdac import CdacParams
from ..circuit import (
    Project,
    Pvt,
    SupplyVals,
    get_param_axes,
    print_netlist_summary,
    pwl_points_to_wave,
    run_netlist_variants,
    run_simulations,
    select_variants,
    wrap_monte_carlo,
)
from ..comp import CompParams
from ..samp import SampParams
from .subckt import Adc, AdcParams


@h.paramclass
class AdcTbParams:
    """ADC testbench parameters."""

    pvt = h.Param(dtype=Pvt, desc="PVT conditions", default=Pvt())
    adc = h.Param(dtype=AdcParams, desc="ADC parameters", default=AdcParams())

    # Conversion timing
    n_conversions = h.Param(dtype=int, desc="Number of ADC conversions", default=2)
    t_settle = h.Param(dtype=h.Scalar, desc="Settling time before conversions", default=10 * n)
    t_conv = h.Param(dtype=h.Scalar, desc="Conversion period (1/sample_rate)", default=100 * n)

    # Input voltage ramp (differential)
    vin_p_start = h.Param(dtype=h.Scalar, desc="vin_p starting voltage", default=1100 * m)
    vin_p_stop = h.Param(dtype=h.Scalar, desc="vin_p ending voltage", default=1050 * m)
    vin_n_start = h.Param(dtype=h.Scalar, desc="vin_n starting voltage", default=800 * m)
    vin_n_stop = h.Param(dtype=h.Scalar, desc="vin_n ending voltage", default=850 * m)

    # Common mode voltage
    vcm = h.Param(dtype=h.Scalar, desc="Common-mode voltage", default=600 * m)


@h.generator
def AdcTb(params: AdcTbParams) -> h.Module:
    """
    ADC testbench generator.

    Creates a testbench with:
    - Supply sources (analog and digital)
    - Differential input ramp (PWL)
    - Sequencer pulse sources (init, samp, comp, update)
    - Enable signals tied to VDD
    - DAC mode/diffcaps control tied to VDD
    - DAC initial state buses (64 bits) tied to VDD
    - Common-mode voltage source

    Conversion timing (default 10 Msps = 100ns period):
      init(5ns) -> samp(10ns) -> comp/update alternating (85ns)
    """
    supplies = SupplyVals.corner(params.pvt.v)
    vdd = supplies.VDD

    # Total simulation time
    t_settle = float(params.t_settle)
    t_conv = float(params.t_conv)
    n_conv = int(params.n_conversions)
    t_stop = t_settle + n_conv * t_conv

    @h.module
    class AdcTb:
        vss = h.Port(desc="Ground")

        # Supplies
        vdd_a = h.Signal(desc="Analog supply")
        vdd_d = h.Signal(desc="Digital supply")

        # Analog inputs
        vin_p = h.Signal(desc="Input positive")
        vin_n = h.Signal(desc="Input negative")

        # Sequencer clocks
        seq_init = h.Signal()
        seq_samp = h.Signal()
        seq_comp = h.Signal()
        seq_update = h.Signal()

        # Enable signals
        en_init = h.Signal()
        en_samp_p = h.Signal()
        en_samp_n = h.Signal()
        en_comp = h.Signal()
        en_update = h.Signal()

        # Control signals
        dac_mode = h.Signal()
        dac_diffcaps = h.Signal()

        # DAC initial state buses (16 bits each)
        dac_astate_p = h.Signal(width=16)
        dac_bstate_p = h.Signal(width=16)
        dac_astate_n = h.Signal(width=16)
        dac_bstate_n = h.Signal(width=16)

        # DAC state outputs (from digital block)
        dac_state_p = h.Signal(width=16)
        dac_state_n = h.Signal(width=16)

    # ---- Supply sources ----
    AdcTb.vvdd_a = Vdc(dc=vdd)(p=AdcTb.vdd_a, n=AdcTb.vss)
    AdcTb.vvdd_d = Vdc(dc=vdd)(p=AdcTb.vdd_d, n=AdcTb.vss)

    # ---- DUT instantiation ----
    AdcTb.xadc = Adc(params.adc)(
        vin_p=AdcTb.vin_p,
        vin_n=AdcTb.vin_n,
        seq_init=AdcTb.seq_init,
        seq_samp=AdcTb.seq_samp,
        seq_comp=AdcTb.seq_comp,
        seq_update=AdcTb.seq_update,
        en_init=AdcTb.en_init,
        en_samp_p=AdcTb.en_samp_p,
        en_samp_n=AdcTb.en_samp_n,
        en_comp=AdcTb.en_comp,
        en_update=AdcTb.en_update,
        dac_mode=AdcTb.dac_mode,
        dac_diffcaps=AdcTb.dac_diffcaps,
        dac_astate_p=AdcTb.dac_astate_p,
        dac_bstate_p=AdcTb.dac_bstate_p,
        dac_astate_n=AdcTb.dac_astate_n,
        dac_bstate_n=AdcTb.dac_bstate_n,
        dac_state_p=AdcTb.dac_state_p,
        dac_state_n=AdcTb.dac_state_n,
        vdd_a=AdcTb.vdd_a,
        vss_a=AdcTb.vss,
        vdd_d=AdcTb.vdd_d,
        vss_d=AdcTb.vss,
    )

    # ---- Differential input ramp (PWL) ----
    wave_p = pwl_points_to_wave(
        [
            (0.0, float(params.vin_p_start)),
            (t_stop, float(params.vin_p_stop)),
        ]
    )
    wave_n = pwl_points_to_wave(
        [
            (0.0, float(params.vin_n_start)),
            (t_stop, float(params.vin_n_stop)),
        ]
    )
    AdcTb.vvin_p = Vpwl(wave=wave_p)(p=AdcTb.vin_p, n=AdcTb.vss)
    AdcTb.vvin_n = Vpwl(wave=wave_n)(p=AdcTb.vin_n, n=AdcTb.vss)

    # ---- Sequencer pulse sources ----
    # Timing within each 100ns conversion period:
    #   0-5ns:    seq_init high
    #   5-15ns:   seq_samp high
    #   15-100ns: seq_comp and seq_update alternate (5ns period each)
    #
    # All delays are relative to t_settle (first conversion starts there).
    # Reference: tb_frida_adc.sp uses SPICE pulse() with identical timing.
    AdcTb.vseq_init = Vpulse(
        v1=0 * m,
        v2=vdd,
        delay=params.t_settle,
        rise=100 * p,
        fall=100 * p,
        width=4800 * p,  # 4.8ns high (5ns - rise - fall)
        period=params.t_conv,
    )(p=AdcTb.seq_init, n=AdcTb.vss)

    AdcTb.vseq_samp = Vpulse(
        v1=0 * m,
        v2=vdd,
        delay=params.t_settle + 5 * n,  # starts 5ns into conversion
        rise=100 * p,
        fall=100 * p,
        width=9800 * p,  # 9.8ns high (10ns - rise - fall)
        period=params.t_conv,
    )(p=AdcTb.seq_samp, n=AdcTb.vss)

    AdcTb.vseq_comp = Vpulse(
        v1=0 * m,
        v2=vdd,
        delay=params.t_settle + 15 * n,  # starts 15ns into conversion
        rise=100 * p,
        fall=100 * p,
        width=2400 * p,  # 2.4ns high (2.5ns - rise/2)
        period=5 * n,  # 5ns period (200 MHz)
    )(p=AdcTb.seq_comp, n=AdcTb.vss)

    AdcTb.vseq_update = Vpulse(
        v1=0 * m,
        v2=vdd,
        delay=params.t_settle + 17500 * p,  # 2.5ns after comp (17.5ns)
        rise=100 * p,
        fall=100 * p,
        width=2400 * p,  # 2.4ns high
        period=5 * n,  # 5ns period
    )(p=AdcTb.seq_update, n=AdcTb.vss)

    # ---- Enable signals - all tied to VDD ----
    AdcTb.ven_init = Vdc(dc=vdd)(p=AdcTb.en_init, n=AdcTb.vss)
    AdcTb.ven_samp_p = Vdc(dc=vdd)(p=AdcTb.en_samp_p, n=AdcTb.vss)
    AdcTb.ven_samp_n = Vdc(dc=vdd)(p=AdcTb.en_samp_n, n=AdcTb.vss)
    AdcTb.ven_comp = Vdc(dc=vdd)(p=AdcTb.en_comp, n=AdcTb.vss)
    AdcTb.ven_update = Vdc(dc=vdd)(p=AdcTb.en_update, n=AdcTb.vss)

    # ---- DAC control signals - tied to VDD ----
    AdcTb.vdac_mode = Vdc(dc=vdd)(p=AdcTb.dac_mode, n=AdcTb.vss)
    AdcTb.vdac_diffcaps = Vdc(dc=vdd)(p=AdcTb.dac_diffcaps, n=AdcTb.vss)

    # ---- DAC initial state buses - all bits tied to VDD ----
    for i in range(16):
        setattr(
            AdcTb,
            f"vdac_astate_p{i}",
            Vdc(dc=vdd)(p=AdcTb.dac_astate_p[i], n=AdcTb.vss),
        )
        setattr(
            AdcTb,
            f"vdac_astate_n{i}",
            Vdc(dc=vdd)(p=AdcTb.dac_astate_n[i], n=AdcTb.vss),
        )
        setattr(
            AdcTb,
            f"vdac_bstate_p{i}",
            Vdc(dc=vdd)(p=AdcTb.dac_bstate_p[i], n=AdcTb.vss),
        )
        setattr(
            AdcTb,
            f"vdac_bstate_n{i}",
            Vdc(dc=vdd)(p=AdcTb.dac_bstate_n[i], n=AdcTb.vss),
        )

    return AdcTb


def sim_input(params: AdcTbParams) -> hs.Sim:
    """Create transient simulation for ADC conversion cycles."""
    sim_temp = Project.temper(params.pvt.t)

    t_settle = float(params.t_settle)
    t_conv = float(params.t_conv)
    n_conv = int(params.n_conversions)
    t_stop = t_settle + n_conv * t_conv

    @hs.sim
    class AdcSim:
        tb = AdcTb(params)
        tr = hs.Tran(tstop=t_stop, tstep=100 * p)
        temp = hs.Options(name="temp", value=sim_temp)

    return AdcSim


def _build_variants():
    """Build the full ADC variant list."""
    n_cycles_list = [16]
    cdac_list = [
        CdacParams(n_dac=11, n_extra=5, unit_cap=1 * f),
        CdacParams(n_dac=11, n_extra=5, unit_cap=2 * f),
    ]
    samp_list = [SampParams()]
    comp_list = [CompParams()]

    variants: list[AdcParams] = []
    for n_cycles in n_cycles_list:
        for cdac in cdac_list:
            for samp in samp_list:
                for comp in comp_list:
                    variants.append(
                        AdcParams(
                            n_cycles=n_cycles,
                            cdac=cdac,
                            samp=samp,
                            comp=comp,
                        )
                    )
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
    """Run ADC netlist generation."""
    all_variants = _build_variants()
    variants = select_variants(all_variants, mode)

    def build_sim(adc_params: AdcParams):
        tb_params = AdcTbParams(adc=adc_params)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return AdcTb(tb_params), sim

    def build_dut(adc_params: AdcParams):
        return Adc(adc_params)

    wall_time = run_netlist_variants(
        "adc",
        variants,
        build_sim,
        outdir,
        simulator=fmt,
        fmt=fmt,
        scope=scope,
        build_dut=build_dut,
    )
    if verbose:
        print_netlist_summary(
            block="adc",
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
    sim_server,
    outdir: Path,
    verbose: bool = False,
) -> None:
    """Run ADC simulation."""
    all_variants = _build_variants()
    variants = select_variants(all_variants, mode)

    def build_sim(adc_params: AdcParams):
        tb_params = AdcTbParams(adc=adc_params)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return AdcTb(tb_params), sim

    wall_time, sims = run_netlist_variants(
        "adc",
        variants,
        build_sim,
        outdir,
        return_sims=True,
        simulator=simulator,
        scope="full",
    )
    if verbose:
        print_netlist_summary(
            block="adc",
            pdk_name=tech,
            count=len(variants),
            total=len(all_variants),
            param_axes=get_param_axes(all_variants),
            wall_time=wall_time,
            outdir=str(outdir),
        )
    run_simulations(sims, sim_options, sim_server=sim_server)
