"""Ideal three-terminal view of a unit-length MOM capacitor."""

import hdl21 as h
from hdl21.primitives import C

from flow.circuit.ports import module_from_ports


@h.bundle
class MomCapPorts:
    PLUS, MINUS, BULK = h.Inouts(3)


PORTS = MomCapPorts.signals


@h.paramclass
class MomCapParams:
    c = h.Param(dtype=h.Scalar, desc="Ideal plate-to-plate capacitance")


@h.generator
def MomCap(params: MomCapParams) -> h.Module:
    """Keep the physical shield terminal; the ideal model has no parasitics."""

    MomCap = module_from_ports("MomCap", PORTS)
    MomCap.cap = C(c=params.c)(p=MomCap.PLUS, n=MomCap.MINUS)
    return MomCap
