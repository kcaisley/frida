"""Ideal three-terminal view of a unit-length MOM capacitor."""

import hdl21 as h
from hdl21.primitives import C


@h.paramclass
class MomCapParams:
    c = h.Param(dtype=h.Scalar, desc="Ideal plate-to-plate capacitance")


@h.generator
def MomCap(params: MomCapParams) -> h.Module:
    """Keep the physical shield terminal; the ideal model has no parasitics."""

    @h.module
    class MomCap:
        PLUS, MINUS, BULK = h.Inouts(3)
        cap = C(c=params.c)(p=PLUS, n=MINUS)

    return MomCap
