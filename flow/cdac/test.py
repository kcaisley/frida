"""Smoke tests for the CDAC generator."""

from .layout import FRIDA_CAP_WEIGHTS, UNARY_WEIGHT, partition_weights
from .subckt import Cdac, CdacParams, RedunStrat, get_cdac_weights


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


def test_explicit_cdac_weights_override_strategy():
    """Explicit physical weights bypass the strategy calculation."""
    explicit = (8, 5, 2, 1)
    params = CdacParams(
        n_dac=3,
        n_extra=1,
        redun_strat=RedunStrat.SUBRDX2,
        weights=explicit,
    )
    assert get_cdac_weights(params) == list(explicit)


def test_explicit_cdac_weights_are_validated():
    """Reject the wrong count and non-positive values."""
    for weights in ((8, 4, 2), (8, 4, 0, 1)):
        params = CdacParams(n_dac=3, n_extra=1, weights=weights)
        try:
            get_cdac_weights(params)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid explicit weights {weights}")


def test_transitional_layout_preserves_frida_weights():
    partitioned = partition_weights(list(FRIDA_CAP_WEIGHTS), UNARY_WEIGHT)

    assert [sum(group) for group in partitioned] == list(FRIDA_CAP_WEIGHTS)
    assert all(0 < chunk <= UNARY_WEIGHT for group in partitioned for chunk in group)
