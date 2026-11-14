"""The charge-sensitive amplifier's generator (``netlist``), the designs its parameters refuse, its
layout view and its placement (``flow.layout.hdl21align``): complete for every instance of its
space, its rows top first."""

import hdl21 as h
import pytest
from hdl21.prefix import f
from hdl21.primitives import MosType

from flow import pipeline
from flow.layout.hdl21align import issues, module_plan, pnr_input

from . import runs
from .params import Feedback, Params, layout_view
from .subckt import netlist


def test_cascoded_input_and_load_of_the_other_type() -> None:
    m = netlist(Params())
    assert m.Min.conns == {"d": m.x, "g": m.inp, "s": m.vss, "b": m.vss}
    assert m.Mcas.conns == {"d": m.out, "g": m.vcas, "s": m.x, "b": m.vss}
    assert m.Mload.conns == {"d": m.out, "g": m.vload, "s": m.vdd, "b": m.vdd}
    assert m.Cf.conns == {"p": m.out, "n": m.inp}
    p = netlist(runs.krum_pmos())
    assert p.Min.conns["s"] is p.vdd and p.Mload.conns["s"] is p.vss


def test_krummenacher_pair_of_the_other_type_returns_the_input_against_vref() -> None:
    m = netlist(runs.krum())
    assert m.Mk_ref.conns == {"d": m.inp, "g": m.vref, "s": m.tail, "b": m.vdd}
    assert m.Mk_sig.conns == {"d": m.mirror, "g": m.out, "s": m.tail, "b": m.vdd}
    assert m.Mk_tail.conns == {"d": m.tail, "g": m.vfb, "s": m.vdd, "b": m.vdd}
    assert m.Mk_diode.conns == {"d": m.mirror, "g": m.mirror, "s": m.vss, "b": m.vss}
    assert m.Mk_mirror.conns == {"d": m.inp, "g": m.mirror, "s": m.vss, "b": m.vss}
    assert m.Mk_filter.conns == {"d": m.vss, "g": m.mirror, "s": m.vss, "b": m.vss}
    assert m.Mk_ref.of.params.tp == MosType.PMOS and m.Mk_mirror.of.params.tp == MosType.NMOS
    assert not hasattr(m, "Mfb")


@pytest.mark.parametrize("case", ("continuous", "reset"))
def test_continuous_and_reset_feedback_bridge_the_capacitor(case) -> None:
    m = netlist(getattr(runs, case)())
    assert m.Mfb.conns == {"d": m.inp, "g": m.vfb, "s": m.out, "b": m.vss}
    assert not hasattr(m, "Mk_ref")


def test_the_layout_view_leaves_the_capacitor_out() -> None:
    assert not hasattr(netlist(Params(cf=0)), "Cf")
    view = layout_view(runs.continuous())
    assert float(view.cf) == 0.0 and view == Params(feedback=Feedback.CONTINUOUS, fb_l=16, cf=0 * f)
    assert not hasattr(netlist(view), "Cf")


@pytest.mark.parametrize(
    "setting", ({"in_w": 0}, {"tail_l": -1}, {"feedback": Feedback.RESET, "fb_w": 0}, {"cf": -1 * f})
)
def test_the_parameters_refuse_what_does_not_build(setting) -> None:
    """A size below one unit, a negative feedback capacitor."""
    with pytest.raises(ValueError):
        Params(**setting)


def test_types() -> None:
    assert Params().input_xtors == MosType.NMOS


def test_the_named_amplifiers_and_their_sizes() -> None:
    """The four named amplifiers; the grid each at seven sizes, the named size among them."""
    named = {name: single() for name, single in pipeline.singles(runs).items()}
    assert list(named) == ["krum", "krum_pmos", "continuous", "reset"]
    assert named["krum_pmos"].input_xtors == MosType.PMOS
    assert (named["continuous"].feedback, named["continuous"].fb_l) == (Feedback.CONTINUOUS, 16)
    assert (named["reset"].feedback, named["reset"].fb_l) == (Feedback.RESET, 1)
    grid = dict(runs.scaled.instances("tsmc65"))
    assert len(grid) == 28 and len({repr(design) for design in grid.values()}) == 28
    for name, design in named.items():
        assert grid[f"scaled({name}_x1)"] == design
    half = grid["scaled(krum_x0.5)"]
    assert (half.in_w, half.cas_w, half.load_w) == (12, 4, 4)
    wide = grid["scaled(reset_x4)"]
    assert (wide.in_w, wide.cas_w, wide.load_w, wide.fb_l) == (96, 32, 32, 1)
    assert grid["scaled(continuous_load_l_x2)"].load_l == 16 and grid["scaled(krum_pmos_in_l_x2)"].in_l == 4


def _module(params):
    netlist.Cache.reset()
    return netlist(params)


@pytest.mark.parametrize("pdk", ("tsmc65", "ihp130", "tsmc28", "tower180", "lf150", "tpsc65", "sky130", "gf180"))
def test_every_instance_states_a_complete_placement(pdk: str) -> None:
    h.pdk.set_default(pytest.importorskip(f"pdk.{pdk}.hdl21").pdk_logic)  # a PDK-free checkout (CI) has none
    for _label, params in runs.scaled.instances(pdk):
        for design in (params, layout_view(params)):
            pnr = pnr_input(_module(design))
            assert pnr is not None and issues(pnr) == []


def test_the_named_amplifiers_rows() -> None:
    """Rows top first, as the hand-written floorplans had them: the input type's rail at the bottom
    for an NMOS input, at the top for a PMOS one."""
    h.pdk.set_default(pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic)
    named = pipeline.singles(runs)
    rows = {name: module_plan(pnr_input(_module(layout_view(named[name]()))))["rows"] for name in named}
    krum = [["Mload", "Mk_tail"], ["Mk_ref", "Mk_sig"], ["Mcas", "Mk_diode", "Mk_mirror"], ["Min", "Mk_filter"]]
    assert rows == {
        "krum": krum,
        "krum_pmos": krum[::-1],
        "continuous": [["Mload"], ["Mcas", "Min", "Mfb"]],
        "reset": [["Mload"], ["Mcas", "Min", "Mfb"]],
    }
