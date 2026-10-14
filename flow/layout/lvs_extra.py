"""Merge what a post step added to a layout (``<gds>.extra.sp``: devices, ``*.PORTS``, ``*.DNW``)
into the LVS source: the devices go into the top cell, the ports onto its .subckt line, and
with ``*.DNW`` (a deep N-well under the block) every NMOS model becomes the variant the PDK's
LVS deck extracts over a deep N-well (``tech.DNW_MODELS``).

    uv run python flow/layout/lvs_extra.py tsmc65 src.cdl extra.sp TOP out.cdl
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(pdk: str, src: str, extra: str, top: str, dst: str) -> None:
    sys.path.insert(0, str(ROOT / "pdk" / pdk / "layout"))
    import tech

    dnw_models = {k.lower(): v for k, v in getattr(tech, "DNW_MODELS", {}).items()}
    lines = Path(src).read_text().splitlines()
    text = Path(extra).read_text().splitlines()
    add = [l for l in text if l.strip() and not l.startswith("*")]
    ports = [p for l in text if l.upper().startswith("*.PORTS") for p in l.split()[1:]]
    dnw = any(l.upper().startswith("*.DNW") for l in text)
    out, inside = [], False
    for line in lines:
        f = line.split()
        if f and f[0].lower() == ".subckt" and f[1].lower() == top.lower():
            inside = True
            line = " ".join([line] + ports)
        elif inside and f and f[0].lower() == ".ends":
            out += add
            inside = False
        out.append(line)
    if dnw:
        out = [
            " ".join(
                dnw_models.get(t.lower(), t) if i > 0 and l.split()[0][0] in "Mm" else t
                for i, t in enumerate(l.split())
            )
            if l.split()
            else l
            for l in out
        ]
    Path(dst).write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:6])
