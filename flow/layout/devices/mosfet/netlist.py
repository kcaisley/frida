"""The analog MOS every generator builds from (``mos``), and drivers as requests: a generator asks for a drive resistance; a PDK's mosfet table sizes it.

``driver(DriverParams(r_ohm, invert))`` is the request: an ideal driver, a controlled source that
copies its input (or its complement, ``invert``) between the rails behind ``r_ohm``, so a netlist
simulates before any PDK. Its view in a PDK (``DriverRequest.resolve``) is a chain of inverters of
the PDK's core transistors at their minimum length, low threshold (the flavor the row cells draw): the last one's NMOS and PMOS each the narrowest
whose switching resistance is at most ``r_ohm`` (``MosfetTable.width``: each type from its own
column, so every PDK gets its own PMOS-to-NMOS ratio), the ones before it tapering evenly down to
its source, a minimum-strength flip-flop: the fewest inverters of the request's polarity in which
none drives more than four times its own input (FO4), the first loading the flip-flop at most
``fanin`` minimum inverters (``DriverRequest.stages``; ``shared_fanin``: a flip-flop's FO4 shared
between the drivers on its net).
"""

import math
from dataclasses import dataclass
from functools import cache

import hdl21 as h
from hdl21.primitives import MosType, MosVth, R, Vcvs
from pydantic import PositiveFloat

from flow.circuit.devices import core_unit, fingers, logic_pair
from flow.layout.hdl21align import constraints as c
from flow.layout.hdl21align import place, row, rows
from flow.layout.package import metal_tracks
from flow.layout.pdkproc import in_pdk, pdk_value

from ..device import active_pdk, mark
from ..device import place as drawn
from .geometry import InverterGeometry
from .table import mosfet_table

# The PDK whose unit sizes analog devices keep physically in another PDK; None keeps them
# relative, in the active PDK's own units.
CONSTANT_FROM = None


def mos(*, tp, vth, w, l):
    """An analog MOS, fingered to the active PDK's row cells.

    With ``CONSTANT_FROM`` set, ``w`` and ``l`` are that PDK's units made physical: the width
    to the nearest whole unit of the active PDK, the length kept as drawn, except at one or two
    minimum lengths, which stay that multiple of the active PDK's minimum.
    """

    if CONSTANT_FROM is not None:
        (w_ref, l_ref), (w_unit, _) = core_unit(CONSTANT_FROM), core_unit(h.pdk.default())
        w = max(1, round(w * w_ref / w_unit))
        if l > 2:
            l = h.Prefixed.new(round(l * l_ref * 1e9), h.Prefix.NANO)
    w, nf = fingers(w, "analog")
    return h.Mos(tp=tp, vth=vth, w=w, l=l, nf=nf)


# the fan-out from one inverter of the chain to the next
_TAPER = 4


@h.paramclass
class DriverParams:
    r_ohm = h.Param(dtype=PositiveFloat, desc="Its output resistance at most (ohm)")
    invert = h.Param(dtype=bool, desc="Whether it drives its input's complement", default=False)
    wide_input = h.Param(
        dtype=bool,
        desc="Whether its first inverter's input bar spans the cell (reached from more tracks)",
        default=False,
    )
    mirror = h.Param(dtype=bool, desc="Whether ALIGN may mirror its chain in its row", default=True)
    fanin = h.Param(
        dtype=PositiveFloat,
        desc="The most its input loads its source, a minimum-strength flip-flop, in minimum inverters (FO4: four)",
        default=4.0,
    )


@h.bundle
class DriverPorts:
    A = h.Input()
    Y = h.Output()
    VDD = h.Power(direction=h.PortDir.INOUT)
    VSS = h.Ground(direction=h.PortDir.INOUT)


def _module(name: str) -> h.Module:
    module = h.Module(name=name)
    for port in DriverPorts.signals.values():
        module.add(h.Signal(name=port.name, vis=h.Visibility.PORT, direction=port.direction, usage=port.usage))
    return module


@dataclass(frozen=True)
class DriverRequest:
    """A driver of at most ``r_ohm``, of its input or (``invert``) its complement, its input loading
    its source, a minimum-strength flip-flop, at most ``fanin`` minimum inverters; as drawn, its
    first inverter's input bar across its cell (``wide_input``: a parent's router reaches it from
    more tracks), its chain mirrored by ALIGN or not (``mirror``)."""

    r_ohm: float
    invert: bool
    wide_input: bool = False
    mirror: bool = True
    fanin: float = float(_TAPER)

    def stages(self, pdk: str) -> list[tuple[int, int]]:
        """The chain's inverters, input first: each one's NMOS and PMOS widths in unit widths.

        The last is the narrowest at ``r_ohm``. The ones before it taper evenly from the source, a
        minimum-strength flip-flop (it drives as the minimum inverter does), counted as the stage
        before the first at a quarter of ``fanin`` minimum inverters, so that the first loads it at
        most ``fanin`` of them: the fewest inverters of the request's polarity (an odd count
        inverts) in which none drives more than four times its own input (FO4), each inner one the
        inverter whose input is nearest its step of the taper (``_pick``)."""
        table = mosfet_table(pdk)
        n = table.width(MosType.NMOS, MosVth.LOW, self.r_ohm).units
        p = table.width(MosType.PMOS, MosVth.LOW, self.r_ohm).units
        ratio, last = p / n, _input(n, p)
        source = _input(1, 1) * self.fanin / _TAPER
        smallest = _input(1, max(1, round(ratio)))  # the least a stage can be, whatever its budget
        for count in range(1 if self.invert else 2, 16, 2):
            step = (last / source) ** (1 / count)
            if step > _TAPER:
                continue
            # each inner one nearest its step, within FO4 of the one before it and large enough
            # that the ones after it reach the last within FO4 too
            chain, before = [], source
            for k in range(1, count):
                high = max(before * _TAPER, smallest)
                pick = _pick(source * step**k, last / _TAPER ** (count - k), high, ratio, n)
                if pick is None:
                    break
                chain.append((pick, max(1, round(pick * ratio))))
                before = _input(*chain[-1])
            else:
                return [*chain, (n, p)]
        raise ValueError(f"no chain of fewer than 16 inverters tapers to {self} at FO4")

    def resolve(self, pdk: str) -> h.Module:
        """The chain of inverters in ``pdk``, input first, each a complementary row cell
        (``inverter``), side by side in one row."""
        stages = self.stages(pdk)
        fixed = not self.mirror and len(stages) > 1
        # named by its cells as drawn: requests whose inverters round alike share one chain
        cells_named = "_".join("{}n{}p{}f".format(*_inverter_sizes(n, p)) for n, p in stages)
        drawn_as = ("_w" if self.wide_input else "") + ("_r0" if fixed else "")
        module = _module(f"driver_{'inv' if self.invert else 'buf'}_{cells_named}{drawn_as}")
        node = module.A
        cells = []
        for index, (n, p) in enumerate(stages):
            out = module.Y if index == len(stages) - 1 else module.add(h.Signal(), name=f"n{index}")
            wide = self.wide_input and index == 0
            cell = inverter(pdk, n, p, wide_input=wide)(A=node, Y=out, VDD=module.VDD, VSS=module.VSS)
            cells.append(module.add(cell, name=f"Xinv{index}"))  # a subcircuit's instance is X...
            node = out
        # the stages' links jog between the M2 tracks of an output and the next input on M1 at the
        # cells' shared edge, where M1 is free: M3 stays the parent's, which runs its links up there.
        # Where an inner stage's gate pad crowds that edge, its link lands inside it instead, and
        # the next one needs room: a gap after it (``_gaps``). A PDK whose row cells cannot draw
        # the chain's inverters gets no gaps: the view still simulates, and a layout of it stops
        # where ALIGN's generator draws the same cell
        try:
            gaps = _gaps(pdk, stages, self.wide_input)
        except AssertionError:
            gaps = [0] * len(stages)
        spread = tuple(c.Spread((cells[k], cells[k + 1]), c.Axis.HORIZONTAL, gap) for k, gap in enumerate(gaps) if gap)
        # a chain not mirrored (``mirror`` False): its output at its right end, wherever it stands,
        # so two chains side by side never turn their outputs towards each other
        unmirrored = (c.PlaceOnGrid(c.Axis.VERTICAL, metal_tracks(pdk, "M1")[0]),) if fixed else ()
        constraints = (c.Route(min_layer=1, max_layer=2), *spread, *unmirrored)
        place(module, rows(row(*cells)), symmetric=False, constraints=constraints)
        return module


_INVERTERS: dict[tuple[str, int, int, int, bool], h.Module] = {}


def _input(n_units: int, p_units: int) -> int:
    """An inverter's input load: its NMOS and PMOS gates' widths as drawn (``_inverter_sizes``), in
    unit widths."""
    n_w, p_w, _ = _inverter_sizes(n_units, p_units)
    return n_w + p_w


def _pick(target: float, low: float, high: float, ratio: float, most: int) -> int | None:
    """The NMOS width (unit widths, at most ``most``) of the inverter, its PMOS ``ratio`` as wide,
    whose input is nearest ``target`` within ``low`` and ``high``; None where none is."""
    sizes = range(max(1, math.floor(low / (1 + ratio)) - 3), min(most, math.ceil(high / (1 + ratio)) + 3) + 1)
    loads = {k: _input(k, max(1, round(k * ratio))) for k in sizes}
    fits = [k for k, load in loads.items() if low <= load <= high]
    return min(fits, key=lambda k: (abs(loads[k] - target), k)) if fits else None


def input_load(pdk: str, request: DriverRequest) -> float:
    """The load ``request``'s chain puts on its source, in minimum inverters: its first one's input."""
    return _input(*request.stages(pdk)[0]) / _input(1, 1)


def shared_fanin(pdk: str, others: list[DriverRequest]) -> float:
    """What a driver's input may load a minimum-strength flip-flop that drives ``others`` too, in
    minimum inverters: its FO4, four of them, less the others' inputs; one at the least."""
    return max(1.0, _TAPER - sum(input_load(pdk, other) for other in others))


def _inverter_sizes(n_units: int, p_units: int) -> tuple[int, int, int]:
    """An inverter's NMOS and PMOS widths (unit widths, in total) and their shared finger count:
    the logic cells' finger widths (``logic_pair``), each finger at least the narrowest its row
    cell contacts (``_least_units``)."""
    (n_w, nf), (p_w, _) = logic_pair(n_units, p_units)
    nf = nf or 1
    n_low, p_low = _least_units(active_pdk())
    return max(n_w, nf * n_low), max(p_w, nf * p_low), nf


@cache
def _least_units(pdk: str | None) -> tuple[int, int]:
    """The narrowest NMOS and PMOS finger (unit widths) of an inverter in ``pdk``: the narrowest the
    PDK contacts (``MOS_FINGER_MIN_UNITS``), and no narrower than its row cell draws, every strip's
    contacts beside the gate pad (``rowcell.inverter_min_widths``); without the PDK's row cells,
    the first alone."""
    low = getattr(h.pdk.default(), "MOS_FINGER_MIN_UNITS", 1)
    if pdk is None:
        return low, low
    unit_m, length_m = core_unit(h.pdk.default())
    try:
        n_nm, p_nm = in_pdk(pdk, "rowcell", "inverter_min_widths", round(length_m * 1e9))
    except FileNotFoundError:  # a PDK without row cells
        return low, low
    unit = round(unit_m * 1e9)
    return max(low, math.ceil(n_nm / unit)), max(low, math.ceil(p_nm / unit))


@cache
def row_height_nm(pdk: str) -> int:
    """The height (nm) of ``pdk``'s rows, the cells' that drivers are drawn in (``rowcell.H``)."""
    return int(pdk_value(pdk, "rowcell", "H"))


def _cases(stages: list[tuple[int, int]]) -> list[tuple[int, int, int, int]]:
    """A chain's inverters as the row cells draw them: (gate length, NMOS and PMOS finger widths,
    fingers), nm, in the active PDK."""
    unit_m, length_m = core_unit(h.pdk.default())
    unit, length = round(unit_m * 1e9), round(length_m * 1e9)
    return [
        (length, n_w * unit // nf, p_w * unit // nf, nf) for n_w, p_w, nf in (_inverter_sizes(n, p) for n, p in stages)
    ]


# each inverter cell's width and gate pad offset (``rowcell.inverter_outlines``), a PDK and case
_OUTLINES: dict[tuple[str, tuple[int, int, int, int]], tuple[int, int]] = {}


def _outlines(pdk: str, cases: list[tuple[int, int, int, int]]) -> list[tuple[int, int]]:
    """Each inverter cell's width (nm) and how far its gate pad stays from its left edge (nm), the
    cases not drawn yet drawn at once in a process bound to ``pdk``."""
    missing = sorted({case for case in cases if (pdk, case) not in _OUTLINES})
    if missing:
        for case, (width, pad) in zip(missing, in_pdk(pdk, "rowcell", "inverter_outlines", missing), strict=True):
            _OUTLINES[pdk, case] = (int(width), int(pad))
    return [_OUTLINES[pdk, case] for case in cases]


def _gaps(pdk: str, stages: list[tuple[int, int]], wide_input: bool = False) -> list[int]:
    """The gap (nm) a chain leaves after each of its inverters: one M1 pitch after an inner one
    whose gate pad keeps less than ALIGN's M1 space from the wire on its left edge's track. The
    link into it cannot jog there and lands on a track inside it, stretching its input bar towards
    the next cell, where the next link jogs: one pitch further on, the two bars keep their M2
    end-to-end space. After a first inverter whose input bar spans its cell (``wide_input``), two
    pitches where the link out of it jogs at the shared edge (the next cell's pad clear of it):
    beside the bar's end, the link would run past the chain's outline. Otherwise none."""
    pitch, width = metal_tracks(pdk, "M1")
    clear = pitch - width + width // 2  # ALIGN's space beside the edge wire, and the wire's half
    pads = [pad for _, pad in _outlines(pdk, _cases(stages))]
    gaps = [pitch if 0 < k < len(stages) - 1 and pads[k] < clear else 0 for k in range(len(stages))]
    if wide_input and len(stages) > 1 and pads[1] >= clear:
        gaps[0] = 2 * pitch
    return gaps


def driver_widths_nm(pdk: str, requests: list[DriverRequest]) -> list[int]:
    """Each driver's width (nm) as ``DriverRequest.resolve`` draws it, its chain's inverter cells
    side by side and the gaps between them (``_gaps``): for planning the rows they stand in. One
    process bound to ``pdk`` draws them."""
    chains = [r.stages(pdk) for r in requests]
    _outlines(pdk, [case for stages in chains for case in _cases(stages)])  # every case at once
    return [
        sum(w for w, _ in _outlines(pdk, _cases(stages))) + sum(_gaps(pdk, stages, r.wide_input))
        for r, stages in zip(requests, chains, strict=True)
    ]


def inverter(pdk: str, n_units: int, p_units: int, wide_input: bool = False) -> h.Module:
    """A complementary inverter of the PDK's core low-threshold transistors at their minimum length,
    ``n_units`` and ``p_units`` of its unit width, in one row cell (``InverterGeometry``): their
    fingers shared (``logic_pair``, the logic cells' finger widths), each at least the narrowest
    finger the PDK contacts; its input bar across the cell where ``wide_input``. One module a PDK,
    size and input bar."""
    n_w, p_w, nf = _inverter_sizes(n_units, p_units)
    key = (pdk, n_w, p_w, nf, wide_input)  # by its sizes: requests that round alike share one module
    if key not in _INVERTERS:
        module = _module(f"inv_{n_w}n{p_w}p{nf}f" + ("_w" if wide_input else ""))
        module.mn0 = h.Mos(tp=MosType.NMOS, vth=MosVth.LOW, w=n_w, l=1, nf=nf)(
            d=module.Y, g=module.A, s=module.VSS, b=module.VSS
        )
        module.mp0 = h.Mos(tp=MosType.PMOS, vth=MosVth.LOW, w=p_w, l=1, nf=nf)(
            d=module.Y, g=module.A, s=module.VDD, b=module.VDD
        )
        _INVERTERS[key] = drawn(module, InverterGeometry(n_w, p_w, nf, wide_input))
    return _INVERTERS[key]


@h.generator
def driver(params: DriverParams) -> h.Module:
    """The request: an ideal driver behind ``r_ohm`` (a copy of ``A``, or ``VDD - A``)."""
    module = _module("driver")
    module.drive = h.Signal()
    if params.invert:
        module.e = Vcvs(gain=-1)(p=module.drive, n=module.VDD, cp=module.A, cn=module.VSS)
    else:
        module.e = Vcvs(gain=1)(p=module.drive, n=module.VSS, cp=module.A, cn=module.VSS)
    module.r = R(r=params.r_ohm)(p=module.drive, n=module.Y)
    return mark(module, DriverRequest(params.r_ohm, params.invert, params.wide_input, params.mirror, params.fanin))
