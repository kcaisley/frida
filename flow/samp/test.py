"""Smoke tests for the sampler generator."""

from .subckt import Samp, SampParams


def test_samp():
    """Verify sampler generator produces a valid module."""
    m = Samp(SampParams())
    assert m is not None
    assert hasattr(m, "din")
    assert hasattr(m, "dout")
