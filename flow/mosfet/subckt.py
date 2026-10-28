"""
Single MOSFET for characterization in FRIDA.

One device of a PDK's core flavors (its type and threshold), sized like every generator's: the
width in the PDK's unit widths, fingered to its row cells, the length in multiples of its minimum.
The characterization's cases are every core flavor the PDK wraps at a few lengths.
"""

from importlib import import_module

import hdl21 as h
from hdl21.primitives import MosFamily, MosType, MosVth

from flow.circuit.devices import mos as _mos
from flow.circuit.ports import module_from_ports


@h.paramclass
class MosfetParams:
    """MOSFET parameters: the width in the PDK's unit widths, the length in multiples of its minimum."""

    tp = h.Param(dtype=MosType, desc="NMOS or PMOS", default=MosType.NMOS)
    vth = h.Param(dtype=MosVth, desc="Threshold flavor", default=MosVth.LOW)
    w = h.Param(dtype=int, desc="Width multiplier", default=8)
    l = h.Param(dtype=int, desc="Length multiplier", default=1)


@h.bundle
class MosfetNets:
    d = h.Inout(desc="Drain")
    g = h.Input(desc="Gate")
    s = h.Inout(desc="Source")
    b = h.Inout(desc="Body")


@h.generator
def Mosfet(param: MosfetParams) -> h.Module:
    """One MOSFET between its four terminals; ``pdk.compile()`` makes it the PDK's device."""

    if min(param.w, param.l) <= 0:
        raise ValueError(f"Invalid MOSFET params: {param}")
    Mosfet = module_from_ports("Mosfet", MosfetNets.signals)
    Mosfet.Mdut = _mos(tp=param.tp, vth=param.vth, w=param.w, l=param.l)(d=Mosfet.d, g=Mosfet.g, s=Mosfet.s, b=Mosfet.b)
    return Mosfet


# ==== The characterization's cases ====

LENGTHS = (1, 2, 4, 8)  # multiples of the minimum length
WIDTH = 8  # unit widths


def flavors(pdk: str) -> dict[str, tuple[MosType, MosVth]]:
    """Each distinct core device the PDK wraps, by name: its type and threshold (the first
    flavor that names it, where several map to one device)."""

    xtors = import_module(f"pdk.{pdk}.hdl21.primitives.prim_dicts").xtors
    found = {}
    for key, module in sorted(xtors.items(), key=lambda item: (item[0][-3].name, item[0][-2].value)):
        tp, vth, family = key[-3:]
        if family == MosFamily.CORE and vth != MosVth.NATIVE:
            found.setdefault(module.name, (tp, vth))
    return found


def cases(pdk: str) -> dict[str, MosfetParams]:
    """Every core device of the PDK at each length, named ``<device>_l<multiple>``."""

    return {
        f"{name}_l{length}": MosfetParams(tp=tp, vth=vth, w=WIDTH, l=length)
        for name, (tp, vth) in flavors(pdk).items()
        for length in LENGTHS
    }
