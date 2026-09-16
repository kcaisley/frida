"""ADC testbench and named Spectre simulation targets."""

import argparse
import hashlib
import json
import math
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime
from itertools import product
from multiprocessing import get_context
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import G, m, p
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.adc.ip import adc_pex, adc_port_aliases, frida1_net_aliases, frida2_net_aliases
from flow.adc.sequences import BASELINE, FIXED_INPUT_SEQUENCES, ORIGINAL
from flow.adc.subckt import Adc, AdcNets, AdcParams, is_valid_adc_params
from flow.caparray import CapArrayConfig, RedunStrat, get_caparray_weights
from flow.circuit.ports import testbench_from_ports
from flow.comp.subckt import CompNets


@h.paramclass
class AdcTbParams:
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
        dtype=AdcParams,
        desc="ADC DUT parameters",
        default=AdcParams(
            cdac=CapArrayConfig(n_dac=11, n_extra=5, redun_strat=RedunStrat.SUBRDX2_OVLY),
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
    seq_init_pattern = h.Param(dtype=str, desc="INIT sequence", default=BASELINE.init)
    seq_samp_pattern = h.Param(dtype=str, desc="SAMP sequence", default=BASELINE.samp)
    seq_comp_pattern = h.Param(dtype=str, desc="COMP sequence", default=BASELINE.comp)
    seq_logic_pattern = h.Param(dtype=str, desc="LOGIC sequence", default=BASELINE.logic)


def is_valid_adc_tb_params(params: AdcTbParams) -> bool:
    """Check DUT, view, supplies, sequencer rows, and sweep length before generation.

    PEX file existence, cell contents, and signoff require the selected file and
    are checked by the caller. This predicate only examines parameter values.
    """
    if not is_valid_adc_params(params.dut):
        return False
    if not math.isfinite(params.waveform_sample_interval_s) or params.waveform_sample_interval_s <= 0:
        return False
    if params.view not in {"frida1", "frida2", "hdl21gen"}:
        return False
    if params.view == "frida2" and params.pex_cell != "adc_12b_17step":
        return False
    if params.view == "hdl21gen" and params.pex_cell:
        return False
    if params.conversions <= 0:
        return False
    try:
        symbol_rate = float(params.symbol_rate)
        if not math.isfinite(symbol_rate) or symbol_rate <= 0.0:
            return False
        supplies = [net.name for net in AdcNets.signals.values() if net.usage == h.Usage.POWER]
        for name in (*supplies, "vin_cm"):
            source = getattr(params, name)
            if source.dc is None or not math.isfinite(float(source.dc)):
                return False
    except (TypeError, ValueError, OverflowError):
        # These sources must be numeric; unresolved HDL21 literals cannot set timing or levels.
        return False
    supply_parasitics = (
        params.supply_series_resistance_ohm,
        params.supply_series_inductance_h,
        params.supply_decoupling_capacitance_f,
    )
    if any(not math.isfinite(value) or value < 0.0 for value in supply_parasitics):
        return False
    if any(supply_parasitics) and not all(value > 0.0 for value in supply_parasitics):
        return False
    if len(params.supply_noise_rms_v) != 3 or any(
        not math.isfinite(value) or value < 0.0 for value in params.supply_noise_rms_v
    ):
        return False
    if not math.isfinite(params.supply_noise_bandwidth_hz) or params.supply_noise_bandwidth_hz <= 0.0:
        return False
    for net in AdcNets.signals.values():
        if net.direction != h.PortDir.INPUT or net.usage != h.Usage.SIGNAL or net in (AdcNets.vin_p, AdcNets.vin_n):
            continue
        value = getattr(params, net.name)
        if net.width == 1:
            if value not in (0, 1):
                return False
        elif len(value) != net.width or any(bit not in (0, 1) for bit in value):
            return False
    patterns = tuple(
        getattr(params, f"{net.name}_pattern")
        for net in AdcNets.signals.values()
        if net.vis == h.Visibility.PORT and net.usage == h.Usage.CLOCK
    )
    if any(not pattern or set(pattern) - {"0", "1"} for pattern in patterns):
        return False
    if len({len(pattern) for pattern in patterns}) != 1 or len(patterns[0]) % 8:
        return False
    if isinstance(params.vin_diff, hs.LinearSweep):
        try:
            start, stop, step = (
                float(value) for value in (params.vin_diff.start, params.vin_diff.stop, params.vin_diff.step)
            )
        except (TypeError, ValueError, OverflowError):
            return False
        if not all(math.isfinite(value) for value in (start, stop, step)) or step == 0.0:
            return False
        if start != stop and (stop > start) != (step > 0):
            return False
        # Inclusive staircase endpoints must contain exactly one level per conversion.
        if not math.isclose((stop - start) / step, params.conversions - 1, rel_tol=0.0, abs_tol=1e-9):
            return False
        if len(patterns[0]) / symbol_rate <= float(100 * p):
            return False
    return True


# Generated DUTs are compiled in place and must not survive in a cached testbench.
def AdcTb(params: AdcTbParams, *, pex_netlist: Path | None = None) -> h.Module:
    """Generate a complete ADC testbench for the selected DUT view."""

    if not is_valid_adc_tb_params(params):
        raise ValueError(f"Invalid ADC testbench params: {params}")
    if (params.view != "hdl21gen") != (pex_netlist is not None):
        raise ValueError("extracted views require a PEX input; HDL21 must not have one")

    if pex_netlist is None:
        ports = {name: net for name, net in AdcNets.signals.items() if net.vis == h.Visibility.PORT}
    else:
        aliases = adc_port_aliases(params.view)
        selected = {net.parent if isinstance(net, h.Slice) else net for net in aliases}
        ports = {name: net for name, net in AdcNets.signals.items() if net in selected}
    tb, connections = testbench_from_ports(f"AdcTb_{params.view}", ports)
    tb.vin_cm, tb.vin_diff = h.Signals(2)
    symbol_period_s = 1.0 / float(params.symbol_rate)
    pattern_period_s = len(params.seq_init_pattern) * symbol_period_s
    transition_s = min(float(100 * p), symbol_period_s / 20.0)
    rlc_enabled = params.supply_series_resistance_ohm > 0.0
    supplies = (net for net in AdcNets.signals.values() if net.usage == h.Usage.POWER)
    for rail, noise_rms_v in zip(supplies, params.supply_noise_rms_v, strict=True):
        rail_name = rail.name
        source_params = getattr(params, rail_name)
        rail = connections[rail_name]
        source_node = h.Signal(name=f"{rail_name}_source") if rlc_enabled else rail
        if rlc_enabled:
            series_node = h.Signal(name=f"{rail_name}_series")
            setattr(tb, f"{rail_name}_source", source_node)
            setattr(tb, f"{rail_name}_series", series_node)
            setattr(
                tb,
                f"r{rail_name}",
                h.Resistor(r=params.supply_series_resistance_ohm)(p=source_node, n=series_node),
            )
            setattr(
                tb,
                f"l{rail_name}",
                h.Inductor(l=params.supply_series_inductance_h)(p=series_node, n=rail),
            )
            setattr(
                tb,
                f"c{rail_name}",
                h.Capacitor(c=params.supply_decoupling_capacitance_f)(p=rail, n=tb.vss),
            )
        if noise_rms_v > 0.0:
            noise_density_v2_per_hz = noise_rms_v**2 / params.supply_noise_bandwidth_hz
            tb.literals.append(
                h.Literal(
                    f"v{rail_name} ({source_node.name} {tb.vss.name}) vsource dc={float(source_params.dc):.12g} "
                    f"noisevec=[0 {noise_density_v2_per_hz:.12g} "
                    f"{params.supply_noise_bandwidth_hz:.12g} {noise_density_v2_per_hz:.12g}]"
                )
            )
        else:
            setattr(tb, f"v{rail_name}", h.Vdc(source_params)(p=source_node, n=tb.vss))
    tb.vvin_cm = h.Vdc(params.vin_cm)(p=tb.vin_cm, n=tb.vss)
    if isinstance(params.vin_diff, h.Vdc.Params):
        tb.vvin_diff = h.Vdc(params.vin_diff)(p=tb.vin_diff, n=tb.vss)
    elif isinstance(params.vin_diff, h.Vsin.Params):
        tb.vvin_diff = h.Vsin(
            voff=params.vin_diff.voff,
            vamp=params.vin_diff.vamp,
            freq=params.vin_diff.freq,
            td=0.0 if params.vin_diff.td is None else params.vin_diff.td,
            phase=0.0 if params.vin_diff.phase is None else params.vin_diff.phase,
        )(p=tb.vin_diff, n=tb.vss)
    elif isinstance(params.vin_diff, hs.LinearSweep):
        wave = h.Pwl.staircase(
            start=params.vin_diff.start,
            stop=params.vin_diff.stop,
            step=params.vin_diff.step,
            dwell=pattern_period_s,
            transition=100 * p,
            transition_at="end",
        )
        tb.vvin_diff = h.Vpwl(wave=wave)(p=tb.vin_diff, n=tb.vss)
    elif isinstance(params.vin_diff, h.Vpwl.Params):
        tb.vvin_diff = h.Vpwl(params.vin_diff)(p=tb.vin_diff, n=tb.vss)
    else:
        raise TypeError(f"unsupported ADC differential source {type(params.vin_diff).__name__}")
    tb.evin_p = h.Vcvs(gain=0.5)(p=tb.vin_p, n=tb.vin_cm, cp=tb.vin_diff, cn=tb.vss)
    tb.evin_n = h.Vcvs(gain=-0.5)(p=tb.vin_n, n=tb.vin_cm, cp=tb.vin_diff, cn=tb.vss)

    for canonical in AdcNets.signals.values():
        if canonical.vis != h.Visibility.PORT or canonical.usage != h.Usage.CLOCK:
            continue
        net = connections[canonical.name]
        pattern = getattr(params, f"{canonical.name}_pattern")
        setattr(
            tb,
            f"v{net.name}",
            h.Vbit(
                data=pattern,
                period=symbol_period_s,
                val0=0.0,
                val1=float(params.vdd_d.dc),
                delay=0.0,
                rise=transition_s,
                fall=transition_s,
                rptstart=1,
                rpttimes=-1,
            )(p=net, n=tb.vss),
        )
    for net in AdcNets.signals.values():
        if net.direction != h.PortDir.INPUT or net.usage != h.Usage.SIGNAL or net in (AdcNets.vin_p, AdcNets.vin_n):
            continue
        value = getattr(params, net.name)
        if net.width == 1:
            tb.add(h.Vdc(dc=float(params.vdd_d.dc) * value)(p=connections[net.name], n=tb.vss), name=f"v{net.name}")
        else:
            for stage, state in enumerate(value):
                tb.add(
                    h.Vdc(dc=float(params.vdd_d.dc) * state)(p=connections[net.name][stage], n=tb.vss),
                    name=f"v{net.name}_{stage}",
                )

    if pex_netlist is None:
        tb.xadc = Adc(params.dut)(**connections)
    else:
        module = adc_pex(pex_netlist, params.pex_cell or "adc_1layer_radix17")
        pex_connections = {
            physical: connections[net.parent.name][net.index] if isinstance(net, h.Slice) else connections[net.name]
            for net, physical in aliases.items()
        }
        if set(pex_connections) != set(module.ports):
            raise ValueError(
                f"External interface {module.name}: missing {set(pex_connections) - set(module.ports)}, "
                f"unknown {set(module.ports) - set(pex_connections)}"
            )
        tb.xadc = module()(**pex_connections)
    return tb


def adc_signal_names(tb: h.Module, view: str, *, save_supply_voltages: bool = False) -> dict[str, str]:
    """Resolve canonical observations once for both Save and raw conversion."""
    if view not in {"hdl21gen", "frida1", "frida2"}:
        raise ValueError(f"Unsupported ADC view {view!r}")
    aliases = frida1_net_aliases() if view == "frida1" else frida2_net_aliases() if view == "frida2" else {}
    names = {"time": "time"}
    for schema, prefix in ((AdcNets, ""), (CompNets, "comp.")):
        for net in schema.signals.values():
            if not net.props.get("save"):
                continue
            testbench_net = schema is AdcNets and net.vis == h.Visibility.PORT and net.width == 1
            path = "xtop" if testbench_net else f"xtop.{tb.xadc.name}"
            if view == "hdl21gen" or testbench_net:
                scope = tb if testbench_net else tb.xadc.of
                if schema is CompNets:
                    path += f".{scope.xcomp.name}"
                    scope = scope.xcomp.of
                actual = scope.namespace[net.name]
                if actual.width != net.width:
                    raise ValueError(f"Generated width differs from canonical net {net.name}")
            for stage in range(net.width):
                canonical = net if net.width == 1 else net[stage]
                if view != "hdl21gen" and not testbench_net:
                    raw = f"{path}.{aliases[canonical]}"
                else:
                    raw = f"{path}.{actual.name}" + (f"_{stage}" if net.width > 1 else "")
                label = f"{prefix}{net.name}" + (f"[{stage}]" if net.width > 1 else "")
                if raw in names or label in names.values():
                    raise ValueError(f"Duplicate probe binding: {raw} -> {label}")
                names[raw] = label
    for net in AdcNets.signals.values():
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
            if save_supply_voltages:
                names[f"xtop.{tb.namespace[net.name].name}"] = net.name
    return names


def _run_adc_sim(
    run_dir: Path,
    params: AdcTbParams,
    *,
    pex_netlist: Path | None = None,
    noise: bool = False,
    check: bool = False,
    expected_disconnect: bool = False,
) -> tuple[Path, dict[str, str]]:
    """Execute one configured ADC experiment, not an entire campaign.

    Targets define the experiment: they construct complete testbench parameters,
    select explicit PEX inputs and noise settings, and submit independent cases
    concurrently. This executor owns the shared mechanics: generate/compile the
    testbench, validate extracted interfaces, build the Spectre simulation, run
    short diagnostics or the full simulation, and return the raw path and probe bindings.
    Flavor/rate sweeps and campaign selection belong in the named targets below,
    not in additional flavor-specific wrappers.
    """

    if not is_valid_adc_tb_params(params):
        raise ValueError(f"Invalid ADC testbench params: {params}")

    from pdk import tsmc65
    from pdk.tsmc65 import site

    # Fixed budgets paired with the target pools: four x six or three x eight.
    spectre_threads = 6 if params.view == "frida1" else 8
    if (params.view != "hdl21gen") != (pex_netlist is not None):
        raise ValueError("extracted views require a PEX input; HDL21 must not have one")
    metadata = {
        "target": run_dir.name,
        "view": params.view,
        "conversions": params.conversions,
        "symbol_rate_hz": float(params.symbol_rate),
        "weights": get_caparray_weights(params.dut.cdac),
        "spectre_threads": spectre_threads,
        "check": check,
        "transient_noise": noise and not check,
        "expected_historical_disconnect": expected_disconnect,
        "sequencer": {
            net.name.removeprefix("seq_"): {"pattern": getattr(params, f"{net.name}_pattern")}
            for net in AdcNets.signals.values()
            if net.vis == h.Visibility.PORT and net.usage == h.Usage.CLOCK
        },
    }
    if pex_netlist is not None:
        if not pex_netlist.is_file() or not pex_netlist.stat().st_size:
            raise FileNotFoundError(pex_netlist)
        from pdk.tsmc65.ringfmom import validate_extracted_netlist

        validate_extracted_netlist(pex_netlist.read_text())
        if params.pex_cell == "adc_12b_17step":
            summary_path = pex_netlist.parent / "signoff_summary.json"
            summary = json.loads(summary_path.read_text())
            known_disconnect = (
                expected_disconnect
                and params.view == "frida1"
                and pex_netlist.stem in ("frida1_2layer_radix17.pex", "frida1_2layer_radix20.pex")
                and summary.get("warnings") == ["expected LVS mismatch: disconnected historical MOM layer"]
            )
            if summary["lvs_correct"] is not True and not known_disconnect:
                raise ValueError(f"unaccepted LVS result in {summary_path}")
            if Path(summary["pex_netlist"]).name != pex_netlist.name:
                raise ValueError(f"PEX input differs from {summary_path}")
            if (
                "pex_sha256" in summary
                and summary["pex_sha256"] != hashlib.sha256(pex_netlist.read_bytes()).hexdigest()
            ):
                raise ValueError(f"PEX content differs from signed-off input in {summary_path}")
        metadata.update(
            pex_netlist=str(pex_netlist),
            pex_sha256=hashlib.sha256(pex_netlist.read_bytes()).hexdigest(),
        )

    h.pdk.set_default(tsmc65.pdk_logic)
    tb = AdcTb(params, pex_netlist=pex_netlist)
    h.pdk.compile(tb)
    signal_names = adc_signal_names(tb, params.view, save_supply_voltages=bool(params.supply_series_resistance_ohm))
    if pex_netlist is not None:
        text = pex_netlist.read_text().replace("\\\n", " ")
        nodes = set(text.replace("\\", "").split())
        missing = [name for name in signal_names if name.startswith("xtop.xadc.") and name[10:] not in nodes]
        if missing:
            raise ValueError(f"PEX waveform nodes missing: {missing}")

    save_targets = [re.sub(r"([/<>-])", r"\\\1", raw_name) for raw_name in signal_names if raw_name != "time"]
    attrs = [
        site.install.include(h.pdk.Corner.TYP),
        site.install.include_pre_simulation(),
    ]
    if pex_netlist is not None:
        attrs.append(hs.Include(path=pex_netlist))
    else:
        driver_cells = site.install.include_stdcell()
        attrs.append(driver_cells)
        # The digital netlist also needs the regular-Vth library; do not
        # include the driver library twice when it is shared with digital.
        standard_cells = (
            *(path for path in site.STANDARD_CELL_SPICE_NETLISTS if path != driver_cells.path),
            Path(__file__).resolve().parents[2] / "design/spice/adc_digital.sp",
        )
        attrs.append(
            h.Literal(
                "\n".join(
                    (
                        "simulator lang=spice",
                        *(f'.include "{path}"' for path in standard_cells),
                        "simulator lang=spectre",
                    )
                )
            )
        )
    attrs.extend(
        (hs.Options(name="temp", value=25.0), hs.Options(name="save", value="selected"), hs.Save(save_targets))
    )
    tstop_s = 100e-9 if check else params.conversions * len(params.seq_init_pattern) / float(params.symbol_rate)
    if not check:
        first_comp_symbol = params.seq_comp_pattern.index("01") + 1
        # Save the next B0 edge plus a symbol of margin, without completing
        # or decoding an extra conversion. The original noise bandwidth stays fixed.
        tstop_s += (first_comp_symbol + 1) / float(params.symbol_rate)
    metadata["final_decision_time_reference"] = "next_init_seq_logic_rising_threshold"
    tran_options = {
        "strobeperiod": params.waveform_sample_interval_s,
        "maxstep": params.waveform_sample_interval_s,
        "strobeoutput": "strobeonly",
    }
    # Preserve the supply experiment's frequency settings without silently
    # enabling device transient noise, which its previous runner did not enable.
    if not check and (noise or any(params.supply_noise_rms_v) or params.supply_series_resistance_ohm):
        tran_options.update(
            noisefmin=1.0 / (params.conversions * len(params.seq_init_pattern) / float(params.symbol_rate)),
            noisefmax="25G",
            noiseseed=1,
        )
    if check:
        attrs.append(
            h.Literal(
                "check_caps static_capacitor type=distr\n"
                "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top "
                "gate2power=on gate2ground=on\n"
                "check_highz static_highz node=[*] fanout=gate_has_driver_no_moscap\n"
                "check_dcpath static_dcpath net=[xtop.vdd_a xtop.vdd_d xtop.vdd_dac 0]\n"
                "check_rcdelay static_rcdelay node=[*] maxnrise=20 maxnfall=20\n"
                "check_stack static_stack count=3\n"
                "check_topology static_topology node=[*] pin2gnd=on\n"
                "check_nodecap dyn_nodecap node=[xtop.vin_p xtop.vin_n xtop.comp_out] time=[50n 99n]\n"
                "check_setuphold dyn_setuphold node=[xtop.comp_out] ref_node=xtop.seq_logic "
                "setup_time=50p hold_time=50p\n"
                "check_power dyn_subcktpwr inst=[xtop.xadc] depth=1 port=[*] power=on"
            )
        )
    attrs.append(hs.Tran(tstop=tstop_s, name="tran", noise=noise and not check, options=tran_options))
    simulation = hs.Sim(tb=tb, attrs=attrs)
    options = SimOptions(
        simulator=SupportedSimulators.SPECTRE,
        fmt=ResultFormat.NONE if check else ResultFormat.SIM_DATA,
        rundir=run_dir,
        simulator_args=(
            "+preset=mx",
            f"+mt={spectre_threads}",
            "+lqtimeout",
            "3600",
            "+escchars",
            "+log",
            "spectre.log",
            *(("-ahdllint=warn", "-ahdllint_log", "ahdllint.log") if check else ()),
        ),
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "input.json").write_text(json.dumps(metadata, indent=2) + "\n")
    simulation.run(options)
    return run_dir / "netlist.raw", signal_names


def hdl21_sample_rate(run_dir: Path, *, check: bool = False) -> Path:
    """Run the generated ADC at 2, 6, and 10 MS/s with 50 mV input."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient

    with ProcessPoolExecutor(max_workers=3, mp_context=get_context("spawn")) as executor:
        futures = []
        for rate, symbol_rate in ((2, 0.32 * G), (6, 0.96 * G), (10, 1.6 * G)):
            params = AdcTbParams(
                view="hdl21gen",
                symbol_rate=symbol_rate,
                conversions=1 if check else 100,
                vin_diff=h.Vdc.Params(dc=0.05),
                **ORIGINAL.as_tb_fields(),
            )
            futures.append(
                (
                    executor.submit(
                        _run_adc_sim,
                        run_dir / f"{float(symbol_rate) / 1e6:g}mbd",
                        params,
                        noise=True,
                        check=check,
                    ),
                    params,
                )
            )
        for future, params in futures:
            raw_path, signal_names = future.result()
            if not check:
                measurement = convert_raw_adc_to_measurement(
                    read_raw_transient(raw_path),
                    params=params,
                    raw_path=raw_path,
                    signal_names=signal_names,
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
    return run_dir


def hdl21_transfer_curve(run_dir: Path, *, check: bool = False) -> Path:
    """Run the generated ADC from -750 mV to +750 mV in 10 mV steps."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient

    params = AdcTbParams(
        view="hdl21gen",
        symbol_rate=1.6 * G,
        conversions=151,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
        **ORIGINAL.as_tb_fields(),
    )
    raw_path, signal_names = _run_adc_sim(
        run_dir,
        params,
        check=check,
    )
    if not check:
        measurement = convert_raw_adc_to_measurement(
            read_raw_transient(raw_path),
            params=params,
            raw_path=raw_path,
            signal_names=signal_names,
        )
        write_measurement(run_dir / "result.h5", measurement)
    return run_dir


def fixed_input_timing_params() -> tuple[tuple[str, AdcTbParams], ...]:
    """Expand the four reviewed timing recipes into complete ADC parameters."""
    return tuple(
        (
            name,
            AdcTbParams(
                symbol_rate=1.6 * G,
                **sequence.as_tb_fields(),
            ),
        )
        for name, sequence in FIXED_INPUT_SEQUENCES
    )


def frida1_sequence(run_dir: Path, *, check: bool = False) -> Path:
    """Compare four timing recipes on four historical flavors, 100 conversions per case."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient

    root = Path(__file__).resolve().parents[2] / "build/layout/adc"
    with ProcessPoolExecutor(max_workers=4, mp_context=get_context("spawn")) as executor:
        futures = []
        for layers in (1, 2):
            for (radix, cdac), (timing, timing_params) in product(
                (
                    (17, CapArrayConfig()),
                    (20, CapArrayConfig(weights=(768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1))),
                ),
                fixed_input_timing_params(),
            ):
                target = f"frida1_{layers}layer_radix{radix}"
                pex = root / target / "20260905_171235" / f"{target}.pex.netlist"
                params = replace(
                    timing_params,
                    view="frida1",
                    pex_cell="adc_12b_17step",
                    dut=AdcParams(adc_bits=12, cdac=cdac),
                    conversions=1 if check else 100,
                    vin_diff=h.Vdc.Params(dc=0.05),
                )
                futures.append(
                    (
                        executor.submit(
                            _run_adc_sim,
                            run_dir / target / timing,
                            params,
                            pex_netlist=pex,
                            noise=True,
                            check=check,
                            expected_disconnect=layers == 2,
                        ),
                        params,
                    )
                )
        for future, params in futures:
            raw_path, signal_names = future.result()
            if not check:
                measurement = convert_raw_adc_to_measurement(
                    read_raw_transient(raw_path),
                    params=params,
                    raw_path=raw_path,
                    signal_names=signal_names,
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
    return run_dir


def frida1_sample_rate(run_dir: Path, *, check: bool = False) -> Path:
    """Run the four original PEX flavors at 2, 6, and 10 MS/s."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient
    from pdk.tsmc65 import site

    with ProcessPoolExecutor(max_workers=4, mp_context=get_context("spawn")) as executor:
        futures = []
        for layers in (1, 2):
            for radix, cdac in (
                (17, CapArrayConfig()),
                (20, CapArrayConfig(weights=(768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1))),
            ):
                cell = f"adc_{layers}layer_radix{radix}"
                pex = (
                    site.ADC_PEX_NETLIST
                    if cell == "adc_1layer_radix17"
                    else site.ADC_PEX_NETLIST.parent / cell / f"{cell}.pex.netlist"
                )
                for rate, symbol_rate in ((2, 0.32 * G), (6, 0.96 * G), (10, 1.6 * G)):
                    params = AdcTbParams(
                        view="frida1",
                        pex_cell=cell,
                        dut=AdcParams(adc_bits=12, cdac=cdac),
                        symbol_rate=symbol_rate,
                        conversions=1 if check else 100,
                        vin_diff=h.Vdc.Params(dc=0.05),
                        **ORIGINAL.as_tb_fields(),
                    )
                    futures.append(
                        (
                            executor.submit(
                                _run_adc_sim,
                                run_dir / cell / f"{float(symbol_rate) / 1e6:g}mbd",
                                params,
                                pex_netlist=pex,
                                noise=True,
                                check=check,
                            ),
                            params,
                        )
                    )
        for future, params in futures:
            raw_path, signal_names = future.result()
            if not check:
                measurement = convert_raw_adc_to_measurement(
                    read_raw_transient(raw_path),
                    params=params,
                    raw_path=raw_path,
                    signal_names=signal_names,
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
    return run_dir


def frida1_transfer_curve(run_dir: Path, *, check: bool = False) -> Path:
    """Run the original extracted ADC from -750 mV to +750 mV in 10 mV steps."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient
    from pdk.tsmc65 import site

    params = AdcTbParams(
        view="frida1",
        symbol_rate=1.6 * G,
        conversions=151,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
        **ORIGINAL.as_tb_fields(),
    )
    raw_path, signal_names = _run_adc_sim(
        run_dir,
        params,
        pex_netlist=site.ADC_PEX_NETLIST,
        check=check,
    )
    if not check:
        measurement = convert_raw_adc_to_measurement(
            read_raw_transient(raw_path),
            params=params,
            raw_path=raw_path,
            signal_names=signal_names,
        )
        write_measurement(run_dir / "result.h5", measurement)
    return run_dir


def frida1_supply_noise(run_dir: Path, *, check: bool = False) -> Path:
    """Run the 15 original extracted-ADC rate/supply-noise combinations."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient
    from pdk.tsmc65 import site

    noise_rms_v = 1e-3
    with ProcessPoolExecutor(max_workers=4, mp_context=get_context("spawn")) as executor:
        futures = []
        for rate, symbol_rate in ((2, 0.32 * G), (6, 0.96 * G), (10, 1.6 * G)):
            for name, rail_noise in (
                ("none", (0.0, 0.0, 0.0)),
                ("vdda", (noise_rms_v, 0.0, 0.0)),
                ("vddd", (0.0, noise_rms_v, 0.0)),
                ("vddac", (0.0, 0.0, noise_rms_v)),
                ("all", (noise_rms_v, noise_rms_v, noise_rms_v)),
            ):
                params = AdcTbParams(
                    view="frida1",
                    symbol_rate=symbol_rate,
                    conversions=1 if check else 100,
                    vin_diff=h.Vdc.Params(dc=0.05),
                    **ORIGINAL.as_tb_fields(),
                    supply_series_resistance_ohm=1.0,
                    supply_series_inductance_h=1e-9,
                    supply_decoupling_capacitance_f=1e-12,
                    supply_noise_rms_v=rail_noise,
                    supply_noise_bandwidth_hz=25e9,
                )
                futures.append(
                    (
                        executor.submit(
                            _run_adc_sim,
                            run_dir / f"{float(symbol_rate) / 1e6:g}mbd_{name}",
                            params,
                            pex_netlist=site.ADC_PEX_NETLIST,
                            check=check,
                        ),
                        params,
                    )
                )
        for future, params in futures:
            raw_path, signal_names = future.result()
            if not check:
                measurement = convert_raw_adc_to_measurement(
                    read_raw_transient(raw_path),
                    params=params,
                    raw_path=raw_path,
                    signal_names=signal_names,
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
    return run_dir


def frida2_sequence(run_dir: Path, *, check: bool = False) -> Path:
    """Compare four timing recipes on three radix-17 stacks, 100 conversions per case.

    Keep sampling, COMP rising edges, and LOGIC rising edges unchanged from
    the September 5 campaign. In extended_comp, six of eight slots evaluate; LOGIC is high
    for the first reset slot and low one slot before the next comparison.
    Edges coincide at the sequencer, not necessarily at the internal clocks.
    continuous_100ns instead uses 15 ns sampling and a shorter final COMP pulse
    to fit back-to-back conversions, as in adc_sequencer_timing_100ns.tex.
    continuous_100ns_comp7of8 shortens SAMP by four symbols and advances
    the decision train by 2.5 ns. All 17 COMP pulses last seven symbols;
    each of the 16 LOGIC updates occupies the final symbol of its slot.
    """

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient

    root = Path(__file__).resolve().parents[2] / "build/layout/adc"
    with ProcessPoolExecutor(max_workers=3, mp_context=get_context("spawn")) as executor:
        futures = []
        for (layers, stamp), (timing, timing_params) in product(
            ((1, "20260905_193440"), (2, "20260905_193629"), (3, "20260905_193816")),
            fixed_input_timing_params(),
        ):
            target = f"frida2_{layers}layer_radix17"
            params = replace(
                timing_params,
                view="frida2",
                pex_cell="adc_12b_17step",
                dut=AdcParams(adc_bits=12, cdac=CapArrayConfig()),
                conversions=1 if check else 100,
                vin_diff=h.Vdc.Params(dc=0.05),
            )
            futures.append(
                (
                    executor.submit(
                        _run_adc_sim,
                        run_dir / target / timing,
                        params,
                        pex_netlist=root / target / stamp / f"{target}.pex.netlist",
                        noise=True,
                        check=check,
                    ),
                    params,
                )
            )
        for future, params in futures:
            raw_path, signal_names = future.result()
            if not check:
                measurement = convert_raw_adc_to_measurement(
                    read_raw_transient(raw_path),
                    params=params,
                    raw_path=raw_path,
                    signal_names=signal_names,
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
    return run_dir


def main() -> None:
    """Select an experiment; diagnostics are available to Python callers only."""

    targets = {
        target.__name__: target
        for target in (
            hdl21_sample_rate,
            hdl21_transfer_curve,
            frida1_sequence,
            frida1_sample_rate,
            frida1_transfer_curve,
            frida1_supply_noise,
            frida2_sequence,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available ADC simulation targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build/sim/adc"
        / (datetime.now().astimezone().strftime("%Y%m%d_%H%M%S") + "_" + args.target)
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
