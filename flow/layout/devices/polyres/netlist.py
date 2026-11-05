"""Poly resistors as requests: a generator asks for a resistance; a PDK's polyres table gives the
body that reaches it.

``resistor(ResistorParams(r_ohm))`` is the request, an ideal resistor, so a netlist simulates
before any PDK. Its view in a PDK is the kit's own device (``device``) at the narrowest width the
kit draws and the length the table gives (``PolyResTable.length``).
"""

from dataclasses import dataclass

import hdl21 as h
from hdl21.prefix import µ
from hdl21.primitives import R
from pydantic import PositiveFloat

from flow.layout.pdkproc import pdk_value

from ..device import mark, place
from .table import polyres_table


@h.paramclass
class DeviceParams:
    l = h.Param(dtype=h.Scalar, desc="Body length")
    w = h.Param(dtype=h.Scalar, desc="Body width")


def device(pdk: str) -> h.ExternalModule:
    """The kit's resistor device: its two heads, and the substrate where its model has a third pin."""
    spec = pdk_value(pdk, "tech", "RES")
    ports = [h.Inout(name="PLUS"), h.Inout(name="MINUS")]
    if spec.get("bulk"):
        ports.append(h.Inout(name="BULK"))
    return h.ExternalModule(
        name=spec.get("sim_model", spec["model"]),
        desc=f"{pdk} poly resistor",
        port_list=ports,
        paramtype=DeviceParams,
    )


@h.paramclass
class ResistorParams:
    r_ohm = h.Param(dtype=PositiveFloat, desc="Its resistance (ohm)")


def _module(name: str) -> h.Module:
    module = h.Module(name=name)
    for port in ("PLUS", "MINUS", "BULK"):
        module.add(h.Inout(name=port))
    return module


@dataclass(frozen=True)
class ResistorRequest:
    r_ohm: float

    def resolve(self, pdk: str) -> h.Module:
        geometry = polyres_table(pdk).length(self.r_ohm)
        module = _module(f"polyres_{geometry.w_nm}_{geometry.l_nm}")
        kit = device(pdk)
        pins = {"PLUS": module.PLUS, "MINUS": module.MINUS}
        if len(kit.port_list) == 3:
            pins["BULK"] = module.BULK
        module.res = kit(DeviceParams(l=geometry.l_nm * 1e-3 * µ, w=geometry.w_nm * 1e-3 * µ))(**pins)
        return place(module, geometry)


@h.generator
def resistor(params: ResistorParams) -> h.Module:
    """The request: an ideal resistor between ``PLUS`` and ``MINUS``."""
    module = _module("resistor")
    module.r = R(r=params.r_ohm)(p=module.PLUS, n=module.MINUS)
    return mark(module, ResistorRequest(params.r_ohm))
