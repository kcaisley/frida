"""The ADC's parameters: its design (``Params``, every combination of which builds) and one generated
testbench (``TbParams``: the view it simulates, its stimulus, its supplies and its sequencer rows,
by default the default recipe's, ``sim.symbol256_init8_samp16_comp11110000_logic00001111``).
"""

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import G, m
from pydantic import PositiveInt

from flow import comp, pipeline, samp
from flow.cdac.caparray import CapArrayConfig, RedunStrat


@h.paramclass
class Params:
    """ADC parameters."""

    # Top-level ADC parameter
    adc_bits = h.Param(dtype=PositiveInt, desc="Nominal normalized ADC resolution", default=12)
    # Component parameters
    cdac = h.Param(
        dtype=CapArrayConfig,
        desc="CDAC parameters",
        default=CapArrayConfig(n_dac=11, n_extra=5),
    )
    samp = h.Param(dtype=samp.Params, desc="Sampler parameters", default=samp.FRIDA1)
    comp = h.Param(dtype=comp.Params, desc="Comparator parameters", default=comp.FRIDA1)


pipeline.Params.register(Params)


@h.paramclass
class TbParams:
    """Parameters which determine one generated ADC testbench."""

    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=10e-12
    )
    view = h.Param(dtype=str, desc="ADC implementation: frida1, frida2, or hdl21gen", default="hdl21gen")
    pex_cell = h.Param(
        dtype=str,
        desc="Calibre-extracted cell; empty selects adc_1layer_radix17 for frida1",
        default="",
    )
    dut = h.Param(
        dtype=Params,
        desc="ADC DUT parameters",
        default=Params(
            cdac=CapArrayConfig(n_dac=11, n_extra=5, redun_strat=RedunStrat.MSB_REDIST),
        ),
    )
    symbol_rate = h.Param(dtype=h.Scalar, desc="DDR symbol rate", default=1.6 * G)
    conversions = h.Param(dtype=int, desc="Number of conversions", default=10_000)
    en_init = h.Param(dtype=int, desc="Enable initialization clock", default=1)
    en_samp_p = h.Param(dtype=int, desc="Enable positive sampling clock", default=1)
    en_samp_n = h.Param(dtype=int, desc="Enable negative sampling clock", default=1)
    en_comp = h.Param(dtype=int, desc="Enable comparator clock", default=1)
    en_update = h.Param(dtype=int, desc="Enable DAC-update clock", default=1)
    dac_mode = h.Param(dtype=int, desc="Select comparator-driven DAC mode", default=1)
    dac_diffcaps = h.Param(dtype=int, desc="Enable differential capacitor controls", default=1)
    dac_astate_p = h.Param(dtype=tuple[int, ...], desc="C0-first positive DAC A state", default=(0, 1) * 8)
    dac_bstate_p = h.Param(dtype=tuple[int, ...], desc="C0-first positive DAC B state", default=(0,) * 16)
    dac_astate_n = h.Param(dtype=tuple[int, ...], desc="C0-first negative DAC A state", default=(0, 1) * 8)
    dac_bstate_n = h.Param(dtype=tuple[int, ...], desc="C0-first negative DAC B state", default=(0,) * 16)
    vdd_a = h.Param(dtype=h.Vdc.Params, desc="Analog supply", default=h.Vdc.Params(dc=1200 * m))
    vdd_d = h.Param(dtype=h.Vdc.Params, desc="Digital supply", default=h.Vdc.Params(dc=1200 * m))
    vdd_dac = h.Param(dtype=h.Vdc.Params, desc="DAC supply", default=h.Vdc.Params(dc=1200 * m))
    supply_series_resistance_ohm = h.Param(
        dtype=float,
        desc="Lumped bond-wire and chip-level PDN series resistance per supply rail",
        default=0.0,
    )
    supply_series_inductance_h = h.Param(
        dtype=float,
        desc="Lumped bond-wire and chip-level PDN series inductance per supply rail",
        default=0.0,
    )
    supply_decoupling_capacitance_f = h.Param(
        dtype=float,
        desc="Local chip-level decoupling capacitance per supply rail",
        default=0.0,
    )
    supply_noise_rms_v = h.Param(
        dtype=tuple[float, ...],
        desc="Added RMS noise on VDD_A, VDD_D, and VDD_DAC",
        default=(0.0, 0.0, 0.0),
    )
    supply_noise_bandwidth_hz = h.Param(
        dtype=float,
        desc="Flat bandwidth over which each added supply-noise RMS value is defined",
        default=25.0e9,
    )
    vin_cm = h.Param(dtype=h.Vdc.Params, desc="Input common mode", default=h.Vdc.Params(dc=700 * m))
    vin_diff = h.Param(
        dtype=h.Vdc.Params | h.Vsin.Params | h.Vpwl.Params | hs.LinearSweep,
        desc="Differential input stimulus",
        default=h.Vdc.Params(dc=0.0),
    )
    # the default recipe's rows (sim.symbol256_init8_samp16_comp11110000_logic00001111; test_params.py)
    seq_init_pattern = h.Param(
        dtype=str,
        desc="INIT sequence",
        default=(
            "11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
        ).replace(" ", ""),
    )
    seq_samp_pattern = h.Param(
        dtype=str,
        desc="SAMP sequence",
        default=(
            "00000000 11111111 11111111 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
        ).replace(" ", ""),
    )
    seq_comp_pattern = h.Param(
        dtype=str,
        desc="COMP sequence",
        default=(
            "00000000 00000000 00000000 00001111 00001111 00001111 00001111 00001111 "
            "00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 "
            "00001111 00001111 00001111 00001111 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
        ).replace(" ", ""),
    )
    seq_logic_pattern = h.Param(
        dtype=str,
        desc="LOGIC sequence",
        default=(
            "00001111 00000000 00000000 00000000 11110000 11110000 11110000 11110000 "
            "11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 "
            "11110000 11110000 11110000 11110000 00000000 00000000 00000000 00000000 "
            "00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 "
        ).replace(" ", ""),
    )
    # TODO: matching a building-block Monte Carlo result to a higher-level run
    # by seed and iteration alone is not valid; the two runs draw independent
    # mismatch. Netlisting does not consume these fields yet.
    mc_seed = h.Param(dtype=int | None, desc="Spectre Monte Carlo seed; None for nominal", default=None)
    mc_index = h.Param(dtype=int | None, desc="Spectre Monte Carlo iteration; None for nominal", default=None)
