"""Smoke tests for the CDAC generator."""

from ..circuit.params import RedunStrat
from .subckt import Cdac, CdacParams, get_cdac_weights


def test_cdac():
    """Verify CDAC generator produces a valid module."""
    m = Cdac(CdacParams())
    assert m is not None


def test_cdac_weights():
    """Test weight calculation for different strategies."""
    params = CdacParams(n_dac=8, n_extra=0, redun_strat=RedunStrat.RDX2)
    weights = get_cdac_weights(params)
    assert len(weights) == 8

    params = CdacParams(n_dac=8, n_extra=2, redun_strat=RedunStrat.SUBRDX2_LIM)
    weights = get_cdac_weights(params)
    assert len(weights) == 10
