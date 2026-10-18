"""Unsilicided poly resistors: their ideal netlist view.

A poly resistor is a front-end row cell (``flow/layout/stems/rescell.py``), its resistance the
PDK's model at the drawn width and length (``tech.RES``, ``polyres_value``); the ideal view is
that resistance between its two heads.
"""

import hdl21 as h
from hdl21.primitives import R

from flow.circuit.ports import module_from_ports


@h.bundle
class PolyResPorts:
    PLUS, MINUS = h.Inouts(2)


PORTS = PolyResPorts.signals


@h.paramclass
class PolyResParams:
    r = h.Param(dtype=h.Scalar, desc="Ideal resistance")


@h.generator
def PolyRes(params: PolyResParams) -> h.Module:
    """The resistance between the heads; the ideal model has no parasitics."""

    PolyRes = module_from_ports("PolyRes", PORTS)
    PolyRes.res = R(r=params.r)(p=PolyRes.PLUS, n=PolyRes.MINUS)
    return PolyRes
