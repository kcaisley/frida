"""A generic, approximate KLayout LVS for a kit without a deck of its own (``flow.layout.signoff
.open_lvs``'s last resort): MOS devices and their wiring, from the kit's layer table
(``pdk.<pdk>.layout.tech.LAYERS``: OD, PO, CO, NW, PP, the metals ``M<k>``, the vias ``V<k>``, the
pin text ``M<k>.PIN``, the silicide block ``RPO`` or ``SALBLOCK`` where it has one; a kit whose rail
taps are counter-doped names that layer, ``LVS_COUNTER_DOPE``), compared with a CDL source by
KLayout's netlist comparer.

Every transistor is a 4-terminal MOS of class NMOS (diffusion outside the P+ implant, outside the
N-well; its bulk the substrate, tied by P+ taps) or PMOS (P+ diffusion in the N-well; its bulk the
well, tied by N+ taps); a source's diffusion butted against its well's tap reaches it through the
silicide over both, outside a silicide block. The source's MOS models are classed alike by their
polarity (``flow.util.mos_models.polarity``, else the model name's first letter): the flavours (threshold, oxide) are not told apart,
and other devices (resistors, capacitors) are not extracted. So it checks the connectivity and the
transistors' sizes, which is what the post-layout simulation's net mapping needs
(``flow.layout.annotate``), not a foundry's LVS.

    from flow.layout.klayout_lvs import lvs
    lvs(gds, top, source, source_top, tech)  # True where the netlists match; <gds>.lvsdb beside it
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import klayout.db as kdb

from flow.util.mos_models import polarity

LOG = logging.getLogger("klayout.lvs")
CLASSES = {"n": "NMOS", "p": "PMOS"}


def _metals(tech: Any) -> list[int]:
    """The metal levels the kit's table names (``M1``, ``M2`` ...), in order."""
    return sorted(int(key[1:]) for key in tech.LAYERS if re.fullmatch(r"M\d+", key))


def _source(source: str) -> Path:
    """The source as KLayout's SPICE reader takes it, beside it (``<source>.klayout.cdl``): each MOS
    of model class NMOS or PMOS by its polarity; no diode (no class for it); no '-' in an element's
    name, no '@' in any name (both misread)."""
    lines = []
    for line in Path(source).read_text().splitlines():
        fields = line.split()
        if fields and fields[0][0] in "Dd":
            continue
        if fields and fields[0][0] in "Mm" and len(fields) > 5:
            # a kit's LVS names its models its own way (N, P3, nmos_hs_4): the polarity the schematic
            # tools know, else the name's first letter
            kind = polarity(fields[5]) or {"n": "n", "p": "p"}.get(fields[5][:1].lower())
            fields[5] = CLASSES.get(kind or "", fields[5])
            line = " ".join(fields)
        if fields and fields[0][0] in "MmXx":
            line = " ".join([line.split()[0].replace("-", "_"), *line.split()[1:]])
        if fields and not fields[0].startswith("*"):
            line = line.replace("@", "_at_")
        lines.append(line)
    clean = Path(source).with_suffix(".klayout.cdl")
    clean.write_text("\n".join(lines) + "\n")
    return clean


def _unused(netlist: kdb.Netlist) -> None:
    """Leave out each unused transistor, as a foundry deck filters them: one whose source or drain
    reaches nothing but itself (a library's dummy gates over continuous diffusion), again until none
    is left. A real device left open is missing from the comparison, so a mismatch all the same."""
    for circuit in netlist.each_circuit():
        while True:
            unused = []
            for device in circuit.each_device():
                ends = [device.net_for_terminal(t.id()) for t in device.device_class().terminal_definitions()]
                names = [t.name for t in device.device_class().terminal_definitions()]
                for name, net in zip(names, ends, strict=True):
                    lone = net is None or (
                        net.terminal_count() == 1 and net.pin_count() == 0 and net.subcircuit_pin_count() == 0
                    )
                    if name in ("S", "D") and lone:
                        unused.append(device)
                        break
            if not unused:
                break
            for device in unused:
                circuit.remove_device(device)


def lvs(gds: str, top: str, source: str, source_top: str, tech: Any) -> bool:
    """Whether the layout ``gds`` (its cell ``top``) is the source netlist (its subcircuit
    ``source_top``), by the kit's layer table ``tech``; the LVS database written beside the GDS
    (``<gds>.lvsdb``, which ``flow.layout.annotate`` reads)."""
    layout = kdb.Layout()
    layout.read(gds)
    cell = layout.cell(top)
    lvs = kdb.LayoutVsSchematic(kdb.RecursiveShapeIterator(layout, cell, []))

    def layer(key: str, name: str) -> kdb.Region:
        number, datatype = tech.LAYERS[key]
        return lvs.make_polygon_layer(layout.layer(number, datatype), name)

    od, po, co, pp, nw = (layer(key, key.lower()) for key in ("OD", "PO", "CO", "PP", "NW"))
    block_key = next((key for key in ("RPO", "SALBLOCK") if key in tech.LAYERS), None)
    block = layer(block_key, "block") if block_key else kdb.Region()
    levels = _metals(tech)
    metals = [layer(f"M{k}", f"m{k}") for k in levels]
    vias = [layer(f"V{k}", f"v{k}") for k in levels[:-1] if f"V{k}" in tech.LAYERS]
    texts = [
        lvs.make_text_layer(layout.layer(*tech.LAYERS[f"M{k}.PIN"]), f"t{k}") if f"M{k}.PIN" in tech.LAYERS else None
        for k in levels
    ]

    # a kit whose rail taps take the implant of the other half under a counter-dope region (its
    # ``LVS_COUNTER_DOPE`` layer: TPSC65's CD) has its taps' polarity swapped there
    counter_key = getattr(tech, "LVS_COUNTER_DOPE", None)
    counter = layer(counter_key, "counter") if counter_key else kdb.Region()
    # a kit's dummy poly (``LVS_DUMMY_POLY``: layer keys of poly that crosses diffusion without
    # making a transistor, a 28 nm library's cell-edge gates) is no gate
    dummy = kdb.Region()
    for key in getattr(tech, "LVS_DUMMY_POLY", ()):
        dummy |= layer(key, key.lower())
    # a gate splits its diffusion: poly over a diffusion's end (a library cell's edge poly, diffusion
    # on one side alone) makes no transistor
    gate = (po & od).interacting(od - po, 2).not_interacting(dummy)
    pactive = (od & pp & nw) - counter
    nactive = ((od - pp) - nw) - counter
    psd, nsd = pactive - gate, nactive - gate
    ptap = (((od & pp) - nw) - counter) | (((od - pp) - nw) & counter)
    ntap = (((od - pp) & nw) - counter) | ((od & pp & nw) & counter)
    sub = kdb.Region(cell.bbox().enlarged(1000)) - nw  # the p-substrate
    # a kit whose library ties its wells by tap cells alone (``LVS_BUTTED_TAPS = False``) butts no tap
    butted = getattr(tech, "LVS_BUTTED_TAPS", True)
    butt_n = (nsd.sized(1) & ptap) - block if butted else kdb.Region()
    butt_p = (psd.sized(1) & ntap) - block if butted else kdb.Region()
    for name, region in (
        ("gate", gate),
        ("psd", psd),
        ("nsd", nsd),
        ("ptap", ptap),
        ("ntap", ntap),
        ("sub", sub),
        ("butt_n", butt_n),
        ("butt_p", butt_p),
    ):
        lvs.register(region, name)
    lvs.extract_devices(
        kdb.DeviceExtractorMOS4Transistor(CLASSES["p"]), {"SD": psd, "G": gate & pactive.sized(1), "P": po, "W": nw}
    )
    lvs.extract_devices(
        kdb.DeviceExtractorMOS4Transistor(CLASSES["n"]), {"SD": nsd, "G": gate & nactive.sized(1), "P": po, "W": sub}
    )

    for region in [psd, nsd, ptap, ntap, butt_n, butt_p, po, co, *metals, *vias, nw, sub]:
        lvs.connect(region)
    for region in (psd, nsd, ptap, ntap, po):
        lvs.connect(region, co)
    lvs.connect(co, metals[0])
    for k, via in enumerate(vias):
        lvs.connect(metals[k], via)
        lvs.connect(via, metals[k + 1])
    for metal, text in zip(metals, texts, strict=True):
        if text is not None:
            lvs.connect(metal, text)
    lvs.connect(ptap, sub)
    lvs.connect(ntap, nw)
    for strip, sd, tap in ((butt_n, nsd, ptap), (butt_p, psd, ntap)):
        lvs.connect(strip, sd)
        lvs.connect(strip, tap)
    lvs.extract_netlist()
    lvs.netlist().flatten()  # the source is flat
    _unused(lvs.netlist())
    lvs.netlist().simplify()
    lvs.netlist().combine_devices()

    ref = kdb.Netlist()
    ref.read(str(_source(source)), kdb.NetlistSpiceReader())
    ref.flatten()
    source_circuit = ref.circuit_by_name(source_top.upper()) or ref.circuit_by_name(source_top)
    for circuit in [c for c in ref.each_circuit() if c.name != source_circuit.name]:
        ref.remove(circuit)  # a library's cells no one calls
    ref.simplify()
    ref.combine_devices()
    lvs.reference = ref
    comparer = kdb.NetlistComparer()
    layout_circuit = lvs.netlist().circuit_by_name(top)
    comparer.same_circuits(layout_circuit, source_circuit)
    ok = lvs.compare(comparer)
    lvs.write(gds + ".lvsdb")
    labelled = {net.name.upper() for net in layout_circuit.each_net() if net.name}
    missing = []
    for pin in source_circuit.each_pin():
        net = source_circuit.net_for_pin(pin.id())
        if net is None or net.terminal_count() + net.subcircuit_pin_count() == 0:
            continue
        name = (pin.name() or net.name or "").upper()
        if name and name not in labelled:
            missing.append(name)
            LOG.warning(f"port {name}: connected in the source, no label on its net in the layout")
    return ok and not missing
