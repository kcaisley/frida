"""
Generic PDK for FRIDA testing and development.

Uses HDL21's built-in MOS primitives with SPICE primitive models.
This PDK is useful for:
- Initial circuit development and debugging
- Netlist verification without a real PDK
- Testing with generic simulators
"""

import copy
import hdl21 as h
from hdl21.prefix import µ, n
from hdl21.primitives import Mos, MosType, MosParams as PrimMosParams
from vlsirtools import SpiceType

from .base import FridaPdk


@h.paramclass
class GenericMosParams:
    """Generic MOS transistor parameters."""

    w = h.Param(dtype=h.Scalar, desc="Width", default=1 * µ)
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
        """Convert primitive MosParams to GenericMosParams."""
        return GenericMosParams(
            w=params.w or 1 * µ,
            l=params.l or 100 * n,
            m=params.mult or 1,
            nf=params.nf or 1,
        )

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
