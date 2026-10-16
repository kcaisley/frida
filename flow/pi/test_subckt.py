"""Software-only structural tests for the phase interpolator generator."""

import pytest

from .subckt import CASES, Pi, PiParams


def test_cmos_slices_share_the_mix() -> None:
    Pi.Cache.reset()
    m = Pi(CASES["cmos_quarter"])
    assert {n for n in m.instances if n.startswith("Mslice_a") and n.endswith("_n")} == {
        f"Mslice_a{k}_n" for k in range(3)
    }
    assert m.Mslice_b0_p.conns["g"] is m.bp and m.Mslice_b0_p.conns["d"] is m.outn
    assert m.Mout_n.conns["g"] is m.outn and m.Mout_n.conns["d"] is m.outp


def test_cml_tails_carry_the_weights() -> None:
    m = Pi(CASES["cml_quarter"])
    assert {n for n in m.instances if n.startswith("Mtail_a")} == {"Mtail_a0", "Mtail_a1", "Mtail_a2"}
    assert m.Min_a_p.conns["s"] is m.tail_a and m.Min_b_n.conns["s"] is m.tail_b and m.Min_b_n.conns["d"] is m.outp


def test_invalid_interpolators_raise() -> None:
    with pytest.raises(ValueError):
        Pi(PiParams(weight_a=0, weight_b=0))
