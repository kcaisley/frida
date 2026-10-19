"""Software-only structural tests for the charge-sensitive amplifier generator."""

import pytest
from hdl21.primitives import MosType

from .subckt import CASES, Csa, CsaParams, Feedback


def test_cascoded_input_and_load_of_the_other_type() -> None:
    Csa.Cache.reset()
    m = Csa(CsaParams())
    assert m.Min.conns == {"d": m.x, "g": m.inp, "s": m.vss, "b": m.vss}
    assert m.Mcas.conns == {"d": m.out, "g": m.vcas, "s": m.x, "b": m.vss}
    assert m.Mload.conns == {"d": m.out, "g": m.vload, "s": m.vdd, "b": m.vdd}
    assert m.Cf.conns == {"p": m.out, "n": m.inp}
    p = Csa(CASES["krum_pmos"])
    assert p.Min.conns["s"] is p.vdd and p.Mload.conns["s"] is p.vss


def test_krummenacher_pair_of_the_other_type_returns_the_input_against_vref() -> None:
    m = Csa(CASES["krum"])
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
    m = Csa(CASES[case])
    assert m.Mfb.conns == {"d": m.inp, "g": m.vfb, "s": m.out, "b": m.vss}
    assert not hasattr(m, "Mk_ref")


def test_layout_netlist_leaves_the_capacitor_out() -> None:
    assert not hasattr(Csa(CsaParams(cf=0)), "Cf")


@pytest.mark.parametrize("setting", ({"in_w": 0}, {"tail_l": -1}, {"feedback": Feedback.RESET, "fb_w": 0}))
def test_invalid_amplifiers_raise(setting) -> None:
    with pytest.raises(ValueError):
        Csa(CsaParams(**setting))


def test_types() -> None:
    assert CsaParams().input_xtors == MosType.NMOS
