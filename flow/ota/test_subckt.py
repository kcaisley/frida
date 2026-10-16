"""Software-only structural tests for the OTA generator."""

import pytest
from hdl21.prefix import f
from hdl21.primitives import MosType

from .subckt import CASES, Ota, OtaParams, Topology


def test_five_t_mirror_makes_outp_follow_inp() -> None:
    Ota.Cache.reset()
    m = Ota(OtaParams())
    assert m.Min_p.conns["d"] is m.mirror and m.Mload_d.conns["g"] is m.mirror and m.Mload_d.conns["d"] is m.mirror
    assert m.Min_n.conns["d"] is m.outp and m.Mload.conns["d"] is m.outp
    assert m.Mtail.conns["g"] is m.vbn and m.Mtail.conns["s"] is m.vss


def test_pmos_input_mirrors_between_the_rails() -> None:
    m = Ota(CASES["five_t_pmos"])
    assert m.Mtail.conns["s"] is m.vdd and m.Mtail.conns["g"] is m.vbp
    assert m.Mload.conns["s"] is m.vss


def test_telescopic_and_folded_cascodes() -> None:
    t = Ota(CASES["telescopic"])
    assert t.Mcas_in_p.conns["s"] is t.Min_p.conns["d"] and t.Mcas_in_p.conns["d"] is t.outn
    assert t.Mcas_load_n.conns["d"] is t.outp and t.Mload_n.conns["g"] is t.vbp
    fo = Ota(CASES["folded"])
    assert fo.Mtop_p.conns["d"] is fo.Min_p.conns["d"] and fo.Mcas_fold_p.conns["s"] is fo.fold_p
    assert fo.Mcas_bottom_p.conns["d"] is fo.outn and fo.Mbottom_p.conns["g"] is fo.vbn


def test_self_biased_tails_follow_the_inp_drains() -> None:
    m = Ota(CASES["self_biased"])
    assert m.Mtail_n.conns["g"] is m.tail_g and m.Mtail_p.conns["g"] is m.tail_g
    assert m.Min_p_n.conns["d"] is m.tail_g and m.Min_n_p.conns["d"] is m.outp


def test_two_stage_drives_the_outputs_from_the_first_stage() -> None:
    m = Ota(CASES["two_stage"])
    assert m.Mcas_in_n.conns["d"] is m.out1p and m.Mstage2_n.conns["g"] is m.out1n
    assert m.Mstage2_p.conns["d"] is m.outp and m.Mstage2_p.conns["s"] is m.vdd
    assert not hasattr(m, "Cmiller_p")
    c = Ota(OtaParams(topology=Topology.TELESCOPIC, two_stage=True, miller=50 * f))
    assert c.Cmiller_p.conns["p"] is c.outp and c.Cmiller_p.conns["n"] is c.out1p


@pytest.mark.parametrize(
    "setting",
    (
        {"topology": Topology.SELF_BIASED, "input_xtors": MosType.PMOS},
        {"miller": 10 * f},  # a Miller capacitor without a second stage
        {"tail_w": 0},
    ),
)
def test_invalid_amplifiers_raise(setting) -> None:
    with pytest.raises(ValueError):
        Ota(OtaParams(**setting))
