"""Software-only structural tests for the clock generator."""

import pytest

from .subckt import CASES, Clkgen, ClkgenParams


def test_nonoverlap_cross_feeds_the_delayed_phases() -> None:
    Clkgen.Cache.reset()
    m = Clkgen(CASES["nonoverlap"])
    assert m.Xnor_p.conns["A"] is m.clkb and m.Xnor_p.conns["B"] is m.outn and m.Xnor_p.conns["Y"] is m.midp
    assert m.Xdly_p1.conns["Y"] is m.outp and m.Xnor_n.conns["B"] is m.outp


def test_pulse_nors_clkb_with_the_delayed_clock() -> None:
    m = Clkgen(CASES["pulse"])
    assert m.Xdly0.conns["A"] is m.clk and m.Xdly7.conns["Y"] is m.clk_d
    assert m.Xnor.conns["A"] is m.clkb and m.Xnor.conns["B"] is m.clk_d and m.Xnor.conns["Y"] is m.outp


def test_gate_latches_en_while_clk_is_low() -> None:
    m = Clkgen(CASES["gate"])
    assert m.Mfwd_n.conns["g"] is m.en and m.Mfwd_nclk.conns["g"] is m.clkb and m.Mout_n.conns["d"] is m.en_l
    assert m.Xnand.conns["A"] is m.clk and m.Xnand.conns["B"] is m.en_l and m.Xout.conns["Y"] is m.outp


def test_invalid_functions_raise() -> None:
    with pytest.raises(ValueError):
        Clkgen(ClkgenParams(drive=3))
