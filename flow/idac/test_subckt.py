"""Software-only structural tests for the current source generator."""

import pytest
from hdl21.primitives import MosType

from .subckt import CASES, Idac, IdacParams, Switch


def test_switched_units_share_one_bias() -> None:
    Idac.Cache.reset()
    m = Idac(CASES["nmos_switched"])
    assert m.Msrc0.conns["g"] is m.vbias and m.Msrc1.conns["g"] is m.vbias and m.Msrc0.conns["s"] is m.vss
    assert m.Msw1.conns == {"d": m.out, "g": m.en, "s": m.src1, "b": m.vss}


def test_pmos_steering_takes_the_complements() -> None:
    m = Idac(CASES["pmos_steer_cas"])
    assert m.Mcas0.conns["s"] is m.src0 and m.Mcas0.conns["g"] is m.vcas
    assert m.Msw0.conns["g"] is m.enb and m.Mdump0.conns["g"] is m.en and m.Mdump0.conns["d"] is m.dump


def test_mirror_has_a_diode_and_always_on_units() -> None:
    m = Idac(CASES["pmos_mirror"])
    assert m.Mref.conns == {"d": m.vbias, "g": m.vbias, "s": m.vdd, "b": m.vdd}
    assert m.Mcas1.conns["d"] is m.out and not hasattr(m, "Msw0")


def test_invalid_units_raise() -> None:
    with pytest.raises(ValueError):
        Idac(IdacParams(units=0))
    assert IdacParams().source_xtors == MosType.NMOS and IdacParams().switch == Switch.SINGLE
