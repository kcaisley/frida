"""ALIGN design directory for a netlist from elsewhere (the layout compiler's,
``flow/layout/compile.py``): text, so its MOS lines are made ALIGN's here (w per finger, ``ng`` as
``nf``, ``far`` where a terminal is on the other type's supply, unused ports dropped), and ALIGN
places it on its own. A block's own netlists come from its module through hdl21 and vlsir
(``flow.circuit.netlists``), placed as its generator states.

Writes <out_dir>/<name>/<name>.sp (the netlist, its subcircuit renamed to ``name``) and
<name>.const.json: the supplies, a roughly square outline, ALIGN's own compiler defaults
(parallel and series devices merged, library primitives, arrays) and its symmetry detection
unless ``symmetric`` is False. The standard cells the netlist uses are defined by their
transistors (``std_subckts``: library SPICE, names made parseable) with a Generator annotation:
ALIGN keeps each one a leaf (primitives/stdcell.py draws it) and knows its inputs are gates and
its outputs drains.

Run bound to a PDK (flow/layout/pdkproc.py); flow/layout/build.py calls ``make_design``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import netcells
from paths import STD_SPICE


def std_subckts(cells: set[str]) -> str:
    """The cells' .subckt blocks for ALIGN: transistors only, '-' in names replaced."""
    out, keep = [], False
    for line in STD_SPICE.read_text().splitlines():
        f = line.split()
        if f and f[0].lower() == ".subckt":
            keep = f[1] in cells
            if keep:  # ALIGN reads the annotation only after a lower-case .subckt
                out += [" ".join([".subckt", *f[1:]]), f"* @: Generator(name='{f[1]}')"]
            continue
        if keep and f and f[0].lower() == ".ends":
            out.append(".ends")
            keep = False
        elif keep and f and f[0][0] in "Mm":
            out.append(_nf(line.replace("-", "_")).rstrip())
    return "\n".join(out) + "\n"


def _nf(line: str) -> str:
    """ALIGN knows fingers as nf: rename a PDK's ng."""
    return re.sub(r"(?i)\bng=", "nf=", line)


def _used_ports(src: str) -> str:
    """The netlist with the ports no instance connects left out of its .subckt line: a block's
    unused options leave ports dangling, which ALIGN places at the origin as terminals with no pin
    and then routes around (LVS compares the connected ones)."""

    lines = src.splitlines()
    used = {net for line in lines if line[:1] in "Mm" for net in line.split()[1:5]}  # drain, gate, source, bulk
    used |= {net for line in lines if line[:1] in "Xx" for net in line.split()[1:-1]}  # a library cell's pins
    out = []
    for line in lines:
        f = line.split()
        if f and f[0].lower() == ".subckt":
            line = " ".join([*f[:2], *(port for port in f[2:] if port in used or port in ("vdd", "vss"))])
        out.append(line)
    return "\n".join(out) + "\n"


FAR_BITS = {"D": 1, "G": 2, "S": 4}  # the far parameter's bit per terminal


def _far(line: str) -> str:
    """A MOS line with its terminals on the other type's rail (an NMOS drain or gate on vdd, say)
    flagged in ``far``: ALIGN's primitives see only their own pins, so primitives/mos.py ties them to
    that rail inside the cell (``rowcell.mos_array``'s ``ties``)."""

    f = line.split()
    pol = next((p for p, model in netcells.MODELS.items() if model == f[5]), None)
    far = {"n": "vdd", "p": "vss"}.get(pol)
    bits = sum(bit for term, bit in FAR_BITS.items() if f[1 + "DGS".index(term)] == far)
    return f"{line} far={bits}" if bits else line


def make_design(pdk: str, netlist: Path, out_dir: Path, *, name: str, symmetric: bool = True) -> Path:
    """Write the design directory ``out_dir/<name>`` for ``netlist`` and return it: ALIGN places
    it on its own, with its symmetry search unless ``symmetric`` is False (no symmetry
    constraints: the placer packs for area alone)."""

    src = netlist.read_text()
    # the design is the netlist's last subcircuit (any before it: cells it instantiates): it takes
    # the design's name
    top = re.findall(r"(?im)^\.subckt\s+(\S+)", src)[-1]
    src = re.sub(rf"(?im)^(\.subckt|\.ends)\s+{re.escape(top)}\b", rf"\1 {name}", src)
    src = _used_ports(src)
    src = (
        "\n".join(_far(_nf(l)) if l[:1] in "Mm" else l for l in netcells.per_finger(src).splitlines()) + "\n"
    )  # ALIGN reads w per finger
    std = {f[0]: f[-1] for f in map(str.split, src.splitlines()) if f and f[0][0] in "Xx"}
    const = [
        {"constraint": "PowerPorts", "ports": ["vdd"]},
        {"constraint": "GroundPorts", "ports": ["vss"]},
        {"constraint": "DoNotRoute", "nets": ["vdd", "vss"]},
        # a roughly square block: the placer chooses each primitive's array (gen_param.py, ALIGN's variants)
        {"constraint": "AspectRatio", "ratio_low": 1 / 1.5, "ratio_high": 1.5},
    ]
    if not symmetric:
        const.insert(0, {"constraint": "ConfigureCompiler", "auto_constraint": False})
    # logic is the PDK's library cells; ALIGN's own logic templates, and its transmission gate,
    # would group an NMOS and a PMOS into one primitive the row cells do not draw (one type per
    # primitive): they stay single devices (ALIGN matches its library's names upper-cased)
    const.append({"constraint": "DoNotUseLib", "libraries": ["INV", "INV_B", "STAGE2_INV", "TGATE"]})
    out = out_dir / name
    out.mkdir(parents=True, exist_ok=True)
    # the cells before the block: ALIGN's parser models an unknown cell at its first instance
    (out / f"{name}.sp").write_text(std_subckts(set(std.values())) + "\n" + src)
    (out / f"{name}.const.json").write_text(json.dumps(const, indent=1) + "\n")
    return out
