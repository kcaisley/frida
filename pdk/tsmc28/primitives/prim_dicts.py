"""Primitive dictionaries for TSMC28."""

from dataclasses import dataclass, field
from typing import Dict, Tuple

import hdl21 as h
from hdl21.prefix import n
from hdl21.primitives import (
    BipolarParams,
    DiodeParams,
    MosFamily,
    MosParams,
    MosType,
    MosVth,
    PhysicalCapacitorParams,
    PhysicalResistorParams,
)

from ..pdk_data import xtor_module

MosKey = Tuple[MosType, MosVth, MosFamily]

xtors: Dict[MosKey, h.ExternalModule] = {
    (MosType.NMOS, MosVth.LOW, MosFamily.CORE): xtor_module("nch_lvt"),
    (MosType.NMOS, MosVth.STD, MosFamily.CORE): xtor_module("nch"),
    (MosType.NMOS, MosVth.HIGH, MosFamily.CORE): xtor_module("nch_hvt"),
    (MosType.PMOS, MosVth.LOW, MosFamily.CORE): xtor_module("pch_lvt"),
    (MosType.PMOS, MosVth.STD, MosFamily.CORE): xtor_module("pch"),
    (MosType.PMOS, MosVth.HIGH, MosFamily.CORE): xtor_module("pch_hvt"),
}

# TODO: fill from PDK when passive/ diode wrappers are defined.
ress: Dict[str, h.ExternalModule] = {}
caps: Dict[str, h.ExternalModule] = {}
diodes: Dict[str, h.ExternalModule] = {}
bjts: Dict[str, h.ExternalModule] = {}
stdcells: Dict[str, h.ExternalModule] = {}


@dataclass
class Cache:
    mos_modcalls: Dict[MosParams, h.ExternalModuleCall] = field(default_factory=dict)
    res_modcalls: Dict[PhysicalResistorParams, h.ExternalModuleCall] = field(
        default_factory=dict
    )
    cap_modcalls: Dict[PhysicalCapacitorParams, h.ExternalModuleCall] = field(
        default_factory=dict
    )
    diode_modcalls: Dict[DiodeParams, h.ExternalModuleCall] = field(
        default_factory=dict
    )
    bjt_modcalls: Dict[BipolarParams, h.ExternalModuleCall] = field(
        default_factory=dict
    )


CACHE = Cache()

default_xtor_size = {
    "nch_lvt": (40 * n, 30 * n),
    "nch": (40 * n, 30 * n),
    "nch_hvt": (40 * n, 30 * n),
    "pch_lvt": (40 * n, 30 * n),
    "pch": (40 * n, 30 * n),
    "pch_hvt": (40 * n, 30 * n),
}
