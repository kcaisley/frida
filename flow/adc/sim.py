"""HDL21 testbench and named Spectre simulation runner for the FRIDA ADC."""

from __future__ import annotations

import argparse
import dataclasses
import math
import re
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import p

from flow.circuit.netlist import write_spectre_input
from flow.pdks import set_pdk
from flow.scans.params import AdcTbParams, convert_sample_rate_to_baud, validate_params
from flow.spice.io import convert_spectre_adc_raw_to_h5

from .subckt import Adc

BASE_PATH = Path(__file__).resolve().parents[2]
MAX_PARALLEL_SIMULATIONS = 3
SPECTRE_THREADS_PER_SIMULATION = 4
PEX_NETLIST = Path("/users/kcaisley/asiclab/tech/tsmc65/cds/PEX/adc_1layer_radix17.pex.netlist")
MODEL_LIBRARY = Path("/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs")
STANDARD_CELL_SPICE = (
    Path("/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lp_200a/tcbn65lp_200a.spi"),
    Path("/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lplvt_200a/tcbn65lplvt_200a.spi"),
)
DIGITAL_SPICE = BASE_PATH / "design" / "spice" / "adc_digital.sp"


# Exact positional signature of the Calibre-extracted FRIDA65A ADC. Friendly
# scalar names retain the logical bus index while preserving the PEX ordering.
FRIDA65A_PEX_PORTS = (
    "vdd_a",
    "vin_p",
    "vss_a",
    "dac_mode",
    "dac_diffcaps",
    "seq_init",
    "en_init",
    "seq_samp",
    "en_samp_p",
    "en_samp_n",
    "seq_comp",
    "en_comp",
    "seq_update",
    "en_update",
    "comp_out",
    "vin_n",
    "vdd_d",
    "vss_d",
    "vdd_dac",
    "vss_dac",
    "dac_bstate_p_4",
    "dac_bstate_p_11",
    "dac_astate_p_0",
    "dac_astate_p_1",
    "dac_astate_p_2",
    "dac_astate_p_3",
    "dac_astate_p_4",
    "dac_astate_p_5",
    "dac_astate_p_6",
    "dac_astate_p_8",
    "dac_astate_p_9",
    "dac_astate_p_10",
    "dac_astate_p_11",
    "dac_astate_p_12",
    "dac_astate_p_13",
    "dac_astate_p_14",
    "dac_astate_p_15",
    "dac_bstate_p_0",
    "dac_bstate_p_2",
    "dac_bstate_p_3",
    "dac_bstate_p_5",
    "dac_bstate_p_6",
    "dac_bstate_p_7",
    "dac_bstate_p_8",
    "dac_bstate_p_10",
    "dac_bstate_p_12",
    "dac_bstate_p_13",
    "dac_bstate_p_14",
    "dac_bstate_p_15",
    "dac_astate_p_7",
    "dac_bstate_p_1",
    "dac_bstate_p_9",
    "dac_astate_n_0",
    "dac_astate_n_1",
    "dac_astate_n_2",
    "dac_astate_n_3",
    "dac_astate_n_4",
    "dac_astate_n_5",
    "dac_astate_n_6",
    "dac_astate_n_7",
    "dac_astate_n_8",
    "dac_astate_n_9",
    "dac_astate_n_10",
    "dac_astate_n_11",
    "dac_astate_n_12",
    "dac_astate_n_13",
    "dac_astate_n_14",
    "dac_astate_n_15",
    "dac_bstate_n_0",
    "dac_bstate_n_1",
    "dac_bstate_n_2",
    "dac_bstate_n_3",
    "dac_bstate_n_4",
    "dac_bstate_n_5",
    "dac_bstate_n_6",
    "dac_bstate_n_7",
    "dac_bstate_n_8",
    "dac_bstate_n_9",
    "dac_bstate_n_10",
    "dac_bstate_n_11",
    "dac_bstate_n_13",
    "dac_bstate_n_14",
    "dac_bstate_n_15",
    "dac_bstate_n_12",
)

Frida65aPexAdc = h.ExternalModule(
    name="adc_1layer_radix17",
    port_list=[h.Inout(name=name) for name in FRIDA65A_PEX_PORTS],
    desc="Calibre xRC extracted FRIDA65A ADC in exact positional pin order",
)


def AdcTb(params: AdcTbParams, view: str) -> h.Module:
    """Build one shared-parameter ADC testbench for a generated or PEX DUT."""

    validate_params(params)
    if view not in {"frida65a", "hdl21gen"}:
        raise ValueError(f"unknown ADC view {view!r}")

    tb = h.Module(name=f"AdcTb_{view}")
    tb.vss = h.Port(desc="Simulator ground")
    tb.vdd_a = h.Signal()
    tb.vdd_d = h.Signal()
    tb.vdd_dac = h.Signal()
    tb.vin_cm = h.Signal()
    tb.vin_diff = h.Signal()
    tb.vin_p = h.Signal()
    tb.vin_n = h.Signal()
    tb.seq_init = h.Signal()
    tb.seq_samp = h.Signal()
    tb.seq_comp = h.Signal()
    tb.seq_logic = h.Signal()
    tb.comp_out = h.Signal()
    tb.dac_astate_p = h.Signal(width=16)
    tb.dac_bstate_p = h.Signal(width=16)
    tb.dac_astate_n = h.Signal(width=16)
    tb.dac_bstate_n = h.Signal(width=16)
    tb.dac_state_p = h.Signal(width=16)
    tb.dac_state_n = h.Signal(width=16)

    tb.vvdd_a = h.Vdc(params.vdd_a)(p=tb.vdd_a, n=tb.vss)
    tb.vvdd_d = h.Vdc(params.vdd_d)(p=tb.vdd_d, n=tb.vss)
    tb.vvdd_dac = h.Vdc(params.vdd_dac)(p=tb.vdd_dac, n=tb.vss)
    tb.vvin_cm = h.Vdc(params.vin_cm)(p=tb.vin_cm, n=tb.vss)
    if isinstance(params.vin_diff, h.Vdc.Params):
        tb.vvin_diff = h.Vdc(params.vin_diff)(p=tb.vin_diff, n=tb.vss)
    elif isinstance(params.vin_diff, h.Vsin.Params):
        # HDL21 leaves delay and phase optional for shared parameter use, but
        # VLSIR's primitive declares every VSIN field. Resolve their ordinary
        # zero defaults only when converting the parameters into a device.
        sine = h.Vsin.Params(
            voff=params.vin_diff.voff,
            vamp=params.vin_diff.vamp,
            freq=params.vin_diff.freq,
            td=0.0 if params.vin_diff.td is None else params.vin_diff.td,
            phase=0.0 if params.vin_diff.phase is None else params.vin_diff.phase,
        )
        tb.vvin_diff = h.Vsin(sine)(p=tb.vin_diff, n=tb.vss)
    elif isinstance(params.vin_diff, h.Vpwl.Params):
        tb.vvin_diff = h.Vpwl(params.vin_diff)(p=tb.vin_diff, n=tb.vss)
    else:
        raise TypeError(f"unsupported differential source {type(params.vin_diff).__name__}")

    # Ideal differential splitter: Vin_p = Vin_cm + Vin_diff/2 and
    # Vin_n = Vin_cm - Vin_diff/2. This works without parsing any HDL21
    # DC, sine, or PWL source representation.
    tb.evin_p = h.Vcvs(gain=0.5)(p=tb.vin_p, n=tb.vin_cm, cp=tb.vin_diff, cn=tb.vss)
    tb.evin_n = h.Vcvs(gain=-0.5)(p=tb.vin_n, n=tb.vin_cm, cp=tb.vin_diff, cn=tb.vss)

    symbol_period_s = 1.0 / float(params.symbol_rate)
    transition_s = min(float(100 * p), symbol_period_s / 20.0)
    sequences = (
        ("init", params.seq_init_pattern, float(params.seq_init_phase_delay_symbols)),
        ("samp", params.seq_samp_pattern, float(params.seq_samp_phase_delay_symbols)),
        ("comp", params.seq_comp_pattern, float(params.seq_comp_phase_delay_symbols)),
        ("logic", params.seq_logic_pattern, float(params.seq_logic_phase_delay_symbols)),
    )
    for name, pattern, phase_symbols in sequences:
        # Rotate whole-symbol delays cyclically so negative offsets and the
        # first conversion behave exactly like every later pattern repeat.
        whole_symbols = math.floor(phase_symbols)
        fractional_symbols = phase_symbols - whole_symbols
        rotation = whole_symbols % len(pattern)
        if rotation:
            pattern = pattern[-rotation:] + pattern[:-rotation]
        setattr(
            tb,
            f"vseq_{name}",
            h.Vbit(
                data=pattern,
                period=symbol_period_s,
                val0=0.0,
                val1=float(params.vdd_d.dc),
                delay=fractional_symbols * symbol_period_s,
                rise=transition_s,
                fall=transition_s,
                rptstart=1,
                rpttimes=-1,
            )(p=getattr(tb, f"seq_{name}"), n=tb.vss),
        )

    logic_bits = {
        "en_init": params.en_init,
        "en_samp_p": params.en_samp_p,
        "en_samp_n": params.en_samp_n,
        "en_comp": params.en_comp,
        "en_update": params.en_update,
        "dac_mode": params.dac_mode,
        "dac_diffcaps": params.dac_diffcaps,
    }
    for name, bit in logic_bits.items():
        signal = h.Signal(name=name)
        setattr(tb, name, signal)
        setattr(tb, f"v{name}", h.Vdc(dc=float(params.vdd_d.dc) * bit)(p=signal, n=tb.vss))
    for bus_name in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n"):
        values = getattr(params, bus_name)
        for tuple_index, bit in enumerate(values):
            bus_index = 15 - tuple_index
            setattr(
                tb,
                f"v{bus_name}_{bus_index}",
                h.Vdc(dc=float(params.vdd_d.dc) * bit)(p=getattr(tb, bus_name)[bus_index], n=tb.vss),
            )

    if view == "hdl21gen":
        tb.xadc = Adc(params.dut)(
            vin_p=tb.vin_p,
            vin_n=tb.vin_n,
            seq_init=tb.seq_init,
            seq_samp=tb.seq_samp,
            seq_comp=tb.seq_comp,
            seq_update=tb.seq_logic,
            en_init=tb.en_init,
            en_samp_p=tb.en_samp_p,
            en_samp_n=tb.en_samp_n,
            en_comp=tb.en_comp,
            en_update=tb.en_update,
            dac_mode=tb.dac_mode,
            dac_diffcaps=tb.dac_diffcaps,
            dac_astate_p=tb.dac_astate_p,
            dac_bstate_p=tb.dac_bstate_p,
            dac_astate_n=tb.dac_astate_n,
            dac_bstate_n=tb.dac_bstate_n,
            dac_state_p=tb.dac_state_p,
            dac_state_n=tb.dac_state_n,
            comp_out=tb.comp_out,
            vdd_a=tb.vdd_a,
            vss_a=tb.vss,
            vdd_d=tb.vdd_d,
            vss_d=tb.vss,
            vdd_dac=tb.vdd_dac,
            vss_dac=tb.vss,
        )
    else:
        pex_connections = {
            "vdd_a": tb.vdd_a,
            "vin_p": tb.vin_p,
            "vss_a": tb.vss,
            "dac_mode": tb.dac_mode,
            "dac_diffcaps": tb.dac_diffcaps,
            "seq_init": tb.seq_init,
            "en_init": tb.en_init,
            "seq_samp": tb.seq_samp,
            "en_samp_p": tb.en_samp_p,
            "en_samp_n": tb.en_samp_n,
            "seq_comp": tb.seq_comp,
            "en_comp": tb.en_comp,
            "seq_update": tb.seq_logic,
            "en_update": tb.en_update,
            "comp_out": tb.comp_out,
            "vin_n": tb.vin_n,
            "vdd_d": tb.vdd_d,
            "vss_d": tb.vss,
            "vdd_dac": tb.vdd_dac,
            "vss_dac": tb.vss,
        }
        for bus_name in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n"):
            for bit in range(16):
                pex_connections[f"{bus_name}_{bit}"] = getattr(tb, bus_name)[bit]
        tb.xadc = Frida65aPexAdc()(**pex_connections)
    return tb


@dataclass(frozen=True, slots=True)
class _AdcSpectreCase:
    """One prepared ADC Spectre case and its conversion metadata."""

    params: AdcTbParams
    case_dir: Path
    deck_path: Path
    raw_path: Path
    h5_path: Path
    log_path: Path
    signal_names: dict[str, str]
    circuit_checks: bool
    maximum_waveform_records: int | None


def _prepare_spectre_case(
    params: AdcTbParams,
    *,
    view: str,
    case_dir: Path,
    circuit_checks: bool,
    transient_noise: bool = True,
    maximum_waveform_records: int | None = None,
) -> _AdcSpectreCase:
    """Generate one complete ADC Spectre case without executing it."""

    validate_params(params)
    if params.conversions > 151:
        raise ValueError("ADC Spectre cases are limited to 151 conversions")
    case_dir.mkdir(parents=True, exist_ok=True)
    deck_path = case_dir / "input.scs"
    raw_path = case_dir / "result.raw"
    h5_path = case_dir / "result.h5"
    log_path = case_dir / "spectre.log"

    set_pdk("tsmc65")
    tb = AdcTb(params, view)
    h.pdk.compile(tb)
    pattern_period_s = len(params.seq_init_pattern) / float(params.symbol_rate)
    symbol_period_s = 1.0 / float(params.symbol_rate)
    # Save uniformly spaced output for unbiased average power and bounded
    # NUTASCII size. Spectre continues taking its finer internal timesteps for
    # 25 GHz transient noise; the stored grid resolves both source transitions
    # and each serializer symbol with at least sixteen samples.
    strobe_period_s = min(symbol_period_s / 16.0, 50e-12)
    tstop_s = 100e-9 if circuit_checks else params.conversions * pattern_period_s

    attrs: list[hs.SimAttr] = [
        hs.Lib(path=MODEL_LIBRARY, section="tt_lib"),
        hs.Lib(path=MODEL_LIBRARY, section="pre_simu"),
        hs.Options(name="temp", value=float(params.temperature_c)),
    ]
    if view == "frida65a":
        attrs.append(hs.Include(path=PEX_NETLIST))
        signal_names = {
            "time_s": "time",
            "vin_p_v": "xtop.vin_p",
            "vin_n_v": "xtop.vin_n",
            "seq_init_v": "xtop.seq_init",
            "seq_samp_v": "xtop.seq_samp",
            "seq_comp_v": "xtop.seq_comp",
            "seq_logic_v": "xtop.seq_logic",
            "comp_out_v": "xtop.comp_out",
            "vdac_p_v": "xtop.xadc.N_VDAC_P_XXsampswitch_p/MM0_d",
            "vdac_n_v": "xtop.xadc.N_VDAC_N_XXsampswitch_n/MM0_d",
            "clk_samp_p_v": "xtop.xadc.N_CLK_SAMP_P_XXsampswitch_p/MM0_g",
            "clk_samp_p_b_v": "xtop.xadc.N_CLK_SAMP_P_B_XXsampswitch_p/MM1_g",
            "clk_samp_n_v": "xtop.xadc.N_CLK_SAMP_N_XXsampswitch_n/MM0_g",
            "clk_samp_n_b_v": "xtop.xadc.N_CLK_SAMP_N_B_XXsampswitch_n/MM1_g",
            "clk_comp_v": "xtop.xadc.N_CLK_COMP_XXcomp/XXLATCH/MMM0_g",
            "comp_out_p_v": "xtop.xadc.N_COMP_OUT_P_XXcomp/XXI3/XXI46/MM_u2_1_d",
            "comp_out_n_v": "xtop.xadc.N_COMP_OUT_N_XXcomp/XXI3/XXI47/MM_u2_1_d",
            "dac_state_p_15_v": ("xtop.xadc.N_DAC_STATE_P_MAIN<15>_XXcapdriver_p_main/XXxor15_0/MMM_u2_1-M_u3_g"),
            "dac_state_p_8_v": "xtop.xadc.N_DAC_STATE_P_MAIN<8>_XXcapdriver_p_main/XXxor8/MMM_u2-M_u3_g",
            "dac_state_p_0_v": "xtop.xadc.N_DAC_STATE_P_MAIN<0>_XXcapdriver_p_main/XXxor0/MMM_u2-M_u3_g",
            "dac_state_n_15_v": ("xtop.xadc.N_DAC_STATE_N_MAIN<15>_XXcapdriver_n_main/XXxor15_0/MMM_u2_1-M_u3_g"),
            "dac_state_n_8_v": "xtop.xadc.N_DAC_STATE_N_MAIN<8>_XXcapdriver_n_main/XXxor8/MMM_u2-M_u3_g",
            "dac_state_n_0_v": "xtop.xadc.N_DAC_STATE_N_MAIN<0>_XXcapdriver_n_main/XXxor0/MMM_u2-M_u3_g",
            "dac_botplate_p_15_v": (
                "xtop.xadc.N_DAC_DRIVE_BOTPLATE_MAIN_P<15>_XXcapdriver_p_main/XXxor15_0/MMM_u4_1-M_u3_d"
            ),
            "dac_botplate_p_8_v": (
                "xtop.xadc.N_DAC_DRIVE_BOTPLATE_MAIN_P<8>_XXcapdriver_p_main/XXxor8/MMM_u4_1-M_u3_d"
            ),
            "dac_botplate_p_0_v": (
                "xtop.xadc.N_DAC_DRIVE_BOTPLATE_MAIN_P<0>_XXcapdriver_p_main/XXxor0/MMM_u4_1-M_u3_d"
            ),
            "dac_botplate_n_15_v": (
                "xtop.xadc.N_DAC_DRIVE_BOTPLATE_MAIN_N<15>_XXcapdriver_n_main/XXxor15_0/MMM_u4_1-M_u3_d"
            ),
            "dac_botplate_n_8_v": (
                "xtop.xadc.N_DAC_DRIVE_BOTPLATE_MAIN_N<8>_XXcapdriver_n_main/XXxor8/MMM_u4_1-M_u3_d"
            ),
            "dac_botplate_n_0_v": (
                "xtop.xadc.N_DAC_DRIVE_BOTPLATE_MAIN_N<0>_XXcapdriver_n_main/XXxor0/MMM_u4_1-M_u3_d"
            ),
            "vdd_a_i": "xtop.vvdd_a:p",
            "vdd_d_i": "xtop.vvdd_d:p",
            "vdd_dac_i": "xtop.vvdd_dac:p",
        }
    else:
        attrs.append(
            h.Literal(
                "\n".join(
                    (
                        "simulator lang=spice",
                        *(f'.include "{path}"' for path in (*STANDARD_CELL_SPICE, DIGITAL_SPICE)),
                        "simulator lang=spectre",
                    )
                )
            )
        )
        signal_names = {
            "time_s": "time",
            "vin_p_v": "xtop.vin_p",
            "vin_n_v": "xtop.vin_n",
            "seq_init_v": "xtop.seq_init",
            "seq_samp_v": "xtop.seq_samp",
            "seq_comp_v": "xtop.seq_comp",
            "seq_logic_v": "xtop.seq_logic",
            "comp_out_v": "xtop.comp_out",
            "vdac_p_v": "xtop.xadc.cdac_top_p",
            "vdac_n_v": "xtop.xadc.cdac_top_n",
            "clk_samp_p_v": "xtop.xadc.clk_samp_p",
            "clk_samp_p_b_v": "xtop.xadc.clk_samp_p_b",
            "clk_samp_n_v": "xtop.xadc.clk_samp_n",
            "clk_samp_n_b_v": "xtop.xadc.clk_samp_n_b",
            "clk_comp_v": "xtop.xadc.clk_comp",
            "comp_out_p_v": "xtop.xadc.comp_out_p",
            "comp_out_n_v": "xtop.xadc.comp_out_n",
            "dac_state_p_15_v": "xtop.xadc.dac_state_p_15",
            "dac_state_p_8_v": "xtop.xadc.dac_state_p_8",
            "dac_state_p_0_v": "xtop.xadc.dac_state_p_0",
            "dac_state_n_15_v": "xtop.xadc.dac_state_n_15",
            "dac_state_n_8_v": "xtop.xadc.dac_state_n_8",
            "dac_state_n_0_v": "xtop.xadc.dac_state_n_0",
            "dac_botplate_p_15_v": "xtop.xadc.xcdac_p.bot_15",
            "dac_botplate_p_8_v": "xtop.xadc.xcdac_p.bot_8",
            "dac_botplate_p_0_v": "xtop.xadc.xcdac_p.bot_0",
            "dac_botplate_n_15_v": "xtop.xadc.xcdac_n.bot_15",
            "dac_botplate_n_8_v": "xtop.xadc.xcdac_n.bot_8",
            "dac_botplate_n_0_v": "xtop.xadc.xcdac_n.bot_0",
            "vdd_a_i": "xtop.vvdd_a:p",
            "vdd_d_i": "xtop.vvdd_d:p",
            "vdd_dac_i": "xtop.vvdd_dac:p",
        }

    save_names = [
        re.sub(r"([/<>-])", r"\\\1", raw_name)
        for canonical_name, raw_name in signal_names.items()
        if canonical_name != "time_s"
    ]
    check_deck_path = case_dir / "checks.scs"
    if circuit_checks:
        check_attrs = [
            *attrs,
            h.Literal("saveOptions options save=selected\nsave xtop.vin_p"),
            h.Literal(
                """check_caps static_capacitor type=distr
check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top gate2power=on gate2ground=on
check_highz static_highz node=[*] fanout=gate_has_driver_no_moscap
check_dcpath static_dcpath net=[xtop.vdd_a xtop.vdd_d xtop.vdd_dac 0]
check_rcdelay static_rcdelay node=[*] maxnrise=20 maxnfall=20
check_stack static_stack count=3
check_topology static_topology node=[*] pin2gnd=on
check_nodecap dyn_nodecap node=[xtop.vin_p xtop.vin_n xtop.comp_out] time=[50n 99n]
check_setuphold dyn_setuphold node=[xtop.comp_out] ref_node=xtop.seq_logic setup_time=50p hold_time=50p
check_power dyn_subcktpwr inst=[xtop.xadc] depth=1 port=[*] power=on"""
            ),
            h.Literal(f"tran tran stop={tstop_s:.12g} strobeperiod={strobe_period_s:.12g} strobeoutput=strobeonly"),
        ]
        # Spectre circuit-check reports require a PSF-style raw directory,
        # whereas NUTASCII uses one plain file. Keep their runs separate to
        # avoid Spectre treating the same output path as both kinds.
        write_spectre_input(hs.Sim(tb=tb, attrs=check_attrs), check_deck_path)
    attrs.append(h.Literal("saveOptions options save=selected rawfmt=nutascii"))
    attrs.append(h.Literal("save \\\n    " + " \\\n    ".join(save_names)))
    tran = f"tran tran stop={tstop_s:.12g} strobeperiod={strobe_period_s:.12g} strobeoutput=strobeonly"
    if not circuit_checks and transient_noise:
        # A finite transient cannot represent noise below 1 / tstop. Spectre
        # silently raises smaller values to this limit, so record the actual
        # simulated band explicitly in every generated production deck.
        tran += f" noisefmin={1.0 / tstop_s:.12g} noisefmax=25G noiseseed=1"
    attrs.append(h.Literal(tran))
    write_spectre_input(hs.Sim(tb=tb, attrs=attrs), deck_path)
    return _AdcSpectreCase(
        params=params,
        case_dir=case_dir,
        deck_path=deck_path,
        raw_path=raw_path,
        h5_path=h5_path,
        log_path=log_path,
        signal_names=signal_names,
        circuit_checks=circuit_checks,
        maximum_waveform_records=maximum_waveform_records,
    )


def _execute_spectre_case(case: _AdcSpectreCase) -> Path:
    """Execute and convert one already prepared ADC Spectre case."""

    if shutil.which("spectre") is None:
        raise RuntimeError("spectre is not on PATH; source design/spice/workspace.sh before running ADC simulations")
    case_dir = case.case_dir
    raw_path = case.raw_path
    if raw_path.is_dir():
        shutil.rmtree(raw_path)
    elif raw_path.exists():
        raw_path.unlink()
    if case.circuit_checks:
        check_deck_path = case_dir / "checks.scs"
        checks_path = case_dir / "checks"
        if checks_path.is_dir():
            shutil.rmtree(checks_path)
        elif checks_path.exists():
            checks_path.unlink()
        subprocess.run(
            [
                "spectre",
                check_deck_path.name,
                "+preset=mx",
                f"+mt={SPECTRE_THREADS_PER_SIMULATION}",
                "+lqtimeout",
                "3600",
                "+escchars",
                "-raw",
                checks_path.name,
                "+log",
                "checks.log",
                "-ahdllint=warn",
                "-ahdllint_log",
                "ahdllint.log",
            ],
            cwd=case_dir,
            check=True,
        )
    command = [
        "spectre",
        case.deck_path.name,
        "+preset=mx",
        f"+mt={SPECTRE_THREADS_PER_SIMULATION}",
        "+lqtimeout",
        "3600",
        "+escchars",
        "-raw",
        raw_path.name,
        "+log",
        case.log_path.name,
    ]
    started = time.perf_counter()
    subprocess.run(command, cwd=case_dir, check=True)
    convert_spectre_adc_raw_to_h5(
        raw_path,
        case.h5_path,
        params=case.params,
        signal_names=case.signal_names,
        maximum_waveform_records=case.maximum_waveform_records,
    )
    print(f"{case_dir.name}: simulated and converted in {time.perf_counter() - started:.1f} s")
    return case.h5_path


def _noise_vs_rate_cases() -> tuple[tuple[str, AdcTbParams], ...]:
    """Build the reviewed fixed-input ADC noise cases."""

    alternating = tuple(int(bit) for bit in "0101010101010101")
    template = AdcTbParams()
    cases = []
    for rate_msps in (10, 6, 2):
        cases.append(
            (
                f"{rate_msps}msps_cm700mv_dc50mv",
                AdcTbParams(
                    symbol_rate=convert_sample_rate_to_baud(template, rate_msps * 1e6),
                    conversions=100,
                    vin_diff=h.Vdc.Params(dc=0.05),
                    seq_logic_phase_delay_symbols=2.0,
                    dac_astate_p=alternating,
                    dac_bstate_p=(0,) * 16,
                    dac_astate_n=alternating,
                    dac_bstate_n=(0,) * 16,
                ),
            )
        )
    return tuple(cases)


def _transfer_curve_cases() -> tuple[tuple[str, AdcTbParams], ...]:
    """Build one settled 10 mV-step transfer sweep."""

    vin_diff_values_v = tuple(step / 100.0 for step in range(-75, 76))
    template = AdcTbParams()
    symbol_rate = convert_sample_rate_to_baud(template, 10.0e6)
    conversion_period_s = len(template.seq_init_pattern) / symbol_rate
    transition_s = 100.0e-12
    points = [(0.0, vin_diff_values_v[0])]
    for index, vin_diff_v in enumerate(vin_diff_values_v[1:], start=1):
        boundary_s = index * conversion_period_s
        points.extend(
            (
                (boundary_s - transition_s, vin_diff_values_v[index - 1]),
                (boundary_s, vin_diff_v),
            )
        )
    points.append((len(vin_diff_values_v) * conversion_period_s, vin_diff_values_v[-1]))
    wave = " ".join(f"{time_s:.12g} {value_v:.12g}" for time_s, value_v in points)
    params = AdcTbParams(
        campaign="adc_transfer",
        symbol_rate=symbol_rate,
        conversions=len(vin_diff_values_v),
        vin_cm=h.Vdc.Params(dc=0.7),
        vin_diff=h.Vpwl.Params(wave=wave),
        seq_logic_phase_delay_symbols=2.0,
    )
    return (("10msps_cm700mv_transfer", params),)


def _smoke_params() -> AdcTbParams:
    """Reduce the 10 MS/s case to one immediately active conversion."""

    params = next(params for name, params in _noise_vs_rate_cases() if name == "10msps_cm700mv_dc50mv")
    first_active = min(
        index
        for index in range(len(params.seq_init_pattern))
        if any(
            pattern[index] == "1"
            for pattern in (
                params.seq_init_pattern,
                params.seq_samp_pattern,
                params.seq_comp_pattern,
                params.seq_logic_pattern,
            )
        )
    )
    return dataclasses.replace(
        params,
        conversions=1,
        seq_init_pattern=params.seq_init_pattern[first_active:] + params.seq_init_pattern[:first_active],
        seq_samp_pattern=params.seq_samp_pattern[first_active:] + params.seq_samp_pattern[:first_active],
        seq_comp_pattern=params.seq_comp_pattern[first_active:] + params.seq_comp_pattern[:first_active],
        seq_logic_pattern=params.seq_logic_pattern[first_active:] + params.seq_logic_pattern[:first_active],
    )


def _run_campaign(
    run_dir: Path,
    *,
    view: str,
    cases: Sequence[tuple[str, AdcTbParams]],
    execute: bool,
    circuit_checks: bool = False,
    transient_noise: bool = True,
    maximum_waveform_records: int | None = None,
) -> Path:
    """Prepare one complete ADC run and optionally execute its cases."""

    prepared = tuple(
        _prepare_spectre_case(
            params,
            view=view,
            case_dir=run_dir / name,
            circuit_checks=circuit_checks,
            transient_noise=transient_noise,
            maximum_waveform_records=maximum_waveform_records,
        )
        for name, params in cases
    )
    if not execute:
        print(f"Prepared {len(prepared)} ADC netlists beneath {run_dir}")
        return run_dir
    failures = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SIMULATIONS) as executor:
        futures = {executor.submit(_execute_spectre_case, case): case for case in prepared}
        for future in as_completed(futures):
            case = futures[future]
            try:
                future.result()
            except (OSError, RuntimeError, TypeError, ValueError, subprocess.CalledProcessError) as error:
                failures.append((case.case_dir.name, repr(error)))
    if failures:
        raise RuntimeError(f"{len(failures)} ADC simulations failed: {failures}")
    print(f"Completed {len(prepared)} ADC simulations beneath {run_dir}")
    return run_dir


def frida65a_noise_vs_rate_netlists() -> Path:
    """Generate the extracted ADC fixed-input noise decks without running them."""

    # TODO: Change every target in this module to build/sim_adc/<short-datetime>.
    run_dir = BASE_PATH / "build/sim/adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(run_dir, view="frida65a", cases=_noise_vs_rate_cases(), execute=False)


def frida65a_noise_smoke() -> Path:
    """Run one short extracted-ADC case with Spectre circuit checks."""

    run_dir = BASE_PATH / "build/sim/adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(
        run_dir,
        view="frida65a",
        cases=(("10msps_cm700mv_dc50mv_smoke", _smoke_params()),),
        execute=True,
        circuit_checks=True,
    )


def frida65a_noise_vs_rate() -> Path:
    """Run the extracted ADC fixed-input noise sweep."""

    run_dir = BASE_PATH / "build/sim/adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(
        run_dir,
        view="frida65a",
        cases=_noise_vs_rate_cases(),
        execute=True,
        maximum_waveform_records=3,
    )


def frida65a_transfer_curve_netlist() -> Path:
    """Generate the extracted ADC transfer deck without running it."""

    run_dir = BASE_PATH / "build/sim/adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(
        run_dir,
        view="frida65a",
        cases=_transfer_curve_cases(),
        execute=False,
        transient_noise=False,
        maximum_waveform_records=3,
    )


def frida65a_transfer_curve() -> Path:
    """Run the extracted ADC full transfer sweep."""

    run_dir = BASE_PATH / "build/sim/adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(
        run_dir,
        view="frida65a",
        cases=_transfer_curve_cases(),
        execute=True,
        transient_noise=False,
        maximum_waveform_records=3,
    )


def hdl21gen_noise_vs_rate_netlists() -> Path:
    """Generate the schematic ADC fixed-input noise decks without running them."""

    run_dir = BASE_PATH / "build/sim/adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(run_dir, view="hdl21gen", cases=_noise_vs_rate_cases(), execute=False)


def hdl21gen_noise_smoke() -> Path:
    """Run one short schematic-ADC case with Spectre circuit checks."""

    run_dir = BASE_PATH / "build/sim/adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(
        run_dir,
        view="hdl21gen",
        cases=(("10msps_cm700mv_dc50mv_smoke", _smoke_params()),),
        execute=True,
        circuit_checks=True,
    )


def hdl21gen_noise_vs_rate() -> Path:
    """Run the schematic ADC fixed-input noise sweep."""

    run_dir = BASE_PATH / "build/sim/adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(
        run_dir,
        view="hdl21gen",
        cases=_noise_vs_rate_cases(),
        execute=True,
        maximum_waveform_records=3,
    )


def hdl21gen_transfer_curve_netlist() -> Path:
    """Generate the schematic ADC transfer deck without running it."""

    run_dir = BASE_PATH / "build/sim/adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(
        run_dir,
        view="hdl21gen",
        cases=_transfer_curve_cases(),
        execute=False,
        transient_noise=False,
        maximum_waveform_records=3,
    )


def hdl21gen_transfer_curve() -> Path:
    """Run the schematic ADC full transfer sweep."""

    run_dir = BASE_PATH / "build/sim/adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(
        run_dir,
        view="hdl21gen",
        cases=_transfer_curve_cases(),
        execute=True,
        transient_noise=False,
        maximum_waveform_records=3,
    )


TARGETS: dict[str, Callable[[], Path]] = {
    target.__name__: target
    for target in (
        frida65a_noise_vs_rate_netlists,
        frida65a_noise_smoke,
        frida65a_noise_vs_rate,
        frida65a_transfer_curve_netlist,
        frida65a_transfer_curve,
        hdl21gen_noise_vs_rate_netlists,
        hdl21gen_noise_smoke,
        hdl21gen_noise_vs_rate,
        hdl21gen_transfer_curve_netlist,
        hdl21gen_transfer_curve,
    )
}


def main() -> None:
    """Run one explicitly named ADC simulation campaign."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(TARGETS))
    args = parser.parse_args()
    if args.target is None:
        print("Available ADC simulation targets:")
        for target in sorted(TARGETS):
            print(f"  {target}")
        return
    run_dir = TARGETS[args.target]()
    print(f"Simulation output: {run_dir}")


if __name__ == "__main__":
    main()
