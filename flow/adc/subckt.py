"""
ADC generator for FRIDA.

Creates a complete SAR ADC by composing:
- Digital control block (ExternalModule from synthesized netlist)
- 2x passive capacitor arrays and 4x capacitor drivers
- 2x Sampling switches
- 1x Comparator

Architecture:
    Adc (HDL21 generator)
    ├── Xadc_digital (ExternalModule - static 16-stage)
    ├── Xcaparray_p / Xcaparray_n (HDL21 CapArray)
    ├── Xcapdriver_{p,n}_{main,diff} (HDL21 CapDriver)
    ├── Xsamp_p (HDL21 Samp)
    ├── Xsamp_n (HDL21 Samp)
    └── Xcomp (HDL21 Comp)
"""

import hdl21 as h
from hdl21.primitives import MosType

from flow.circuit.ports import module_from_ports, port_connections

from ..caparray import CapArray, CapArrayConfig, CapArrayParams, get_caparray_weights, is_valid_caparray_config
from ..capdriver import CapDriver, CapDriverParams
from ..comp import Comp, CompParams, is_valid_comp_params
from ..samp import Samp, SampParams


@h.paramclass
class AdcParams:
    """ADC parameters."""

    # Top-level ADC parameter
    adc_bits = h.Param(dtype=int, desc="Nominal normalized ADC resolution", default=12)
    # Component parameters
    cdac = h.Param(
        dtype=CapArrayConfig,
        desc="CDAC parameters",
        default=CapArrayConfig(n_dac=11, n_extra=5),
    )
    samp = h.Param(dtype=SampParams, desc="Sampler parameters", default=SampParams())
    comp = h.Param(dtype=CompParams, desc="Comparator parameters", default=CompParams())


@h.bundle
class AdcNets:
    """Canonical C0-first nets. External ports and internal signals stay flat."""

    vin_p, vin_n = (h.Input(props=h.Properties(inner={"save": True})) for _ in range(2))
    seq_init, seq_samp, seq_comp, seq_logic = (h.Clock(props=h.Properties(inner={"save": True})) for _ in range(4))
    en_init, en_samp_p, en_samp_n, en_comp, en_update = (h.Input() for _ in range(5))
    dac_mode, dac_diffcaps = h.Input(), h.Input()
    dac_astate_p, dac_bstate_p, dac_astate_n, dac_bstate_n = (h.Input(width=16) for _ in range(4))
    dac_state_p, dac_state_n = (h.Output(width=16, props=h.Properties(inner={"save": True})) for _ in range(2))
    comp_out = h.Output(props=h.Properties(inner={"save": True}))
    vdd_a = h.Power(direction=h.PortDir.INOUT)
    vss_a = h.Ground(direction=h.PortDir.INOUT)
    vdd_d = h.Power(direction=h.PortDir.INOUT)
    vss_d = h.Ground(direction=h.PortDir.INOUT)
    vdd_dac = h.Power(direction=h.PortDir.INOUT)
    vss_dac = h.Ground(direction=h.PortDir.INOUT)
    clk_samp_p, clk_samp_p_b, clk_samp_n, clk_samp_n_b, clk_comp = (
        h.Signal(usage=h.Usage.CLOCK, props=h.Properties(inner={"save": True})) for _ in range(5)
    )
    clk_comp_b = h.Signal(usage=h.Usage.CLOCK)
    comp_out_p, comp_out_n, vdac_p, vdac_n = (h.Signal(props=h.Properties(inner={"save": True})) for _ in range(4))
    dac_state_p_diff, dac_state_n_diff = (
        h.Signal(width=16, props=h.Properties(inner={"save": True})) for _ in range(2)
    )
    dac_botplate_p, dac_botplate_n, dac_botplate_p_diff, dac_botplate_n_diff = (
        h.Signal(width=16, props=h.Properties(inner={"save": True})) for _ in range(4)
    )
    dac_invert_p_main, dac_invert_p_diff, dac_invert_n_main, dac_invert_n_diff = h.Signals(4)


def is_valid_adc_params(param: AdcParams) -> bool:
    """Check resolution, component parameters, and the fixed 16-stage interface."""
    if param.adc_bits <= 0 or param.cdac.n_dac <= 0 or param.cdac.n_extra < 0:
        return False
    if param.cdac.n_dac + param.cdac.n_extra != AdcNets.dac_state_p.width:
        return False
    if not is_valid_caparray_config(param.cdac):
        return False
    if len(get_caparray_weights(param.cdac)) != AdcNets.dac_state_p.width:
        return False
    if param.samp.mos_w <= 0 or param.samp.mos_l <= 0:
        return False
    return is_valid_comp_params(param.comp)


# Keep the driver hierarchy fresh when this ADC is requested after compilation.
@h.generator(enable_cache=False)
def Adc(p: AdcParams) -> h.Module:
    """
    SAR ADC generator.

    Composes digital control with analog blocks (CDAC, sampler, comparator).

    The fabricated digital block fixes this implementation at 16 capacitor
    stages and 17 comparator decisions.
    """
    if not is_valid_adc_params(p):
        raise ValueError(f"Invalid ADC params: {p}")

    Adc = module_from_ports("Adc", AdcNets.signals)
    # The IP adapter imports AdcNets; import here after this module is defined.
    from .ip import adc_digital, digital_net_aliases

    digital = adc_digital()
    Adc.xdigital = digital()(
        **{
            physical: Adc.namespace[net.parent.name][net.index] if isinstance(net, h.Slice) else Adc.namespace[net.name]
            for net, physical in digital_net_aliases(digital).items()
        }
    )

    # The generated comparator consumes both clock polarities, whereas the
    # synthesized digital block exposes only ``clk_comp``. Generate its true
    # complement locally instead of borrowing an unrelated sampling clock.
    Adc.MP_clk_comp_b = h.Mos(tp=MosType.PMOS, vth=p.comp.rst_vth, w=10, l=1)(
        d=Adc.clk_comp_b,
        g=Adc.clk_comp,
        s=Adc.vdd_a,
        b=Adc.vdd_a,
    )
    Adc.MN_clk_comp_b = h.Mos(tp=MosType.NMOS, vth=p.comp.rst_vth, w=10, l=1)(
        d=Adc.clk_comp_b,
        g=Adc.clk_comp,
        s=Adc.vss_a,
        b=Adc.vss_a,
    )

    # Identical passive arrays share their definition; each ADC gets fresh drivers.
    array = CapArray(CapArrayParams(cdac=p.cdac))
    driver = CapDriver(CapDriverParams(n_stages=AdcNets.dac_state_p.width, strengths=p.cdac.driver_strengths))
    sampler = Samp(p.samp)
    for side, vin, top, main_state, diff_state, main_invert, diff_invert, main_bot, diff_bot, clk, clk_b in (
        (
            "p",
            Adc.vin_p,
            Adc.vdac_p,
            Adc.dac_state_p,
            Adc.dac_state_p_diff,
            Adc.dac_invert_p_main,
            Adc.dac_invert_p_diff,
            Adc.dac_botplate_p,
            Adc.dac_botplate_p_diff,
            Adc.clk_samp_p,
            Adc.clk_samp_p_b,
        ),
        (
            "n",
            Adc.vin_n,
            Adc.vdac_n,
            Adc.dac_state_n,
            Adc.dac_state_n_diff,
            Adc.dac_invert_n_main,
            Adc.dac_invert_n_diff,
            Adc.dac_botplate_n,
            Adc.dac_botplate_n_diff,
            Adc.clk_samp_n,
            Adc.clk_samp_n_b,
        ),
    ):
        for kind, state, invert, bottom in (
            ("main", main_state, main_invert, main_bot),
            ("diff", diff_state, diff_invert, diff_bot),
        ):
            Adc.add(
                driver(dac_state=state, dac_drive=bottom, dac_drive_invert=invert, vdd=Adc.vdd_dac, vss=Adc.vss_dac),
                name=f"xcapdriver_{side}_{kind}",
            )
        array_connections = {array.cap_topplate.name: top, array.cap_shieldplate.name: Adc.vss_a}
        for kind, bottom in (("main", main_bot), ("diff", diff_bot)):
            for stage in range(bottom.width):
                array_connections[array.ports[f"cap_botplate_{kind}<{stage}>"].name] = bottom[stage]
        Adc.add(array(**array_connections), name=f"xcaparray_{side}")
        Adc.add(sampler(din=vin, dout=top, clk=clk, clk_b=clk_b, vdd=Adc.vdd_a, vss=Adc.vss_a), name=f"xsamp_{side}")

    # Instantiate comparator
    comparator = Comp(p.comp)
    Adc.xcomp = comparator(
        **port_connections(
            comparator.ports,
            Adc,
            inp=Adc.vdac_p,
            inn=Adc.vdac_n,
            outp=Adc.comp_out_p,
            outn=Adc.comp_out_n,
            clk=Adc.clk_comp,
            clkb=Adc.clk_comp_b,
            vdd=Adc.vdd_a,
            vss=Adc.vss_a,
        )
    )

    return Adc
