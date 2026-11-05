"""A block's netlists from its one hdl21 module, exported by vlsir as the simulators' netlists are
(after Fritchman's AlignHdl21: one module compiled for each context, ALIGN | LVS | SIM).

``compile_block`` elaborates a generator once in a PDK (its device requests resolved,
``flow.layout.devices``; compiled to the PDK's devices). ``package`` exports it (``hdl21.to_proto``)
and puts vlsir's package in a context by passes on its data, none on netlist text:

* both: the top named for the netlist; each library cell called as itself (hdl21's wrapper around
  it inlined); each instance's own name without its element letter, lower case (the netlister
  writes the letter, upper case: ``Mdiff_p``, ``Xdrive_p``); nets and ports lower case.
* ALIGN: each MOM unit called as the PDK's first-class device (``fmomcap``, its design values and
  its generator's parameters on the call, ``flow/layout/primitives/models.py``); each row cell's
  subcircuit under its generator's annotation; each MOS as ALIGN reads it (width per finger, all
  fingers in ``nf``, ``far`` where a terminal is on the other type's supply), split into the parts
  its placement names (``hdl21align.halves``).
* LVS: each MOM unit as the devices the PDK's deck recognizes in it (``mom_devices``), each MOS
  as the deck reads it (``mos``), both the kit's rules (``pdk/<pdk>/netlist/lvs.py``, ``kit_lvs``);
  no annotation.

``write`` netlists a package with vlsirtools' CDL netlister (``*.PININFO`` with each port's
direction), after the PDK's library text the context needs (ALIGN: the standard cells' transistors;
LVS: their subcircuits and the MOM devices' library).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum, auto
from importlib import import_module
from io import StringIO
from pathlib import Path
from typing import Any

import hdl21 as h
import vlsir.circuit_pb2 as vckt
import vlsir.utils_pb2 as vutils
import vlsirtools
from hdl21.primitives import C, Mos  # noqa: F401  (hdl21's devices, as the passes see them)

from flow.layout.hdl21align import own_name

LOG = logging.getLogger("flow.netlist")


class Context(Enum):
    """What a netlist of a block is written for: ALIGN's layout or LVS (simulation is hdl21's own)."""

    ALIGN = auto()
    LVS = auto()


# an element's letter by vlsir's spice type (SPICE reads the type from it)
_LETTER = {
    vckt.SpiceType.SUBCKT: "x",
    vckt.SpiceType.RESISTOR: "r",
    vckt.SpiceType.CAPACITOR: "c",
    vckt.SpiceType.INDUCTOR: "l",
    vckt.SpiceType.MOS: "m",
    vckt.SpiceType.DIODE: "d",
    vckt.SpiceType.BIPOLAR: "q",
}
_SI = {"YOCTO": -24, "ZEPTO": -21, "ATTO": -18, "FEMTO": -15, "PICO": -12, "NANO": -9, "MICRO": -6, "MILLI": -3}
_SI |= {"CENTI": -2, "DECI": -1, "DECA": 1, "HECTO": 2, "KILO": 3, "MEGA": 6, "GIGA": 9, "TERA": 12, "UNIT": 0}


@dataclass
class Block:
    """A block's module in a PDK (``compile_block``): its generator's, the device requests resolved
    and the devices compiled to the PDK's; its top's name in the netlists and its ports in its
    bundle's order."""

    module: h.Module
    pdk: str
    name: str
    ports: list


def compile_block(generator, params, pdk: str, name: str, nets, seconds: dict | None = None) -> Block:
    """``generator(params)`` in ``pdk`` (``pdk.<pdk>.hdl21``'s logic), its requests resolved and its
    devices compiled; ``seconds``, where given, gets the elaboration's (``parameters``)."""
    from flow.layout.devices.device import resolve

    logic = import_module(f"pdk.{pdk}.hdl21").pdk_logic
    manager = import_module("hdl21.pdk.pdk")._mgr  # hdl21 offers no public way back to "no default set"
    previous = manager.default
    started = time.monotonic()
    try:
        h.pdk.set_default(logic)
        generator.Cache.reset()
        LOG.info(f"hdl21: elaborating {getattr(generator, '__name__', generator)}({params})")
        module = generator(params)
        resolve(module, pdk)
        h.pdk.set_default(logic)
        h.pdk.compile(module, logic)
    finally:
        generator.Cache.reset()
        manager.default = previous
    ports = [module.ports.get(n, s) for n, s in nets.signals.items() if s.vis == h.Visibility.PORT]
    if seconds is not None:
        seconds["parameters"] = round(time.monotonic() - started, 1)
    return Block(module, pdk, name, ports)


# ---------------------------------------------------------------- vlsir data


def number(value: vutils.ParamValue) -> float:
    """A parameter's value as a number (SI-prefixed, a literal or a plain number)."""
    kind = value.WhichOneof("value")
    if kind == "prefixed":
        p = value.prefixed
        digits = getattr(p, p.WhichOneof("number"))
        return float(digits) * 10.0 ** _SI[vutils.SIPrefix.Name(p.prefix)]
    if kind in ("int64_value", "double_value"):
        return float(getattr(value, kind))
    text = str(getattr(value, kind)).strip("'").lower()
    scale = {"f": -15, "p": -12, "n": -9, "u": -6, "m": -3, "k": 3}
    return float(text[:-1]) * 10.0 ** scale[text[-1]] if text[-1:] in scale else float(text)


def literal(text: str) -> vutils.ParamValue:
    return vutils.ParamValue(literal=str(text))


def _params(instance: vckt.Instance) -> dict[str, vutils.ParamValue]:
    return {p.name: p.value for p in instance.parameters}


def _set_params(instance: vckt.Instance, values: dict[str, vutils.ParamValue]) -> None:
    del instance.parameters[:]
    instance.parameters.extend(vutils.Param(name=k, value=v) for k, v in values.items())


def _short(name: str) -> str:
    """A module's name as the netlister writes it (its exporter's path left off)."""
    return name.split(".")[-1]


@dataclass
class _Index:
    """The package's modules by name, external modules by name, what each reference points at."""

    pkg: vckt.Package

    def module(self, name: str) -> vckt.Module | None:
        return next((m for m in self.pkg.modules if m.name == name), None)

    def external(self, ref: vutils.Reference) -> vckt.ExternalModule | None:
        if ref.WhichOneof("to") != "external":
            return None
        q = ref.external
        return next((e for e in self.pkg.ext_modules if e.name.domain == q.domain and e.name.name == q.name), None)

    def letter(self, instance: vckt.Instance) -> str:
        ext = self.external(instance.module)
        return _LETTER.get(ext.spicetype, "x") if ext is not None else "x"


def _external(pkg: vckt.Package, name: str, ports: list[str]) -> vutils.Reference:
    """A reference to the external module ``name`` (a PDK's device or cell, called as a subcircuit),
    declared once in ``pkg``."""
    qualified = vutils.QualifiedName(domain="frida", name=name)
    if not any(e.name.domain == "frida" and e.name.name == name for e in pkg.ext_modules):
        ext = pkg.ext_modules.add()
        ext.name.CopyFrom(qualified)
        ext.spicetype = vckt.SpiceType.SUBCKT
        for port in ports:
            ext.signals.add(name=port, width=1)
            ext.ports.add(signal=port, direction=vckt.Port.Direction.NONE)
    return vutils.Reference(external=qualified)


def _connect(instance: vckt.Instance, conns: dict[str, vckt.ConnectionTarget]) -> None:
    del instance.connections[:]
    for port, target in conns.items():
        c = instance.connections.add(portname=port)
        c.target.CopyFrom(target)


# ---------------------------------------------------------------- passes on the package


def _modules(module: h.Module) -> dict[str, h.Module]:
    """A module's hierarchy by name (hdl21's names: one module a name)."""
    found: dict[str, h.Module] = {}

    def walk(m: h.Module) -> None:
        if m.name in found:
            return
        found[m.name] = m
        for instance in m.instances.values():
            if isinstance(instance.of, h.Module):
                walk(instance.of)

    walk(module)
    return found


def _targets(target: vckt.ConnectionTarget):
    """The signal references a connection holds (one, a slice's, a concatenation's parts)."""
    kind = target.WhichOneof("stype")
    if kind == "concat":
        for part in target.concat.parts:
            yield from _targets(part)
    else:
        yield target


def _lower_target(target: vckt.ConnectionTarget) -> None:
    for t in _targets(target):
        if t.WhichOneof("stype") == "sig":
            t.sig = t.sig.lower()
        elif t.WhichOneof("stype") == "slice":
            t.slice.signal = t.slice.signal.lower()


def _pdk_mos(pkg: vckt.Package) -> None:
    """Each PDK MOS a MOS element (``hdl21align.is_pdk_mos``: its ports ``d g s b``), also where its
    PDK's models are subcircuits, as the layout's and LVS's tools read it."""
    from flow.layout.hdl21align import MOS_PORTS

    for ext in pkg.ext_modules:
        if {p.signal.lower() for p in ext.ports} == MOS_PORTS:
            ext.spicetype = vckt.SpiceType.MOS


def _inline_cells(pkg: vckt.Package) -> None:
    """Each library cell called as itself: a module holding one call of an external subcircuit, on
    its own ports alone (hdl21's wrapper of a PDK's logic cell), left out, its calls made the cell's."""
    index = _Index(pkg)
    wrappers = {}
    for m in pkg.modules:
        if len(m.instances) != 1:
            continue
        (inner,) = m.instances
        ext = index.external(inner.module)
        ports = {p.signal for p in m.ports}
        sigs = {c.portname: c.target.sig for c in inner.connections if c.target.WhichOneof("stype") == "sig"}
        if ext is None or ext.spicetype != vckt.SpiceType.SUBCKT or len(sigs) != len(inner.connections):
            continue
        if not set(sigs.values()) <= ports:
            continue
        wrappers[m.name] = (inner, sigs)
    for m in pkg.modules:
        for instance in m.instances:
            if instance.module.WhichOneof("to") != "local" or instance.module.local not in wrappers:
                continue
            inner, sigs = wrappers[instance.module.local]
            outer = {c.portname: c.target for c in instance.connections}
            instance.module.CopyFrom(inner.module)
            _connect(instance, {cell_port: outer[port] for cell_port, port in sigs.items()})
    keep = [m for m in pkg.modules if m.name not in wrappers]
    del pkg.modules[:]
    pkg.modules.extend(keep)


def _drawn_devices(pkg: vckt.Package, views: dict[str, Any], context: Context) -> None:
    """Each MOM unit (a view of ``views``: hdl21 module name to its geometry and design values)
    called as its device: ALIGN's first-class device (its design values, then its generator's
    parameters), or for LVS the same call (the deck's devices come of it at signoff)."""
    from flow.layout.devices.momcap.geometry import PINS

    for m in pkg.modules:
        for instance in m.instances:
            if instance.module.WhichOneof("to") != "local" or _short(instance.module.local) not in views:
                continue
            geometry, design = views[_short(instance.module.local)]
            pins = [p.lower() for p in PINS[geometry.style]]
            outer = {c.portname.lower(): c.target for c in instance.connections}
            instance.module.CopyFrom(_external(pkg, geometry.device, pins))
            _connect(instance, {pin: outer[pin] for pin in pins})
            values = {**design, **geometry.align_parameters()}
            _set_params(instance, {k: literal(v) for k, v in values.items()})
    keep = [m for m in pkg.modules if _short(m.name) not in views]
    del pkg.modules[:]
    pkg.modules.extend(keep)


def _names(pkg: vckt.Package, top: str) -> None:
    """The top named ``top``; each instance's own name (``own_name``), nets and ports lower case,
    a call of a module of the package by its ports lower case."""
    index = _Index(pkg)
    local = {m.name for m in pkg.modules}
    pkg.modules[-1].name = top
    for m in pkg.modules:
        for s in m.signals:
            s.name = s.name.lower()
        for p in m.ports:
            p.signal = p.signal.lower()
        seen = set()
        for instance in m.instances:
            instance.name = own_name(instance.name, index.letter(instance))
            if (index.letter(instance), instance.name) in seen:
                raise ValueError(f"{m.name}: two instances named {instance.name}")
            seen.add((index.letter(instance), instance.name))
            for c in instance.connections:
                _lower_target(c.target)
                if instance.module.WhichOneof("to") == "local" and instance.module.local in local:
                    c.portname = c.portname.lower()


def _row_cells(pkg: vckt.Package, cells: dict[str, tuple[str, dict]]) -> None:
    """Each row cell's subcircuit under its generator's annotation (``cells``: module to generator
    and its parameters, which ALIGN hands the generator with the cell's devices)."""
    for m in pkg.modules:
        generator, parameters = cells.get(_short(m.name), (None, {}))
        if generator:
            extra = f", parameters={parameters!r}" if parameters else ""
            m.literals.append(f"* @: Generator(name='{generator}'{extra})")


def _mos_for_align(pkg: vckt.Package, w_per_finger: bool, models: dict[str, str], supplies: dict[str, tuple]) -> None:
    """Each MOS as ALIGN reads it: its width per finger and all its fingers in ``nf`` (``m`` one),
    ``far`` where a terminal is on the other type's supply (bits D 1, G 2, S 4; flow/layout/primitives/
    mos.py ties it inside the cell)."""
    index = _Index(pkg)
    bits = {"d": 1, "g": 2, "s": 4}
    for m in pkg.modules:
        power, ground = supplies.get(_short(m.name), ({"vdd"}, {"vss"}))
        for instance in m.instances:
            ext = index.external(instance.module)
            if ext is None or ext.spicetype != vckt.SpiceType.MOS:
                continue
            p = {k.lower(): v for k, v in _params(instance).items()}
            fingers = int(number(p.get("nf", p.get("ng", literal("1")))))
            count = fingers * int(number(p.get("m", literal("1"))))
            w = number(p["w"]) if w_per_finger else number(p["w"]) / fingers
            values = {"w": literal(f"{round(w * 1e9)}n"), "l": literal(f"{round(number(p['l']) * 1e9)}n")}
            values |= {"nf": literal(str(count)), "m": literal("1")}
            far_net = power if ext.name.name == models.get("n") else ground
            nets = {
                c.portname.lower(): c.target.sig for c in instance.connections if c.target.WhichOneof("stype") == "sig"
            }
            far = sum(bit for term, bit in bits.items() if nets.get(term) in far_net)
            if far:
                values["far"] = literal(str(far))
            _set_params(instance, values)


def _split(pkg: vckt.Package, splits: dict[str, dict[str, int]]) -> None:
    """Each device its placement splits (``splits``: module to netlist name to parts) as its parts,
    ``<name>_a`` ..., its fingers shared out."""
    index = _Index(pkg)
    for m in pkg.modules:
        parts = splits.get(_short(m.name), {})
        if not parts:
            continue
        out = []
        for instance in m.instances:
            n = parts.get(index.letter(instance).upper() + instance.name)
            if not n:
                out.append(instance)
                continue
            p = _params(instance)
            fingers = int(number(p["nf"]))
            if fingers % n:
                raise ValueError(f"{m.name}.{instance.name}: {fingers} fingers do not split into {n} parts")
            for k in range(n):
                part = vckt.Instance()
                part.CopyFrom(instance)
                part.name = f"{instance.name}_{chr(ord('a') + k)}"
                _set_params(part, {**p, "nf": literal(str(fingers // n))})
                out.append(part)
        del m.instances[:]
        m.instances.extend(out)


def _used_ports(pkg: vckt.Package) -> None:
    """The top's ports some instance connects: a block's unused option leaves a port dangling,
    which ALIGN would place at the origin as a terminal with no pin."""
    top = pkg.modules[-1]
    used = {
        t.sig if t.WhichOneof("stype") == "sig" else t.slice.signal
        for i in top.instances
        for c in i.connections
        for t in _targets(c.target)
    }
    keep = [p for p in top.ports if p.signal in used]
    del top.ports[:]
    top.ports.extend(keep)


def kit_lvs(pdk: str, mos: list[tuple], mom: list[tuple], cells: list[str]) -> tuple[list, list, str]:
    """The kit's LVS rules (``pdk/<pdk>/netlist/lvs.py``, run in a process bound to ``pdk``): for
    each MOS (its model, total width and length, metres) the deck's device and parameters, or None
    (as compiled); for each MOM unit (its style, metals, finger lengths) the devices the deck reads
    in it (none: plain metal to the deck); the library text the source calls (``cells``' and the
    devices' subcircuits)."""
    kit = import_module(f"pdk.{pdk}.netlist.lvs")
    mos_rule, mom_rule = getattr(kit, "mos", None), getattr(kit, "mom_devices", None)
    mos_out = [mos_rule(*r) if mos_rule else None for r in mos]
    mom_out = [list(mom_rule(*r)) if mom_rule else [] for r in mom]
    devices = {device for found in mom_out for _, device, _ in found}
    return mos_out, mom_out, kit.library(set(cells), devices)


def _microns(value_m: float) -> vutils.ParamValue:
    return literal(f"{round(value_m * 1e6, 6):g}u")


def _for_lvs(pkg: vckt.Package, pdk: str) -> str:
    """Each MOS as the PDK's deck reads it (its total width, ``kit_lvs``), each MOM unit as the
    devices the deck reads in it (named ``<unit>_<terminal>``, between the unit's top plate and
    that finger's net, over its shield), or none; returns the library text the source calls."""
    from flow.layout.devices.momcap.geometry import DEVICES
    from flow.layout.pdkproc import in_pdk

    index = _Index(pkg)
    moms = set(DEVICES.values())
    mos_at, mom_at = [], []
    for m in pkg.modules:
        for at, instance in enumerate(m.instances):
            ext = index.external(instance.module)
            if ext is None:
                continue
            p = {k.lower(): v for k, v in _params(instance).items()}
            if ext.spicetype == vckt.SpiceType.MOS:
                total = number(p["w"]) * number(p.get("m", literal("1")))
                mos_at.append((instance, ext, (ext.name.name, total, number(p["l"]))))
            elif ext.name.domain == "frida" and ext.name.name in moms:
                text = {k: str(getattr(v, v.WhichOneof("value"))).strip("'") for k, v in p.items()}
                spec = (
                    text["style"].lower(),
                    int(text["layers"]),
                    int(text["length"]),
                    int(text.get("diff_length", 0)),
                )
                mom_at.append(((m.name, at), instance, spec))
    mos, mom, library = in_pdk(
        pdk,
        "flow.circuit.netlists",
        "kit_lvs",
        pdk,
        [r for *_, r in mos_at],
        [r for *_, r in mom_at],
        library_cells(pkg),
    )
    for (instance, ext, _), found in zip(mos_at, mos, strict=True):
        if found is None:
            continue
        model, values = found
        if model != ext.name.name:
            device = pkg.ext_modules.add()
            device.CopyFrom(ext)
            device.name.name = model
            instance.module.CopyFrom(vutils.Reference(external=device.name))
        _set_params(instance, {k: _microns(v) for k, v in values.items()})
    replaced: dict[tuple[str, int], list[vckt.Instance]] = {}
    for (where, instance, _), found in zip(mom_at, mom, strict=True):
        conns = {c.portname.lower(): c.target for c in instance.connections}
        parts = replaced[where] = []
        for terminal, model, c_f in found:
            part = vckt.Instance(name=f"{instance.name}_{terminal}")
            part.module.CopyFrom(_external(pkg, model, ["top", "inner", "shield"]))
            _connect(part, {"top": conns["top"], "inner": conns[terminal], "shield": conns["shield"]})
            _set_params(part, {"c": literal(f"{c_f:.6e}")})
            parts.append(part)
    for m in pkg.modules:
        if not any(name == m.name for name, _ in replaced):
            continue
        out = []
        for at, instance in enumerate(m.instances):
            if (m.name, at) in replaced:
                out += replaced[m.name, at]
            else:
                kept = vckt.Instance()
                kept.CopyFrom(instance)
                out.append(kept)
        del m.instances[:]
        m.instances.extend(out)
    # the MOM units' own device declarations are no call's now
    called = {(i.module.external.domain, i.module.external.name) for m in pkg.modules for i in m.instances}
    keep = [e for e in pkg.ext_modules if (e.name.domain, e.name.name) in called]
    del pkg.ext_modules[:]
    pkg.ext_modules.extend(keep)
    return library


# ---------------------------------------------------------------- the netlists


def package(block: Block, context: Context, splits: dict[str, dict[str, int]] | None = None) -> vckt.Package:
    """The block's vlsir package in ``context``: exported (``hdl21.to_proto``) and passed through
    (module docstring); ``splits`` (ALIGN: module to netlist name to parts) from its placements."""
    from flow.layout.devices.device import AlignDrawn, geometry_of
    from flow.layout.pdkproc import pdk_value
    from flow.layout.rows import mosline

    modules = _modules(block.module)
    views, cells = {}, {}
    for name, m in modules.items():
        geometry = geometry_of(m)
        if isinstance(geometry, AlignDrawn):
            if getattr(geometry, "netlist_devices", False):
                cells[name] = (geometry.align_generator, geometry.align_parameters())
            else:
                views[name] = (geometry, dict(m.props.get("design") or {}))
    pkg = h.to_proto(block.module)
    _pdk_mos(pkg)
    _inline_cells(pkg)
    _drawn_devices(pkg, views, context)
    _names(pkg, block.name)
    if context is Context.ALIGN:
        root = Path(__file__).resolve().parents[2]
        supplies = {name: _supplies(m) for name, m in modules.items()}
        supplies[block.name] = _supplies(block.module)
        models = pdk_value(block.pdk, "tech", "MODELS", {})
        _row_cells(pkg, cells)
        _mos_for_align(pkg, mosline.w_per_finger(root / "pdk" / block.pdk), models, supplies)
        _split(pkg, splits or {})
        _used_ports(pkg)
    return pkg


def _supplies(module: h.Module) -> tuple[set[str], set[str]]:
    """A module's power and ground nets, by its ports' usage."""
    power = {n.lower() for n, p in module.ports.items() if getattr(p, "usage", None) == h.Usage.POWER}
    ground = {n.lower() for n, p in module.ports.items() if getattr(p, "usage", None) == h.Usage.GROUND}
    return power or {"vdd"}, ground or {"vss"}


def library_cells(pkg: vckt.Package) -> list[str]:
    """The PDK's library cells the package calls (external subcircuits not frida's own devices)."""
    return sorted(
        {e.name.name for e in pkg.ext_modules if e.spicetype == vckt.SpiceType.SUBCKT and e.name.domain != "frida"}
    )


def write(pkg: vckt.Package, path: Path, library: str = "") -> Path:
    """The package as a CDL netlist at ``path`` (vlsirtools' ``CdlNetlister``), after ``library``
    (the PDK's library text the netlist calls)."""
    out = StringIO()
    vlsirtools.netlist(pkg, out, fmt="cdl")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((library.rstrip("\n") + "\n\n" if library else "") + out.getvalue())
    return path


def lvs_source(block: Block, path: Path) -> Path:
    """The block's LVS source at ``path``: its netlist in the LVS context (``_for_lvs``), after the
    library text it calls (the standard cells' subcircuits, the MOM devices' library)."""
    pkg = package(block, Context.LVS)
    return write(pkg, path, _for_lvs(pkg, block.pdk))


# ---------------------------------------------------------------- ALIGN's design directory

# ALIGN compiles a placed module as its plan states it: no constraints of its own, nothing merged or
# identified, each group a subcircuit of its own told the same
COMPILER = {
    "constraint": "ConfigureCompiler",
    "auto_constraint": False,
    "merge_series_devices": False,
    "merge_parallel_devices": False,
    "remove_dummy_hierarchies": False,
    "identify_array": False,
    "propagate": True,
}
# logic is the PDK's library cells: ALIGN's own logic templates and its transmission gate would group
# an NMOS and a PMOS into one primitive the row cells do not draw (one type a primitive)
NO_LOGIC_TEMPLATES = {"constraint": "DoNotUseLib", "libraries": ["INV", "INV_B", "STAGE2_INV", "TGATE"]}


def _constraints(pkg: vckt.Package, m: vckt.Module, module: h.Module | None, plan: dict | None) -> list[dict]:
    """A module's ``.const.json``: its supplies (its ports' usage); where it states its layout
    (``plan``, ``hdl21align.module_plan``) the compiler's settings, its groups, its rows as a
    Floorplan, its devices in no group left unidentified (ALIGN would pair them by their
    connections alone), its own constraints, Stackups last (appended, one lifts the non-overlap
    ALIGN's consistency check holds, and the next re-checks the whole module at once); else ALIGN
    places it, in a roughly square outline."""
    power, ground = _supplies(module) if module is not None else ({"vdd"}, {"vss"})
    ports = {p.signal for p in m.ports}
    power, ground = sorted(power & ports), sorted(ground & ports)
    stated = plan["constraints"] if plan is not None else []
    # one DoNotRoute list a module, the supplies' and the module's own nets: ALIGN's reader keeps
    # the last list it reads, not their union
    unrouted = [*power, *ground]
    unrouted += [n for s in stated if s["constraint"] == "DoNotRoute" for n in s["nets"] if n not in unrouted]
    supplies = [
        *([{"constraint": "PowerPorts", "ports": power}] if power else []),
        *([{"constraint": "GroundPorts", "ports": ground}] if ground else []),
        *([{"constraint": "DoNotRoute", "nets": unrouted}] if unrouted else []),
    ]
    if plan is None:
        return [*supplies, {"constraint": "AspectRatio", "ratio_low": 1 / 1.5, "ratio_high": 1.5}, NO_LOGIC_TEMPLATES]
    index = _Index(pkg)
    present = {index.letter(i).upper() + i.name for i in m.instances}
    groups = [dict(c) for c in stated if c["constraint"] == "GroupBlocks"]
    for group in groups:
        inner = group.get("constraints") or []
        if not any(c["constraint"] == "ConfigureCompiler" for c in inner):
            group["constraints"] = [COMPILER, *inner]
    known = present | {g["instance_name"] for g in groups}
    rows = [[n for n in r if n in known] for r in plan["rows"]]
    const = [COMPILER, *supplies, *groups]
    if sum(len(r) for r in rows) > 1:  # one instance: nothing to place (ALIGN refuses it)
        const.append(
            {
                "constraint": "Floorplan",
                "regions": [r for r in rows if r],
                "order": True,
                "symmetrize": plan["symmetric"],
            }
        )
    grouped = {member for g in groups for member in g["instances"]}
    loose = sorted(n for n in present if n[:1] == "M" and n not in grouped)
    if loose:
        const.append({"constraint": "DoNotIdentify", "instances": loose})
    const += [c for c in stated if c["constraint"] not in ("GroupBlocks", "DoNotRoute")]
    const.append(NO_LOGIC_TEMPLATES)
    return [c for c in const if c["constraint"] != "Stackup"] + [c for c in const if c["constraint"] == "Stackup"]


def align_design(block: Block, out_dir: Path, placed: bool = True) -> tuple[Path, list[str]]:
    """ALIGN's design directory for the block, ``out_dir/<name>``: its netlist in the ALIGN context
    (``<name>.sp``, after the PDK's standard cells' transistors, each a primitive of its own), and
    a ``<subckt>.const.json`` for each module that is no primitive: its stated layout, or none
    (``placed`` False: ALIGN places every module). Returns it and the library cells the netlist calls."""
    from flow.layout.hdl21align import module_plan, pnr_inputs
    from flow.layout.pdkproc import in_pdk

    plans = {pnr.module.name: module_plan(pnr) for pnr in pnr_inputs(block.module)} if placed else {}
    netlist_names = {block.module.name: block.name}
    splits = {netlist_names.get(n, n): p["split"] for n, p in plans.items() if p["split"]}
    pkg = package(block, Context.ALIGN, splits)
    cells = library_cells(pkg)
    library = in_pdk(block.pdk, "flow.layout.make_design", "std_subckts", set(cells)) if cells else ""
    design = Path(out_dir) / block.name
    write(pkg, design / f"{block.name}.sp", library)
    by_subckt = {netlist_names.get(n, n): m for n, m in _modules(block.module).items()}
    for m in pkg.modules:
        if any(line.startswith("* @: Generator") for line in m.literals):
            continue  # a primitive: its generator draws it
        module = by_subckt.get(_short(m.name))
        plan = plans.get(module.name) if module is not None else None
        const = _constraints(pkg, m, module, plan)
        (design / f"{_short(m.name)}.const.json").write_text(json.dumps(const, indent=1) + "\n")
    LOG.info(
        f"ALIGN's input: {design}: {len(pkg.modules)} subcircuits, {len(plans)} placed, {len(cells)} library cells"
    )
    return design, cells
