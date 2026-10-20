"""Software-only structural tests for the MOSFET generator and its cases."""

import pytest
from hdl21.primitives import MosType, MosVth

from .subckt import LENGTHS, Mosfet, MosfetParams, cases, flavors


def test_one_device_between_four_terminals() -> None:
    m = Mosfet(MosfetParams(tp=MosType.PMOS, vth=MosVth.STD, l=2))
    assert set(m.instances) == {"Mdut"}
    assert m.Mdut.conns == {"d": m.d, "g": m.g, "s": m.s, "b": m.b}


def test_invalid_devices_raise() -> None:
    with pytest.raises(ValueError):
        Mosfet(MosfetParams(w=0))


@pytest.mark.parametrize("pdk", ["tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65"])
def test_every_core_device_at_every_length(pdk: str) -> None:
    pytest.importorskip(f"pdk.{pdk}.hdl21.primitives.prim_dicts")
    found = flavors(pdk)
    assert found and {tp for tp, _vth in found.values()} == {MosType.NMOS, MosType.PMOS}
    assert MosVth.NATIVE not in {vth for _tp, vth in found.values()}
    named = cases(pdk)
    assert len(named) == len(found) * len(LENGTHS)
    assert {params.l for params in named.values()} == set(LENGTHS)
