"""MOM capacitors as requests: a generator asks for a capacitance and a style; a PDK's momcap table
gives the fingers that reach it.

- ``strip(StripParams(net_f, whole_f, layers))``: a difference strip, a main and a difference
  capacitor in line under one top plate, its weight their difference ``net_f``, every strip as long
  as the whole one (``whole_f``: at its longest with a minimum-length difference stub);
- ``unit(UnitParams(c_f, layers))``: a ring unit of ``c_f``.

The request's body is ideal (a strip's two capacitors share ``whole_f`` and differ by ``net_f``),
so a netlist simulates before any PDK. Its view in a PDK has the lengths the table gives
(``MomcapTable.strip``, ``.unit``, on the PDK's grid: on fewer metals than asked where a unit is
below the smallest the asked-for count draws, and at the smallest on one metal, with its ``FloorError``,
where it is below even that) and every capacitance the table fits at them,
the plates' coupling to the shield and the substrate (``SHIELD``) too; its ports are the terminals ALIGN's
``MomUnit`` draws and labels. The view carries its geometry
(``device.geometry_of``), what ALIGN's ``MomUnit`` draws.

A capacitor's view is its plate-to-plate capacitances (``MomCap``, ``mom_cap`` as a device): ideal,
or, where it ``varies``, its value in a Monte Carlo (``variation``).

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

from dataclasses import dataclass, replace
from functools import cache
from typing import Any

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, Vdc
from pydantic import NonNegativeFloat, NonNegativeInt, PositiveFloat, PositiveInt

from flow.circuit.ports import module_from_ports
from flow.layout.pdkproc import in_pdk

from ..device import FloorError, mark, place
from .geometry import PINS, ArrayKind, MomcapGeometry, MomStyle, Neighbour
from .table import momcap_table

# the module's port of each terminal the extraction names (the substrate with the shield, which a block ties to ground)
_PORT = {"TOP": "TOP", "MAIN": "MAIN", "DIFF": "DIFF", "INNER": "INNER", "SHIELD": "SHIELD", "GROUND": "SHIELD"}


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


def variation(pelgrom: float = 0.0, gradient_per_um: float = 0.0) -> list[Any]:
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
    MomCap.props["c"] = c  # its nominal value, for what reads the netlist unsimulated (its area)
    MomCap.drawn = h.Signal()
    MomCap.probe = Vdc(dc=h.Literal(f"{value}/1e-15"))(p=MomCap.drawn, n=MomCap.BULK)
    return MomCap


def mom_cap(c_f, *, varies=False, x_um=0.0, y_um=0.0):
    """An FMOM leaf of ``c_f`` farads (``MomCap``), varying with a Monte Carlo at (``x_um``,
    ``y_um``) where ``varies``, as the circuit's device factories give one ."""
    return MomCap(MomCapParams(c=c_f, varies=varies, x_um=x_um, y_um=y_um))


@h.paramclass
class StripParams:
    net_f = h.Param(dtype=NonNegativeFloat, desc="Its main less its difference capacitance (F): its weight")
    whole_f = h.Param(dtype=PositiveFloat, desc="A whole strip's net capacitance (F), which sets every strip's length")
    layers = h.Param(dtype=PositiveInt, desc="How many of the PDK's MOM metals it stacks", default=3)
    left = h.Param(dtype=Neighbour, desc="What its left side meets in an array", default=Neighbour.EDGE)
    right = h.Param(dtype=Neighbour, desc="What its right side meets in an array", default=Neighbour.EDGE)


@h.paramclass
class UnitParams:
    c_f = h.Param(dtype=PositiveFloat, desc="Its capacitance (F)")
    layers = h.Param(dtype=PositiveInt, desc="How many of the PDK's MOM metals it stacks", default=3)
    left = h.Param(dtype=Neighbour, desc="What its left side meets in an array", default=Neighbour.EDGE)
    right = h.Param(dtype=Neighbour, desc="What its right side meets in an array", default=Neighbour.EDGE)
    above = h.Param(dtype=Neighbour, desc="What its top meets in a column array", default=Neighbour.EDGE)
    below = h.Param(dtype=Neighbour, desc="What its bottom meets in a column array", default=Neighbour.EDGE)
    frame_f = h.Param(
        dtype=NonNegativeFloat, desc="The capacitance whose finger sets the ring (F); 0: its own", default=0.0
    )
    array = h.Param(dtype=ArrayKind, desc="How it meets its neighbours", default=ArrayKind.CHANNELS)
    pin_band_nm = h.Param(
        dtype=NonNegativeInt,
        desc="A column unit's strip pins this high from its bottom at most (nm); 0: all",
        default=0,
    )


@cache
def array_outline_nm(pdk: str, geometry: MomcapGeometry) -> tuple[int, int]:
    """An abutting array unit of ``geometry`` in ``pdk``: its outline (nm, wide, tall), from wall
    centre to wall centre and bar centre to bar centre (``MomUnit``), a band under a column array's
    bottom row aside."""
    g = in_pdk(pdk, "capcell", "mom_geometry", geometry.layers)
    w, s, e = g["width"], g["space"], g["end_gap"]
    if geometry.style is MomStyle.DIFFERENCE:
        tall = geometry.length_nm + geometry.diff_length_nm + 3 * e + w
    else:
        tall = max(geometry.length_nm, geometry.frame_nm) + 2 * e + w
    return 2 * w + 2 * s, tall


def _module(name: str, ports: tuple[str, ...]) -> h.Module:
    module = h.Module(name=name)
    for port in ports:
        module.add(h.Inout(name=port))
    return module


def si_f(c_f: float) -> str:
    """A capacitance as a netlist writes it: three digits in fF (``2.27f``)."""
    return f"{c_f * 1e15:.3g}f"


def _view(name: str, ports: tuple[str, ...], pdk: str, geometry: MomcapGeometry, floor: FloorError | None) -> h.Module:
    """A unit as drawn: every terminal pair's capacitance the table gives, between their ports. Its
    design values (``design``, the parameters its device's call carries in a netlist): its plate's
    capacitance to the top plate (``c``; a strip's difference plate's too, ``c_diff``), or a
    strip pair's between its plates."""
    module = _module(name, ports)
    between = {}
    for index, ((a, b), c_f) in enumerate(sorted(momcap_table(pdk).capacitances(geometry).items())):
        p, n = _PORT[a], _PORT[b]
        if p != n and c_f > 0:
            module.add(C(c=c_f)(p=getattr(module, p), n=getattr(module, n)), name=f"c{index}_{a.lower()}_{b.lower()}")
            between[frozenset((p, n))] = c_f
    design = {
        "c": between.get(
            frozenset(("INNER", "TOP")), between.get(frozenset(("MAIN", "TOP")), between.get(frozenset(("A", "B"))))
        ),
        "c_diff": between.get(frozenset(("DIFF", "TOP"))),
    }
    module.props.set("design", {k: si_f(v) for k, v in design.items() if v})
    return place(module, geometry, floor)


@dataclass(frozen=True)
class StripRequest:
    net_f: float
    whole_f: float
    layers: int
    left: Neighbour = Neighbour.EDGE
    right: Neighbour = Neighbour.EDGE

    def resolve(self, pdk: str) -> h.Module:
        geometry, floor = momcap_table(pdk).strip(self.layers, self.net_f, self.whole_f)
        geometry = replace(geometry, left=self.left, right=self.right)
        name = f"strip_{geometry.layers}m_{geometry.length_nm}_{geometry.diff_length_nm}_{geometry.sides}"
        return _view(name, PINS[MomStyle.DIFFERENCE], pdk, geometry, floor)


@dataclass(frozen=True)
class UnitRequest:
    c_f: float
    layers: int
    left: Neighbour = Neighbour.EDGE
    right: Neighbour = Neighbour.EDGE
    above: Neighbour = Neighbour.EDGE
    below: Neighbour = Neighbour.EDGE
    frame_f: float = 0.0
    array: ArrayKind = ArrayKind.CHANNELS
    pin_band_nm: int = 0

    def resolve(self, pdk: str) -> h.Module:
        table = momcap_table(pdk)
        exact = self.array is ArrayKind.COLUMNS  # an array's units share their stack
        geometry, floor = table.unit(self.layers, self.c_f, exact=exact)
        frame = table.unit(self.layers, self.frame_f, exact=exact)[0].length_nm if self.frame_f else 0
        geometry = replace(
            geometry,
            left=self.left,
            right=self.right,
            above=self.above,
            below=self.below,
            frame_nm=frame,
            array=self.array,
            pin_band_nm=self.pin_band_nm,
        )
        name = f"unit_{geometry.layers}m_{geometry.length_nm}_{geometry.sides}" + (f"_f{frame}" if frame else "")
        name += f"_b{self.pin_band_nm}" if self.pin_band_nm else ""
        return _view(name, PINS[MomStyle.RING], pdk, geometry, floor)


@h.generator
def strip(params: StripParams) -> h.Module:
    """The request: a strip's main and difference capacitors, ideal."""
    module = _module("strip", PINS[MomStyle.DIFFERENCE])
    module.cmain = C(c=(params.whole_f + params.net_f) / 2)(p=module.MAIN, n=module.TOP)
    if params.whole_f > params.net_f:
        module.cdiff = C(c=(params.whole_f - params.net_f) / 2)(p=module.DIFF, n=module.TOP)
    return mark(module, StripRequest(params.net_f, params.whole_f, params.layers, params.left, params.right))


@h.generator
def unit(params: UnitParams) -> h.Module:
    """The request: a unit capacitor, ideal."""
    module = _module("unit", PINS[MomStyle.RING])
    module.c = C(c=params.c_f)(p=module.INNER, n=module.TOP)
    return mark(
        module,
        UnitRequest(
            params.c_f,
            params.layers,
            params.left,
            params.right,
            params.above,
            params.below,
            params.frame_f,
            params.array,
            params.pin_band_nm,
        ),
    )
