"""ALIGN design directory for a design in standard-cell rows, from a shared floorplan.

Writes <out_dir>/<name>/<name>.sp (the netlist, its subcircuit renamed to ``name``) and
<name>.const.json: with a floorplan, its rows as ALIGN's Floorplan constraint (top first,
ordered, and mirrored unless the floorplan says ``"symmetric": false``), the netlist split as it
says, vdd/vss left to the rails.

The standard cells the netlist uses are defined by their transistors (library SPICE, names
made parseable, diodes dropped) with a Generator annotation: ALIGN keeps each one a leaf
(align/pdk/stdcell.py draws it) and knows its inputs are gates and its outputs drains.

Without a floorplan ("free"): ALIGN's own compiler defaults (parallel and series devices
merged, library primitives, arrays) and its symmetry detection; only the supplies are declared.
Identical parallel devices must be merged for the symmetry search, which pairs every neighbour
of a net uniquely.

Run bound to a PDK (flow/layout/pdkproc.py); flow/layout/align/build.py calls ``make_design``.
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
    flagged in ``far``: ALIGN's primitives see only their own pins, so align/pdk/mos.py ties them to
    that rail inside the cell (``rowcell.mos_array``'s ``ties``)."""

    f = line.split()
    pol = next((p for p, model in netcells.MODELS.items() if model == f[5]), None)
    far = {"n": "vdd", "p": "vss"}.get(pol)
    bits = sum(bit for term, bit in FAR_BITS.items() if f[1 + "DGS".index(term)] == far)
    return f"{line} far={bits}" if bits else line


def make_design(
    pdk: str, netlist: Path, out_dir: Path, *, floorplan: Path | None = None, name: str, symmetric: bool = True
) -> Path:
    """Write the design directory ``out_dir/<name>`` for ``netlist`` and return it; free
    (ALIGN places on its own) when ``floorplan`` is None, then with ALIGN's symmetry search unless
    ``symmetric`` is False (no symmetry constraints: the placer packs for area alone)."""

    free = floorplan is None
    # a free design keeps the netlist unsplit
    src = netlist.read_text() if floorplan is None else netcells.floorplan_netlist(floorplan, pdk, netlist)[1]
    src = re.sub(r"(?im)^(\.subckt|\.ends)\s+\S+", rf"\1 {name}", src)
    src = _used_ports(src)
    src = (
        "\n".join(_far(_nf(l)) if l[:1] in "Mm" else l for l in netcells.per_finger(src).splitlines()) + "\n"
    )  # ALIGN reads w per finger
    std = {}  # instance -> (cell, nets)
    for line in src.splitlines():
        f = line.split()
        if f and f[0][0] in "Xx":
            std[f[0]] = (f[-1], f[1:-1])
    supplies = [
        {"constraint": "PowerPorts", "ports": ["vdd"]},
        {"constraint": "GroundPorts", "ports": ["vss"]},
        {"constraint": "DoNotRoute", "nets": ["vdd", "vss"]},
    ]
    if free:
        const = [
            *supplies,
            # a roughly square block: the placer chooses each primitive's array (gen_param.py, ALIGN's variants)
            {"constraint": "AspectRatio", "ratio_low": 1 / 1.5, "ratio_high": 1.5},
        ]
        if not symmetric:
            const.insert(0, {"constraint": "ConfigureCompiler", "auto_constraint": False})
    else:
        fp = json.loads(floorplan.read_text())
        # a floorplan drawn for a block's largest netlist (clkgen's pulse at eight delay stages) lists
        # instances a smaller one lacks: ALIGN refuses a region naming one, so they are dropped
        names = {f[0] for f in map(str.split, src.splitlines()) if f and f[0][0] in "XxMm"}
        rows = [[m for m in row if m in names or any(n.startswith(f"{m}_") for n in names)] for row in fp["rows"]]
        const = [
            {
                "constraint": "ConfigureCompiler",
                "auto_constraint": False,
                "merge_series_devices": False,
                "merge_parallel_devices": False,
                "remove_dummy_hierarchies": False,
                "identify_array": False,
                "propagate": True,
            },
            *supplies,
            {
                "constraint": "Floorplan",
                "regions": [row for row in rows if row],
                "order": True,
                "symmetrize": fp.get("symmetric", True),
            },
        ]
        # the floorplan's groups name each device's primitive; a device in none stays a primitive of
        # its own: ALIGN's matching would pair it by its connections alone (two devices sharing a gate
        # and a source as a current mirror, say) and demand the pair mirrored in one row
        parts = fp.get("split", {})
        grouped = {
            dev if dev not in parts else f"{dev}_{chr(ord('a') + k)}"
            for members in fp.get("groups", {}).values()
            for dev in members
            for k in range(parts.get(dev, 1))
        }
        loose = [f[0] for f in map(str.split, src.splitlines()) if f and f[0][0] in "Mm" and f[0] not in grouped]
        if loose:
            const.append({"constraint": "DoNotIdentify", "instances": loose})
    # logic is the PDK's library cells (flow/layout/stdcells.py recognizes them); ALIGN's own logic
    # templates, and its transmission gate, would group an NMOS and a PMOS into one primitive the row
    # cells do not draw (one type per primitive): they stay single devices (ALIGN matches its
    # library's names upper-cased)
    const.append({"constraint": "DoNotUseLib", "libraries": ["INV", "INV_B", "STAGE2_INV", "TGATE"]})
    out = out_dir / name
    out.mkdir(parents=True, exist_ok=True)
    # the cells before the block: ALIGN's parser models an unknown cell at its first instance
    (out / f"{name}.sp").write_text(std_subckts({c for c, _ in std.values()}) + "\n" + src)
    (out / f"{name}.const.json").write_text(json.dumps(const, indent=1) + "\n")
    print(out)
    return out
