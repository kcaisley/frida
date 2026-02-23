"""HDL21 compile logic for Tower180."""

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
    """Site installation for Tower180."""

    pdk_path: Path = Path("/eda/kits/TOWER/ts18is_Rev_6.3.6/HOTCODE/models")

    def include_fet(self, corner: h.pdk.Corner) -> h.sim.Lib:
        corner_map: Dict[h.pdk.Corner, str] = {
            h.pdk.Corner.TYP: "NOM",
            h.pdk.Corner.FAST: "FAST",
            h.pdk.Corner.SLOW: "SLOW",
        }
        if corner not in corner_map:
            raise ValueError(f"Invalid corner {corner}")
        return h.sim.Lib(
            path=self.pdk_path / "spectre/tower18.scs",
            section=corner_map[corner],
        )

    def include_global(self) -> h.sim.Lib:
        return h.sim.Lib(path=self.pdk_path / "spectre/tower18.scs", section="BSIM")

    def include(self, corner: h.pdk.Corner) -> h.sim.Lib:
        return self.include_fet(corner)


class Tower180Walker(h.HierarchyWalker):
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
            # TODO: add passive/ diode/ bjt wrappers for Tower180.
            return call
        return call

    def mos_module(self, params: MosParams) -> h.ExternalModule:
        mostype = params.tp or MosType.NMOS
        mosvth = params.vth or MosVth.STD
        mosfam = params.family or MosFamily.CORE
        mod = xtors.get((mostype, mosvth, mosfam))
        if mod is None:
            raise RuntimeError(
                f"No Tower180 MOS module for type={mostype}, vth={mosvth}, family={mosfam}"
            )
        return mod

    def mos_params(self, params: MosParams, modname: str):
        from .pdk_data import Tower180MosParams

        w, l = self.use_defaults(params, modname)
        return Tower180MosParams(
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
    """Compile source into Tower180 modules."""
    Tower180Walker().walk(src)
