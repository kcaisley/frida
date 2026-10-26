"""Fringe metal-oxide-metal (FMOM) capacitors: the styles, and their netlist view.

Every style stacks the same plates on one to three thin metals at their minimum width and space,
the plates of one terminal joined through vias, over a shield on the metal below:

- ``DIFFERENCE``: a ring (the top plate) around two inner fingers in line, each from one end, a
  main and a difference finger (FRIDA's CDAC unit: its weight is the length difference);
- ``RING``: a ring around one inner finger;
- ``STRIP``: two open-ended strips side by side.

A capacitor's netlist is its plate-to-plate capacitance (``MomCap``, or ``mom_cap`` as a device): ideal, or, where it ``varies``,
its value in a Monte Carlo (``variation``). Its dependence on the plates' length is a PDK's fit to
extracted test structures (``tech.MOM_FITS``, from ``momcap_characterization``).

**Variation.** A varying capacitor of value C at (x, y) on the die is, in each Monte Carlo run,

    C (1 + A / sqrt(C / 1 fF) z + g (x g_x + y g_y) / |(g_x, g_y)|)

Pelgrom's mismatch, sigma_C / C = A / sqrt(C / 1 fF), with z drawn for each capacitor alone, and a
linear process gradient of g per um across the die in a direction (g_x, g_y) drawn once a run. A
(``mom_pelgrom``, a fraction: 0.001 is 0.1 %·sqrt(fF)) and g (``mom_gradient``, per um) are the
run's conditions, set by ``variation``; zero keeps every capacitor at C, so a nominal run of the
same netlist is the ideal view's. Pelgrom's variances add, so one capacitor of the extraction's
value varies as its parts would together. A varying capacitor also carries a probe: its net
``drawn`` sits at its value in fF above its ``BULK``, so a Monte Carlo of operating points reads
back what each run drew.
"""

from enum import Enum, auto

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, Vdc

from flow.circuit.ports import module_from_ports


class MomStyle(Enum):
    DIFFERENCE = auto()
    RING = auto()
    STRIP = auto()


@h.bundle
class MomCapPorts:
    PLUS, MINUS, BULK = h.Inouts(3)


PORTS = MomCapPorts.signals

# the Monte Carlo's netlist parameters: the run's conditions, then the drawn variables
PELGROM, GRADIENT = "mom_pelgrom", "mom_gradient"
MISMATCH, GRADIENT_X, GRADIENT_Y = "mom_mismatch", "mom_gx", "mom_gy"
# Spectre draws z for each capacitor (mismatch: for each subcircuit instance that reads it) and
# the gradient's direction once a run (process)
STATISTICS = f"""statistics {{
    process {{
        vary {GRADIENT_X} dist=gauss std=1
        vary {GRADIENT_Y} dist=gauss std=1
    }}
    mismatch {{
        vary {MISMATCH} dist=gauss std=1
    }}
}}"""


@h.paramclass
class MomCapParams:
    c = h.Param(dtype=h.Scalar, desc="Plate-to-plate capacitance (F): the extraction's, where it varies")
    varies = h.Param(
        dtype=bool, desc="Whether the value follows the Monte Carlo's variation (``variation``)", default=False
    )
    x_um = h.Param(dtype=float, desc="The plates' centroid on the die (um), across", default=0.0)
    y_um = h.Param(dtype=float, desc="The plates' centroid on the die (um), along", default=0.0)


def variation(pelgrom: float = 0.0, gradient_per_um: float = 0.0) -> list:
    """A simulation's attributes that set the varying capacitors' conditions: Pelgrom's coefficient
    ``pelgrom`` (a fraction: 0.001 is 0.1 %·sqrt(fF)) and the gradient's magnitude per um, with
    the drawn variables at their nominal 0 and Spectre's statistics over them. Zero gives every
    capacitor its value."""
    nominal = {PELGROM: pelgrom, GRADIENT: gradient_per_um, MISMATCH: 0.0, GRADIENT_X: 0.0, GRADIENT_Y: 0.0}
    return [*(hs.Param(name=name, val=value) for name, value in nominal.items()), hs.Literal(STATISTICS)]


@h.generator
def MomCap(params: MomCapParams) -> h.Module:
    """Keep the physical shield terminal; the ideal model has no parasitics. A varying capacitor's
    value is the Monte Carlo's expression of it, and its probe ``drawn`` reads it back."""

    MomCap = module_from_ports("MomCap", PORTS)
    if not params.varies:
        MomCap.cap = C(c=params.c)(p=MomCap.PLUS, n=MomCap.MINUS)
        return MomCap
    c = float(params.c)
    direction = f"sqrt({GRADIENT_X}*{GRADIENT_X} + {GRADIENT_Y}*{GRADIENT_Y} + 1e-30)"
    value = (
        f"{c:.9g}*(1 + {PELGROM}/sqrt({c:.9g}/1e-15)*{MISMATCH}"
        f" + {GRADIENT}*({params.x_um:.9g}*{GRADIENT_X} + {params.y_um:.9g}*{GRADIENT_Y})/{direction})"
    )
    MomCap.cap = C(c=h.Literal(value))(p=MomCap.PLUS, n=MomCap.MINUS)
    MomCap.drawn = h.Signal()
    MomCap.probe = Vdc(dc=h.Literal(f"{value}/1e-15"))(p=MomCap.drawn, n=MomCap.BULK)
    return MomCap


def mom_cap(c_f, *, varies=False, x_um=0.0, y_um=0.0):
    """An FMOM leaf of ``c_f`` farads (``MomCap``), varying with a Monte Carlo at (``x_um``,
    ``y_um``) where ``varies``, as the circuit's device factories give one (``flow.circuit.devices``)."""
    return MomCap(MomCapParams(c=c_f, varies=varies, x_um=x_um, y_um=y_um))
