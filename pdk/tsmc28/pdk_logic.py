"""HDL21 compile logic for TSMC28."""

from pathlib import Path
from typing import Dict

from pydantic.dataclasses import dataclass

import hdl21 as h
from hdl21.pdk import PdkInstallation
from hdl21.primitives import (
    Bipolar,
    Diode,
    Mos,
    MosFamily,
    MosParams,
    MosType,
    MosVth,
    PhysicalCapacitor,
    PhysicalResistor,
    ThreeTerminalCapacitor,
    ThreeTerminalResistor,
)

from .primitives.prim_dicts import CACHE, default_xtor_size, xtors


@dataclass
class Install(PdkInstallation):
    """Site installation for TSMC28."""

    pdk_path: Path = Path("/eda/kits/TSMC/28HPC+/2023_v1.1")

    def include(self, corner: h.pdk.Corner) -> h.sim.Lib:
        corner_map: Dict[h.pdk.Corner, str] = {
            h.pdk.Corner.TYP: "att_pt",
            h.pdk.Corner.FAST: "aff_pf",
            h.pdk.Corner.SLOW: "ass_ps",
        }
        if corner not in corner_map:
            raise ValueError(f"Invalid corner {corner}")
        return h.sim.Lib(
            path=self.pdk_path
            / "pdk/1P9M_5X1Y1Z1U_UT_AlRDL/SPICE/models/all_1p9m_5x1y1z1u_ut_alrdl.scs",
            section=corner_map[corner],
        )


class Tsmc28Walker(h.HierarchyWalker):
    """Primitive-to-ExternalModule compiler pass."""

    def visit_primitive_call(self, call: h.PrimitiveCall) -> h.Instantiable:
        if call.prim is Mos:
            return self.mos_module_call(call.params)
        if call.prim in {
            PhysicalResistor,
            ThreeTerminalResistor,
            PhysicalCapacitor,
            ThreeTerminalCapacitor,
            Diode,
            Bipolar,
        }:
            # TODO: add passive/ diode/ bjt wrappers for TSMC28.
            return call
        return call

    def mos_module(self, params: MosParams) -> h.ExternalModule:
        mostype = params.tp or MosType.NMOS
        mosvth = params.vth or MosVth.STD
        mosfam = params.family or MosFamily.CORE
        mod = xtors.get((mostype, mosvth, mosfam))
        if mod is None:
            raise RuntimeError(
                f"No TSMC28 MOS module for type={mostype}, vth={mosvth}, family={mosfam}"
            )
        return mod

    def mos_params(self, params: MosParams, modname: str):
        from .pdk_data import Tsmc28MosParams

        w, l = self.use_defaults(params, modname)
        return Tsmc28MosParams(
            w=w,
            l=l,
            nf=params.nf or 1,
            m=params.mult or 1,
        )

    def mos_module_call(self, params: MosParams) -> h.ExternalModuleCall:
        if params in CACHE.mos_modcalls:
            return CACHE.mos_modcalls[params]
        mod = self.mos_module(params)
        modparams = self.mos_params(params, mod.name)
        modcall = mod(modparams)
        CACHE.mos_modcalls[params] = modcall
        return modcall

    def scale_param(self, orig: h.Scalar | None, default: h.Prefixed) -> h.Scalar:
        if orig is None:
            return default
        if isinstance(orig, h.Prefixed):
            if orig.prefix == h.Prefix.UNIT:
                return orig.number * default
            return orig
        if isinstance(orig, (int, float)):
            return h.Prefixed.new(orig, h.Prefix.UNIT) * default
        if isinstance(orig, h.Literal):
            return h.Literal(f"({orig.text} * {default.number}e{default.prefix.value})")
        raise TypeError(f"Param value {orig}")

    def use_defaults(self, params: h.paramclass, modname: str) -> tuple[h.Scalar, h.Scalar]:
        w0, l0 = default_xtor_size.get(modname, default_xtor_size["nch"])
        w = self.scale_param(params.w, w0) if hasattr(params, "w") else w0
        l = self.scale_param(params.l, l0) if hasattr(params, "l") else l0
        return w, l


def compile(src: h.Elaboratables) -> None:
    """Compile source into TSMC28 modules."""
    Tsmc28Walker().walk(src)
