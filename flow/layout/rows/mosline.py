"""A netlist's MOS lines: their widths and fingers, as the PDK's netlists give them.

A MOS line carries its fingers in ``nf`` (``ng`` in some PDKs) or, with neither, in ``m``, its
``w`` then one finger's width. With ``nf``, ``w`` is the total width of the fingers, unless the
PDK's hdl21 ``pdk_logic`` sets ``MOS_W_PER_FINGER`` (its models read ``w`` as one finger's
width): then ``w`` is per finger there too. The netlists stay as the PDK writes them (the
simulators and LVS read them so); the layout flow interprets them here.

``split``, ``per_finger`` and ``finger_width`` take the convention as an argument;
``w_per_finger`` reads it for the PDK this process is bound to (``flow/layout/pdkproc.py``),
from its ``pdk_logic`` source without importing hdl21 (ALIGN's own Python imports the engine
too). Nothing here imports the PDK, so it is tested without one.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Sequence
from functools import cache
from pathlib import Path


def nm(v: str) -> int:
    """A SPICE length in nm: 400n, 0.4u, 4e-07 (metres without a suffix, nm when >= 1)."""
    m = re.fullmatch(r"([-+0-9.eE]+)(n|u|m)?", v.strip())
    if m is None:
        raise ValueError(f"not a length: {v!r}")
    x = float(m.group(1))
    scale = {"n": 1, "u": 1000, "m": 1e6}.get(m.group(2) or "", 1 if x >= 1 else 1e9)
    return round(x * scale)


def params(fields: Sequence[str]) -> dict[str, str]:
    """A MOS line's ``key=value`` parameters (its fields after the model)."""
    return dict(kv.split("=", 1) for kv in fields[6:])


def fingers(p: dict[str, str]) -> int:
    """Fingers of one copy: nf (or ng); a device with neither is fingered by m."""
    return int(float(p.get("nf", p.get("ng", 1))))


def finger_key(p: dict[str, str]) -> str:
    """The parameter that carries a device's fingers: nf, ng, or m (with w per finger) where neither is given."""
    return "nf" if "nf" in p else "ng" if "ng" in p else "m"


def finger_width(p: dict[str, str], w_per_finger: bool) -> int:
    """One finger's width in nm."""
    w = nm(p["w"])
    return w if w_per_finger else w // fingers(p)


def split(src: str, parts: dict[str, int], w_per_finger: bool) -> str:
    """Split devices into equal parallel parts named ``<device>_a``, ``_b``, ...: a floorplan's
    ``split`` (e.g. the halves of a cross-quad pair placed in two rows). Each part takes an
    equal share of the fingers (and, where ``w`` is the total width, of ``w``)."""

    out = []
    for line in src.splitlines():
        f = line.split()
        if f and f[0] in parts:
            n = parts[f[0]]
            p = params(f)
            key = finger_key(p)
            count, w = int(float(p.get(key, 1))), nm(p["w"])
            total = key != "m" and not w_per_finger  # w is the total width, shared by the parts
            if count % n or (total and w % n):
                raise ValueError(f"{f[0]}: {count} fingers, {w} nm do not split into {n} equal parts")
            p[key] = str(count // n)
            if total:
                p["w"] = f"{w // n}n"
            for k in range(n):
                out.append(" ".join([f"{f[0]}_{chr(ord('a') + k)}", *f[1:6], *(f"{a}={b}" for a, b in p.items())]))
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def per_finger(src: str, w_per_finger: bool) -> str:
    """The netlist with each MOS width per finger and all its fingers in nf (or ng), m=1 (as
    ALIGN reads ``w`` and ``nf``)."""

    out = []
    for line in src.splitlines():
        f = line.split()
        if f and f[0][0] in "Mm" and len(f) > 6:
            p = params(f)
            count, m = fingers(p), int(p.get("m", 1))
            p.update({"w": f"{finger_width(p, w_per_finger)}n", "ng" if "ng" in p else "nf": str(count * m), "m": "1"})
            line = " ".join([*f[:6], *(f"{a}={b}" for a, b in p.items())])
        out.append(line)
    return "\n".join(out) + "\n"


def _assigned(source: Path, name: str, default):
    """A module-level constant of a Python file, read (``ast.literal_eval``), not imported."""
    if not source.is_file():
        return default
    for node in ast.parse(source.read_text()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    return default


@cache
def w_per_finger(pdk_dir: Path | None = None) -> bool:
    """Whether the PDK's netlists give ``w`` per finger with ``nf`` (its ``pdk_logic``'s
    ``MOS_W_PER_FINGER``); ``pdk_dir``: the PDK's directory (``pdk/<pdk>``), else the one this
    process is bound to (its ``layout/tech.py`` on the path)."""

    if pdk_dir is None:
        import tech  # the bound PDK's

        pdk_dir = Path(tech.__file__).resolve().parents[1]
    return bool(_assigned(Path(pdk_dir) / "hdl21" / "pdk_logic.py", "MOS_W_PER_FINGER", False))
