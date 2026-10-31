"""Generic standard-cell capacitor drivers."""

from .subckt import CapDriver, CapDriverParams, Cells, ClockXor, ClockXorParams


def view_netlist(params):
    """The circuit a characterization instance (``sweep.CapdriverLoad``) drives its load with, for
    its page's schematic: the driver generator and its parameters."""
    return CapDriver, params.driver


__all__ = ["CapDriver", "CapDriverParams", "Cells", "ClockXor", "ClockXorParams", "view_netlist"]
