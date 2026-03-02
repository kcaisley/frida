"""Smoke tests for the comparator generator."""

from .subckt import Comp, CompParams


def test_comp():
    """Verify comparator generator produces a valid module."""
    m = Comp(CompParams())
    assert m is not None
