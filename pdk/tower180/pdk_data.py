"""PDK data definitions for Tower180."""

from copy import deepcopy

import hdl21 as h
from hdl21.prefix import n
from hdl21.primitives import Mos
from vlsirtools import SpiceType

PDK_NAME = "tower180"


@h.paramclass
class Tower180MosParams:
    """Tower180 MOS parameters."""

    w = h.Param(dtype=h.Scalar, desc="Width", default=220 * n)
    l = h.Param(dtype=h.Scalar, desc="Length", default=180 * n)
    nf = h.Param(dtype=int, desc="Number of fingers", default=1)
    m = h.Param(dtype=int, desc="Multiplier", default=1)


def xtor_module(modname: str) -> h.ExternalModule:
    """Create a MOS external module."""
    return h.ExternalModule(
        domain=PDK_NAME,
        name=modname,
        desc=f"{PDK_NAME} PDK MOS {modname}",
        port_list=deepcopy(Mos.port_list),
        paramtype=Tower180MosParams,
        spicetype=SpiceType.MOS,
    )
