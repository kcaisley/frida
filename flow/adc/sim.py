"""The ADC's runs (``TbParams``) and their measurements: the testbench of a run (``testbench``: the
generated converter's netlist, or a fabricated converter's extraction, on the run's stimulus,
supplies and sequencer lines), the run itself (``simulate``: Spectre on that testbench, or the
behavioral converter), and its raw output as a measurement (``read``).

A Spectre run saves its probes (``_probes``: every probed node, or the codes alone, ``Probes``) and
leaves their map beside its raw file (``names.json``), which ``read`` decodes as the converter's
rows of conversions (``_decode``), each decision sampled at its LOGIC update. A fabricated
converter's extraction is its tape-out's (``Extraction.TAPEOUT``: the TSMC65 kit's ``site.FRIDA1``)
or its layout's signoff (``Extraction.SIGNOFF``: the newest standing layout of its instance,
``flow.sweep.lookup.laid_out``), which the run checks before it simulates.

The behavioral converter (``_Converter``, ``_convert``): the ADC's blocks' models, each built from
the same parameters its netlist generator takes (``Params``) and from its own characterization in
the PDK, switched by its SAR loop; a behavioral run writes its conversions as a measurement
(``capture.h5``) with the converter's own numbers among its readbacks, which ``read`` reads back.
The blocks: the comparator (``flow.comp.model``), the sampling switch (``flow.samp.model``) and the
capacitive DAC with its drivers (``flow.capdac.model``). The DAC's is looked up and never run here
(minutes of SPICE an array, which every converter on the array would wait for: ``python -m flow run
capdac`` runs it ahead); where there is none, the DAC converts as designed (``capdac.Model.design``),
with a warning. Its plates are the array as drawn: its design's at the reference they are drawn
for, its top plate loaded as its measured gain gives, each stage's main plate drawn so that its step
at that load is the one measured (``capdac.Model.behavioral``), so its full scale is the measured
steps' and the "extracted" weights a capture decodes with, those steps, are the plates' own; each
stage's step starts its driver's delay after the LOGIC edge and settles with its own time constant,
as measured; and the converter calibrates on one of its Monte Carlo draws (``_Converter.drawn``). Its
drivers' energy is not characterized (its settling run saves no supply current): they draw none
here, which the record states. The SAR logic is the fixed digital netlist built by OpenROAD: it is
not characterized, so its energies are the ones fitted to the FRIDA-2 three-layer PEX transient
(``_SALOGIC``). The DAC's reference is ideal unless the run's ``reference_*`` set it.

The SAR loop (``_convert``) runs four blocks driven by HDL21 parameters. The sampler, the comparator
and the capacitor array with its drivers are their blocks' models (``flow.samp.model.Model.sample``,
``flow.comp.model.Model.compare`` and ``capdac.Model.switch``, each with its physics as
``Model.Behavioral``); ``_salogic`` models the SAR logic. Stage and decision counts come from the
CDAC configuration, and every time from the sequencer lines' rows and symbol rate, so resolution and
speed are free parameters. The SAR logic is a stage counter and a branch select: INIT loads the A
state, then each LOGIC edge writes the counted stage, ``1 - B`` on the P side and ``B`` on the N side
(``dac_mode=1``), or reloads the B state (``dac_mode=0``). Diff bottom plates follow ``state XOR
dac_diffcaps``. Logic, comparator, and driver energies are fixed amounts pinned to these actions.
The CDAC charge is computed: every top plate is one floating node loaded by its main and diff
capacitors and a parasitic capacitance, and the plates at VDD_DAC after an edge draw
``C * (dV_bottom - dV_top)`` from it.

The stimulus as the behavioral converter sees it: a source's value over time (``_source_value``: a
DC, sine or repeating PWL input; a sequencer line, ``h.Vbit``, as its ideal bits) and the interface
waveform a behavioral capture stores (``_interface_wave``).
"""

import dataclasses
import hashlib
import importlib
import json
import math
import re
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.prefix import p
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators
from vlsirtools.spice.sim_data import TranResult

import flow.comp.model as comp_model
import flow.samp.model as samp_model
from flow import capdac, comp
from flow.adc.params import (
    DECAP_COVERAGE,
    DRAWN_PERCENTILE,
    DRAWN_RUN,
    NOMINAL_RATE_HZ,
    VIN_CM_FRACTION,
    Extraction,
    Params,
    Probes,
    Quiet,
    Simulator,
    TbParams,
)
from flow.adc.subckt import (
    Nets,
    _digital_netlist,
    _fabricated,
    _frida1_ports,
    _frida1_terminals,
    _generated_aliases,
    _nets,
    _pex,
    netlist,
)
from flow.analysis import calc
from flow.analysis.io import interpolate_wave_records, read_measurement, write_measurement
from flow.analysis.types import MeasAdc, MeasInfo
from flow.circuit.ports import testbench_from_ports
from flow.circuit.results import _RAW_STEP_RTOL, _conversion_inputs, read_raw_transient
from flow.pipeline import Meas, Wave
from flow.sweep import lookup


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


def _extraction(tb: TbParams) -> tuple[Path, str]:
    """The extraction a fabricated converter's Spectre run simulates, its netlist and cell: the
    tape-out's of its flavor (``site.FRIDA1``, cell ``adc_<layers>layer_radix<radix>``), or its
    layout's signoff (``flow.sweep.lookup.laid_out``: the newest standing layout of its instance,
    cell ``adc_12b_17step``)."""
    fabricated = tb.params.fabricated
    if fabricated is None or tb.extraction is None:
        raise ValueError("a generated converter has no extraction")
    match tb.extraction:
        case Extraction.TAPEOUT:
            site = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site")
            cell = f"adc_{fabricated.layers}layer_radix{fabricated.radix}"
            return site.FRIDA1 / f"{cell}.pex.netlist", cell
        case Extraction.SIGNOFF:
            from flow.sweep.runner import ROOT

            path = Path(lookup.laid_out("adc", tb.pdk, tb.params)["pex"]["netlist"])
            return (path if path.is_absolute() else ROOT / path), "adc_12b_17step"


def _signed_off(tb: TbParams, path: Path) -> None:
    """Refuse a signoff extraction (``path``, ``_extraction``'s) its layout's signoff does not stand
    behind: an LVS result other than correct (or, for a two-layer flavor, its accepted historical
    disconnect), or content other than it signed."""
    entry = lookup.laid_out("adc", tb.pdk, tb.params)
    # the two-layer flavors' signoff keeps their historical MOM layer disconnected
    accepted = tb.expected_disconnect and entry.get("warnings") == [
        "expected LVS mismatch: disconnected historical MOM layer"
    ]
    if entry.get("lvs_correct") is not True and not accepted:
        raise ValueError(f"unaccepted LVS result for {tb.params.fabricated}: {entry}")
    signed = entry["pex"].get("sha256")
    if signed is not None and signed != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError(f"PEX content of {path} differs from the signed-off input")


def _checked(tb: TbParams) -> Path:
    """The extraction a fabricated converter's Spectre run ``tb`` simulates (``_extraction``), refused
    unless it stands: its file there and not empty, as the kit's check of an extracted netlist
    passes it, and a signoff's as its layout signed it (``_signed_off``). The sweep checks each of a
    level's circuit runs so before the first runs (``flow.adc.sweep.runs``), and each run again."""
    path, _cell = _extraction(tb)
    if not path.is_file() or not path.stat().st_size:
        raise FileNotFoundError(path)
    from pdk.tsmc65.calibre.ringfmom import validate_extracted_netlist

    validate_extracted_netlist(path.read_text())
    if tb.extraction is Extraction.SIGNOFF:
        _signed_off(tb, path)
    return path


def testbench(tb: TbParams) -> h.Module:
    """The testbench of the run ``tb``: its supplies (each behind its supply network and with its
    noise where ``tb`` gives them), its differential input about its common mode, its sequencer's
    four lines (``h.Vbit``, as stored), its static controls and DAC states, and its top: a fabricated
    converter's extraction in a Spectre run (``_extraction``), its black box otherwise
    (``flow.adc.subckt.netlist``), or the generated converter's netlist."""

    if not _runnable(tb):
        raise ValueError(f"Invalid ADC testbench params: {tb}")
    fabricated = tb.params.fabricated is not None
    nets = _nets(tb.stages)
    if fabricated:
        aliases = _frida1_ports()
        selected = {net.parent if isinstance(net, h.Slice) else net for net in aliases}
        ports = {name: net for name, net in nets.signals.items() if net in selected}
    else:
        ports = {name: net for name, net in nets.signals.items() if net.vis == h.Visibility.PORT}
    bench, connections = testbench_from_ports(f"AdcTb_{'frida1' if fabricated else 'hdl21gen'}", ports)
    bench.vin_cm, bench.vin_diff = h.Signals(2)
    pattern_period_s = len(tb.seq_init.data) / float(tb.symbol_rate)
    rlc_enabled = tb.supply_series_resistance_ohm > 0.0
    supplies = (net for net in nets.signals.values() if net.usage == h.Usage.POWER)
    for rail, noise_rms_v in zip(supplies, tb.supply_noise_rms_v, strict=True):
        rail_name = rail.name
        source_params = getattr(tb, rail_name)
        rail = connections[rail_name]
        source_node = h.Signal(name=f"{rail_name}_source") if rlc_enabled else rail
        if rlc_enabled:
            series_node = h.Signal(name=f"{rail_name}_series")
            setattr(bench, f"{rail_name}_source", source_node)
            setattr(bench, f"{rail_name}_series", series_node)
            setattr(
                bench,
                f"r{rail_name}",
                h.Resistor(r=tb.supply_series_resistance_ohm)(p=source_node, n=series_node),
            )
            setattr(
                bench,
                f"l{rail_name}",
                h.Inductor(l=tb.supply_series_inductance_h)(p=series_node, n=rail),
            )
            setattr(
                bench,
                f"c{rail_name}",
                h.Capacitor(c=tb.supply_decoupling_capacitance_f)(p=rail, n=bench.vss),
            )
        if noise_rms_v > 0.0:
            noise_density_v2_per_hz = noise_rms_v**2 / tb.supply_noise_bandwidth_hz
            bench.literals.append(
                h.Literal(
                    f"v{rail_name} ({source_node.name} {bench.vss.name}) vsource dc={float(source_params.dc):.12g} "
                    f"noisevec=[0 {noise_density_v2_per_hz:.12g} "
                    f"{tb.supply_noise_bandwidth_hz:.12g} {noise_density_v2_per_hz:.12g}]"
                )
            )
        else:
            setattr(bench, f"v{rail_name}", h.Vdc(source_params)(p=source_node, n=bench.vss))
    bench.vvin_cm = h.Vdc(tb.vin_cm)(p=bench.vin_cm, n=bench.vss)
    if isinstance(tb.vin_diff, h.Vdc.Params):
        bench.vvin_diff = h.Vdc(tb.vin_diff)(p=bench.vin_diff, n=bench.vss)
    elif isinstance(tb.vin_diff, h.Vsin.Params):
        bench.vvin_diff = h.Vsin(
            voff=tb.vin_diff.voff,
            vamp=tb.vin_diff.vamp,
            freq=tb.vin_diff.freq,
            td=0.0 if tb.vin_diff.td is None else tb.vin_diff.td,
            phase=0.0 if tb.vin_diff.phase is None else tb.vin_diff.phase,
        )(p=bench.vin_diff, n=bench.vss)
    elif isinstance(tb.vin_diff, hs.LinearSweep):
        wave = h.Pwl.staircase(
            start=tb.vin_diff.start,
            stop=tb.vin_diff.stop,
            step=tb.vin_diff.step,
            dwell=pattern_period_s,
            transition=100 * p,
            transition_at="end",
        )
        bench.vvin_diff = h.Vpwl(wave=wave)(p=bench.vin_diff, n=bench.vss)
    elif isinstance(tb.vin_diff, h.Vpwl.Params):
        bench.vvin_diff = h.Vpwl(tb.vin_diff)(p=bench.vin_diff, n=bench.vss)
    else:
        raise TypeError(f"unsupported ADC differential source {type(tb.vin_diff).__name__}")
    bench.evin_p = h.Vcvs(gain=0.5)(p=bench.vin_p, n=bench.vin_cm, cp=bench.vin_diff, cn=bench.vss)
    bench.evin_n = h.Vcvs(gain=-0.5)(p=bench.vin_n, n=bench.vin_cm, cp=bench.vin_diff, cn=bench.vss)

    for canonical in nets.signals.values():
        if canonical.vis != h.Visibility.PORT or canonical.usage != h.Usage.CLOCK:
            continue
        net = connections[canonical.name]
        # the run's line as it is: its row, a symbol a period, between ground and the digital supply
        setattr(bench, f"v{net.name}", h.Vbit(getattr(tb, canonical.name))(p=net, n=bench.vss))
    for net in nets.signals.values():
        if net.direction != h.PortDir.INPUT or net.usage != h.Usage.SIGNAL or net in (nets.vin_p, nets.vin_n):
            continue
        value = getattr(tb, net.name)
        if net.width == 1:
            bench.add(h.Vdc(dc=float(tb.vdd_d.dc) * value)(p=connections[net.name], n=bench.vss), name=f"v{net.name}")
        else:
            for stage, state in enumerate(value):
                bench.add(
                    h.Vdc(dc=float(tb.vdd_d.dc) * state)(p=connections[net.name][stage], n=bench.vss),
                    name=f"v{net.name}_{stage}",
                )

    if not fabricated:
        bench.xadc = netlist(tb.params)(**connections)
        return bench
    # a fabricated converter: its extraction's cell (its black box, outside Spectre), by its pins
    module = _pex(*_extraction(tb)) if tb.simulator is Simulator.SPECTRE else _fabricated()
    pex_connections = {
        physical: connections[net.parent.name][net.index] if isinstance(net, h.Slice) else connections[net.name]
        for net, physical in aliases.items()
    }
    if set(pex_connections) != set(module.ports):
        raise ValueError(
            f"External interface {module.name}: missing {set(pex_connections) - set(module.ports)}, "
            f"unknown {set(module.ports) - set(pex_connections)}"
        )
    bench.xadc = module()(**pex_connections)
    return bench


def _probes(bench: h.Module, tb: TbParams) -> dict[str, str]:
    """What a Spectre run of ``tb`` saves (``bench``, its testbench), each raw name with its
    canonical label, resolved once for the save statement and the decode: with ``Probes.NODES``
    every probed net (``Nets``' and the comparator's that are marked ``save``), with
    ``Probes.CODES`` only what the conversions need (the sequencer's lines, the comparator's output
    and the input); and each supply's current, its voltage too behind a supply network. The
    generated ADC holds its nets itself but for its bottom plates, which are its DAC's sides'
    (``subckt._generated_aliases``; a plate its array has none of, a unit capacitor's difference
    plate, is not saved); an extraction's are RC terminals of it (``subckt._frida1_terminals``)."""
    nets = _nets(tb.stages)
    generated = tb.params.fabricated is None
    aliases: Mapping[h.Signal | h.Slice, str | None] = (
        _generated_aliases(bench.xadc.of, nets) if generated else _frida1_terminals()
    )
    codes = {nets.seq_init, nets.seq_samp, nets.seq_comp, nets.seq_logic, nets.comp_out, nets.vin_p, nets.vin_n}
    names = {"time": "time"}
    for schema, prefix in ((nets, ""), (comp.Nets, "comp.")):
        for net in schema.signals.values():
            if not net.props.get("save") or (tb.probes is Probes.CODES and net not in codes):
                continue
            testbench_net = schema is nets and net.vis == h.Visibility.PORT and net.width == 1
            path = "xtop" if testbench_net else f"xtop.{bench.xadc.name}"
            bits = [net] if net.width == 1 else [net[stage] for stage in range(net.width)]
            # by its own name, the testbench's or the generated ADC's, where no alias binds it
            named = testbench_net or (generated and not any(bit in aliases for bit in bits))
            if named:
                scope = bench if testbench_net else bench.xadc.of
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
            if tb.supply_series_resistance_ohm:
                names[f"xtop.{bench.namespace[net.name].name}"] = net.name
    return names


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``tb`` into ``run_dir`` and return its raw output: the behavioral converter's conversions
    (``capture.h5``, a measurement), or a Spectre run of its testbench (``netlist.raw``, with
    ``input.json`` and its probes' map ``names.json`` beside it; ``tb.transient_noise``, its short
    static and dynamic checks alone where ``tb.check``). One run, not a campaign: the sweep's
    ``runs`` and the runner pick the runs and read each (``read``)."""

    if tb.simulator is Simulator.BEHAVIORAL:
        return _capture(tb, run_dir)
    if not _runnable(tb):
        raise ValueError(f"Invalid ADC testbench params: {tb}")
    if tb.pdk != "tsmc65":
        raise ValueError(f"a Spectre run of the ADC is TSMC65's alone (its kit's includes), not {tb.pdk}'s")
    nets = _nets(tb.stages)
    noise, check = tb.transient_noise, tb.check
    fabricated = tb.params.fabricated is not None
    # its extraction checked before anything is built
    pex_netlist = _checked(tb) if fabricated else None

    from pdk.tsmc65.hdl21 import pdk_logic, site

    # Fixed budgets paired with the named runs' pools: four x six or three x eight.
    spectre_threads = 6 if fabricated else 8
    metadata = {
        "target": run_dir.name,
        "top": "extraction" if fabricated else "generated",
        "fabricated": None if tb.params.fabricated is None else tb.params.fabricated.name,
        "extraction": None if tb.extraction is None else tb.extraction.name,
        "probes": tb.probes.name,
        "conversions": tb.conversions,
        "symbol_rate_hz": float(tb.symbol_rate),
        "weights": list(capdac.Model.weights(tb.params.cdac)),
        "spectre_threads": spectre_threads,
        "check": check,
        "transient_noise": noise and not check,
        "expected_historical_disconnect": tb.expected_disconnect,
        "sequencer": {
            net.name.removeprefix("seq_"): {"pattern": getattr(tb, net.name).data}
            for net in nets.signals.values()
            if net.vis == h.Visibility.PORT and net.usage == h.Usage.CLOCK
        },
    }
    if pex_netlist is not None:
        metadata.update(
            pex_netlist=str(pex_netlist),
            pex_sha256=hashlib.sha256(pex_netlist.read_bytes()).hexdigest(),
        )

    h.pdk.set_default(pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    signal_names = _probes(bench, tb)
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
            _digital_netlist(tb.stages)[0],
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
    (run_dir / "names.json").write_text(json.dumps(signal_names, indent=1) + "\n")
    simulation.run(options)
    return run_dir / "netlist.raw"


def read(raw: Path, tb: TbParams) -> Meas:
    """The run ``tb``'s raw output (``simulate``'s) as a measurement: a behavioral run's capture
    as written, or a Spectre run's transient decoded as conversions (``_decode``) through the
    probes' map it left beside it (``names.json``)."""
    if raw.suffix == ".h5":
        measurement = read_measurement(raw)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{raw} holds a {type(measurement).__name__}, not a converter's conversions")
        return measurement
    names = json.loads((raw.parent / "names.json").read_text())
    return _decode(read_raw_transient(raw), params=tb, raw_path=raw, signal_names=names)


# A Spectre run's raw output as the converter's rows of conversions, each decision sampled at its
# LOGIC update


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

    supply_rails = tuple(net.name for net in Nets.signals.values() if net.usage == h.Usage.POWER)
    times_s, signals, currents = _conversion_inputs(
        result, signal_names, params.waveform_sample_interval_s, supply_rails=supply_rails
    )
    code_weights = np.asarray([2 * weight for weight in capdac.Model.weights(params.params.cdac)] + [1], dtype=np.int64)
    threshold_v = float(params.vdd_d.dc) / 2
    starts, comp_times, logic_times = _decision_times(
        times_s,
        signals[Nets.seq_init.name],
        signals[Nets.seq_comp.name],
        signals[Nets.seq_logic.name],
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
        calc.value(signals[Nets.comp_out.name], times_s, sample_times_s.ravel()).reshape(sample_times_s.shape)
        > threshold_v
    ).astype(np.uint8)
    dout_raw = bout.astype(np.int64) @ code_weights
    dout = np.rint(dout_raw * ((1 << params.params.adc_bits) - 1) / np.sum(code_weights)).astype(np.int64)
    conversion_start_indices = np.searchsorted(times_s, starts[valid], side="right")
    conversion_start_indices[starts[valid] == times_s[0]] = 0
    conversion_starts_s = times_s[conversion_start_indices]
    vin_diff_v = calc.value(signals[Nets.vin_p.name] - signals[Nets.vin_n.name], times_s, comp_edge_times_s[:, 0])
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


def _capture(tb: TbParams, run_dir: Path) -> Path:
    """A behavioral run: the converter of ``tb``'s design in its PDK (``_Converter.of``, once a
    process) converts every conversion of it, and its measurement, the converter's own numbers among
    its readbacks (``_Converter.numbers``), is written to ``run_dir/capture.h5``."""
    converter = _converter(tb.pdk, tb.params)
    measurement = converter.capture(tb, None)
    info = dataclasses.replace(measurement.info, readbacks={**measurement.info.readbacks, **converter.numbers()})
    run_dir.mkdir(parents=True, exist_ok=True)
    return write_measurement(run_dir / "capture.h5", dataclasses.replace(measurement, info=info))


@cache
def _converter(pdk: str, params: Params) -> "_Converter":
    """The behavioral converter of ``params`` in ``pdk`` (``_Converter.of``), assembled once a
    process: a campaign's runs share it."""
    return _Converter.of(pdk, params)


def _pwl_value(source: h.Vpwl.Params, time_s: np.ndarray) -> np.ndarray:
    """Evaluate a PWL source that repeats after its last time point."""

    if isinstance(source.wave, str):
        values = np.asarray([float(value) for value in source.wave.split()], dtype=np.float64)
        pwl_time_s, pwl_value_v = values[0::2], values[1::2]
    else:
        pwl_time_s = np.asarray([float(time) for time, _value in source.wave.points], dtype=np.float64)
        pwl_value_v = np.asarray([float(value) for _time, value in source.wave.points], dtype=np.float64)
    period_s = pwl_time_s[-1] - pwl_time_s[0]
    return np.interp(pwl_time_s[0] + np.mod(time_s - pwl_time_s[0], period_s), pwl_time_s, pwl_value_v)


def _bit_value(source: h.Vbit.Params, time_s: np.ndarray) -> np.ndarray:
    """A bit source (a sequencer line) as the behavioral converter sees it: each symbol's level,
    ``val1`` for a 1 and ``val0`` for a 0, from its start (``delay``) a ``period`` each, its edges
    ideal (the converter's own times are the symbols' boundaries, ``_sequence_times``); repeated from
    the start forever (``rptstart`` 1, ``rpttimes`` < 0), else its last symbol held; ``val0``
    before it starts."""
    bits = np.fromiter((bit == "1" for bit in source.data), dtype=bool)
    # a symbol's boundary on a sample (k periods, to rounding) is the next symbol's
    position = np.round((np.asarray(time_s, dtype=np.float64) - float(source.delay)) / float(source.period), 9)
    index = np.floor(position).astype(np.int64)
    if source.rptstart != 1 or source.rpttimes >= 0:
        raise ValueError("a sequencer line repeats its row from the start, forever")
    level = np.where(bits[np.mod(index, len(bits))], float(source.val1), float(source.val0))
    return np.where(index < 0, float(source.val0), level)


def _source_value(source, time_s: np.ndarray) -> np.ndarray:
    """Evaluate a DC, sine, or repeating PWL differential source, or a sequencer line (``h.Vbit``,
    ``_bit_value``)."""

    if isinstance(source, h.Vbit.Params):
        return _bit_value(source, time_s)
    if isinstance(source, h.Vpwl.Params):
        return _pwl_value(source, time_s)
    if isinstance(source, h.Vsin.Params):
        return float(source.voff) + float(source.vamp) * np.sin(
            2.0 * np.pi * float(source.freq) * time_s + np.deg2rad(float(source.phase or 0.0))
        )
    return np.full_like(time_s, float(source.dc), dtype=np.float64)


def _interface_wave(
    tb: TbParams,
    bout: Sequence[int],
    *,
    conversion_index: int = 0,
    samples_per_symbol: int = 4,
) -> Wave:
    """One conversion's interface waveform, as a behavioral capture stores it: the input, the
    COMP and LOGIC lines (``_source_value``) and the comparator's output, holding each decision of
    ``bout`` from its COMP pulse's fall."""

    if samples_per_symbol <= 0:
        raise ValueError("samples_per_symbol must be positive")
    bout_array = np.asarray(bout, dtype=np.uint8)
    if bout_array.ndim != 1 or np.any((bout_array != 0) & (bout_array != 1)):
        raise ValueError("Bout must be one binary decision vector")

    sequence_length = len(tb.seq_init.data)
    comp_symbols = np.fromiter((int(bit) for bit in tb.seq_comp.data), dtype=np.uint8)
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

    symbol_period_s = 1.0 / float(tb.symbol_rate)
    time_s = np.arange(sequence_length * samples_per_symbol, dtype=np.float64)
    time_s *= symbol_period_s / samples_per_symbol
    vin_diff_v = _source_value(tb.vin_diff, time_s + conversion_index * sequence_length * symbol_period_s)
    logic_high_v = float(tb.vdd_d.dc)
    return Wave(
        record_index=np.asarray([conversion_index], dtype=np.int64),
        time_s=time_s,
        v={
            "vin_diff": vin_diff_v[None, :],
            Nets.seq_comp.name: _source_value(tb.seq_comp, time_s)[None, :],
            Nets.seq_logic.name: _source_value(tb.seq_logic, time_s)[None, :],
            Nets.comp_out.name: (logic_high_v * np.repeat(comp_out_symbols, samples_per_symbol))[None, :],
        },
    )


# The behavioral converter: its SAR loop's blocks and logic (``_Behavioral``), and the loop


@h.paramclass
class _Salogic:
    """SAR stage counter and branch select; energy is pinned per action and register."""

    clock_energy_j = h.Param(dtype=float, desc="Energy per register per LOGIC edge", default=0.0)
    write_energy_j = h.Param(dtype=float, desc="Energy per state-register value change", default=0.0)
    register_static_w = h.Param(dtype=float, desc="Static power per register with its logic", default=0.0)


@h.paramclass
class _Behavioral:
    """One HDL21 testbench configuration plus the block physics it does not describe."""

    tb = h.Param(dtype=TbParams, desc="ADC stimulus and digital configuration")
    samp = h.Param(dtype=samp_model.Model.Behavioral, desc="Sampler", default=samp_model.Model.Behavioral())
    comp = h.Param(dtype=comp_model.Model.Behavioral, desc="Comparator", default=comp_model.Model.Behavioral())
    cdac = h.Param(dtype=capdac.Model.Behavioral, desc="Capacitor array and drivers", default=capdac.Model.Behavioral())
    salogic = h.Param(dtype=_Salogic, desc="SAR logic", default=_Salogic())
    seed = h.Param(dtype=int, desc="Noise random seed", default=0)


@dataclass(frozen=True, slots=True)
class _Conversions:
    """Decisions, per-conversion energy by rail, and static power by rail."""

    bout: np.ndarray
    energy_j: dict[str, np.ndarray]
    static_power_w: dict[str, float]


# The SAR logic's energies, fitted to the FRIDA-2 three-layer PEX transient (10 MS/s): 22.85 pJ a
# conversion and 1.338 uW idle on VDD_D over its 48 registers.
_SALOGIC = _Salogic(clock_energy_j=25.5e-15, write_energy_j=31.9e-15, register_static_w=27.9e-9)


@dataclass(frozen=True)
class _Converter:
    """A SAR ADC's blocks, as their characterizations measured them: the behavioral converter of a
    design in a PDK (``of``), which converts a run (``capture``)."""

    pdk: str
    params: Params
    comp: comp_model.Model
    samp: samp_model.Model
    cdac: capdac.Model  # its DAC, its drivers with it: as characterized, else as designed
    # the plates the converter calibrates on, (main, diff) for the P side then the N side: its DAC's
    # Monte Carlo draw (DRAWN_RUN at DRAWN_PERCENTILE, drawn in SPICE); None where none is characterized
    drawn: tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]] | None = None

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> "_Converter":
        # the DAC's characterization is looked up, never run here (minutes of SPICE an array, which
        # every converter on the array would wait for); where there is none, or the settling run its
        # record keeps cannot be read (OSError, as for its Monte Carlo below), the DAC as designed
        try:
            dac = capdac.Model.of(pdk, params.cdac, simulate=False)
        except (KeyError, LookupError, OSError, RuntimeError) as error:
            warnings.warn(f"the DAC is not characterized ({error}); it converts as designed instead", stacklevel=2)
            dac = capdac.Model.design(pdk, params.cdac)
        try:
            drawn = capdac.Model.drawn(pdk, params.cdac, DRAWN_RUN, DRAWN_PERCENTILE)
        except (KeyError, LookupError, OSError, RuntimeError) as error:
            warnings.warn(
                f"the DAC's Monte Carlo is not characterized ({error}); its draws convert nominal", stacklevel=2
            )
            drawn = None
        return cls(
            pdk=pdk,
            params=params,
            comp=comp_model.Model.of(pdk, params.comp, simulate=simulate),
            samp=samp_model.Model.of(pdk, params.samp, simulate=simulate),
            cdac=dac,
            drawn=drawn,
        )

    @property
    def stages(self) -> int:
        return len(capdac.Model.weights(self.params.cdac))

    @property
    def supply_v(self) -> float:
        return importlib.import_module(f"pdk.{self.pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)

    @property
    def load_f(self) -> float:
        """Each top plate's whole load: its DAC's design plates over the measured gain, the plates as
        drawn and the parasitic beside them (``capdac.Model.behavioral``)."""
        dac = self.cdac.behavioral()
        return float(np.sum(dac.main_p_f) + np.sum(dac.diff_p_f)) + dac.parasitic_f

    @property
    def full_scale_v(self) -> float:
        """The differential full scale (+-) at the PDK's supply: its DAC's
        (``capdac.Model.full_scale_v``)."""
        return self.cdac.full_scale_v(self.supply_v)

    @property
    def stage_tau_s(self) -> tuple[float, ...]:
        """Each stage's top-plate settling time constant, C0 first: the one that brings its step
        within half an LSB when SPICE does (``flow.capdac.model``); as designed, the one its drivers
        are sized for."""
        return self.cdac.tau_s

    @property
    def stage_delay_s(self) -> tuple[float, ...]:
        """Each stage's delay from the LOGIC edge until its step starts, C0 first: its driver's delay
        to 50 % in SPICE (``flow.capdac.model``); none as designed."""
        return self.cdac.delay_s

    @property
    def settling_tau_s(self) -> float:
        """The slowest stage's settling time constant."""
        return max(self.stage_tau_s)

    @property
    def decoupling_f(self) -> float:
        """The reference node's decoupling: decap cells over ``DECAP_COVERAGE`` of the footprint of the
        DAC's two sides (each side's layout, its drivers with it) at the PDK's density, to one
        significant figure; NaN where the PDK gives none or the DAC is not laid out."""
        density = getattr(importlib.import_module(f"pdk.{self.pdk}.hdl21").pdk_logic, "DECAP_FF_PER_UM2", math.nan)
        capacitance_f = DECAP_COVERAGE * 2 * self.cdac.area_um2 * density * 1e-15
        return float(f"{capacitance_f:.0e}") if capacitance_f > 0 else math.nan

    def tb(self, *, conversions: int, rate_hz: float, vin_diff) -> TbParams:
        """The testbench of ``conversions`` at ``rate_hz`` with the continuous sequence (8 symbols a
        decision), an alternating A state and the PDK's supply on every rail."""
        supply = h.Vdc.Params(dc=round(self.supply_v, 4))
        tb = TbParams(
            pdk=self.pdk,
            params=self.params,
            conversions=conversions,
            vin_diff=vin_diff,
            vin_cm=h.Vdc.Params(dc=round(VIN_CM_FRACTION * self.supply_v, 4)),
            vdd_a=supply,
            vdd_d=supply,
            vdd_dac=supply,
            dac_astate_p=tuple(stage % 2 for stage in range(self.stages)),
            dac_astate_n=tuple(stage % 2 for stage in range(self.stages)),
            dac_bstate_p=(0,) * self.stages,
            dac_bstate_n=(0,) * self.stages,
        ).continuous(self.stages)
        return tb.sequenced(symbol_rate=rate_hz * len(tb.seq_init.data))

    def behavioral(self, tb: TbParams) -> _Behavioral:
        """The behavioral ADC of the run ``tb``, as its knobs set it: the DAC's SPICE draw where
        ``tb.drawn`` (``drawn``; nominal where there is none), else one Pelgrom draw of its
        design's plates from ``tb.mismatch_seed`` at ``tb.unit_mismatch``, as its Monte Carlo
        draws them, the P side then the N side, each its main then its difference plates (none where
        ``unit_mismatch`` is 0, which takes nothing from the seed's stream), each the array as drawn
        about it (``capdac.Model.behavioral``); ``tb.quiet`` silences the sampling noise (kT/C and
        the aperture jitter, ``Quiet.SAMPLING``) or the comparator's noise alone
        (``Quiet.COMPARATOR_NOISE``: its delay stays, so a late decision still holds the last bit),
        or makes the comparator ideal (``Quiet.COMPARATOR``: no noise, never late) or the sampler a
        perfect track-and-hold (``Quiet.SAMPLER``: no on-resistance, so no tracking error; its noise
        is the sampling's). Each stage's step starts its delay after the LOGIC edge (the SAR
        register's clock-to-output is not modeled) and settles with the stage's time constant, times
        ``tb.tau_scale`` (0: ideal, every step whole at once); the reference as ``tb.reference_*``
        sets it."""
        seed, unit_mismatch, quiet, tau_scale = tb.mismatch_seed, tb.unit_mismatch, tb.quiet, tb.tau_scale
        rng = np.random.default_rng(seed)
        sides = None  # the design's plates
        if tb.drawn:
            sides = self.drawn
        elif unit_mismatch:
            # the design's plates drawn, as the DAC's Monte Carlo draws them: the P side's main and
            # difference plates, then the N side's
            plates = capdac.Model.plates(self.params.cdac, self.cdac.reference_v)
            main_p, diff_p, main_n, diff_n = (
                capdac.Model.draw(plate_f, pelgrom=unit_mismatch, rng=rng) for plate_f in (*plates, *plates)
            )
            sides = ((main_p, diff_p), (main_n, diff_n))
        # the plates the DAC switches, the array as drawn about them, at the parasitic of its drawn
        # gain, its delays and time constants
        dac = self.cdac.behavioral(sides)
        samp = self.samp.behavioral(load_f=self.load_f)
        comp = self.comp.behavioral(vin_cm_v=float(tb.vin_cm.dc))
        if Quiet.SAMPLING in quiet:
            samp = type(samp)(**{**samp.__dict__, "noise_v": 0.0, "jitter_s": 0.0})
        if Quiet.SAMPLER in quiet:
            # a perfect track-and-hold: the held value is the input at the sampling instant (the
            # switch's on-resistance, which lags the input by R(v) C dv/dt, gone)
            samp = type(samp)(
                **{
                    **samp.__dict__,
                    "ron_table_v": None,
                    "ron_table_ohm": None,
                    "n_conductance_s_per_v": 0.0,
                    "p_conductance_s_per_v": 0.0,
                }
            )
        if Quiet.COMPARATOR in quiet:
            # an ideal comparator: no noise, and never late
            comp = type(comp)(**{**comp.__dict__, "noise_v": 0.0, "delay_table_v": None, "delay_table_s": None})
        elif Quiet.COMPARATOR_NOISE in quiet:
            comp = type(comp)(**{**comp.__dict__, "noise_v": 0.0})
        return _Behavioral(
            tb=tb,
            samp=samp,
            comp=comp,
            # its drivers draw no energy: capdac does not characterize it
            cdac=capdac.Model.Behavioral(
                **{
                    **dac.__dict__,
                    "settling_tau_s": self.settling_tau_s * tau_scale,
                    "stage_tau_s": tuple(tau_s * tau_scale for tau_s in self.stage_tau_s),
                    # ideal settling: the drivers' delay goes too
                    "stage_delay_s": tuple(delay_s if tau_scale else 0.0 for delay_s in self.stage_delay_s),
                    "reference_r_ohm": tb.reference_r_ohm,
                    "reference_c_f": tb.reference_c_f,
                    "reference_noise_v": tb.reference_noise_v,
                }
            ),
            salogic=_SALOGIC,
            seed=seed,
        )

    def capture(self, tb: TbParams, path: Path | None) -> MeasAdc:
        """Convert every conversion of ``tb`` (its behavioral converter, ``behavioral``; its noise
        drawn from ``tb.noise_seed``, the mismatch seed's where None) and write the MeasAdc with its
        supply power to ``path`` (kept in memory alone where it is None); its ``cap_table`` readback
        names the decoding's "extracted" weights: the measurement the DAC's characterization keeps of
        its settling run, each stage's step as measured (``flow.analysis.io.read_cap_table``), none
        where the DAC is designed alone (its design weights)."""

        params = self.behavioral(tb)
        if tb.noise_seed is not None:
            params = _Behavioral(**{**params.__dict__, "seed": tb.noise_seed})
        seed, unit_mismatch, tau_scale, drawn = tb.mismatch_seed, tb.unit_mismatch, tb.tau_scale, tb.drawn
        sample_rate_hz = float(tb.symbol_rate) / len(tb.seq_init.data)
        time_s = np.arange(tb.conversions) / sample_rate_hz
        vin_diff_v = _source_value(tb.vin_diff, time_s)
        # a centred difference over 1 ps gives the slope the sampler tracks
        slope = (_source_value(tb.vin_diff, time_s + 0.5e-12) - _source_value(tb.vin_diff, time_s - 0.5e-12)) / 1e-12
        result = _convert(params, vin_diff_v, slope)
        # each capacitor's decision weighs twice its weight (both sides move), the last decision one
        code_weights = np.asarray([2 * weight for weight in capdac.Model.weights(tb.params.cdac)] + [1], dtype=np.int64)
        dout_raw = result.bout.astype(np.int64) @ code_weights
        dout = np.rint(dout_raw * ((1 << tb.params.adc_bits) - 1) / code_weights.sum()).astype(np.int64)
        # active power averages one conversion window, as for SPICE captures
        active_rate_hz = float(tb.symbol_rate) / tb.conversion_symbols
        readbacks: dict[str, str | int | float | bool] = {
            "cap_table": str(self.cdac.settling_meas or ""),
            "unit_mismatch": unit_mismatch,
            "drawn": bool(drawn and self.drawn is not None),
            "tau_scale": tau_scale,
            "pdk": self.pdk,
        }
        for rail in ("vdd_a", "vdd_d", "vdd_dac"):
            static_w = result.static_power_w[rail]
            readbacks[f"{rail}_static_average_power_w"] = static_w
            readbacks[f"{rail}_active_average_power_w"] = (
                static_w + float(np.mean(result.energy_j[rail])) * active_rate_hz
            )
        measurement = MeasAdc(
            group=seed if unit_mismatch else None,
            index=0 if unit_mismatch else None,
            dut=tb.params,
            info=MeasInfo(
                backend="behavioral",
                timestamp_utc=datetime.now().astimezone(),
                instruments={"model": f"{type(self).__module__}.{type(self).__qualname__}"},
                readbacks=readbacks,
            ),
            param=params,
            conversion_index=np.arange(tb.conversions),
            bout=result.bout,
            dout_raw=dout_raw,
            dout=dout,
            vin_diff_v=vin_diff_v,
            wave=_interface_wave(tb, result.bout[0]),
        )
        if path is not None:
            write_measurement(path, measurement)
        return measurement

    def metastability(self) -> dict[str, float]:
        """The comparator's regeneration time constant, the time a decision has at the nominal rate
        (the shortest of its sequence's windows), and the input below which it is late there, in LSB:
        the measured delay extrapolated by the time constant, V0 * exp(-(window - t0) / tau)."""
        tb = self.tb(conversions=1, rate_hz=NOMINAL_RATE_HZ, vin_diff=h.Vdc.Params(dc=0.0))
        window_s = float(min(_decision_windows(tb, self.stages + 1)))
        tau_s = self.comp.regeneration_tau_s
        # a delay curve that does not grow as the input falls (a fast latch measured above its
        # regeneration) has no time constant to extrapolate: no input is known to be late
        late_v = (
            self.comp.delay_table_v[0] * math.exp(-(window_s - self.comp.delay_table_s[0]) / tau_s)
            if tau_s > 0
            else math.nan
        )
        return {
            "comp_regeneration_tau_s": tau_s,
            "decision_window_s": window_s,
            "metastable_input_lsb": late_v / (2 * self.full_scale_v / 2**self.params.adc_bits),
        }

    def numbers(self) -> dict[str, float]:
        """The converter's own numbers, which a behavioral run's capture carries among its readbacks
        (``_capture``): its full scale and supply, its slowest settling time constant, its
        reference's decoupling, its DAC drivers' energy a transition (none: not characterized),
        its comparator's noise and delay, and its metastability (``metastability``)."""
        return {
            "full_scale_v": float(self.full_scale_v),
            "supply_v": float(self.supply_v),
            "settling_tau_s": float(self.settling_tau_s),
            "decoupling_f": float(self.decoupling_f),
            "dac_driver_energy_j": float(self.cdac.behavioral().driver_energy_j),
            "comp_noise_v": float(self.comp.noise_v),
            "comp_delay_s": float(self.comp.delay_s),
            **{name: float(value) for name, value in self.metastability().items()},
        }


def _sequence_times(tb: TbParams, decisions: int) -> tuple[np.ndarray, np.ndarray]:
    """Return COMP and post-INIT LOGIC rising times relative to the INIT rise."""

    init, _, comp, logic = tb.rows_from_init
    symbol_s = 1.0 / float(tb.symbol_rate)
    comp_s = _rising(comp) * symbol_s
    logic_s = _rising(logic) * symbol_s
    logic_s = logic_s[logic_s > symbol_s * init.count("1")]
    if len(comp_s) != decisions or len(logic_s) < decisions - 1:
        raise ValueError(f"sequence must contain {decisions} COMP and {decisions - 1} LOGIC rises after INIT")
    return comp_s, logic_s[: decisions - 1]


def _rising(row: str) -> np.ndarray:
    """The symbols at which a row rises (cyclically: a rise at symbol 0 where it ends low)."""
    bits = np.asarray([int(bit) for bit in row])
    return np.flatnonzero((bits == 1) & (np.roll(bits, 1) == 0))


def _decision_windows(tb: TbParams, decisions: int) -> np.ndarray:
    """Return, for each COMP rise, the time until the comparator resets (COMP falls) or the SAR
    logic reads it (LOGIC rises), whichever comes first, wrapping into the next conversion."""

    _, _, comp_row, logic_row = tb.rows_from_init
    symbol_s = 1.0 / float(tb.symbol_rate)
    comp = np.asarray([int(bit) for bit in comp_row])
    logic = np.asarray([int(bit) for bit in logic_row])
    rises = np.flatnonzero((comp == 1) & (np.roll(comp, 1) == 0))
    ends = np.flatnonzero(((comp == 0) & (np.roll(comp, 1) == 1)) | ((logic == 1) & (np.roll(logic, 1) == 0)))
    if len(rises) != decisions or not len(ends):
        raise ValueError(f"sequence must contain {decisions} COMP rises and a COMP fall or LOGIC rise")
    # symbols from each rise to every end, the next conversion's ends a whole conversion later
    after = (ends[None, :] - rises[:, None] - 1) % len(comp) + 1
    return np.min(after, axis=1) * symbol_s


def _salogic(tb: TbParams, state: dict[str, np.ndarray], stage: int, decided: np.ndarray):
    """Write the counted stage from the decision, or reload the B state; return the new state."""

    after = {}
    for side, target in (("p", 1 - decided), ("n", decided)):
        after[side] = state[side].copy()
        if tb.dac_mode:
            after[side][:, stage] = target
        else:
            after[side][:] = np.asarray(getattr(tb, f"dac_bstate_{side}"), dtype=np.int64)
    return after


def _convert(
    params: _Behavioral, vin_diff_v: np.ndarray, vin_diff_slope_v_per_s: np.ndarray | None = None
) -> _Conversions:
    """Convert one differential input per conversion, in order, through the four blocks.

    ``vin_diff_slope_v_per_s`` is the input slope at each sampling instant;
    the sampler's tracking lag needs it, and it defaults to a static input.
    """

    tb = params.tb
    vin_diff_v = np.asarray(vin_diff_v, dtype=np.float64)
    conversions = len(vin_diff_v)
    stages = len(capdac.Model.weights(tb.params.cdac))
    comp_s, logic_s = _sequence_times(tb, stages + 1)
    windows_s = _decision_windows(tb, stages + 1)
    stage_tau_s = params.cdac.stage_tau_s or (params.cdac.settling_tau_s,) * stages
    stage_delay_s = params.cdac.stage_delay_s or (0.0,) * stages
    initial = {side: np.asarray(getattr(tb, f"dac_astate_{side}"), dtype=np.int64) for side in ("p", "n")}
    if any(len(value) != stages for value in initial.values()):
        raise ValueError(f"A states must hold one value per capacitor ({stages})")
    rng = np.random.default_rng(params.seed)
    # the reference's noise draws from a stream of its own, so the other sources draw alike with and
    # without it
    reference_rng = rng.spawn(1)[0]
    vin_cm_v = float(tb.vin_cm.dc)
    slope = np.zeros(conversions) if vin_diff_slope_v_per_s is None else np.asarray(vin_diff_slope_v_per_s)
    caps = {side: capdac.Model.plates_f(params.cdac, side, tb.params.cdac, float(tb.vdd_dac.dc)) for side in ("p", "n")}
    parasitic_f = params.cdac.parasitic_f
    load_f = {side: float(np.sum(main_f) + np.sum(diff_f)) + parasitic_f for side, (main_f, diff_f) in caps.items()}
    vref_v, diffcaps = float(tb.vdd_dac.dc), int(tb.dac_diffcaps)
    top = samp_model.Model.sample(
        tb.params.samp,
        params.samp,
        {"p": vin_cm_v + vin_diff_v / 2, "n": vin_cm_v - vin_diff_v / 2},
        {"p": slope / 2, "n": -slope / 2},
        load_f=load_f,
        gate_v=float(tb.vdd_d.dc),
        rng=rng,
    )
    sampled = {side: top[side].copy() for side in ("p", "n")}
    state = {side: np.broadcast_to(initial[side], (conversions, stages)).copy() for side in ("p", "n")}
    dac_charge = np.zeros(conversions)
    transitions = np.zeros(conversions)
    writes = np.zeros(conversions)
    steps: list[tuple[float, float, np.ndarray]] = []
    bout = np.empty((conversions, stages + 1), dtype=np.uint8)
    # the comparator's SR latch holds its last decision: the previous conversion's last, a coin
    # toss here, before the first
    held = rng.integers(0, 2, conversions)
    # each side's capacitance whose bottom plates sit at the reference (main and difference plates),
    # kept up to date stage by stage
    at_main_f = {side: state[side] @ caps[side][0] for side in ("p", "n")}
    at_diff_f = {side: (state[side] ^ diffcaps) @ caps[side][1] for side in ("p", "n")}
    # the reference node's dip below its value, each conversion's, as of dip_s: every switch draws its
    # charge from the decoupling capacitance and the driver restores it with R C; the node has
    # recovered over the sampling phase by the first decision
    reference_tau_s = params.cdac.reference_r_ohm * params.cdac.reference_c_f
    droop = reference_tau_s > 0
    dip = np.zeros(conversions)
    dip_s = 0.0
    for decision in range(stages + 1):
        # Unsettled remainders of earlier updates decay with one time constant.
        seen = top["p"] - top["n"]
        if params.cdac.reference_noise_v or droop:
            # the reference's error (its dip, a noise sample) reaches each top plate through the
            # fraction of its load whose bottom plates sit at the reference
            reference_v = dip * np.exp(-(comp_s[decision] - dip_s) / reference_tau_s) if droop else 0.0
            if params.cdac.reference_noise_v:
                reference_v = reference_v + reference_rng.normal(0.0, params.cdac.reference_noise_v, conversions)
            for side, sign in (("p", 1.0), ("n", -1.0)):
                main_f, diff_f = caps[side]
                at_vref_f = state[side] @ main_f + (state[side] ^ diffcaps) @ diff_f
                seen = seen + sign * reference_v * at_vref_f / load_f[side]
        # each stage's step starts after its driver's delay and settles with its own time constant;
        # one not yet started is missing whole. A step 36 time constants on (2e-16 of itself, below a
        # double's resolution of it) or without settling is done and leaves the list
        unsettled = []
        for start_s, tau_s, step in steps:
            elapsed_s = comp_s[decision] - start_s
            if elapsed_s < 0:
                seen = seen - step
                unsettled.append((start_s, tau_s, step))
            elif tau_s > 0 and elapsed_s < 36 * tau_s:
                seen = seen - step * np.exp(-elapsed_s / tau_s)
                unsettled.append((start_s, tau_s, step))
        steps = unsettled
        decided = comp_model.Model.compare(
            tb.params.comp, params.comp, seen, rng, vin_cm_v=vin_cm_v, window_s=float(windows_s[decision]), held=held
        )
        bout[:, decision] = decided
        held = decided
        if decision == stages:
            break
        differential_step = np.zeros(conversions)
        step_charge = np.zeros(conversions)
        if tb.dac_mode:
            # the counted stage alone switches: its column, in place
            for side, target in (("p", 1 - decided), ("n", decided)):
                main_f, diff_f = caps[side]
                before = state[side][:, decision].copy()
                state[side][:, decision] = target
                at_main_f[side] += (target - before) * main_f[decision]
                at_diff_f[side] += ((target ^ diffcaps) - (before ^ diffcaps)) * diff_f[decision]
                at_vref_f = at_main_f[side] + at_diff_f[side]
                top_step, charge, toggled = capdac.Model.switch_stage(
                    main_f, diff_f, parasitic_f, vref_v, diffcaps, decision, before, target, at_vref_f
                )
                top[side] = top[side] + top_step
                dac_charge += charge
                step_charge += charge
                transitions += toggled
                writes += target != before
                differential_step += top_step if side == "p" else -top_step
        else:
            after = _salogic(tb, state, decision, decided)
            for side in ("p", "n"):
                main_f, diff_f = caps[side]
                top_step, charge, toggled = capdac.Model.switch(
                    main_f, diff_f, parasitic_f, vref_v, diffcaps, state[side], after[side]
                )
                top[side] = top[side] + top_step
                dac_charge += charge
                step_charge += charge
                transitions += toggled
                writes += np.sum(after[side] != state[side], axis=1)
                differential_step += top_step if side == "p" else -top_step
                at_main_f[side] = after[side] @ caps[side][0]
                at_diff_f[side] = (after[side] ^ diffcaps) @ caps[side][1]
            state = after
        switch_s = logic_s[decision] + stage_delay_s[decision]
        steps.append((switch_s, stage_tau_s[decision], differential_step))
        if droop:
            dip = dip * np.exp(-(switch_s - dip_s) / reference_tau_s) - step_charge / params.cdac.reference_c_f
            dip_s = switch_s

    # INIT reloads the A state with floating top plates, then SAMP forces them
    # to the new input; both edges start from the previous conversion's end.
    for side in ("p", "n"):
        previous_state = np.roll(state[side], 1, axis=0)
        init_state = np.broadcast_to(initial[side], (conversions, stages))
        main_f, diff_f = caps[side]
        top_step, charge, toggled = capdac.Model.switch(
            main_f, diff_f, parasitic_f, vref_v, diffcaps, previous_state, init_state
        )
        at_vref_f = init_state @ main_f + (init_state ^ diffcaps) @ diff_f
        dac_charge += charge - at_vref_f * (sampled[side] - (np.roll(top[side], 1) + top_step))
        transitions += toggled
        writes += np.sum(init_state != previous_state, axis=1)

    # Two registers per stage hold the P and N states and one the one-hot
    # stage counter, whose bits each rise and fall once per conversion. Every
    # LOGIC edge, including the INIT load, clocks all registers.
    registers = 3 * stages
    logic_edges = stages + 1
    writes += 2 * stages
    return _Conversions(
        bout=bout,
        energy_j={
            "vdd_a": np.full(conversions, params.comp.decision_energy_j * (stages + 1)),
            "vdd_d": registers * logic_edges * params.salogic.clock_energy_j + writes * params.salogic.write_energy_j,
            "vdd_dac": float(tb.vdd_dac.dc) * dac_charge + transitions * params.cdac.driver_energy_j,
        },
        static_power_w={
            "vdd_a": params.comp.static_power_w,
            "vdd_d": registers * params.salogic.register_static_w,
            "vdd_dac": 4 * stages * params.cdac.driver_static_w,
        },
    )
