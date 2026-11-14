"""The follower's generator (``netlist``), the designs its parameters refuse, and its placement
(``flow.layout.hdl21align``): complete for every instance of its space, its rows top first."""

import hdl21 as h
import pytest
from hdl21.primitives import MosType

from flow import pipeline
from flow.layout.hdl21align import issues, module_plan, pnr_input

from . import runs
from .params import Params, Topology
from .subckt import netlist


def test_source_follower_drain_on_the_far_rail() -> None:
    m = netlist(Params())
    assert m.Min.conns == {"d": m.vdd, "g": m.vin, "s": m.vout, "b": m.vss}
    assert m.Mbias.conns == {"d": m.vout, "g": m.vbn, "s": m.vss, "b": m.vss}
    p = netlist(runs.source_pmos())
    assert p.Min.conns["d"] is p.vss and p.Min.conns["b"] is p.vdd and p.Mbias.conns["g"] is p.vbp


def test_flipped_follower_feeds_the_input_drain_to_the_shunt() -> None:
    m = netlist(runs.flipped())
    assert m.Min.conns["d"] is m.fb and m.Min.conns["s"] is m.vout
    assert m.Mbias.conns["d"] is m.fb and m.Mbias.conns["g"] is m.vbp and m.Mbias.conns["s"] is m.vdd
    assert m.Mfb.conns == {"d": m.vout, "g": m.fb, "s": m.vss, "b": m.vss}
    p = netlist(runs.flipped_pmos())
    assert p.Msink.conns["d"] is p.vout and p.Msink.conns["s"] is p.vss and p.Mfb.conns["s"] is p.vdd


@pytest.mark.parametrize("setting", ({"sink": True}, {"in_w": 0}, {"topology": Topology.SOURCE, "fb_l": -1}))
def test_the_parameters_refuse_what_does_not_build(setting) -> None:
    """An output sink on a source follower, and a size below one unit."""
    with pytest.raises(ValueError):
        Params(**setting)


def test_types() -> None:
    assert Params().input_xtors == MosType.NMOS


def test_the_named_followers_and_their_sizings() -> None:
    """The four named followers; the grid each at eight sizings, a source follower (no shunt
    device to size) at seven, the named sizing among them."""
    named = {name: single() for name, single in pipeline.singles(runs).items()}
    assert list(named) == ["source", "source_pmos", "flipped", "flipped_pmos"]
    assert (named["source"].in_w, named["source"].bias_w) == (32, 16)
    assert named["flipped_pmos"].sink and named["flipped_pmos"].input_xtors == MosType.PMOS
    grid = dict(runs.scaled.instances("tsmc65"))
    assert len(grid) == 30 and len({repr(design) for design in grid.values()}) == 30
    for name, design in named.items():
        assert grid[f"scaled({name}_x1)"] == design
    assert (grid["scaled(source_x0.5)"].in_w, grid["scaled(source_x0.5)"].bias_w) == (16, 8)
    wide = grid["scaled(flipped_x4)"]
    assert (wide.in_w, wide.bias_w, wide.fb_w) == (64, 32, 64)
    assert grid["scaled(flipped_fb_w_x2)"].fb_w == 32 and "scaled(source_fb_w_x2)" not in grid
    assert grid["scaled(source_pmos_bias_l_x2)"].bias_l == 8 and grid["scaled(flipped_pmos_in_l_x2)"].in_l == 2


def _module(params):
    netlist.Cache.reset()
    return netlist(params)


@pytest.mark.parametrize("pdk", ("tsmc65", "ihp130", "tsmc28", "tower180", "lf150", "tpsc65", "sky130", "gf180"))
def test_every_instance_states_a_complete_placement(pdk: str) -> None:
    h.pdk.set_default(pytest.importorskip(f"pdk.{pdk}.hdl21").pdk_logic)  # a PDK-free checkout (CI) has none
    for _label, params in runs.scaled.instances(pdk):
        pnr = pnr_input(_module(params))
        assert pnr is not None and issues(pnr) == []


def test_the_named_followers_rows() -> None:
    h.pdk.set_default(pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic)
    named = pipeline.singles(runs)
    rows = {name: module_plan(pnr_input(_module(named[name]())))["rows"] for name in named}
    assert rows == {
        "source": [["Min"], ["Mbias"]],
        "source_pmos": [["Min"], ["Mbias"]],
        "flipped": [["Mbias"], ["Min", "Mfb"]],
        "flipped_pmos": [["Min", "Mfb"], ["Mbias", "Msink"]],
    }
