"""Fringe metal-oxide-metal (FMOM) capacitors: the styles, and their ideal netlist view.

Every style stacks the same plates on one to three thin metals at their minimum width and space,
the plates of one terminal joined through vias, over a shield on the metal below:

- ``DIFFERENCE``: a ring (the top plate) around two inner fingers in line, each from one end, a
  main and a difference finger (FRIDA's CDAC unit: its weight is the length difference);
- ``RING``: a ring around one inner finger;
- ``STRIP``: two open-ended strips side by side.

A capacitor's netlist is its plate-to-plate capacitance (``MomCap``, the ideal view); its
dependence on the plates' length is a PDK's fit to extracted test structures (``tech.MOM_FITS``,
from ``momcap_characterization``).
"""

from enum import Enum, auto

import hdl21 as h
from hdl21.primitives import C

from flow.circuit.ports import module_from_ports


class MomStyle(Enum):
    DIFFERENCE = auto()
    RING = auto()
    STRIP = auto()


@h.bundle
class MomCapPorts:
    PLUS, MINUS, BULK = h.Inouts(3)


PORTS = MomCapPorts.signals


@h.paramclass
class MomCapParams:
    c = h.Param(dtype=h.Scalar, desc="Ideal plate-to-plate capacitance")


@h.generator
def MomCap(params: MomCapParams) -> h.Module:
    """Keep the physical shield terminal; the ideal model has no parasitics."""

    MomCap = module_from_ports("MomCap", PORTS)
    MomCap.cap = C(c=params.c)(p=MomCap.PLUS, n=MomCap.MINUS)
    return MomCap
