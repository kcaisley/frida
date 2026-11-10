"""The generic KLayout LVS (``flow.layout.klayout_lvs``) on a toy layout: one NMOS and its substrate
tap, drawn on a made-up layer table, against its source; a source of another netlist is refused."""

from pathlib import Path
from types import SimpleNamespace

import klayout.db as kdb

from flow.layout.klayout_lvs import lvs

# made-up layers (layer, datatype)
TECH = SimpleNamespace(
    LAYERS={
        "OD": (1, 0),
        "PO": (2, 0),
        "CO": (3, 0),
        "PP": (4, 0),
        "NW": (5, 0),
        "M1": (6, 0),
        "M1.PIN": (6, 2),
        "M2": (7, 0),
        "V1": (8, 0),
    }
)


def _layout(path: Path, labels: dict[str, tuple[int, int]]) -> None:
    """An NMOS (diffusion 0..1000 x 0..400, a poly gate 450..550 across it) with a contact and a
    metal pad on its drain, source and gate, and a P+ substrate tap below; ``labels`` its M1 pins."""
    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")

    def box(key, x0, y0, x1, y1):
        top.shapes(layout.layer(*TECH.LAYERS[key])).insert(kdb.Box(x0, y0, x1, y1))

    box("OD", 0, 0, 1000, 400)
    box("PO", 450, -100, 550, 700)
    box("OD", 0, -800, 1000, -500)  # the tap
    box("PP", -100, -900, 1100, -400)
    for x0, y0 in ((100, 150), (850, 150), (475, 600), (450, -700)):
        box("CO", x0, y0, x0 + 50, y0 + 50)
        box("M1", x0 - 50, y0 - 50, x0 + 100, y0 + 100)
    for name, (x, y) in labels.items():
        top.shapes(layout.layer(*TECH.LAYERS["M1.PIN"])).insert(kdb.Text(name, kdb.Trans(x, y)))
    layout.write(str(path))


def test_a_transistor_and_its_tap_match_their_source(tmp_path: Path) -> None:
    gds, source = tmp_path / "toy.gds", tmp_path / "toy.cdl"
    pins = {"s": (125, 175), "d": (875, 175), "g": (500, 625), "vss": (475, -675)}
    _layout(gds, pins)
    # its model the kit's own name (classed NMOS by its first letter)
    source.write_text(".subckt toy s d g vss\nM0 d g s vss n_core w=0.4u l=0.1u\n.ends\n")
    assert lvs(str(gds), "TOP", str(source), "toy", TECH)
    assert (tmp_path / "toy.gds.lvsdb").exists()
    # the drain's label on the gate instead: the nets differ
    _layout(gds, {**pins, "d": (500, 625)})
    assert not lvs(str(gds), "TOP", str(source), "toy", TECH)
