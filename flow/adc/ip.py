"""Hardened ADC/digital interfaces and canonical-to-physical net bindings.

Physical names are relative to the selected ADC instance. Save statements and
raw readers add that instance path; these bindings never rename the IP itself.
"""

import re
from pathlib import Path

import hdl21 as h

from flow.comp.subckt import CompNets
from flow.util.netlist import normalize_bus_pin, subcircuit_ports

from .subckt import AdcNets


def adc_digital() -> h.ExternalModule:
    """Use the synthesized block's exact scalar pin order."""
    path = Path(__file__).resolve().parents[2] / "design/spice/adc_digital.sp"
    return h.ExternalModule(
        name="adc_digital", port_list=[h.Inout(name=pin) for pin in subcircuit_ports(path.read_text(), "adc_digital")]
    )


def digital_net_aliases(module: h.ExternalModule) -> dict[h.Signal | h.Slice, str]:
    """Bind every digital pin to its canonical ADC net; physical bit 15 is C0."""
    renamed = {
        AdcNets.seq_logic: "seq_update",
        AdcNets.dac_state_p: "dac_state_p_main",
        AdcNets.dac_state_n: "dac_state_n_main",
    }
    by_physical_name = {renamed.get(net, net.name): net for net in AdcNets.signals.values()}
    aliases = {}
    for pin in module.port_list:
        if match := re.fullmatch(r"(.+)\[(\d+)\]", pin.name):
            net = by_physical_name[match[1]]
            index = net.width - 1 - int(match[2])
            if not 0 <= index < net.width:
                raise ValueError(f"Digital pin {pin.name} exceeds canonical width {net.width}")
            canonical = net[index]
        else:
            canonical = by_physical_name[pin.name]
            if canonical.width != pin.width:
                raise ValueError(f"Digital pin width differs from {canonical.name}")
        if canonical in aliases:
            raise ValueError(f"Duplicate digital binding for {canonical}")
        aliases[canonical] = pin.name
    return aliases


def adc_pex(netlist_path: Path, cell: str) -> h.ExternalModule:
    """Declare the selected extraction from its actual positional header."""
    pins = [normalize_bus_pin(pin) for pin in subcircuit_ports(netlist_path.read_text(), cell)]
    if len(pins) != len(set(pins)):
        raise ValueError(f"Duplicate external pins in {cell}")
    return h.ExternalModule(name=cell, port_list=[h.Inout(name=pin) for pin in pins])


def adc_port_aliases(view: str) -> dict[h.Signal | h.Slice, str]:
    """Canonical ADC ports -> scalar PEX pins, with C0 first in Python."""
    if view not in {"frida1", "frida2"}:
        raise ValueError(f"Unsupported ADC IP view {view!r}")
    renamed = {AdcNets.seq_logic: "seq_update"}
    aliases = {}
    for net in AdcNets.signals.values():
        if net.vis != h.Visibility.PORT or net in (AdcNets.dac_state_p, AdcNets.dac_state_n):
            continue
        if net.width == 1:
            aliases[net] = renamed.get(net, net.name)
        else:
            for bit in range(net.width):
                physical = net.width - 1 - bit if view == "frida1" else bit
                aliases[net[bit]] = f"{net.name}_{physical}"
    return aliases


def frida1_net_aliases() -> dict[h.Signal | h.Slice, str]:
    """Canonical ADC/comparator observations -> exact FRIDA-1 RC terminals."""
    return {
        AdcNets.vdac_p: "N_VDAC_P_XXsampswitch_p/MM0_d",
        AdcNets.vdac_n: "N_VDAC_N_XXsampswitch_n/MM0_d",
        AdcNets.clk_samp_p: "N_CLK_SAMP_P_XXsampswitch_p/MM0_g",
        AdcNets.clk_samp_p_b: "N_CLK_SAMP_P_B_XXsampswitch_p/MM1_g",
        AdcNets.clk_samp_n: "N_CLK_SAMP_N_XXsampswitch_n/MM0_g",
        AdcNets.clk_samp_n_b: "N_CLK_SAMP_N_B_XXsampswitch_n/MM1_g",
        AdcNets.clk_comp: "N_CLK_COMP_XXcomp/XXLATCH/MMM0_g",
        AdcNets.comp_out_p: "N_COMP_OUT_P_XXcomp/XXI3/XXI46/MM_u2_1_d",
        AdcNets.comp_out_n: "N_COMP_OUT_N_XXcomp/XXI3/XXI47/MM_u2_1_d",
        CompNets.latch_p: "N_XXCOMP/COMP_P_XXcomp/XXLATCH/MMM4_d",
        CompNets.latch_n: "N_XXCOMP/COMP_N_XXcomp/XXLATCH/MMM3_d",
        CompNets.input_p_drain: "N_XXCOMP/XXLATCH/NET031_XXcomp/XXLATCH/MMM1_d",
        CompNets.input_n_drain: "N_XXCOMP/XXLATCH/NET037_XXcomp/XXLATCH/MMM2_d",
        AdcNets.dac_state_p[0]: "N_DAC_STATE_P_MAIN<15>_XXcapdriver_p_main/XXxor15_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p[0]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<15>_XXcapdriver_p_main/XXxor15_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[0]: "N_DAC_STATE_P_DIFF<15>_XXcapdriver_p_diff/XXxor15_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p_diff[0]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<15>_XXcapdriver_p_diff/XXxor15_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[0]: "N_DAC_STATE_N_MAIN<15>_XXcapdriver_n_main/XXxor15_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n[0]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<15>_XXcapdriver_n_main/XXxor15_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[0]: "N_DAC_STATE_N_DIFF<15>_XXcapdriver_n_diff/XXxor15_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n_diff[0]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<15>_XXcapdriver_n_diff/XXxor15_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[1]: "N_DAC_STATE_P_MAIN<14>_XXcapdriver_p_main/XXxor14_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p[1]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<14>_XXcapdriver_p_main/XXxor14_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[1]: "N_DAC_STATE_P_DIFF<14>_XXcapdriver_p_diff/XXxor14_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p_diff[1]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<14>_XXcapdriver_p_diff/XXxor14_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[1]: "N_DAC_STATE_N_MAIN<14>_XXcapdriver_n_main/XXxor14_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n[1]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<14>_XXcapdriver_n_main/XXxor14_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[1]: "N_DAC_STATE_N_DIFF<14>_XXcapdriver_n_diff/XXxor14_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n_diff[1]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<14>_XXcapdriver_n_diff/XXxor14_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[2]: "N_DAC_STATE_P_MAIN<13>_XXcapdriver_p_main/XXxor13/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p[2]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<13>_XXcapdriver_p_main/XXxor13/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[2]: "N_DAC_STATE_P_DIFF<13>_XXcapdriver_p_diff/XXxor13/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p_diff[2]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<13>_XXcapdriver_p_diff/XXxor13/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[2]: "N_DAC_STATE_N_MAIN<13>_XXcapdriver_n_main/XXxor13/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n[2]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<13>_XXcapdriver_n_main/XXxor13/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[2]: "N_DAC_STATE_N_DIFF<13>_XXcapdriver_n_diff/XXxor13/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n_diff[2]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<13>_XXcapdriver_n_diff/XXxor13/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[3]: "N_DAC_STATE_P_MAIN<12>_XXcapdriver_p_main/XXxor12/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p[3]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<12>_XXcapdriver_p_main/XXxor12/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[3]: "N_DAC_STATE_P_DIFF<12>_XXcapdriver_p_diff/XXxor12/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p_diff[3]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<12>_XXcapdriver_p_diff/XXxor12/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[3]: "N_DAC_STATE_N_MAIN<12>_XXcapdriver_n_main/XXxor12/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n[3]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<12>_XXcapdriver_n_main/XXxor12/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[3]: "N_DAC_STATE_N_DIFF<12>_XXcapdriver_n_diff/XXxor12/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n_diff[3]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<12>_XXcapdriver_n_diff/XXxor12/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[4]: "N_DAC_STATE_P_MAIN<11>_XXcapdriver_p_main/XXxor11/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[4]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<11>_XXcapdriver_p_main/XXxor11/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[4]: "N_DAC_STATE_P_DIFF<11>_XXcapdriver_p_diff/XXxor11/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[4]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<11>_XXcapdriver_p_diff/XXxor11/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[4]: "N_DAC_STATE_N_MAIN<11>_XXcapdriver_n_main/XXxor11/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[4]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<11>_XXcapdriver_n_main/XXxor11/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[4]: "N_DAC_STATE_N_DIFF<11>_XXcapdriver_n_diff/XXxor11/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[4]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<11>_XXcapdriver_n_diff/XXxor11/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[5]: "N_DAC_STATE_P_MAIN<10>_XXcapdriver_p_main/XXxor10/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[5]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<10>_XXcapdriver_p_main/XXxor10/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[5]: "N_DAC_STATE_P_DIFF<10>_XXcapdriver_p_diff/XXxor10/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[5]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<10>_XXcapdriver_p_diff/XXxor10/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[5]: "N_DAC_STATE_N_MAIN<10>_XXcapdriver_n_main/XXxor10/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[5]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<10>_XXcapdriver_n_main/XXxor10/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[5]: "N_DAC_STATE_N_DIFF<10>_XXcapdriver_n_diff/XXxor10/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[5]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<10>_XXcapdriver_n_diff/XXxor10/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[6]: "N_DAC_STATE_P_MAIN<9>_XXcapdriver_p_main/XXxor9/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[6]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<9>_XXcapdriver_p_main/XXxor9/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[6]: "N_DAC_STATE_P_DIFF<9>_XXcapdriver_p_diff/XXxor9/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[6]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<9>_XXcapdriver_p_diff/XXxor9/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[6]: "N_DAC_STATE_N_MAIN<9>_XXcapdriver_n_main/XXxor9/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[6]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<9>_XXcapdriver_n_main/XXxor9/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[6]: "N_DAC_STATE_N_DIFF<9>_XXcapdriver_n_diff/XXxor9/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[6]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<9>_XXcapdriver_n_diff/XXxor9/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[7]: "N_DAC_STATE_P_MAIN<8>_XXcapdriver_p_main/XXxor8/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[7]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<8>_XXcapdriver_p_main/XXxor8/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[7]: "N_DAC_STATE_P_DIFF<8>_XXcapdriver_p_diff/XXxor8/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[7]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<8>_XXcapdriver_p_diff/XXxor8/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[7]: "N_DAC_STATE_N_MAIN<8>_XXcapdriver_n_main/XXxor8/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[7]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<8>_XXcapdriver_n_main/XXxor8/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[7]: "N_DAC_STATE_N_DIFF<8>_XXcapdriver_n_diff/XXxor8/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[7]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<8>_XXcapdriver_n_diff/XXxor8/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[8]: "N_DAC_STATE_P_MAIN<7>_XXcapdriver_p_main/XXxor7/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[8]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<7>_XXcapdriver_p_main/XXxor7/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[8]: "N_DAC_STATE_P_DIFF<7>_XXcapdriver_p_diff/XXxor7/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[8]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<7>_XXcapdriver_p_diff/XXxor7/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[8]: "N_DAC_STATE_N_MAIN<7>_XXcapdriver_n_main/XXxor7/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[8]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<7>_XXcapdriver_n_main/XXxor7/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[8]: "N_DAC_STATE_N_DIFF<7>_XXcapdriver_n_diff/XXxor7/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[8]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<7>_XXcapdriver_n_diff/XXxor7/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[9]: "N_DAC_STATE_P_MAIN<6>_XXcapdriver_p_main/XXxor6/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[9]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<6>_XXcapdriver_p_main/XXxor6/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[9]: "N_DAC_STATE_P_DIFF<6>_XXcapdriver_p_diff/XXxor6/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[9]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<6>_XXcapdriver_p_diff/XXxor6/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[9]: "N_DAC_STATE_N_MAIN<6>_XXcapdriver_n_main/XXxor6/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[9]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<6>_XXcapdriver_n_main/XXxor6/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[9]: "N_DAC_STATE_N_DIFF<6>_XXcapdriver_n_diff/XXxor6/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[9]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<6>_XXcapdriver_n_diff/XXxor6/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[10]: "N_DAC_STATE_P_MAIN<5>_XXcapdriver_p_main/XXxor5/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[10]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<5>_XXcapdriver_p_main/XXxor5/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[10]: "N_DAC_STATE_P_DIFF<5>_XXcapdriver_p_diff/XXxor5/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[10]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<5>_XXcapdriver_p_diff/XXxor5/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[10]: "N_DAC_STATE_N_MAIN<5>_XXcapdriver_n_main/XXxor5/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[10]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<5>_XXcapdriver_n_main/XXxor5/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[10]: "N_DAC_STATE_N_DIFF<5>_XXcapdriver_n_diff/XXxor5/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[10]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<5>_XXcapdriver_n_diff/XXxor5/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[11]: "N_DAC_STATE_P_MAIN<4>_XXcapdriver_p_main/XXxor4/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[11]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<4>_XXcapdriver_p_main/XXxor4/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[11]: "N_DAC_STATE_P_DIFF<4>_XXcapdriver_p_diff/XXxor4/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[11]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<4>_XXcapdriver_p_diff/XXxor4/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[11]: "N_DAC_STATE_N_MAIN<4>_XXcapdriver_n_main/XXxor4/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[11]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<4>_XXcapdriver_n_main/XXxor4/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[11]: "N_DAC_STATE_N_DIFF<4>_XXcapdriver_n_diff/XXxor4/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[11]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<4>_XXcapdriver_n_diff/XXxor4/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[12]: "N_DAC_STATE_P_MAIN<3>_XXcapdriver_p_main/XXxor3/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[12]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<3>_XXcapdriver_p_main/XXxor3/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[12]: "N_DAC_STATE_P_DIFF<3>_XXcapdriver_p_diff/XXxor3/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[12]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<3>_XXcapdriver_p_diff/XXxor3/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[12]: "N_DAC_STATE_N_MAIN<3>_XXcapdriver_n_main/XXxor3/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[12]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<3>_XXcapdriver_n_main/XXxor3/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[12]: "N_DAC_STATE_N_DIFF<3>_XXcapdriver_n_diff/XXxor3/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[12]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<3>_XXcapdriver_n_diff/XXxor3/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[13]: "N_DAC_STATE_P_MAIN<2>_XXcapdriver_p_main/XXxor2/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[13]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<2>_XXcapdriver_p_main/XXxor2/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[13]: "N_DAC_STATE_P_DIFF<2>_XXcapdriver_p_diff/XXxor2/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[13]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<2>_XXcapdriver_p_diff/XXxor2/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[13]: "N_DAC_STATE_N_MAIN<2>_XXcapdriver_n_main/XXxor2/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[13]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<2>_XXcapdriver_n_main/XXxor2/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[13]: "N_DAC_STATE_N_DIFF<2>_XXcapdriver_n_diff/XXxor2/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[13]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<2>_XXcapdriver_n_diff/XXxor2/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[14]: "N_DAC_STATE_P_MAIN<1>_XXcapdriver_p_main/XXxor1/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[14]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<1>_XXcapdriver_p_main/XXxor1/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[14]: "N_DAC_STATE_P_DIFF<1>_XXcapdriver_p_diff/XXxor1/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[14]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<1>_XXcapdriver_p_diff/XXxor1/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[14]: "N_DAC_STATE_N_MAIN<1>_XXcapdriver_n_main/XXxor1/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[14]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<1>_XXcapdriver_n_main/XXxor1/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[14]: "N_DAC_STATE_N_DIFF<1>_XXcapdriver_n_diff/XXxor1/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[14]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<1>_XXcapdriver_n_diff/XXxor1/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[15]: "N_DAC_STATE_P_MAIN<0>_XXcapdriver_p_main/XXxor0/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[15]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<0>_XXcapdriver_p_main/XXxor0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[15]: "N_DAC_STATE_P_DIFF<0>_XXcapdriver_p_diff/XXxor0/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[15]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<0>_XXcapdriver_p_diff/XXxor0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[15]: "N_DAC_STATE_N_MAIN<0>_XXcapdriver_n_main/XXxor0/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[15]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<0>_XXcapdriver_n_main/XXxor0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[15]: "N_DAC_STATE_N_DIFF<0>_XXcapdriver_n_diff/XXxor0/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[15]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<0>_XXcapdriver_n_diff/XXxor0/MMM_u4_1-M_u3_d",
    }


def frida2_net_aliases() -> dict[h.Signal | h.Slice, str]:
    """Canonical ADC/comparator observations -> exact FRIDA-2 RC terminals."""
    return {
        AdcNets.vdac_p: "N_VDAC_P_XXsampswitch_p/MM0_d",
        AdcNets.vdac_n: "N_VDAC_N_XXsampswitch_n/MM0_d",
        AdcNets.clk_samp_p: "N_CLK_SAMP_P_XXsampswitch_p/MM0_g",
        AdcNets.clk_samp_p_b: "N_CLK_SAMP_P_B_XXsampswitch_p/MM1_g",
        AdcNets.clk_samp_n: "N_CLK_SAMP_N_XXsampswitch_n/MM0_g",
        AdcNets.clk_samp_n_b: "N_CLK_SAMP_N_B_XXsampswitch_n/MM1_g",
        AdcNets.clk_comp: "N_CLK_COMP_XXcomp/XXLATCH/MMM0_g",
        AdcNets.comp_out_p: "N_COMP_OUT_P_XXcomp/XXI3/XXI46/MM_u2_1_d",
        AdcNets.comp_out_n: "N_COMP_OUT_N_XXcomp/XXI3/XXI47/MM_u2_1_d",
        CompNets.latch_p: "N_XXCOMP/COMP_P_XXcomp/XXLATCH/MMM4_d",
        CompNets.latch_n: "N_XXCOMP/COMP_N_XXcomp/XXLATCH/MMM3_d",
        CompNets.input_p_drain: "N_XXCOMP/XXLATCH/NET031_XXcomp/XXLATCH/MMM1_d",
        CompNets.input_n_drain: "N_XXCOMP/XXLATCH/NET037_XXcomp/XXLATCH/MMM2_d",
        AdcNets.dac_state_p[0]: "N_DAC_STATE_P_MAIN<0>_XXcapdriver_p_main/XXxor15_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p[0]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<0>_XXcapdriver_p_main/XXxor15_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[0]: "N_DAC_STATE_P_DIFF<0>_XXcapdriver_p_diff/XXxor15_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p_diff[0]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<0>_XXcapdriver_p_diff/XXxor15_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[0]: "N_DAC_STATE_N_MAIN<0>_XXcapdriver_n_main/XXxor15_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n[0]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<0>_XXcapdriver_n_main/XXxor15_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[0]: "N_DAC_STATE_N_DIFF<0>_XXcapdriver_n_diff/XXxor15_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n_diff[0]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<0>_XXcapdriver_n_diff/XXxor15_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[1]: "N_DAC_STATE_P_MAIN<1>_XXcapdriver_p_main/XXxor14_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p[1]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<1>_XXcapdriver_p_main/XXxor14_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[1]: "N_DAC_STATE_P_DIFF<1>_XXcapdriver_p_diff/XXxor14_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p_diff[1]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<1>_XXcapdriver_p_diff/XXxor14_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[1]: "N_DAC_STATE_N_MAIN<1>_XXcapdriver_n_main/XXxor14_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n[1]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<1>_XXcapdriver_n_main/XXxor14_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[1]: "N_DAC_STATE_N_DIFF<1>_XXcapdriver_n_diff/XXxor14_0/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n_diff[1]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<1>_XXcapdriver_n_diff/XXxor14_0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[2]: "N_DAC_STATE_P_MAIN<2>_XXcapdriver_p_main/XXxor13/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p[2]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<2>_XXcapdriver_p_main/XXxor13/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[2]: "N_DAC_STATE_P_DIFF<2>_XXcapdriver_p_diff/XXxor13/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p_diff[2]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<2>_XXcapdriver_p_diff/XXxor13/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[2]: "N_DAC_STATE_N_MAIN<2>_XXcapdriver_n_main/XXxor13/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n[2]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<2>_XXcapdriver_n_main/XXxor13/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[2]: "N_DAC_STATE_N_DIFF<2>_XXcapdriver_n_diff/XXxor13/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n_diff[2]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<2>_XXcapdriver_n_diff/XXxor13/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[3]: "N_DAC_STATE_P_MAIN<3>_XXcapdriver_p_main/XXxor12/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p[3]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<3>_XXcapdriver_p_main/XXxor12/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[3]: "N_DAC_STATE_P_DIFF<3>_XXcapdriver_p_diff/XXxor12/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_p_diff[3]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<3>_XXcapdriver_p_diff/XXxor12/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[3]: "N_DAC_STATE_N_MAIN<3>_XXcapdriver_n_main/XXxor12/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n[3]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<3>_XXcapdriver_n_main/XXxor12/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[3]: "N_DAC_STATE_N_DIFF<3>_XXcapdriver_n_diff/XXxor12/MMM_u2_1-M_u3_g",
        AdcNets.dac_botplate_n_diff[3]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<3>_XXcapdriver_n_diff/XXxor12/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[4]: "N_DAC_STATE_P_MAIN<4>_XXcapdriver_p_main/XXxor11/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[4]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<4>_XXcapdriver_p_main/XXxor11/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[4]: "N_DAC_STATE_P_DIFF<4>_XXcapdriver_p_diff/XXxor11/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[4]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<4>_XXcapdriver_p_diff/XXxor11/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[4]: "N_DAC_STATE_N_MAIN<4>_XXcapdriver_n_main/XXxor11/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[4]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<4>_XXcapdriver_n_main/XXxor11/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[4]: "N_DAC_STATE_N_DIFF<4>_XXcapdriver_n_diff/XXxor11/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[4]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<4>_XXcapdriver_n_diff/XXxor11/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[5]: "N_DAC_STATE_P_MAIN<5>_XXcapdriver_p_main/XXxor10/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[5]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<5>_XXcapdriver_p_main/XXxor10/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[5]: "N_DAC_STATE_P_DIFF<5>_XXcapdriver_p_diff/XXxor10/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[5]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<5>_XXcapdriver_p_diff/XXxor10/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[5]: "N_DAC_STATE_N_MAIN<5>_XXcapdriver_n_main/XXxor10/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[5]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<5>_XXcapdriver_n_main/XXxor10/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[5]: "N_DAC_STATE_N_DIFF<5>_XXcapdriver_n_diff/XXxor10/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[5]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<5>_XXcapdriver_n_diff/XXxor10/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[6]: "N_DAC_STATE_P_MAIN<6>_XXcapdriver_p_main/XXxor9/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[6]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<6>_XXcapdriver_p_main/XXxor9/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[6]: "N_DAC_STATE_P_DIFF<6>_XXcapdriver_p_diff/XXxor9/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[6]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<6>_XXcapdriver_p_diff/XXxor9/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[6]: "N_DAC_STATE_N_MAIN<6>_XXcapdriver_n_main/XXxor9/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[6]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<6>_XXcapdriver_n_main/XXxor9/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[6]: "N_DAC_STATE_N_DIFF<6>_XXcapdriver_n_diff/XXxor9/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[6]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<6>_XXcapdriver_n_diff/XXxor9/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[7]: "N_DAC_STATE_P_MAIN<7>_XXcapdriver_p_main/XXxor8/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[7]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<7>_XXcapdriver_p_main/XXxor8/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[7]: "N_DAC_STATE_P_DIFF<7>_XXcapdriver_p_diff/XXxor8/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[7]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<7>_XXcapdriver_p_diff/XXxor8/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[7]: "N_DAC_STATE_N_MAIN<7>_XXcapdriver_n_main/XXxor8/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[7]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<7>_XXcapdriver_n_main/XXxor8/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[7]: "N_DAC_STATE_N_DIFF<7>_XXcapdriver_n_diff/XXxor8/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[7]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<7>_XXcapdriver_n_diff/XXxor8/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[8]: "N_DAC_STATE_P_MAIN<8>_XXcapdriver_p_main/XXxor7/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[8]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<8>_XXcapdriver_p_main/XXxor7/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[8]: "N_DAC_STATE_P_DIFF<8>_XXcapdriver_p_diff/XXxor7/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[8]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<8>_XXcapdriver_p_diff/XXxor7/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[8]: "N_DAC_STATE_N_MAIN<8>_XXcapdriver_n_main/XXxor7/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[8]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<8>_XXcapdriver_n_main/XXxor7/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[8]: "N_DAC_STATE_N_DIFF<8>_XXcapdriver_n_diff/XXxor7/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[8]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<8>_XXcapdriver_n_diff/XXxor7/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[9]: "N_DAC_STATE_P_MAIN<9>_XXcapdriver_p_main/XXxor6/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[9]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<9>_XXcapdriver_p_main/XXxor6/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[9]: "N_DAC_STATE_P_DIFF<9>_XXcapdriver_p_diff/XXxor6/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[9]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<9>_XXcapdriver_p_diff/XXxor6/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[9]: "N_DAC_STATE_N_MAIN<9>_XXcapdriver_n_main/XXxor6/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[9]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<9>_XXcapdriver_n_main/XXxor6/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[9]: "N_DAC_STATE_N_DIFF<9>_XXcapdriver_n_diff/XXxor6/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[9]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<9>_XXcapdriver_n_diff/XXxor6/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[10]: "N_DAC_STATE_P_MAIN<10>_XXcapdriver_p_main/XXxor5/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[10]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<10>_XXcapdriver_p_main/XXxor5/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[10]: "N_DAC_STATE_P_DIFF<10>_XXcapdriver_p_diff/XXxor5/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[10]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<10>_XXcapdriver_p_diff/XXxor5/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[10]: "N_DAC_STATE_N_MAIN<10>_XXcapdriver_n_main/XXxor5/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[10]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<10>_XXcapdriver_n_main/XXxor5/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[10]: "N_DAC_STATE_N_DIFF<10>_XXcapdriver_n_diff/XXxor5/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[10]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<10>_XXcapdriver_n_diff/XXxor5/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[11]: "N_DAC_STATE_P_MAIN<11>_XXcapdriver_p_main/XXxor4/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[11]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<11>_XXcapdriver_p_main/XXxor4/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[11]: "N_DAC_STATE_P_DIFF<11>_XXcapdriver_p_diff/XXxor4/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[11]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<11>_XXcapdriver_p_diff/XXxor4/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[11]: "N_DAC_STATE_N_MAIN<11>_XXcapdriver_n_main/XXxor4/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[11]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<11>_XXcapdriver_n_main/XXxor4/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[11]: "N_DAC_STATE_N_DIFF<11>_XXcapdriver_n_diff/XXxor4/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[11]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<11>_XXcapdriver_n_diff/XXxor4/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[12]: "N_DAC_STATE_P_MAIN<12>_XXcapdriver_p_main/XXxor3/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[12]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<12>_XXcapdriver_p_main/XXxor3/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[12]: "N_DAC_STATE_P_DIFF<12>_XXcapdriver_p_diff/XXxor3/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[12]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<12>_XXcapdriver_p_diff/XXxor3/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[12]: "N_DAC_STATE_N_MAIN<12>_XXcapdriver_n_main/XXxor3/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[12]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<12>_XXcapdriver_n_main/XXxor3/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[12]: "N_DAC_STATE_N_DIFF<12>_XXcapdriver_n_diff/XXxor3/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[12]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<12>_XXcapdriver_n_diff/XXxor3/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[13]: "N_DAC_STATE_P_MAIN<13>_XXcapdriver_p_main/XXxor2/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[13]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<13>_XXcapdriver_p_main/XXxor2/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[13]: "N_DAC_STATE_P_DIFF<13>_XXcapdriver_p_diff/XXxor2/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[13]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<13>_XXcapdriver_p_diff/XXxor2/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[13]: "N_DAC_STATE_N_MAIN<13>_XXcapdriver_n_main/XXxor2/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[13]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<13>_XXcapdriver_n_main/XXxor2/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[13]: "N_DAC_STATE_N_DIFF<13>_XXcapdriver_n_diff/XXxor2/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[13]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<13>_XXcapdriver_n_diff/XXxor2/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[14]: "N_DAC_STATE_P_MAIN<14>_XXcapdriver_p_main/XXxor1/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[14]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<14>_XXcapdriver_p_main/XXxor1/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[14]: "N_DAC_STATE_P_DIFF<14>_XXcapdriver_p_diff/XXxor1/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[14]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<14>_XXcapdriver_p_diff/XXxor1/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[14]: "N_DAC_STATE_N_MAIN<14>_XXcapdriver_n_main/XXxor1/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[14]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<14>_XXcapdriver_n_main/XXxor1/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[14]: "N_DAC_STATE_N_DIFF<14>_XXcapdriver_n_diff/XXxor1/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[14]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<14>_XXcapdriver_n_diff/XXxor1/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p[15]: "N_DAC_STATE_P_MAIN<15>_XXcapdriver_p_main/XXxor0/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p[15]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<15>_XXcapdriver_p_main/XXxor0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_p_diff[15]: "N_DAC_STATE_P_DIFF<15>_XXcapdriver_p_diff/XXxor0/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_p_diff[15]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<15>_XXcapdriver_p_diff/XXxor0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n[15]: "N_DAC_STATE_N_MAIN<15>_XXcapdriver_n_main/XXxor0/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n[15]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<15>_XXcapdriver_n_main/XXxor0/MMM_u4_1-M_u3_d",
        AdcNets.dac_state_n_diff[15]: "N_DAC_STATE_N_DIFF<15>_XXcapdriver_n_diff/XXxor0/MMM_u2-M_u3_g",
        AdcNets.dac_botplate_n_diff[15]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<15>_XXcapdriver_n_diff/XXxor0/MMM_u4_1-M_u3_d",
    }
