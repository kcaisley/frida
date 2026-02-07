"""
ADC generator for FRIDA.

Creates a complete SAR ADC by composing:
- Digital control block (ExternalModule from synthesized netlist)
- 2× CDAC with integrated drivers
- 2× Sampling switches
- 1× Comparator

Architecture:
    Adc (HDL21 generator)
    ├── Xadc_digital (ExternalModule - static 16-stage)
    ├── Xcdac_p (HDL21 Cdac)
    ├── Xcdac_n (HDL21 Cdac)
    ├── Xsamp_p (HDL21 Samp)
    ├── Xsamp_n (HDL21 Samp)
    └── Xcomp (HDL21 Comp)
"""

import numpy as np

import hdl21 as h

from ..cdac import Cdac, CdacParams, get_cdac_weights
from ..comp import Comp, CompParams
from ..samp import Samp, SampParams


@h.paramclass
class AdcParams:
    """ADC parameters."""

    # Top-level ADC parameter
    n_cycles = h.Param(dtype=int, desc="Number of SAR comparison cycles", default=16)

    # Component parameters
    cdac = h.Param(
        dtype=CdacParams,
        desc="CDAC parameters",
        default=CdacParams(n_dac=11, n_extra=5),
    )
    samp = h.Param(dtype=SampParams, desc="Sampler parameters", default=SampParams())
    comp = h.Param(dtype=CompParams, desc="Comparator parameters", default=CompParams())


def get_adc_weights(p: AdcParams) -> np.ndarray:
    """Get the capacitor weights for measurement functions."""
    return np.array(get_cdac_weights(p.cdac))


# =============================================================================
# Digital Block ExternalModule
# =============================================================================

# The adc_digital block is a static ExternalModule from the synthesized netlist.
# Currently fixed at 16 stages. When we implement a parametric generator,
# this will be replaced.
#
# Port list from spice/adc_digital.cdl (simplified - main signals only):
# - Sequencer inputs: seq_init, seq_samp, seq_comp, seq_update
# - Enable inputs: en_init, en_samp_p, en_samp_n, en_comp, en_update
# - Control: dac_mode, dac_diffcaps
# - DAC state inputs: dac_astate_p[15:0], dac_bstate_p[15:0],
#                     dac_astate_n[15:0], dac_bstate_n[15:0]
# - Comparator feedback: comp_out_p, comp_out_n
# - Clock outputs: clk_samp_p, clk_samp_p_b, clk_samp_n, clk_samp_n_b, clk_comp
# - DAC state outputs: dac_state_p_main[15:0], dac_state_n_main[15:0]
# - Supplies: vdd_d, vss_d

AdcDigital = h.ExternalModule(
    name="adc_digital",
    port_list=[
        # Sequencer clock inputs
        h.Input(name="seq_init"),
        h.Input(name="seq_samp"),
        h.Input(name="seq_comp"),
        h.Input(name="seq_update"),
        # Enable inputs
        h.Input(name="en_init"),
        h.Input(name="en_samp_p"),
        h.Input(name="en_samp_n"),
        h.Input(name="en_comp"),
        h.Input(name="en_update"),
        # Control inputs
        h.Input(name="dac_mode"),
        h.Input(name="dac_diffcaps"),
        # DAC initial state inputs (16-bit buses)
        h.Input(name="dac_astate_p", width=16),
        h.Input(name="dac_bstate_p", width=16),
        h.Input(name="dac_astate_n", width=16),
        h.Input(name="dac_bstate_n", width=16),
        # Comparator feedback
        h.Input(name="comp_out_p"),
        h.Input(name="comp_out_n"),
        # Clock outputs
        h.Output(name="clk_samp_p"),
        h.Output(name="clk_samp_p_b"),
        h.Output(name="clk_samp_n"),
        h.Output(name="clk_samp_n_b"),
        h.Output(name="clk_comp"),
        # DAC state outputs (main capacitors only - no diffcaps)
        h.Output(name="dac_state_p_main", width=16),
        h.Output(name="dac_state_p_diff", width=16),  # Unused but in netlist
        h.Output(name="dac_state_n_main", width=16),
        h.Output(name="dac_state_n_diff", width=16),  # Unused but in netlist
        # Supplies
        h.Port(name="vdd_d"),
        h.Port(name="vss_d"),
    ],
    desc="Synthesized ADC digital control block (salogic + clkgate + sampdriver)",
)


@h.generator
def Adc(p: AdcParams) -> h.Module:
    """
    SAR ADC generator.

    Composes digital control with analog blocks (CDAC, sampler, comparator).

    Note: Currently requires n_cycles=16 to match the static digital block.
    Future versions will support parametric digital generation.
    """
    # Validate n_cycles matches static digital block
    if p.n_cycles != 16:
        raise ValueError(
            f"ADC currently requires n_cycles=16 (got {p.n_cycles}). "
            "Parametric digital block not yet implemented."
        )

    # Get CDAC bit width
    # NOTE: Future work could make n_bits parametric by updating the digital
    # SAR controller to handle variable bit widths (see SarDigital in digital.py)
    n_bits = len(get_cdac_weights(p.cdac))
    if n_bits != 16:
        raise ValueError(
            f"ADC currently requires 16-bit CDAC (got {n_bits}). "
            "CDAC params must give 16 physical bits."
        )

    @h.module
    class Adc:
        """SAR ADC module."""

        # External IO
        vin_p = h.Input(desc="Positive analog input")
        vin_n = h.Input(desc="Negative analog input")

        # Sequencer clock inputs (directly connected to digital block)
        seq_init = h.Input(desc="Initialize sequence")
        seq_samp = h.Input(desc="Sample sequence")
        seq_comp = h.Input(desc="Compare sequence")
        seq_update = h.Input(desc="Update sequence")

        # Enable inputs
        en_init = h.Input(desc="Enable initialization")
        en_samp_p = h.Input(desc="Enable positive sampler")
        en_samp_n = h.Input(desc="Enable negative sampler")
        en_comp = h.Input(desc="Enable comparator")
        en_update = h.Input(desc="Enable update")

        # Control inputs
        dac_mode = h.Input(desc="DAC mode control")
        dac_diffcaps = h.Input(desc="Differential caps control")

        # DAC initial state (for calibration/testing)
        dac_astate_p = h.Input(width=16, desc="DAC A-state positive")
        dac_bstate_p = h.Input(width=16, desc="DAC B-state positive")
        dac_astate_n = h.Input(width=16, desc="DAC A-state negative")
        dac_bstate_n = h.Input(width=16, desc="DAC B-state negative")

        # Digital outputs (for readout)
        dac_state_p = h.Output(width=16, desc="DAC state positive (bits)")
        dac_state_n = h.Output(width=16, desc="DAC state negative (bits)")

        # Supplies
        vdd_a = h.Port(desc="Analog supply")
        vss_a = h.Port(desc="Analog ground")
        vdd_d = h.Port(desc="Digital supply")
        vss_d = h.Port(desc="Digital ground")

        # Internal signals
        clk_samp_p = h.Signal(desc="Sample clock positive")
        clk_samp_p_b = h.Signal(desc="Sample clock positive bar")
        clk_samp_n = h.Signal(desc="Sample clock negative")
        clk_samp_n_b = h.Signal(desc="Sample clock negative bar")
        clk_comp = h.Signal(desc="Comparator clock")
        comp_out_p = h.Signal(desc="Comparator output positive")
        comp_out_n = h.Signal(desc="Comparator output negative")
        cdac_top_p = h.Signal(desc="CDAC top plate positive")
        cdac_top_n = h.Signal(desc="CDAC top plate negative")
        dac_state_p_diff = h.Signal(width=16)  # Unused
        dac_state_n_diff = h.Signal(width=16)  # Unused

    # Instantiate digital control block
    Adc.xdigital = AdcDigital()(
        seq_init=Adc.seq_init,
        seq_samp=Adc.seq_samp,
        seq_comp=Adc.seq_comp,
        seq_update=Adc.seq_update,
        en_init=Adc.en_init,
        en_samp_p=Adc.en_samp_p,
        en_samp_n=Adc.en_samp_n,
        en_comp=Adc.en_comp,
        en_update=Adc.en_update,
        dac_mode=Adc.dac_mode,
        dac_diffcaps=Adc.dac_diffcaps,
        dac_astate_p=Adc.dac_astate_p,
        dac_bstate_p=Adc.dac_bstate_p,
        dac_astate_n=Adc.dac_astate_n,
        dac_bstate_n=Adc.dac_bstate_n,
        comp_out_p=Adc.comp_out_p,
        comp_out_n=Adc.comp_out_n,
        clk_samp_p=Adc.clk_samp_p,
        clk_samp_p_b=Adc.clk_samp_p_b,
        clk_samp_n=Adc.clk_samp_n,
        clk_samp_n_b=Adc.clk_samp_n_b,
        clk_comp=Adc.clk_comp,
        dac_state_p_main=Adc.dac_state_p,
        dac_state_p_diff=Adc.dac_state_p_diff,
        dac_state_n_main=Adc.dac_state_n,
        dac_state_n_diff=Adc.dac_state_n_diff,
        vdd_d=Adc.vdd_d,
        vss_d=Adc.vss_d,
    )

    # Instantiate positive CDAC
    Adc.xcdac_p = Cdac(p.cdac)(
        top=Adc.cdac_top_p,
        dac=Adc.dac_state_p,
        vdd=Adc.vdd_a,
        vss=Adc.vss_a,
    )

    # Instantiate negative CDAC
    Adc.xcdac_n = Cdac(p.cdac)(
        top=Adc.cdac_top_n,
        dac=Adc.dac_state_n,
        vdd=Adc.vdd_a,
        vss=Adc.vss_a,
    )

    # Instantiate positive sampler
    Adc.xsamp_p = Samp(p.samp)(
        din=Adc.vin_p,
        dout=Adc.cdac_top_p,
        clk=Adc.clk_samp_p,
        clk_b=Adc.clk_samp_p_b,
        vdd=Adc.vdd_a,
        vss=Adc.vss_a,
    )

    # Instantiate negative sampler
    Adc.xsamp_n = Samp(p.samp)(
        din=Adc.vin_n,
        dout=Adc.cdac_top_n,
        clk=Adc.clk_samp_n,
        clk_b=Adc.clk_samp_n_b,
        vdd=Adc.vdd_a,
        vss=Adc.vss_a,
    )

    # Instantiate comparator
    Adc.xcomp = Comp(p.comp)(
        inp=Adc.cdac_top_p,
        inn=Adc.cdac_top_n,
        outp=Adc.comp_out_p,
        outn=Adc.comp_out_n,
        clk=Adc.clk_comp,
        clkb=Adc.clk_samp_p_b,  # Reuse inverted clock
        vdd=Adc.vdd_a,
        vss=Adc.vss_a,
    )

    return Adc
