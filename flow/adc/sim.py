"""ADC testbench and its Spectre run (``simulate``; the named runs that use them are
``flow.adc.sweep``'s): the generated converter's netlist, or a fabricated converter's extraction, on
the run's stimulus, supplies and sequencer lines (``TbParams``: the four lines' rows are a recipe's,
``flow.adc.params.Recipe``); and a run's raw output decoded as conversions (``_decode``).

The stimulus as a behavioral conversion sees it: a differential source's value over time
(``calc_source_value``) and the interface waveform a behavioral capture stores
(``build_adc_interface_wave``).
"""

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.prefix import p
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators
from vlsirtools.spice.sim_data import TranResult

from flow import capdac, comp
from flow.adc.params import Extraction, Probes, Simulator, TbParams
from flow.adc.subckt import (
    Adc,
    AdcNets,
    adc_nets,
    adc_pex,
    adc_port_aliases,
    digital_netlist,
    frida1_net_aliases,
    generated_net_aliases,
)
from flow.analysis import calc
from flow.analysis.io import interpolate_wave_records
from flow.analysis.types import MeasAdc, MeasInfo
from flow.circuit.ports import testbench_from_ports
from flow.circuit.results import _RAW_STEP_RTOL, _conversion_inputs
from flow.pipeline import Wave


def _runnable(tb: TbParams) -> bool:
    """Whether ``tb``'s top runs it (its values ``TbParams`` checks itself): one COMP pulse a
    decision, a decision a stage and the last; and the generated converter, which wires the
    subtraction in (its difference plates switch opposite the main ones), at ``dac_diffcaps`` 1: a
    run of it at 0 would be decoded and analyzed as adding them."""
    comp_row = tb.seq_comp.data
    pulses = sum(
        bit == "1" and before == "0" for before, bit in zip(comp_row[-1] + comp_row[:-1], comp_row, strict=True)
    )
    if pulses != tb.decisions:
        return False
    return tb.params.fabricated is not None or bool(tb.dac_diffcaps)


def _view(tb: TbParams) -> str:
    """The top a run converts on, as the testbench and its probes name it: a fabricated converter's
    extraction ("frida1"), or the generated netlist ("hdl21gen")."""
    return "hdl21gen" if tb.params.fabricated is None else "frida1"


def _pex_cell(tb: TbParams) -> str:
    """The extracted cell a fabricated converter's run simulates: the tape-out's cell of its flavor,
    or the signoff's (its layout's top)."""
    fabricated = tb.params.fabricated
    if fabricated is None or tb.extraction is None:
        raise ValueError("a generated converter has no extraction")
    match tb.extraction:
        case Extraction.TAPEOUT:
            return f"adc_{fabricated.layers}layer_radix{fabricated.radix}"
        case Extraction.SIGNOFF:
            return "adc_12b_17step"


# Generated DUTs are compiled in place and must not survive in a cached testbench.
def testbench(params: TbParams, *, pex_netlist: Path | None = None) -> h.Module:
    """Generate a complete ADC testbench for the selected DUT view."""

    if not _runnable(params):
        raise ValueError(f"Invalid ADC testbench params: {params}")
    if (params.params.fabricated is not None) != (pex_netlist is not None):
        raise ValueError("extracted views require a PEX input; HDL21 must not have one")

    view = _view(params)
    nets = adc_nets(params.stages)
    if pex_netlist is None:
        ports = {name: net for name, net in nets.signals.items() if net.vis == h.Visibility.PORT}
    else:
        aliases = adc_port_aliases(view)
        selected = {net.parent if isinstance(net, h.Slice) else net for net in aliases}
        ports = {name: net for name, net in nets.signals.items() if net in selected}
    tb, connections = testbench_from_ports(f"AdcTb_{view}", ports)
    tb.vin_cm, tb.vin_diff = h.Signals(2)
    pattern_period_s = len(params.seq_init.data) / float(params.symbol_rate)
    rlc_enabled = params.supply_series_resistance_ohm > 0.0
    supplies = (net for net in nets.signals.values() if net.usage == h.Usage.POWER)
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

    for canonical in nets.signals.values():
        if canonical.vis != h.Visibility.PORT or canonical.usage != h.Usage.CLOCK:
            continue
        net = connections[canonical.name]
        # the run's line as it is: its row, a symbol a period, between ground and the digital supply
        setattr(tb, f"v{net.name}", h.Vbit(getattr(params, canonical.name))(p=net, n=tb.vss))
    for net in nets.signals.values():
        if net.direction != h.PortDir.INPUT or net.usage != h.Usage.SIGNAL or net in (nets.vin_p, nets.vin_n):
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
        tb.xadc = Adc(params.params)(**connections)
    else:
        module = adc_pex(pex_netlist, _pex_cell(params))
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


def adc_signal_names(tb: h.Module, view: str, *, save_supply_voltages: bool = False, nets=AdcNets) -> dict[str, str]:
    """Resolve canonical observations once for both Save and raw conversion; ``nets`` are the
    ADC's (``adc_nets`` of its stage count). The generated ADC holds its nets itself but for its
    bottom plates, which are its DAC's sides' (``generated_net_aliases``; a plate its array has none
    of, a unit capacitor's difference plate, is not saved); an extracted view's are RC terminals of
    its extraction (``frida1_net_aliases``)."""
    if view not in {"hdl21gen", "frida1"}:
        raise ValueError(f"Unsupported ADC view {view!r}")
    generated = view == "hdl21gen"
    aliases: Mapping[h.Signal | h.Slice, str | None] = (
        generated_net_aliases(tb.xadc.of, nets) if generated else frida1_net_aliases()
    )
    names = {"time": "time"}
    for schema, prefix in ((nets, ""), (comp.Nets, "comp.")):
        for net in schema.signals.values():
            if not net.props.get("save"):
                continue
            testbench_net = schema is nets and net.vis == h.Visibility.PORT and net.width == 1
            path = "xtop" if testbench_net else f"xtop.{tb.xadc.name}"
            bits = [net] if net.width == 1 else [net[stage] for stage in range(net.width)]
            # by its own name, the testbench's or the generated ADC's, where no alias binds it
            named = testbench_net or (generated and not any(bit in aliases for bit in bits))
            if named:
                scope = tb if testbench_net else tb.xadc.of
                if schema is comp.Nets:
                    path += f".{scope.xcomp.name}"
                    scope = scope.xcomp.of
                actual = scope.namespace[net.name]
                if actual.width != net.width:
                    raise ValueError(f"Generated width differs from canonical net {net.name}")
            for stage, canonical in enumerate(bits):
                if named:
                    raw = f"{path}.{actual.name}" + (f"_{stage}" if net.width > 1 else "")
                elif (alias := aliases[canonical]) is not None:
                    raw = f"{path}.{alias}"
                else:
                    continue  # a plate the generated ADC's array has none of
                label = f"{prefix}{net.name}" + (f"[{stage}]" if net.width > 1 else "")
                if raw in names or label in names.values():
                    raise ValueError(f"Duplicate probe binding: {raw} -> {label}")
                names[raw] = label
    for net in nets.signals.values():
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
            if save_supply_voltages:
                names[f"xtop.{tb.namespace[net.name].name}"] = net.name
    return names


def calc_pwl_value(source: h.Vpwl.Params, time_s: np.ndarray) -> np.ndarray:
    """Evaluate a PWL source that repeats after its last time point."""

    if isinstance(source.wave, str):
        values = np.asarray([float(value) for value in source.wave.split()], dtype=np.float64)
        pwl_time_s, pwl_value_v = values[0::2], values[1::2]
    else:
        pwl_time_s = np.asarray([float(time) for time, _value in source.wave.points], dtype=np.float64)
        pwl_value_v = np.asarray([float(value) for _time, value in source.wave.points], dtype=np.float64)
    period_s = pwl_time_s[-1] - pwl_time_s[0]
    return np.interp(pwl_time_s[0] + np.mod(time_s - pwl_time_s[0], period_s), pwl_time_s, pwl_value_v)


def calc_source_value(source, time_s: np.ndarray) -> np.ndarray:
    """Evaluate a DC, sine, or repeating PWL differential source."""

    if isinstance(source, h.Vpwl.Params):
        return calc_pwl_value(source, time_s)
    if isinstance(source, h.Vsin.Params):
        return float(source.voff) + float(source.vamp) * np.sin(
            2.0 * np.pi * float(source.freq) * time_s + np.deg2rad(float(source.phase or 0.0))
        )
    return np.full_like(time_s, float(source.dc), dtype=np.float64)


def build_adc_interface_wave(
    params: TbParams,
    bout: Sequence[int],
    *,
    conversion_index: int = 0,
    samples_per_symbol: int = 4,
) -> Wave:
    """Build one dense behavioral ADC-interface waveform from test parameters."""

    if samples_per_symbol <= 0:
        raise ValueError("samples_per_symbol must be positive")
    bout_array = np.asarray(bout, dtype=np.uint8)
    if bout_array.ndim != 1 or np.any((bout_array != 0) & (bout_array != 1)):
        raise ValueError("Bout must be one binary decision vector")

    sequence_length = len(params.seq_init.data)

    seq_comp, seq_logic = (
        np.repeat(np.fromiter((int(bit) for bit in line.data), dtype=np.uint8), samples_per_symbol)
        for line in (params.seq_comp, params.seq_logic)
    )
    comp_symbols = seq_comp.reshape(sequence_length, samples_per_symbol)[:, 0]
    falling_symbols = np.flatnonzero((comp_symbols[:-1] == 1) & (comp_symbols[1:] == 0)) + 1
    if len(falling_symbols) < len(bout_array):
        raise ValueError(
            f"sequencer has {len(falling_symbols)} comparator decisions, but Bout contains {len(bout_array)} bits"
        )
    comp_out_symbols = np.zeros(sequence_length, dtype=np.uint8)
    state = 0
    decision_index = 0
    for symbol in range(sequence_length):
        if decision_index < len(bout_array) and symbol == falling_symbols[decision_index]:
            state = int(bout_array[decision_index])
            decision_index += 1
        comp_out_symbols[symbol] = state

    symbol_period_s = 1.0 / float(params.symbol_rate)
    time_s = np.arange(sequence_length * samples_per_symbol, dtype=np.float64)
    time_s *= symbol_period_s / samples_per_symbol
    vin_diff_v = calc_source_value(params.vin_diff, time_s + conversion_index * sequence_length * symbol_period_s)
    logic_high_v = float(params.vdd_d.dc)
    return Wave(
        record_index=np.asarray([conversion_index], dtype=np.int64),
        time_s=time_s,
        v={
            "vin_diff": vin_diff_v[None, :],
            AdcNets.seq_comp.name: (logic_high_v * seq_comp)[None, :],
            AdcNets.seq_logic.name: (logic_high_v * seq_logic)[None, :],
            AdcNets.comp_out.name: (logic_high_v * np.repeat(comp_out_symbols, samples_per_symbol))[None, :],
        },
    )


def simulate(
    tb: TbParams,
    run_dir: Path,
    *,
    pex_netlist: Path | None = None,
) -> tuple[Path, dict[str, str]]:
    """Execute one configured ADC experiment, not an entire campaign: a Spectre run of ``tb``
    (``tb.transient_noise``, ``tb.check``), on the generated netlist or on a fabricated converter's
    extraction ``pex_netlist``.

    Targets define the experiment: they construct complete testbench parameters,
    select explicit PEX inputs, and submit independent cases
    concurrently. This executor owns the shared mechanics: generate/compile the
    testbench, validate extracted interfaces, build the Spectre simulation, run
    short diagnostics or the full simulation, and return the raw path and probe bindings.
    Flavor/rate sweeps and campaign selection belong in the named runs (``flow.adc.sweep``),
    not in additional flavor-specific wrappers.
    """

    if tb.simulator is not Simulator.SPECTRE:
        raise ValueError("simulate runs Spectre: the behavioral converter is flow.adc.model's")
    if tb.probes is not Probes.NODES:
        raise ValueError("a Spectre run saves every probed node: Probes.CODES is not yet netlisted")
    if not _runnable(tb):
        raise ValueError(f"Invalid ADC testbench params: {tb}")
    nets = adc_nets(tb.stages)
    noise, check, expected_disconnect = tb.transient_noise, tb.check, tb.expected_disconnect
    view = _view(tb)

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    # Fixed budgets paired with the target pools: four x six or three x eight.
    spectre_threads = 6 if tb.params.fabricated is not None else 8
    if (tb.params.fabricated is not None) != (pex_netlist is not None):
        raise ValueError("extracted views require a PEX input; HDL21 must not have one")
    metadata = {
        "target": run_dir.name,
        "view": view,
        "fabricated": None if tb.params.fabricated is None else tb.params.fabricated.name,
        "extraction": None if tb.extraction is None else tb.extraction.name,
        "conversions": tb.conversions,
        "symbol_rate_hz": float(tb.symbol_rate),
        "weights": list(capdac.Model.weights(tb.params.cdac)),
        "spectre_threads": spectre_threads,
        "check": check,
        "transient_noise": noise and not check,
        "expected_historical_disconnect": expected_disconnect,
        "sequencer": {
            net.name.removeprefix("seq_"): {"pattern": getattr(tb, net.name).data}
            for net in nets.signals.values()
            if net.vis == h.Visibility.PORT and net.usage == h.Usage.CLOCK
        },
    }
    if pex_netlist is not None:
        if not pex_netlist.is_file() or not pex_netlist.stat().st_size:
            raise FileNotFoundError(pex_netlist)
        from pdk.tsmc65.calibre.ringfmom import validate_extracted_netlist

        validate_extracted_netlist(pex_netlist.read_text())
        if tb.extraction is Extraction.SIGNOFF:
            summary_path = pex_netlist.parent / "signoff_summary.json"
            summary = json.loads(summary_path.read_text())
            known_disconnect = (
                expected_disconnect
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
    bench = testbench(tb, pex_netlist=pex_netlist)
    h.pdk.compile(bench)
    signal_names = adc_signal_names(bench, view, save_supply_voltages=bool(tb.supply_series_resistance_ohm), nets=nets)
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
        # the digital block's standard cells (the generated ADC's only ones: its DAC's drivers are
        # the PDK's transistors), the library the site includes and the regular-Vth one, each once
        library_cells = site.install.include_stdcell()
        attrs.append(library_cells)
        standard_cells = (
            *(path for path in site.STANDARD_CELL_SPICE_NETLISTS if path != library_cells.path),
            digital_netlist(tb.stages)[0],
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
    tstop_s = 100e-9 if check else tb.conversions * len(tb.seq_init.data) / float(tb.symbol_rate)
    if not check:
        first_comp_symbol = tb.seq_comp.data.index("01") + 1
        # Save the next B0 edge plus a symbol of margin, without completing
        # or decoding an extra conversion. The original noise bandwidth stays fixed.
        tstop_s += (first_comp_symbol + 1) / float(tb.symbol_rate)
    metadata["final_decision_time_reference"] = "next_init_seq_logic_rising_threshold"
    tran_options = {
        "strobeperiod": tb.waveform_sample_interval_s,
        "maxstep": tb.waveform_sample_interval_s,
        "strobeoutput": "strobeonly",
    }
    # Preserve the supply experiment's frequency settings without silently
    # enabling device transient noise, which its previous runner did not enable.
    if not check and (noise or any(tb.supply_noise_rms_v) or tb.supply_series_resistance_ohm):
        tran_options.update(
            noisefmin=1.0 / (tb.conversions * len(tb.seq_init.data) / float(tb.symbol_rate)),
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
    simulation = hs.Sim(tb=bench, attrs=attrs)
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


# A Spectre run's raw output as the converter's rows of conversions (``sweep``'s named runs read it
# so), each decision sampled at its LOGIC update


def _decision_times(
    time: np.ndarray,
    init: np.ndarray,
    comp: np.ndarray,
    logic: np.ndarray,
    conversions: int,
    threshold: float,
    *,
    decisions: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pair each COMP rise with its unique LOGIC rise, per conversion.

    Conversions start at INIT rises and contain exactly ``decisions`` COMP
    rises. The final decision's LOGIC observation belongs to the next INIT,
    before its B0; NaN marks a final observation that was not saved. A partial
    next cycle supplies observation edges but is never counted as a requested
    conversion.
    """
    final = decisions - 1
    init = calc.cross(init, time, threshold, edge="rising", initial_high=True)
    comp = calc.cross(comp, time, threshold, edge="rising", initial_high=True)
    logic = calc.cross(logic, time, threshold, edge="rising", initial_high=True)
    if len(init) < conversions:
        raise ValueError("raw data lacks the requested INIT edges")
    starts = init[:conversions]
    comp_times = np.empty((conversions, decisions))
    logic_times = np.full_like(comp_times, np.nan)
    for conversion, start in enumerate(starts):
        stop = init[conversion + 1] if conversion + 1 < len(init) else time[-1]
        indices = np.flatnonzero((comp >= start) & (comp < stop))
        if len(indices) != decisions:
            raise ValueError(
                f"conversion {conversion} contains {len(indices)} COMP rising edges; expected exactly {decisions}"
            )
        for decision, index in enumerate(indices):
            next_comp = comp[index + 1] if index + 1 < len(comp) else np.nan
            following = logic[(logic > comp[index]) & (logic < next_comp if np.isfinite(next_comp) else True)]
            when = following[0] if len(following) == 1 else np.nan
            if decision < final and (len(following) != 1 or not np.isfinite(next_comp)):
                raise ValueError(f"conversion {conversion}, B{decision}: missing unique LOGIC update")
            if (
                decision == final
                and np.isfinite(when)
                and not stop <= when < (next_comp if np.isfinite(next_comp) else np.inf)
            ):
                raise ValueError("final-decision LOGIC observation must be in the next INIT before its B0")
            comp_times[conversion, decision] = comp[index]
            logic_times[conversion, decision] = when
    return starts, comp_times, logic_times


def _complete(logic_times: np.ndarray) -> np.ndarray:
    """Require at least one complete ADC record, including the next-cycle B16 observation.

    Return the mask of usable records; incomplete records are still discarded.
    """
    valid = np.all(np.isfinite(logic_times), axis=1)
    if not np.any(valid):
        raise ValueError("No complete ADC conversions; save the next-cycle B16 observation")
    return valid


def _decode(
    result: TranResult,
    *,
    params: TbParams,
    raw_path: Path,
    signal_names: Mapping[str, str],
) -> MeasAdc:
    """Map a VLSIR transient to canonical ADC records and decode LOGIC observations once."""

    supply_rails = tuple(net.name for net in AdcNets.signals.values() if net.usage == h.Usage.POWER)
    times_s, signals, currents = _conversion_inputs(
        result, signal_names, params.waveform_sample_interval_s, supply_rails=supply_rails
    )
    code_weights = np.asarray([2 * weight for weight in capdac.Model.weights(params.params.cdac)] + [1], dtype=np.int64)
    threshold_v = float(params.vdd_d.dc) / 2
    starts, comp_times, logic_times = _decision_times(
        times_s,
        signals[AdcNets.seq_init.name],
        signals[AdcNets.seq_comp.name],
        signals[AdcNets.seq_logic.name],
        params.conversions,
        threshold_v,
        decisions=len(code_weights),
    )
    valid = _complete(logic_times)
    unavailable_conversions = np.flatnonzero(~valid).tolist()
    retained_conversions = np.flatnonzero(valid).tolist()
    decode_starts = starts
    comp_edge_times_s = comp_times[valid]
    final_sample_times_s = logic_times[valid, -1]
    sample_times_s = logic_times[valid]
    bout = (
        calc.value(signals[AdcNets.comp_out.name], times_s, sample_times_s.ravel()).reshape(sample_times_s.shape)
        > threshold_v
    ).astype(np.uint8)
    dout_raw = bout.astype(np.int64) @ code_weights
    dout = np.rint(dout_raw * ((1 << params.params.adc_bits) - 1) / np.sum(code_weights)).astype(np.int64)
    conversion_start_indices = np.searchsorted(times_s, starts[valid], side="right")
    conversion_start_indices[starts[valid] == times_s[0]] = 0
    conversion_starts_s = times_s[conversion_start_indices]
    vin_diff_v = calc.value(signals[AdcNets.vin_p.name] - signals[AdcNets.vin_n.name], times_s, comp_edge_times_s[:, 0])
    complete_conversions = len(conversion_start_indices)
    params = dataclasses.replace(params, conversions=complete_conversions)

    # Align waveform records to the repeated sequencer-pattern boundary, not
    # to SEQ_INIT's rising edge inside that pattern. This retains the pre-INIT
    # portion of each conversion; the next-cycle tail retains the B16 observation.
    waveform_starts_s = conversion_starts_s - (conversion_starts_s[0] - times_s[0])
    # Keep a next-cycle tail in every record, including the final B16 observation.
    period_s = len(params.seq_init.data) / float(params.symbol_rate)
    tail_s = (params.seq_comp.data.index("01") + 2) / float(params.symbol_rate)
    record_duration_s = min(period_s + tail_s, float(times_s[-1] - waveform_starts_s[-1]))
    waveform_conversion_indices = np.asarray(retained_conversions, dtype=np.int64)
    intervals = [(float(start), float(start + record_duration_s)) for start in waveform_starts_s]
    relative_time_s, waveform_records = interpolate_wave_records(
        times_s,
        signals,
        intervals,
        params.waveform_sample_interval_s,
    )
    _, current_records = interpolate_wave_records(
        times_s,
        currents,
        intervals,
        params.waveform_sample_interval_s,
    )

    readbacks: dict[str, str | int | float | bool] = {
        "raw_file": Path(raw_path).name,
        "raw_format": "spectre_nutbin",
        "raw_points": len(times_s),
        "raw_max_timestep_s": calc.ymax(np.diff(times_s)),
        "waveform_sample_interval_s": params.waveform_sample_interval_s,
        "waveform_interpolated_from_coarser_raw": bool(
            calc.ymax(np.diff(times_s)) > params.waveform_sample_interval_s * (1.0 + _RAW_STEP_RTOL)
        ),
        "decision_sample_fraction": 1.0,
        "decision_time_reference": "seq_logic_rising_threshold_B0_B15",
        "original_conversion_count": len(decode_starts),
        "unavailable_logic_conversions_json": json.dumps(unavailable_conversions),
        "final_decision_sample_fraction": 1.0,
        "final_decision_time_reference": "next_init_seq_logic_rising_threshold",
        "final_decision_sample_times_s_json": json.dumps([float(value) for value in final_sample_times_s]),
        "supply_power_available": True,
        "supply_current_convention": "positive_current_draw",
        "signal_map_json": json.dumps(dict(signal_names), sort_keys=True),
    }
    rail_voltages = {name: float(getattr(params, name).dc) for name in supply_rails}
    for rail, voltage_v in rail_voltages.items():
        current_draw_a = currents[rail]
        average_current_a = calc.average(current_draw_a, times_s)
        readbacks[f"{rail}_active_average_current_a"] = average_current_a
        readbacks[f"{rail}_active_average_power_w"] = voltage_v * average_current_a

    return MeasAdc(
        group=params.mc_seed,
        index=params.mc_index,
        dut=params.params,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime.fromtimestamp(
                Path(raw_path).stat().st_mtime,
                tz=UTC,
            ),
            instruments={"simulator": "Spectre"},
            readbacks=readbacks,
        ),
        param=params,
        conversion_index=np.asarray(retained_conversions, dtype=np.int64),
        bout=bout,
        dout_raw=dout_raw,
        dout=dout,
        vin_diff_v=vin_diff_v,
        wave=Wave(
            record_index=waveform_conversion_indices,
            time_s=relative_time_s,
            v=waveform_records,
            i=current_records,
        ),
    )
