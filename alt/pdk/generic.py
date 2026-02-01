"""
Generic PDK for FRIDA testing and development.

Uses HDL21's built-in MOS primitives with SPICE primitive models.
This PDK is useful for:
- Initial circuit development and debugging
- Netlist verification without a real PDK
- Testing with generic simulators

Implements multiplier-based scaling: w/l values from generators are
treated as multipliers of W_MIN/L_MIN to produce physical dimensions.
"""

import copy
from typing import Optional

import hdl21 as h
from hdl21.prefix import m, n, µ
from hdl21.primitives import Mos, MosType
from hdl21.primitives import MosParams as PrimMosParams
from vlsirtools import SpiceType

from .base import FridaPdk

# Process parameters for generic PDK
W_MIN = 100 * n  # 100nm minimum width
L_MIN = 100 * n  # 100nm minimum length
VDD_NOM = 1200 * m  # 1.2V nominal supply


@h.paramclass
class GenericMosParams:
    """Generic MOS transistor parameters."""

    w = h.Param(dtype=h.Scalar, desc="Width", default=100 * n)
    l = h.Param(dtype=h.Scalar, desc="Length", default=100 * n)
    nf = h.Param(dtype=int, desc="Number of fingers", default=1)
    m = h.Param(dtype=int, desc="Multiplier", default=1)


# Define generic NMOS and PMOS as SPICE primitive MOS elements
_Nmos = h.ExternalModule(
    domain="generic",
    name="nmos",
    desc="Generic NMOS (SVT)",
    port_list=copy.deepcopy(Mos.port_list),
    paramtype=GenericMosParams,
    spicetype=SpiceType.MOS,
)

_Pmos = h.ExternalModule(
    domain="generic",
    name="pmos",
    desc="Generic PMOS (SVT)",
    port_list=copy.deepcopy(Mos.port_list),
    paramtype=GenericMosParams,
    spicetype=SpiceType.MOS,
)

_NmosLvt = h.ExternalModule(
    domain="generic",
    name="nmos_lvt",
    desc="Generic NMOS (LVT)",
    port_list=copy.deepcopy(Mos.port_list),
    paramtype=GenericMosParams,
    spicetype=SpiceType.MOS,
)

_PmosLvt = h.ExternalModule(
    domain="generic",
    name="pmos_lvt",
    desc="Generic PMOS (LVT)",
    port_list=copy.deepcopy(Mos.port_list),
    paramtype=GenericMosParams,
    spicetype=SpiceType.MOS,
)


class GenericPdkWalker(h.HierarchyWalker):
    """
    Hierarchy walker to convert hdl21.primitives to generic PDK modules.
    """

    def __init__(self):
        super().__init__()
        self.mos_modcalls = dict()

    def visit_primitive_call(self, call: h.PrimitiveCall) -> h.Instantiable:
        """Replace h.primitives.Mos with our ExternalModules."""
        if call.prim is h.primitives.Mos:
            return self.mos_module_call(call.params)
        return call

    def mos_module(self, params: PrimMosParams) -> h.ExternalModule:
        """Select NMOS or PMOS based on primitive params."""
        if params.tp == MosType.PMOS:
            return _Pmos
        return _Nmos

    def mos_params(self, params: PrimMosParams) -> GenericMosParams:
        """Convert primitive MosParams to GenericMosParams.

        Implements multiplier-based scaling:
        - If w/l are integers or have UNIT prefix, treat as multipliers of W_MIN/L_MIN
        - If w/l have physical prefixes (NANO, MICRO), use as absolute values
        """
        w = self._scale_dimension(params.w, W_MIN, default_mult=10)
        l = self._scale_dimension(params.l, L_MIN, default_mult=1)

        return GenericMosParams(
            w=w,
            l=l,
            m=params.mult or 1,
            nf=params.nf or 1,
        )

    def _scale_dimension(
        self,
        value: Optional[h.Scalar],
        min_dim: h.Prefixed,
        default_mult: int = 1,
    ) -> h.Prefixed:
        """
        Scale a dimension value using multiplier-based approach.

        Args:
            value: The input value (could be int, Prefixed, or None)
            min_dim: The minimum dimension (W_MIN or L_MIN)
            default_mult: Default multiplier if value is None

        Returns:
            Physical dimension as h.Prefixed
        """
        if value is None:
            return default_mult * min_dim

        # If it's an integer, treat as multiplier
        if isinstance(value, int):
            return value * min_dim

        # If it's a Prefixed value, check the prefix
        if isinstance(value, h.Prefixed):
            # Check if it has a physical prefix (NANO, MICRO, etc.)
            # Values with UNIT prefix (1.0) or no prefix are treated as multipliers
            if value.prefix == h.prefix.UNIT:
                # Treat the number as a multiplier
                return int(value.number) * min_dim
            else:
                # It's an absolute physical value - use as-is
                return value

        # For other numeric types, treat as multiplier
        try:
            mult = int(value)
            return mult * min_dim
        except (TypeError, ValueError):
            # Fall back to using as-is
            return value

    def mos_module_call(self, params: PrimMosParams) -> h.ExternalModuleCall:
        """Get or create a module call for given params."""
        if params in self.mos_modcalls:
            return self.mos_modcalls[params]

        mod = self.mos_module(params)
        modparams = self.mos_params(params)
        modcall = mod(modparams)
        self.mos_modcalls[params] = modcall
        return modcall


class GenericPdk(FridaPdk):
    """Generic PDK implementation using SPICE primitive models."""

    # Process parameters
    W_MIN = 100 * n
    L_MIN = 100 * n
    VDD_NOM = 1200 * m

    @property
    def name(self) -> str:
        return "generic"

    @property
    def Nmos(self) -> h.ExternalModule:
        return _Nmos

    @property
    def Pmos(self) -> h.ExternalModule:
        return _Pmos

    @property
    def NmosLvt(self) -> h.ExternalModule:
        return _NmosLvt

    @property
    def PmosLvt(self) -> h.ExternalModule:
        return _PmosLvt

    def compile(self, src: h.Elaboratables) -> None:
        """Compile primitives to generic PDK modules."""
        return GenericPdkWalker.walk(src)
