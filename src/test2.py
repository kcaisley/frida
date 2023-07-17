import hdl21 as h
from hdl21.prefix import NANO, µ
from decimal import Decimal

@h.paramclass
class MyMosParams:
    w = h.Param(dtype=h.Scalar, desc="Width", default=1e-6) # Default `float` converts to a `Prefixed`
    l = h.Param(dtype=h.Scalar, desc="Length", default="w/5") # Default `str` converts to a `Literal`

