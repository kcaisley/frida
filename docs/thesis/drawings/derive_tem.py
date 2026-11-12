"""The application sketches, derived from docs/images/tem.svg (Inkscape): each a copy of that
drawing with its own layers switched, its beam reshaped and its labels changed, reusing its
elements and styles. Edit tem.svg in Inkscape and rerun to carry the changes into all four.

    python docs/thesis/drawings/derive_tem.py
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEM = HERE.parents[1] / "images" / "tem.svg"
VIEW = (100, 0, 330, 285.75)  # the column, its labels and the stroboscopic annotations


def layers(svg: str, shown: set[str]) -> str:
    def toggle(match: re.Match) -> str:
        tag = match.group(0)
        label = re.search(r'inkscape:label="([^"]*)"', tag).group(1)
        return re.sub(r"display:(none|inline)", "display:" + ("inline" if label in shown else "none"), tag)

    return re.sub(r'<g\b[^>]*inkscape:groupmode="layer"[^>]*>', toggle, svg)


def element(svg: str, ident: str) -> tuple[int, int]:
    """The span of the element with this id (a path, or a text with its tspans)."""
    at = svg.index(f'id="{ident}"')
    start = svg.rfind("<", 0, at)
    tag = re.match(r"<(\w+)", svg[start:]).group(1)
    end = svg.index("</text>", start) + 7 if tag == "text" else svg.index("/>", start) + 2
    return start, end


def set_d(svg: str, ident: str, d: str) -> str:
    start, end = element(svg, ident)
    return svg[:start] + re.sub(r'\bd="[^"]*"', f'd="{d}"', svg[start:end], count=1) + svg[end:]


def set_text(svg: str, ident: str, *lines: str) -> str:
    """A label's lines, one per tspan (extra tspans emptied)."""
    start, end = element(svg, ident)
    text = svg[start:end]
    spans = list(re.finditer(r"(<tspan\b[^>]*>)([^<]*)(</tspan>)", text))
    for i, span in reversed(list(enumerate(spans))):
        new = lines[i] if i < len(lines) else ""
        text = text[: span.start(2)] + new + text[span.end(2) :]
    return svg[:start] + text + svg[end:]


def copy(svg: str, ident: str, new_id: str, dy: float = 0.0, d: str | None = None, lines: tuple[str, ...] = ()) -> str:
    """A copy of an element placed after it: moved down by dy, or given new path data or text."""
    start, end = element(svg, ident)
    clone = re.sub(r'\bid="([^"]*)"', lambda m: f'id="{m.group(1)}-{new_id}"', svg[start:end])
    if d is not None:
        clone = re.sub(r'\bd="[^"]*"', f'd="{d}"', clone, count=1)
    if dy:
        clone = re.sub(r'\by="([-\d.]+)"', lambda m: f'y="{float(m.group(1)) + dy:.4f}"', clone)
    for i, line in enumerate(lines):
        spans = list(re.finditer(r"(<tspan\b[^>]*>)([^<]*)(</tspan>)", clone))
        if i < len(spans):
            span = spans[i]
            clone = clone[: span.start(2)] + line + clone[span.end(2) :]
    return svg[:end] + "\n" + clone + svg[end:]


def crop(svg: str) -> str:
    head_end = svg.index(">", svg.index("<svg")) + 1
    head = svg[:head_end]
    x, y, w, h = VIEW
    head = re.sub(r'\bviewBox="[^"]*"', f'viewBox="{x} {y} {w} {h}"', head, count=1)
    head = re.sub(r'\bwidth="[^"]*"', f'width="{w * 1920 / 508:.0f}"', head, count=1)
    return head + svg[head_end:]


BASE = {"chip", "optics", "target", "beam", "source"}


def tem(svg: str) -> str:
    """Transmission electron microscopy: the drawing as it is."""
    return crop(layers(svg, BASE))


def stroboscopic(svg: str) -> str:
    """In-situ and stroboscopic TEM: the drawing's own packet beam and annotations."""
    return crop(layers(svg, BASE - {"beam"} | {"beam_packets", "annotate2"}))


def stem(svg: str) -> str:
    """4D-STEM: the beam focused to a probe at the sample, scanned by two coil pairs, then a
    diffraction cone to the detector."""
    svg = layers(svg, BASE)
    svg = set_d(svg, "path28571", "m 250,120 h 10 l -5,20 5,20 h -10 l 5,-20 z")
    for k, y in enumerate((93, 106)):
        for side, x in (("l", 240), ("r", 262)):
            svg = copy(svg, "path32432-2", f"coil{k}{side}", d=f"m {x},{y} v -6 h 8 c 0,0 0,6 0,6 h -8")
    svg = copy(svg, "text19241-9", "scan", dy=31, lines=("Scan coils",))
    return crop(svg)


def xray(svg: str) -> str:
    """X-ray diffraction: a photon source, no electron optics, a pencil beam on the sample and
    the scattered photons in the detector's cone."""
    svg = layers(svg, BASE - {"optics"})
    svg = set_text(svg, "text19241", "Photon source")
    svg = copy(svg, "text19241", "kind", dy=8.5, lines=("(synchrotron, FEL)",))
    svg = set_d(svg, "path28384", "m 254,40 h 2 v 95 h -2 z")
    svg = set_d(svg, "path28571", "m 255,140 v 0")
    svg = set_d(svg, "path29078", "m 255,140 40,117 h -80 z")
    svg = set_text(svg, "text19241-9-1", "Hybrid pixel", "detector")
    return crop(svg)


def main() -> None:
    svg = TEM.read_text()
    for name, derive in (
        ("app_tem", tem),
        ("app_4dstem", stem),
        ("app_xray", xray),
        ("app_stroboscopic", stroboscopic),
    ):
        (HERE / f"{name}.svg").write_text(derive(svg))
        print(HERE / f"{name}.svg")


if __name__ == "__main__":
    main()
