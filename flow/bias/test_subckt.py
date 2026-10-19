"""Software-only structural tests for the cascode bias generator."""

import pytest

from .subckt import CASES, Bias, BiasParams


def test_self_cascoded_references_and_weak_cascode_diodes() -> None:
    Bias.Cache.reset()
    m = Bias(BiasParams())
    assert m.Mn.conns == {"d": m.nx, "g": m.vbn, "s": m.vss, "b": m.vss}
    assert m.Mn_cas.conns == {"d": m.vbn, "g": m.vcasn, "s": m.nx, "b": m.vss}
    assert m.Mp.conns == {"d": m.px, "g": m.vbp, "s": m.vdd, "b": m.vdd}
    assert m.Mp_cas.conns == {"d": m.vbp, "g": m.vcasp, "s": m.px, "b": m.vdd}
    assert m.Mcasn.conns == {"d": m.vcasn, "g": m.vcasn, "s": m.vss, "b": m.vss}
    assert m.Mcasp.conns == {"d": m.vcasp, "g": m.vcasp, "s": m.vdd, "b": m.vdd}


def test_cascoded_copies_feed_the_other_references() -> None:
    m = Bias(BiasParams())
    assert m.Mn_to_p.conns["g"] is m.vbn and m.Mn_to_p_cas.conns["d"] is m.vbp and m.Mn_to_p_cas.conns["g"] is m.vcasn
    assert m.Mn_to_casp.conns["g"] is m.vbn and m.Mn_to_casp_cas.conns["d"] is m.vcasp
    assert m.Mp_to_casn.conns["g"] is m.vbp and m.Mp_to_casn_cas.conns["d"] is m.vcasn
    assert m.Mp_to_casn_cas.conns["g"] is m.vcasp
    # start-up: a follower from vbn onto vcasn
    assert m.Mstart.conns == {"d": m.vdd, "g": m.vbn, "s": m.vcasn, "b": m.vss}


def test_margin_case_has_weaker_diodes() -> None:
    wide, margin = CASES["wide"], CASES["margin"]
    assert margin.casn_w / margin.casn_l < wide.casn_w / wide.casn_l
    assert margin.casp_w / margin.casp_l < wide.casp_w / wide.casp_l


@pytest.mark.parametrize("setting", ({"n_w": 0}, {"casp_l": -1}, {"start_w": 0}))
def test_invalid_generators_raise(setting) -> None:
    with pytest.raises(ValueError):
        Bias(BiasParams(**setting))
