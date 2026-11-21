"""The capacitive DAC's circuit: its nets (``Nets``) and its generator (``netlist``), one side's
stages of the design ``Params``: each stage's capacitors and the drivers of their bottom plates.

The block is one side of the converter's differential DAC, in its netlist, its schematic, its
layout and its extraction alike. The two sides share no net but the supply: the converter holds a
second, this one's mirror image (each side's MSB outside), and a testbench two (``flow.capdac.sim``).
A mirror image matches the sides however this one is laid out. A gradient across the pair moves
each stage's two sides oppositely: a step that switches both sides at once (the testbench's) cancels
it, but the converter switches one side a decision, from its A state (``calc_decision_steps``), so
there it shifts both outcomes of a decision alike, an offset that changes from decision to decision
and that only the redundancy absorbs.

The array (``params._weights``, the arithmetic a run's ``TbParams`` reads too) is the N - 1 binary
steps of an N-bit converter, spent over its extra cycles by its ``Redundancy``, C0 the heaviest.
Each side switches ``scale`` times the least capacitance at which the sampled noise equals the
quantization noise (``params._switched_f``), at a full scale of the DAC's whole reference, the
PDK's supply (the side's own full scale is below it: ``params.Params``); a unit of weight is its
share of it.

A stage's weight is built in pieces (``params._pieces``), whole increments of ``coarse_weight`` and the
remainder below it, each a main and a difference plate (DIFFERENCE_CAPS: a whole piece's plates a
coarse weight together) or a unit capacitor (UNIT_CAPS). The pieces are drawn as requests for
capacitors (``flow.layout.devices.momcap``) arranged so that the side's outline, its capacitors and
both bands of drivers, comes nearest two to one tall to wide (``_two_to_one``: the converter's two
sides side by side about square) without more area: difference strips all of one length, a stage's
pieces end to end cut into the fewest strips of one load that hold it (``_strips``: a piece in
several strips where short, several pieces in one where long; the stage's plates the same), a
stage's last strip in the row's ring where it holds less; unit capacitors each in one unit or
several, in a column array of so many rows. A stage's main bottom plates follow its state and its
difference plates the complement, each through a request for a driver
(``flow.layout.devices.mosfet``) of the on-resistance that settles the stage's step to half an LSB
within ``settle_ps`` over ``settle_margin`` (``_drive_r_ohm``: past its chain of FO4 delays, for its
plate's load as the table draws it, ``_plate_loads``). The step sized for is the testbench's, both
sides switched at once (``flow.capdac.sim``); the converter switches one side a decision, half the
step in its LSB, which the same drivers settle ln 2 time constants sooner. A minimum-strength flip-flop drives each state at FO4:
the difference driver one inverter (the complement), the main driver's chain loading it with what
is left of four minimum inverters (``shared_fanin``); the difference drivers take the states on
an input of their own (``dac_state_diff``), the same flip-flops' outputs brought from outside the
side, so that the side's two bands of drivers share no wire. Each stage's main plate is sensed by
the least inverter the kit draws (``least_inverter``), the sense inverters in a row of their own at
the main band's outer edge: each one's output the side's ``dac_plate`` port (the plate's complement
at full swing, landed on the side's bottom edge), its input part of the plate's load.

The netlist holds no PDK's dimensions: every request is an ideal device, so it simulates as it is,
and ``flow.layout.devices.device.resolve`` makes each the PDK's own from its precharacterized
tables: a strip's or a unit's finger lengths, a driver's inverters' widths.

The generator states its layout as it builds (``_place``, ``flow.layout.hdl21align``, after
Fritchman's AlignHdl21): rows of its own instances, which ALIGN places as stated, each driver a cell
of its own rows (a chain of inverters one cell, its links its own, ``rowcell.inverter_chain``). In
a kit whose rails carry no taps (its row ends' tie cells alone tie the wells), the layout's band
rows of a side wider than twice the ties' reach (the kit's ``TIE_REACH``) take its tie cells among
their drivers too (``params.WellTies``, ``_tied_row``).
"""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from importlib import import_module
from itertools import combinations, pairwise
from math import log

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.cells import library_module
from flow.circuit.ports import module_from_ports
from flow.layout.devices.device import FloorError, active_pdk
from flow.layout.devices.momcap.geometry import ArrayKind, MomcapGeometry, Neighbour
from flow.layout.devices.momcap.netlist import StripParams, UnitParams, array_outline_nm, strip, unit
from flow.layout.devices.momcap.table import momcap_table, stacked_over_rows
from flow.layout.devices.mosfet.geometry import flavor
from flow.layout.devices.mosfet.netlist import (
    DriverParams,
    DriverRequest,
    drawn_ohm,
    driver,
    driver_widths_nm,
    input_f,
    least_inverter,
    row_height_nm,
    shared_fanin,
)
from flow.layout.devices.mosfet.table import mosfet_table
from flow.layout.hdl21align import Border, EdgePin, Spot, edge_pins, place, row, rows
from flow.layout.hdl21align import constraints as c
from flow.layout.package import metal_tracks, pdk_dir

from .params import Params, WeightImpl, WellTies, _pieces, _plates, _switched_f, _weights


@h.bundle
class Nets:
    """The side's stage states in, a bit per stage, C0 first; each stage's main bottom plate sensed
    out (``dac_plate``, the owner's, 2026-11-20: a self-timed converter's sign that the stage has
    switched); its top plate; the DAC's supply, which its drivers switch the bottom
    plates between (the ADC's DAC reference). A side of difference strips (DIFFERENCE_CAPS) has a
    second input of the same states, its difference drivers' (``dac_state_diff``), at the strips'
    far end, driven from outside the side, so that no wire of it runs between its two bands of
    drivers."""

    dac_state = h.Input(desc="The stage states, C0 first")
    dac_plate = h.Output(desc="Each stage's main bottom plate's complement at full swing, C0 first")
    vdac = h.Inout(desc="The top plate")
    vdd = h.Power(direction=h.PortDir.INOUT, desc="The DAC's supply, its reference")
    vss = h.Ground(direction=h.PortDir.INOUT, desc="The DAC's ground, the capacitors' shield")


def _drive_r_ohm(params: Params, share: float, load_f: float, pdk: str, invert: bool, fanin: float) -> float:
    """The on-resistance at most of a driver whose plate, of drawn load ``load_f`` (``_plate_loads``),
    is in a stage of ``share`` of the array's weight, so that the stage's step settles to half an
    LSB within ``settle_ps`` over ``settle_margin`` of its state's edge (the tables are the typical
    corner's). The step at the top plates, both sides', is 2 V w C_unit / C_top; half an LSB is
    FS / 2^N, FS = V W C_unit / C_top for the array's total weight W, so it takes k = ln(2^(N+1) w /
    W) time constants, about ln 4w: N ln 2 for the binary MSB, ln 4 for a unit. That is the
    testbench's step, both sides switched at once; the converter switches one side a decision
    ([Razavi-ADC] Sec. 16.2.1, p. 346), a step of 2^N w / W LSB that takes ln 2 time constants fewer,
    so the drivers are sized conservatively for it (by up to twice the time constants a unit stage
    needs). The edge passes the driver's chain first, each inner inverter one FO4 delay (it tapers
    at FO4; ``DriverRequest``); its last inverter swings the plate to mid-supply in ln 2 time
    constants of its switching resistance and settles the rest, k - ln 2 of them, at its
    on-resistance (in triode by then). A main and a difference driver sized so each settles its own
    plate's step to the same fraction at the budget, their delays taken off it, leave residues that
    cancel there as their steps do."""
    table = mosfet_table(pdk)
    # [Razavi-ADC] Sec. 8.2.2, p. 150: the DAC's settling time t_s, into an error band of +-0.5 LSB
    # Terms: t_s ``budget_s`` = settle_ps / settle_margin, the typical corner's share of settle_ps.
    # Holds for: the typical corner of the kit's tables; settle_ps is the limit at every corner,
    #   which the slow and fast corner runs judge (``flow.capdac.runs``).
    budget_s = params.settle_ps * 1e-12 / params.settle_margin
    # [Razavi-ADC] Eq. (8.14), p. 151; Eqs. (9.6)-(9.8), p. 161: a single-pole step settles into
    #   half an LSB in tau ln(step / half an LSB) time constants
    # Terms: the step 2 V_REF w C_0 / C_top, both sides' (``TbParams.ideal_step_v``); half an LSB
    #   V_REF W C_0 / (C_top 2^N); their ratio 2^(N+1) w / W, ``share`` = w / W.
    # Ours against the source: the bench's two-sided step; the converter's one side, 2^N w / W,
    #   needs ln 2 fewer (sized conservatively for it).
    # Holds for: a step that settles as one pole once its last inverter is in triode.
    constants = log(2 ** (params.bits + 1) * share)
    # [Baker] Eq. (10.17), p. 333; Eq. (10.19), p. 334: an RC step half done after 0.7 (ln 2) RC,
    #   t_PHL = 0.7 R_n C_tot at the switching resistance R_n; [Razavi-Analog] Eq. (2.11), p. 15:
    #   R_on, the triode resistance the rest settles at
    # Terms: R_n the kit's switching resistance ``table.switching_ohm``, R_on ``table.triode_ohm``,
    #   rho their ratio, the slower type's; C_tot the plate's load ``load_f``.
    # Ours against the source: the source's delay alone; here ln 2 of the k time constants at R_n,
    #   the other k - ln 2 at R_on, both scaled by the driver's own on-resistance.
    # Holds for: the last inverter of the chain driving the plate; the low-threshold devices.
    rho = max(
        table.switching_ohm[flavor(tp, MosVth.LOW)] / table.triode_ohm[flavor(tp, MosVth.LOW)]
        for tp in (MosType.NMOS, MosType.PMOS)
    )
    # fitted, not derived: the kit's scale of the time constants (its tech's ``DRIVER_TAU_SCALE``;
    #   1 where it gives none), fitted per kit to FRIDA-1's array's settling (mostly post-layout,
    #   some kits pre-layout) against the budget, so it holds the layout's routing and top-plate
    #   load as well as the device model's departure, and is checked on that one array only
    scale = getattr(import_module(f"pdk.{pdk}.layout.tech"), "DRIVER_TAU_SCALE", 1.0)
    per_ohm = load_f * (constants - log(2) + log(2) * rho) * scale
    # [Baker] Sec. 11.4, Eqs. (11.17)-(11.21), pp. 359-360: a chain tapered by A, each inverter
    #   the same delay; here A = 4 (FO4: ``DriverRequest``), each inner inverter the kit's FO4 delay
    # Terms: the delay of each inner inverter ``gate_s`` = the kit's FO4 delay ``table.fo4``.
    # Ours against the source: the source's chain ends in the load; here the last inverter's own
    #   delay is in the k time constants above, so a chain of n takes n - 1 delays first.
    # Holds for: a chain from a minimum flip-flop at FO4 (``shared_fanin``).
    gate_s = table.fo4(MosVth.LOW)
    r_ohm, chain = budget_s / per_ohm, 0
    while (count := len(DriverRequest(r_ohm, invert, fanin=fanin).stages(pdk))) != chain:
        chain = count
        if budget_s <= (chain - 1) * gate_s:
            raise ValueError(
                f"a chain of {chain} inverters takes {chain - 1} FO4 delays, the whole {budget_s:g} s budget"
            )
        r_ohm = (budget_s - (chain - 1) * gate_s) / per_ohm
    return r_ohm


def _plate_loads(
    pdk: str, layers: int, strips: list[list[tuple[float, float]]], unit_f: float, difference: bool
) -> list[tuple[float, float | None]]:
    """Each stage's plates' loads as the PDK's momcap table draws them (its strips', or its units'):
    the main (or a unit's inner) plate's and the difference plate's capacitance to the top plate in
    series with the rest of the top plate, with their capacitances to the shield and the substrate,
    and twice their capacitance to each other (they swing apart); the main plate's with its sense
    inverter's input. A difference plate is a strip's stub at the least where its piece is whole,
    the plates' share of the table's, not the design's."""
    table = momcap_table(pdk)
    # each piece's capacitances between its terminals as the kit's momcap table draws it (the
    # table's: a fitted model of the drawn units, not in the reference texts)
    drawn = [
        [
            {
                frozenset(pair): c_f
                for pair, c_f in table.capacitances(
                    table.strip(layers, (main_u - diff_u) * unit_f, (main_u + diff_u) * unit_f)[0]
                    if difference
                    else table.unit(layers, main_u * unit_f, exact=True)[0]
                ).items()
            }
            for main_u, diff_u in stage
        ]
        for stage in strips
    ]
    # not in the reference texts: the top plate's capacitance, every piece's to it (main, difference
    #   or inner plate, and its own shield and ground), summed over the side
    top_f = sum(c_f for stage in drawn for piece in stage for pair, c_f in piece.items() if "TOP" in pair)

    # fitted, not derived: each plate's wiring from its driver to its landing, a load the
    # table's plates leave out and the same for every plate whatever its size (the kit's
    # ``DRIVER_ROUTE_F``, fitted to its extraction; 0 where it gives none), which a small stage's
    # driver, sized for its plate alone, otherwise settles slowly through
    route_f = getattr(import_module(f"pdk.{pdk}.layout.tech"), "DRIVER_ROUTE_F", 0.0)
    # [Baker] Eq. (11.12), p. 355: an inverter's input capacitance C_in, here the sense inverter's
    #   (the least the kit draws; the mosfet table's input_f, from the kit's devices) on each main
    #   (inner) plate
    sense_f = input_f(pdk, least_inverter(pdk))
    if not difference:
        return [(_plate_load(stage, "INNER", None, top_f) + route_f + sense_f, None) for stage in drawn]
    return [
        (
            _plate_load(stage, "MAIN", "DIFF", top_f) + route_f + sense_f,
            _plate_load(stage, "DIFF", "MAIN", top_f) + route_f,
        )
        for stage in drawn
    ]


def _plate_load(stage: list[dict[frozenset[str], float]], plate: str, other: str | None, top_f: float) -> float:
    """One plate's load over a stage's pieces (``_plate_loads``): its capacitance to the top plate
    in series with the rest of the top plate's (``top_f``, all of it), its capacitances to the
    shield and the substrate, and twice its coupling to the ``other`` plate."""
    to_top = sum(piece.get(frozenset((plate, "TOP")), 0.0) for piece in stage)
    fixed = sum(piece.get(frozenset((plate, ground)), 0.0) for piece in stage for ground in ("SHIELD", "GROUND"))
    apart = sum(piece.get(frozenset((plate, other)), 0.0) for piece in stage) if other else 0.0
    # [Razavi-ADC] Eq. (11.10), p. 215: a switched k C_0 sees the rest of the array's (m - k) C_0 in
    #   series, k C_0 (m - k) C_0 / (m C_0); [Razavi-Analog] Eq. (6.2), p. 174: a capacitance to a
    #   node swinging the other way (A_v = -1) loads as twice itself (Miller)
    # Terms: k C_0 ``to_top``; m C_0 ``top_f``; the shield's and ground's ``fixed``; the coupling to
    #   the stage's other plate ``apart`` (main and difference switch opposite).
    # Ours against the source: the source's rest of the array is ideally grounded; here every other
    #   plate's driver holds it (at its own on-resistance), and the top plate floats on a 1 TOhm bleed.
    # Holds for: a stage switching alone, its two plates opposite (DIFFERENCE_CAPS), or one (UNIT_CAPS).
    return to_top * (top_f - to_top) / top_f + fixed + 2 * apart


def _reference_v() -> float:
    """The DAC's reference: the active PDK's typical supply."""
    pdk = h.pdk.default()
    if pdk is None:
        raise RuntimeError("the CDAC's netlist takes its reference from the active PDK: none is set")
    site = import_module(".site", pdk.__package__)
    return site.install.supply_voltage(h.pdk.Corner.TYP)


def _drive(r_ohm: float, invert: bool, fanin: float, difference: bool) -> DriverParams:
    """A driver's request as the side draws it: in a strip side (DIFFERENCE_CAPS) its input bar
    spans its first cell, where a router reaches it from above on M3 among the other stages' runs;
    in a column side its chain never mirrored, where two chains side by side would turn their
    outputs towards each other closer than a route can leave them. Every driver's input is a port of
    the side, reached from the converter's top level (``port_input``)."""
    return DriverParams(
        r_ohm=r_ohm, invert=invert, wide_input=difference, mirror=difference, fanin=fanin, port_input=True
    )


def _driven(module: h.Module, name: str, state: h.Signal, params: DriverParams) -> tuple[h.Signal, h.Instance]:
    """A bottom plate ``name`` and the driver request (``params``) that drives it from ``state``."""
    plate = module.add(h.Signal(), name=name)
    request = driver(params)
    drive = module.add(request(A=state, Y=plate, VDD=module.vdd, VSS=module.vss), name=f"drive_{name}")
    return plate, drive


@dataclass
class _Stage:
    """A stage as it is placed: its drivers, its pieces and its main plate's sense inverter."""

    main: h.Instance
    diff: h.Instance | None
    pieces: list[h.Instance]
    sense: h.Instance | None = None


def _strided(count: int, rows: int) -> list[list[int]]:
    """``count`` stages (their indices) in ``rows`` rows, each row every ``rows``-th stage in their
    order, the first row the first stage's."""
    return [list(range(j, count, rows)) for j in range(rows)]


def _rows_width(widths: list[int], rows: list[list[int]], gap_nm: int = 0) -> int:
    """The widest of ``rows`` (stage indices) of drivers ``widths`` wide (nm), neighbours in a row
    ``gap_nm`` apart."""
    return max((sum(widths[i] for i in r) + gap_nm * (len(r) - 1) for r in rows if r), default=0)


def _packed(widths: list[int], capacity: int, gap_nm: int = 0) -> list[list[int]]:
    """Stages ``widths`` wide (nm) in rows no wider than ``capacity``, neighbours in a row ``gap_nm``
    apart: the widest first, each into the first row it fits; each row in the stages' order, the
    widest stage's first."""
    rows: list[list[int]] = []
    for i in sorted(range(len(widths)), key=lambda i: (-widths[i], i)):
        for r in rows:
            if sum(widths[j] for j in r) + widths[i] + gap_nm * len(r) <= capacity:
                r.append(i)
                break
        else:
            rows.append([i])
    return [sorted(r) for r in rows]


def _balanced(widths: list[int], rows: int, gap_nm: int = 0) -> list[list[int]]:
    """Stages ``widths`` wide (nm) in ``rows`` rows, neighbours in a row ``gap_nm`` apart, the
    widest row as narrow as it goes: the widest first, each into the row narrowest so far, then a
    stage moved out of the widest row, or one or two swapped for another row's one, while that
    narrows it; each row in the stages' order."""
    out: list[list[int]] = [[] for _ in range(rows)]
    wide = lambda r: sum(widths[j] for j in r) + gap_nm * (len(r) - 1)
    for i in sorted(range(len(widths)), key=lambda i: (-widths[i], i)):
        min(out, key=wide).append(i)
    improved = True
    while improved:
        improved = False
        top = max(out, key=wide)
        for other in (r for r in out if r is not top):
            moves = [([i], []) for i in top] + [([i], [j]) for i in top for j in other]
            moves += [([i, k], [j]) for i, k in combinations(top, 2) for j in other]
            for give, take in moves:
                a = [i for i in top if i not in give] + take
                b = [j for j in other if j not in take] + give
                if max(wide(a), wide(b)) < wide(top):
                    top[:], other[:] = a, b
                    improved = True
                    break
            if improved:
                break
    return [sorted(r) for r in out if r]


# a band's rows at most (the owner's, 2026-11-16): the main drivers' and the difference drivers'
MAIN_ROWS, DIFF_ROWS = 3, 2
# the plates' routes along the capacitors' end (``_crossings``) a band's row holds over itself on its
# drivers' free M2, beside the gap's own tracks (``_landing_gap_nm``). Fitted, not derived: to capdac
# frida1's layouts (2026-11-20, every kit whose capacitors stand beside the rows), where every band
# routed its routes along on the gap's three tracks with at most three over each of its rows (GF180,
# IHP130, LF150, SKY130, TPSC65: up to 7 past one place over two rows, LF150's main band, and 6 over
# one, IHP130's and LF150's difference bands) but Tower180's difference band, 8 past one place over
# its one row, whose last two ALIGN's router took under the array; the routes the rows hold depend
# on their cells' own M2, which the flow does not count
_ROUTES_OVER_ROW = 3


def _driver_rows(
    main: list[int], diff: list[int], cap_nm: tuple[int, int], row_nm: int, stacked: bool, gap_nm: int = 0
) -> tuple[list[list[int]], list[list[int]]]:
    """The rows the main and the difference drivers (their widths, nm, in the stages' order; no
    difference drivers: none) stand in, as stage indices, each band's row beside the capacitors'
    end last: the main band at the side's bottom edge, the difference band at its top, beyond the
    capacitors' ends or, where they stack (``stacked``), under them.

    The main band takes ``MAIN_ROWS`` rows at most, the difference band ``DIFF_ROWS``, each its
    rows every so many stages in their order or balanced (``_balanced``: the widest rows as narrow
    as it goes), the difference drivers ``gap_nm`` apart in a row; a main band may pack its stages
    instead, into rows as wide as the widest of the capacitors and the drivers (``_packed``), where
    that takes no more rows, and never stands more than one row of a single driver (a main driver
    wider than the strips, which every other stage's would only widen). Where the drivers do not
    fit that many rows across the capacitors' width, the rows reach past it. Of the outlines the
    capacitors (``cap_nm``, wide, tall) and the rows (each ``row_nm`` tall) take together, the
    least; of those, where the capacitors stack, two difference rows (the stages alternating
    between them, a difference driver's output with more exits up to its strip); of those, the
    fewest rows."""
    mains = [_strided(len(main), k) for k in range(1, min(MAIN_ROWS, len(main)) + 1)]
    mains += [_balanced(main, k) for k in range(2, min(MAIN_ROWS, len(main)) + 1)]
    if diff:
        mains = [r for r in mains if sum(len(row) == 1 for row in r) <= 1] or mains[:1]
        packed = _packed(main, max(cap_nm[0], *main))
        if len(packed) <= MAIN_ROWS:
            mains.append(packed)
    diffs = [[]]
    if diff:
        diffs = [_strided(len(diff), k) for k in range(1, min(DIFF_ROWS, len(diff)) + 1)]
        diffs += [_balanced(diff, k, gap_nm) for k in range(2, min(DIFF_ROWS, len(diff)) + 1)]
    return min(
        ((m, d) for m in mains for d in diffs),
        key=lambda pair: _bands_outline(pair, main, diff, cap_nm, row_nm, stacked, gap_nm),
    )


def _bands_outline(
    pair: tuple[list[list[int]], list[list[int]]],
    main: list[int],
    diff: list[int],
    cap_nm: tuple[int, int],
    row_nm: int,
    stacked: bool,
    gap_nm: int,
) -> tuple[int, bool, int]:
    """``_driver_rows``'s order of a main band's and a difference band's rows (``pair``): the outline
    they and the capacitors take, then (where the capacitors stack) fewer than two difference rows
    last, then the row count."""
    m, d = pair
    width, tall = _extent(pair, main, diff, cap_nm, row_nm, stacked, gap_nm)
    return width * tall, stacked and bool(diff) and len(d) < min(2, len(diff)), len(m) + len(d)


def _extent(
    pair: tuple[list[list[int]], list[list[int]]],
    main: list[int],
    diff: list[int],
    cap_nm: tuple[int, int],
    row_nm: int,
    stacked: bool,
    gap_nm: int,
    sense_nm: int = 0,
) -> tuple[int, int]:
    """The side's outline (nm, wide, tall) of the capacitors (``cap_nm``) and the driver bands'
    rows (``pair``) and the sense inverters' row (``sense_nm`` wide; 0: none), each ``row_nm``
    tall: under the capacitors where they stack (``stacked``), else beyond their ends."""
    m, d = pair
    count = len(m) + len(d) + bool(sense_nm)
    width = max(cap_nm[0], _rows_width(main, m), _rows_width(diff, d, gap_nm), sense_nm)
    tall = max(cap_nm[1], count * row_nm) if stacked or not diff else cap_nm[1] + count * row_nm
    return width, tall


def _miss(outline: tuple[int, int], aspect: tuple[float, float]) -> float:
    """How far (in ratio) an outline (wide, tall) is tall to wide from ``aspect``."""
    ratio = outline[1] / outline[0]
    return max(0.0, math.log(aspect[0] / ratio), math.log(ratio / aspect[1]))


def _two_to_one[K](
    outlines: dict[K, tuple[int, int]], plain: K, aspect: tuple[float, float] = (1.6, 2.5), growth: float = 1.05
) -> K:
    """Of the side's arrangements' outlines (nm, wide, tall) by their key, the one tall to wide in
    ``aspect`` (the owner's, 2026-11-16: about two to one, one side of the converter's DAC, its
    mirror image beside it, the pair about square), or nearest it, at ``growth`` times the plain
    arrangement's area (``plain``) at most: the least of how far it is from ``aspect`` and how much
    more area than the plain one it takes (both in ratio, to a percent); of those, the least area,
    the plain one first."""
    area = math.prod(outlines[plain])
    held = [key for key, outline in outlines.items() if math.prod(outline) <= growth * area]
    return min(held, key=lambda key: (_cost(outlines[key], area, aspect), math.prod(outlines[key]), key != plain))


def _cost(outline: tuple[int, int], area: int, aspect: tuple[float, float]) -> float:
    """An outline's distance from ``aspect`` and its area over ``area`` (both in ratio, to a percent)."""
    return round(_miss(outline, aspect) + max(0.0, math.log(math.prod(outline) / area)), 2)


def _side_nm(cap_nm: tuple[int, int], bands: tuple[list[int], list[int], int, bool, int, int]) -> tuple[int, int]:
    """The side's outline (nm, wide, tall): the capacitors ``cap_nm`` (wide, tall) and the driver
    bands ``_driver_rows`` stands them in, ``bands`` its main and difference drivers' widths, its
    rows' height, whether the capacitors stack over them, the difference drivers' gap and the sense
    inverters' row's width."""
    main, diff, row_nm, stacked, gap_nm, sense_nm = bands
    pair = _driver_rows(main, diff, cap_nm, row_nm, stacked, gap_nm)
    return _extent(pair, main, diff, cap_nm, row_nm, stacked, gap_nm, sense_nm)


def _drawn(found: tuple[MomcapGeometry, FloorError | None], layers: int) -> bool:
    """Whether a capacitor's lookup draws it on ``layers`` metals, at no PDK's floor."""
    return found[0].layers == layers and found[1] is None


def _strip_length(
    pdk: str,
    layers: int,
    plates: list[list[tuple[float, float]]],
    unit_f: float,
    coarse: int,
    bands: tuple[list[int], list[int], int, bool, int, int],
) -> float:
    """The difference strips' length, as the load a strip holds in coarse weights (``coarse`` units
    of ``unit_f``), whose side comes nearest two to one (``_two_to_one``): a coarse weight (the
    plain arrangement: a strip a piece); shorter, a piece in two to four strips; longer, two to eight
    pieces end to end; and every eighth of an octave between a quarter and eight; each where every
    strip (``_strips``) draws on ``layers`` metals."""
    table = momcap_table(pdk)
    scales = sorted({*(1 / k for k in range(1, 5)), *range(2, 9), *(2 ** (i / 8) for i in range(-16, 25))})
    outlines = {}
    for scale in scales:
        length_f = coarse * scale * unit_f
        strips = _strips(plates, coarse * scale)
        drawn = {((m - d) * unit_f, (m + d) * unit_f) for stage in strips for m, d in stage} | {(length_f, length_f)}
        if scale != 1 and not all(_drawn(table.strip(layers, *f), layers) for f in drawn):
            continue
        wide, tall = array_outline_nm(pdk, table.strip(layers, length_f, length_f)[0])
        outlines[scale] = _side_nm((sum(map(len, strips)) * wide, tall), bands)
    return _two_to_one(outlines, 1.0)


def _unit_array(
    pdk: str,
    layers: int,
    pieces: list[tuple[int, ...]],
    unit_f: float,
    whole_f: float,
    bands: tuple[list[int], list[int], int, bool, int, int],
    folds: int = 4,
) -> tuple[int, int]:
    """The unit capacitors' arrangement whose side comes nearest two to one (``_two_to_one``): each
    piece in so many units (1 to ``folds``, each its share: shorter units, where every one draws on
    ``layers`` metals), in a column array (``_columns``) of so many rows; the plain one a unit a
    piece in the rows nearest two to one alone (``_grid_rows``)."""
    table = momcap_table(pdk)
    outlines, shaped, unit_nm = {}, {}, {}  # each column array once, by the fewest rows that make it
    for fold in range(1, folds + 1):
        folded = [tuple(p / fold for p in stage for _ in range(fold)) for stage in pieces]
        if fold > 1 and not all(
            _drawn(table.unit(layers, p * unit_f, exact=True), layers) for p in set(sum(folded, ()))
        ):
            continue
        unit_nm[fold] = array_outline_nm(pdk, table.unit(layers, whole_f / fold, exact=True)[0])
        for count in range(1, sum(map(len, folded)) + 1):
            shape = tuple(map(len, _columns(folded, count)))
            if (fold, shape) not in shaped:
                shaped[fold, shape] = (fold, count)
                outlines[fold, count] = _side_nm((len(shape) * unit_nm[fold][0], max(shape) * unit_nm[fold][1]), bands)
    whole = [tuple(map(float, stage)) for stage in pieces]
    plain = tuple(map(len, _columns(whole, _grid_rows(sum(map(len, pieces)), unit_nm[1]))))
    return _two_to_one(outlines, shaped[1, plain])


def _segments(plates: list[tuple[float, float]], count: int) -> list[tuple[float, float]]:
    """A stage's pieces' plates (main, difference, in units), end to end in their order, cut into
    ``count`` strips of one load (main and difference together): each strip's plates the shares of
    the pieces it spans. As many strips as pieces, the pieces themselves."""
    load = sum(main + diff for main, diff in plates) / count
    out = []
    for j in range(count):
        low, high, start = j * load, (j + 1) * load, 0.0
        main_u = diff_u = 0.0
        for main, diff in plates:
            end = start + main + diff
            share = max(0.0, min(high, end) - max(low, start)) / (main + diff)
            main_u, diff_u, start = main_u + share * main, diff_u + share * diff, end
        out.append((main_u, diff_u))
    return out


def _strips(plates: list[list[tuple[float, float]]], length: float) -> list[list[tuple[float, float]]]:
    """Each stage's strips (their plates, main and difference, in units), no strip holding more
    than ``length`` units: the stage's pieces end to end in the fewest strips of one load
    (``_segments``)."""
    return [_segments(stage, math.ceil(sum(m + d for m, d in stage) / length - 1e-9)) for stage in plates]


def _grid_rows(count: int, unit_nm: tuple[int, int]) -> int:
    """A unit-capacitor array's rows: of ``count`` units ``unit_nm`` (wide, tall) each, the array
    nearest two to one tall to wide."""
    wide, tall = unit_nm
    return min(range(1, count + 1), key=lambda rows: abs(math.log(rows * tall / (-(-count // rows) * wide) / 2)))


def _columns(pieces: list[tuple[float, ...]], rows: int) -> list[list[tuple[int, int]]]:
    """A unit-capacitor array's columns left to right, each its units bottom up as (stage, piece):
    a stage of a column's worth or more fills whole columns, MSB first; what is left of it, and
    every smaller stage, stacks bottom up in a shared column in order, a stage never split there."""
    full, rest = [], []
    for stage, stage_pieces in enumerate(pieces):
        n, k = len(stage_pieces), 0
        while n - k >= rows:
            full.append([(stage, i) for i in range(k, k + rows)])
            k += rows
        if k < n:
            rest.append([(stage, i) for i in range(k, n)])
    shared: list[list[tuple[int, int]]] = []
    for chunk in rest:
        if not shared or len(shared[-1]) + len(chunk) > rows:
            shared.append([])
        shared[-1] += chunk
    return full + shared


def _column_sides(columns: list[list[tuple[int, int]]], col: int, row: int) -> tuple[Neighbour, ...]:
    """A unit's neighbours in its column array (left, right, above, below): its stage's (joined),
    another stage's (apart), or the array's edge. Left and right count in the bottom row alone,
    where the bars joining a stage's columns run; elsewhere they are apart. A short column's top
    unit is apart from the empty place above it, so that its row's units are all one height."""
    stage = columns[col][row][0]
    return (
        _beside(columns, stage, row, col - 1),
        _beside(columns, stage, row, col + 1),
        _stacked(columns[col], stage, max(map(len, columns)), row + 1),
        _stacked(columns[col], stage, max(map(len, columns)), row - 1),
    )


def _stacked(column: list[tuple[int, int]], stage: int, rows: int, k: int) -> Neighbour:
    """The place ``k`` of a column of a unit of ``stage``: the array's edge, empty (apart), or a
    unit of its stage (joined) or another's (apart)."""
    if not 0 <= k < rows:
        return Neighbour.EDGE
    if k >= len(column):
        return Neighbour.APART
    return Neighbour.JOINED if column[k][0] == stage else Neighbour.APART


def _beside(columns: list[list[tuple[int, int]]], stage: int, row: int, c: int) -> Neighbour:
    """The column ``c`` beside a unit of ``stage`` in ``row``: apart above the bottom row, else the
    array's edge, or its bottom unit's stage's (joined) or another's (apart)."""
    if row:
        return Neighbour.APART
    if not 0 <= c < len(columns):
        return Neighbour.EDGE
    return Neighbour.JOINED if columns[c][0][0] == stage else Neighbour.APART


def _tied_row(
    side: h.Module, cell: h.ExternalModule, groups: list[tuple[h.Instance, ...]], wide: set[str], name: str
) -> tuple[tuple[h.Instance, ...], list[c.Constraint]]:
    """A band row's ``groups`` of cells (a driver, or sense inverters abutting within the ties'
    reach), with the kit's well-tie cell ``cell`` abutting each group on its left, and on its right
    too where its first is wider than the reach (its name in ``wide``): wherever ALIGN stands the
    row's groups, none farther from a tie than the reach. The row's entries left to right and the
    abutments."""
    entries: list[h.Instance] = []
    abut: list[c.Constraint] = []
    for k, group in enumerate(groups):
        ties = [side.add(cell()(VDD=side.vdd, VSS=side.vss), name=f"Xtie_{name}_{k}")]
        members = [ties[0], *group]
        if group[0].name in wide:
            ties.append(side.add(cell()(VDD=side.vdd, VSS=side.vss), name=f"Xtie_{name}_{k}r"))
            members.append(ties[1])
        entries += members
        abut.append(c.Order(tuple(members), c.OrderDirection.LEFT_TO_RIGHT, abut=True))
    return tuple(entries), abut


def _ordered(stages: list[_Stage], pick) -> tuple[h.Instance, ...]:
    """The instances ``pick`` gives of each stage, in the stages' order: the MSB's first, on the left,
    outside (the converter's other side is this one's mirror image)."""
    return tuple(x for stage in stages for x in pick(stage) if x is not None)


def _place(
    side: h.Module,
    stages: list[_Stage],
    grid: list[list[h.Instance]] | None,
    main_rows: list[list[int]],
    diff_rows: list[list[int]],
    gap_nm: int,
    room_nm: int = 0,
    apart_nm: tuple[int, int] = (0, 0),
    ties: tuple[h.ExternalModule, set[str]] | None = None,
    senses: list[list[int]] | None = None,
) -> None:
    """The side's layout (``side``): its rows top first, its difference drivers, its capacitors, its
    main drivers, every stage's pieces together, its MSB on the left, outside.

    The side is one module so that the router joining a stage's pieces to its drivers sees both:
    ALIGN lays out and routes a module before its parent places anything beside or under it, so a
    module of the capacitors alone would wire a stage's pieces through the drivers it cannot see.
    The capacitors abut, neighbours sharing their ring walls (one top plate). Each band of drivers
    is tight, its rows abutting, its outer row on the side's edge: the main drivers' at the bottom,
    under the capacitors' main channels, its outer row the stages' sense inverters (``senses``,
    stage indices in groups: a tied row's tie abuts each group), the difference drivers' at the
    top, by their difference
    channels at the strips' far end, each band's drivers in a row on one line. Where the PDK's
    capacitors lie above the metals the rows route on (``stacked_over_rows``), they stand over both
    bands (``Stackup``), the rows between the bands left free (``flow.layout.step.free_rows``),
    the side routed up to the shield's metal, where the capacitors' bottom plates have their pins;
    where they stand beside the rows, no higher than the metal over their shield (where the kit's
    router can: ``MOM_PLATES_ROUTED_LOW``), so the plates' routes beside the array keep off the
    top plate's ring on its own metals (and the array's frame keeps them a track from under it,
    ``MomUnit._channels``).
    Unit capacitors stand in a column array (``grid``, ``_columns``): its rows, top first, each
    row's units side by side and its columns' units one above the other, abutting. The drivers
    stand in ``main_rows`` and ``diff_rows`` (``_driver_rows``: stage indices, each band's row
    beside the capacitors last), the difference drivers ``gap_nm`` apart in their rows. Routing room
    at the side's left and right edges, ``room_nm``, kept clear of every instance inside the outline
    the routers keep to (its right edge is the seam with the converter's other side). Where the
    bands stand beyond the capacitors' ends, each band's row beside them ``apart_nm`` from them (the
    difference band's, the main band's): a
    row's rail beside the capacitors' shield keeps its metals' space from it. ``ties``: the kit's
    well-tie cell, abutting each driver (``_tied_row``), and the drivers wider than its reach."""

    pdk = active_pdk()
    slice_ = stacked_over_rows(pdk, _array_layers(pdk)) if pdk else None
    caps = _ordered(stages, lambda stage: stage.pieces)
    drivers = _ordered(stages, lambda stage: [stage.main, stage.sense, stage.diff])
    # each band's rows from the side's edge in, in groups (``_tied_row``): the main band's bottom up,
    # its sense inverters' row first, the difference band's top down
    sensing = [[tuple(s for i in group if (s := stages[i].sense) is not None) for group in senses or []]]
    main_groups = [*(r for r in sensing if r), *([(stages[i].main,) for i in r] for r in main_rows)]
    diff_groups = [[(stages[i].diff,) for i in r if stages[i].diff is not None] for r in diff_rows]
    mains = [tuple(x for group in r for x in group) for r in main_groups]
    diffs = [tuple(x for group in r for x in group) for r in diff_groups]
    plain_diffs = [r for r in diffs if r]  # the difference drivers alone, spread apart
    tie_abut: list[c.Constraint] = []
    if ties is not None:
        cell, wide = ties
        for band, groups, band_rows in (("main", main_groups, mains), ("diff", diff_groups, diffs)):
            for k, r in enumerate(groups):
                entries, abut = _tied_row(side, cell, r, wide, f"{band}{k}")
                drivers += tuple(x for x in entries if all(x is not y for y in band_rows[k]))
                band_rows[k] = entries
                tie_abut += abut
    mains = [r for r in reversed(mains) if r]  # top first
    diffs = [r for r in diffs if r]
    if grid:  # the column array's rows, top first, and its columns
        height = max(map(len, grid))
        cap_rows = [tuple(col[r] for col in grid if r < len(col)) for r in reversed(range(height))]
        bottom = cap_rows[-1]
        arrange: list[c.Constraint] = []
        for r, cap_row in enumerate(reversed(cap_rows)):
            runs: list[list[h.Instance]] = [[]]  # side by side where neighbouring columns reach row r
            for col in grid:
                if r < len(col):
                    runs[-1].append(col[r])
                elif runs[-1]:
                    runs.append([])
            arrange += [c.Order(tuple(run), c.OrderDirection.LEFT_TO_RIGHT, abut=True) for run in runs if len(run) > 1]
            if len(cap_row) > 1:
                arrange.append(c.Align(cap_row, c.Line.H_BOTTOM))
        for col in grid:
            if len(col) > 1:
                arrange += [
                    c.Order(tuple(reversed(col)), c.OrderDirection.TOP_TO_BOTTOM, abut=True),
                    c.Align(tuple(col), c.Line.V_LEFT),
                ]
    else:
        cap_rows, bottom = [caps], caps
        arrange = [c.Order(caps, c.OrderDirection.LEFT_TO_RIGHT, abut=True), c.Align(caps, c.Line.H_BOTTOM)]
    inner: list[c.Constraint] = list(arrange)
    if gap_nm:
        inner += [c.Spread(tuple(r), c.Axis.HORIZONTAL, gap_nm) for r in plain_diffs if len(r) > 1]
    inner += tie_abut
    # each row's drivers on one line (else ALIGN stands a driver on a free line between two rows,
    # its corners on the rows' cells across the rails, their implants unmatched), each band's rows
    # abutting: under the capacitors nothing else holds them together
    inner += [c.Align(tuple(r), c.Line.H_BOTTOM) for r in (*diffs, *mains) if len(r) > 1]
    for band in (diffs, mains):
        inner += [
            c.Order((upper[0], lower[0]), c.OrderDirection.TOP_TO_BOTTOM, abut=True) for upper, lower in pairwise(band)
        ]
    for band, apart in ((diffs[-1:], apart_nm[0]), (mains[:1], apart_nm[1])):
        if band and apart:
            inner.append(c.Spread((*caps, *band[0]), c.Axis.VERTICAL, apart))
    room = (c.Boundary(halo_horizontal_um=room_nm / 1000),) if room_nm else ()
    if slice_ is not None:
        shield, top = slice_
        inner += [
            c.PlaceOnBoundary(south=(*bottom, *(mains[-1] if mains else ())), north=diffs[0] if diffs else ()),
            c.Route(max_layer=shield),
            # the top plate unrouted: the capacitors' top plates join where they abut (their
            # shared ring walls), and their pins lie above the metals the side routes on, where
            # the router tried and failed each one in turn
            c.DoNotRoute((side.vdac,)),
            *room,
            # last: a Stackup lifts the non-overlap ALIGN's consistency check holds
            # (flow/layout/make_design.py), which then re-checks the whole cell at once
            # the capacitors from the metal under their shield (their channels' landings), the
            # drivers below it (their cells and chains route on M1 and M2 alone)
            c.Stackup(caps, min_layer=shield - 1, max_layer=top),
            c.Stackup(drivers, max_layer=shield - 2),
        ]
    elif pdk:
        # beside the rows, the side routed no higher than the metal over the capacitors' shield:
        # the plates' routes run there and below, out of the array under its frame, never along the
        # top plate's ring on its own metals (ALIGN's router takes one set of metals for all nets,
        # the customized ones too); where the kit's router cannot route the side so, at any height
        # (its tech's ``MOM_PLATES_ROUTED_LOW``)
        tech = import_module(f"pdk.{pdk}.layout.tech")
        if getattr(tech, "MOM_PLATES_ROUTED_LOW", True):
            inner.append(c.Route(max_layer=tech.MOM_LAYERS[-_array_layers(pdk)]))
        inner += room
    else:
        inner += room
    regions = [region for region in (*diffs, *cap_rows, *mains) if region]
    # not mirrored: a capacitor's channels meet its neighbours' as drawn, so ALIGN mirrors none
    place(side, rows(*(row(*region) for region in regions)), symmetric=False, constraints=tuple(inner))


def _row_places(widths: list[int], targets: list[float], extent: int) -> list[float]:
    """A row's drivers ``widths`` wide (nm, in the row's order, abutting at the closest) along
    ``extent``, each as near its ``target`` (the middle it would stand on) as the row's order allows:
    their middles, the squares of their distances from the targets least (pool-adjacent-violators on
    the left edges less the widths before them, held within the extent)."""
    before = [sum(widths[:k]) for k in range(len(widths))]
    want = [t - w / 2 - b for t, w, b in zip(targets, widths, before, strict=True)]
    blocks: list[list[float]] = []  # [mean, count]
    for value in want:
        blocks.append([value, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            (a, n), (b, m) = blocks.pop(-2), blocks.pop()
            blocks.append([(a * n + b * m) / (n + m), n + m])
    low, high = 0, max(0, extent - sum(widths))
    lefts = [min(max(mean, low), high) for mean, count in blocks for _ in range(int(count))]
    return [q + b + w / 2 for q, b, w in zip(lefts, before, widths, strict=True)]


def _crossings(widths: list[int], rows: list[list[int]], pieces: list[int], unit_nm: int, gap_nm: int = 0) -> int:
    """The most routes of a band's drivers that run along the capacitors' end past one place: each
    stage's from its driver (``rows``, stage indices; ``widths``, nm; neighbours ``gap_nm`` apart, each
    as near the middle of its stage's pieces as its row allows, ``_row_places``) to its pieces'
    landings, every one of them (``pieces`` a stage, ``unit_nm`` wide each, side by side in the
    stages' order), from the nearest of those to the farthest."""
    starts = [sum(pieces[:k]) * unit_nm for k in range(len(pieces))]
    extent = max(sum(pieces) * unit_nm, _rows_width(widths, rows, gap_nm))
    ends: list[tuple[float, int]] = []
    for stages in rows:
        if not stages:
            continue
        middles = [starts[k] + pieces[k] * unit_nm / 2 for k in stages]
        places = _row_places([widths[k] + gap_nm for k in stages], middles, extent + gap_nm)
        for k, x in zip(stages, places, strict=True):
            first, last = starts[k] + unit_nm / 2, starts[k] + (pieces[k] - 0.5) * unit_nm
            ends += [(min(x, first), 1), (max(x, last), -1)]
    most = level = 0
    for _x, step in sorted(ends):  # a route that ends where another starts passes it
        level += step
        most = max(most, level)
    return most


def _landing_gap_nm(pdk: str, along: int = 3) -> int:
    """Where the capacitors stand beside the rows (their shield on M2, their landings on M1 under
    their channels' bars at the array's top and bottom edges), the least distance from the array's
    edge to the line of a band's row beside it that holds ``along`` free M2 tracks between them,
    three at least: a route
    from a landing runs up or down it on M1 out of the array, under the shield's edge, and turns onto
    M2 there, its cut's M1 pad M1's space from the rail and its wire M2's space from the shield's bar
    at the array's edge and from the rail's own M2 (a kit whose rails carry no taps draws one). Whole
    M2 tracks, as ALIGN places the rows and the capacitors on them. A band nearer than this leaves
    each plate there only the shield's metal to reach its driver on, which ALIGN's router cannot
    (``Router-Error: fail to find dest vertices on grids``); with one track, neighbouring stages'
    routes block each other there. Of the band's routes that run along the capacitors' end past one
    place (``_crossings``), the gap takes those its rows do not hold over themselves
    (``_ROUTES_OVER_ROW``; the caller's ``along``): with fewer tracks ALIGN's router, which never rips
    a route up, takes the last of them under the capacitors, below their shield."""
    tech = import_module(f"pdk.{pdk}.layout.tech")
    pitch, width = metal_tracks(pdk, "M2")
    rules = tech.RULES
    pad = rules["V1"]["cut"] // 2 + rules["V1"]["enclosure"][0]  # the cut's M1 pad along the M1 wire
    clear = tech.RAIL + tech.M1_SPACE + pad
    if not getattr(tech, "RAIL_TAPS", True):  # the rail's M2 over its M1
        rail_m2 = max(width // 2, getattr(tech, "M2_VIA_PAD", {}).get("V1", (0, 0))[1])
        clear = max(clear, rail_m2 + tech.M2_SPACE + width // 2)
    track = -(-clear // pitch) * pitch  # the track nearest the rail its route may take
    # and more: a route turns onto M2 under its landing, on a wire of M2's minimum length, longer
    # than a unit is wide, so neighbouring stages' turns take a track each; and the plates' routes
    # run along the array on M2 there, no higher than the metal over the shield (``_place``), a
    # track each
    track += (max(3, along) - 1) * pitch
    return -(-(track + width // 2 + tech.M2_SPACE) // pitch) * pitch


def _array_layers(pdk: str, most: int = 3) -> int:
    """How many of ``pdk``'s MOM metals the side's capacitors stack: the most, up to ``most``, whose
    shield, the metal below them, is a horizontal metal on M2's tracks in ALIGN's grid, where an
    array unit's channels and pins run (``MomUnit._tracks``)."""
    tech = import_module(f"pdk.{pdk}.layout.tech")
    grid = {m["Layer"]: m for m in json.loads((pdk_dir(pdk) / "layers.json").read_text())["Abstraction"]}
    m2 = grid["M2"]["Pitch"]
    for layers in range(min(most, len(tech.MOM_LAYERS)), 0, -1):
        shield = grid.get(f"M{tech.MOM_LAYERS[-layers] - 1}", {})
        if shield.get("Direction", "").lower() == "h" and shield.get("Pitch") == m2:
            return layers
    raise ValueError(f"{pdk}: no MOM metals over a horizontal metal on M2's tracks, where an array's channels run")


def _keys(
    params: Params,
    pdk: str,
    weights: Sequence[float],
    loads: list[tuple[float, float | None]],
    difference: bool,
    mains: Sequence[float] | None = None,
) -> list[tuple[tuple[float, bool, float], tuple[float, bool, float] | None]]:
    """Each stage's drivers (on-resistance, inversion, fan-in), for its plates' ``loads``: the main
    plates' of its input, the difference plates' of its complement, both on the state's flip-flop:
    the difference driver first, the main chain on what is left of the flip-flop's FO4. Each sized
    for its stage's weight, their residues cancelling as their steps do; where the difference
    driver is drawn faster than the main (the kit's least inverter, stronger than a small plate
    asks), the main driver settles its plate's own step (``mains``: each stage's main plates, in
    units of weight) to half an LSB too."""
    keys = []
    for stage, (weight, (main_f, diff_f)) in enumerate(zip(weights, loads, strict=True)):
        share = weight / sum(weights)
        diff_key = None
        if difference and diff_f is not None:
            fanin = shared_fanin(pdk, [])
            diff_key = (_drive_r_ohm(params, share, diff_f, pdk, True, fanin), True, fanin)
        beside = [DriverRequest(diff_key[0], True, fanin=diff_key[2])] if diff_key else []
        fanin = shared_fanin(pdk, beside)
        main_r = _drive_r_ohm(params, share, main_f, pdk, False, fanin)
        if beside and diff_f is not None and mains is not None and drawn_ohm(pdk, beside[0]) * diff_f < main_r * main_f:
            # not in the reference texts: the two plates' residues cancel at the top plate only
            # while they settle together; where the difference plate's drawn driver settles first
            # (its R C below the main's), the main plate's own step is left, so the main driver
            # also settles that step, its main plates' units ``mains`` over W, to half an LSB
            # Terms: R C of each plate, ``drawn_ohm`` times its load; ``mains[stage]`` in units.
            # Holds for: a small stage whose difference driver is the kit's least inverter.
            main_r = min(main_r, _drive_r_ohm(params, mains[stage] / sum(weights), main_f, pdk, False, fanin))
        keys.append(((main_r, False, fanin), diff_key))
    return keys


# a fresh module every call: resolving the requests in a PDK swaps them in place
@h.generator(enable_cache=False)
def netlist(params: Params) -> h.Module:
    """The side's stages: each stage's pieces between its bottom plates and the top plate, the
    drivers of its main and (DIFFERENCE_CAPS) difference plates, and its main plate's sense
    inverter. A plate drawn as a difference stub alone has a driver sized for a unit of load."""
    weights = _weights(params)
    # [Razavi-ADC] Sec. 11.8, p. 229: the unit capacitance C_0, the side's switched capacitance at
    #   the kit's supply over the total weight (``params._design_plates``'s)
    unit_f = _switched_f(params, _reference_v()) / sum(weights)
    whole_f = params.coarse_weight * unit_f
    pieces = [_pieces(params, weight) for weight in weights]
    plates = [[_plates(params, piece) for piece in stage] for stage in pieces]
    mains = [sum(main for main, _diff in stage) for stage in plates]  # each stage's main plates (units)
    # not in the reference texts: the design's top plate, every plate's units of C_0 (``TbParams.load_f``)
    top_f = unit_f * sum(main + diff for stage in plates for main, diff in stage)
    difference = params.weight_impl is WeightImpl.DIFFERENCE_CAPS

    ports = dict(Nets.signals)
    ports["dac_state"] = replace(ports["dac_state"], width=len(weights))
    ports["dac_plate"] = replace(ports["dac_plate"], width=len(weights))
    if difference:  # the difference drivers' own input of the states
        ports["dac_state_diff"] = replace(
            ports["dac_state"], name="dac_state_diff", desc="The stage states at the difference drivers, C0 first"
        )
    Capdac = module_from_ports("Capdac", ports)
    # the top plate's landing on the outline's top, at its inner end (the LSB's, the seam with the
    # converter's other side, by the comparator), above the shield (flow.layout.pins), its wire
    # shielded from the plates' routes under it (each would couple to the top plate there, its
    # stage's weight with it), the ground's strip between them
    # each stage's sensed plate on the outline's bottom, the main band's edge, where its sense
    # inverter's output comes nearest it
    edge_pins(
        Capdac, EdgePin(Capdac.vdac, Border.TOP, Spot.LAST, shield=True), EdgePin(Capdac.dac_plate, Border.BOTTOM)
    )
    pdk = active_pdk()
    if pdk is None:
        raise RuntimeError(
            "the CDAC's layout plan takes its units' and drivers' sizes from the active PDK: none is set"
        )
    table, layers = momcap_table(pdk), _array_layers(pdk)
    # each main plate sensed by the least inverter the kit draws, the sense inverters in a row of
    # their own at the main band's outer edge, by their pins
    sense = least_inverter(pdk)
    sense_nm = driver_widths_nm(pdk, [sense])[0]
    sense_row_nm = len(weights) * sense_nm
    # each stage's drivers sized for its plates' loads: first the design's (each plate in series
    # with the rest of the top plate), then those the drawn arrangement gives (``_plate_loads``: its
    # stubs and parasitics), until the arrangement, which the drivers' widths choose, stands still
    designed = [[max(unit_f, unit_f * sum(plate)) for plate in zip(*stage, strict=True)] for stage in plates]
    # [Razavi-ADC] Eq. (11.10), p. 215: the first sizing's load, each plate (a unit of load at the
    #   least: a stub) in series with the rest of the design's top plate (``_plate_load``'s, without
    #   the drawn parasitics)
    loads: list[tuple[float, float | None]] = [
        (main_f * (top_f - main_f) / top_f, diff_f * (top_f - diff_f) / top_f) for main_f, diff_f in designed
    ]
    for _attempt in range(3):
        keys = _keys(params, pdk, weights, loads, difference, mains)
        drives = sorted({key for pair in keys for key in pair if key is not None})

        # the drivers' widths as drawn and the rows they stand in, of the outline the capacitors and the
        # rows take together the least; a column unit's strip has its pins in the
        # rows' band and a row above it, where the drivers reach it from below
        requests = [
            DriverRequest(d.r_ohm, d.invert, d.wide_input, d.mirror, d.fanin)
            for d in (_drive(*key, difference) for key in drives)
        ]
        widths = dict(zip(drives, driver_widths_nm(pdk, requests), strict=True))
        row_nm = row_height_nm(pdk)
        # a routing track between neighbouring difference drivers, on the metal the drivers rise on to
        # the capacitors standing over them: a difference driver's output's few exits up to them are
        # taken by its own state's drop and the strips' landing stubs unless its neighbour stands a track off
        slice_ = stacked_over_rows(pdk, layers)
        gap_nm = metal_tracks(pdk, f"M{slice_[0] - 1}")[0] if difference and slice_ is not None else 0
        main_widths = [widths[main] for main, _ in keys]
        diff_widths = [widths[diff] for _, diff in keys if diff is not None]

        # the capacitors' arrangement whose side, with its driver bands, comes nearest two to one tall
        # to wide: difference strips of a length (``_strip_length``, ``_strips``; the array the same,
        # its plates' sums), unit pieces each in so many units in a column array of so many rows
        # (``_unit_array``, ``_columns``); each piece's column, row and neighbours
        bands = (main_widths, diff_widths, row_nm, slice_ is not None, gap_nm, sense_row_nm)
        if difference:
            scale = _strip_length(pdk, layers, plates, unit_f, params.coarse_weight, bands)
            frame_f = params.coarse_weight * scale * unit_f
            strips = _strips(plates, params.coarse_weight * scale)
            outline = array_outline_nm(pdk, table.strip(layers, frame_f, frame_f)[0])
            columns: list[list[tuple[int, int]]] = []
        else:
            fold, count = _unit_array(pdk, layers, [tuple(stage) for stage in pieces], unit_f, whole_f, bands)
            frame_f = whole_f / fold
            outline = array_outline_nm(pdk, table.unit(layers, frame_f, exact=True)[0])
            strips = [[(p / fold, 0.0) for p in stage for _ in range(fold)] for stage in pieces]
            columns = _columns([tuple(m for m, _ in stage) for stage in strips], count)
        drawn = _plate_loads(pdk, layers, strips, unit_f, difference)
        if _keys(params, pdk, weights, drawn, difference, mains) == keys:
            break
        loads = drawn
    else:
        # the drivers would be sized for loads the arrangement they choose does not draw
        raise RuntimeError(
            f"{params}: the drivers and the arrangement they choose did not stand still in three sizings"
        )
    at = {piece: (col, row) for col, column in enumerate(columns) for row, piece in enumerate(column)}
    wide, tall = (len(columns), max(map(len, columns))) if columns else (sum(map(len, strips)), 1)
    # where the kit's rails carry no taps (its row ends' tie cells alone tie the wells), a side wider
    # than twice the ties' reach has a tie cell abut each driver in its bands, two a driver wider than
    # the reach (the layout's, ``_tied_row``)
    tech = import_module(f"pdk.{pdk}.layout.tech")
    reach_nm, tie = getattr(tech, "TIE_REACH", 0), getattr(tech, "EDGE_TIE", None)
    tied = (
        params.well_ties is WellTies.ROWS
        and reach_nm
        and tie
        and _side_nm((wide * outline[0], tall * outline[1]), bands)[0] > 2 * reach_nm
    )
    # the sense inverters in groups, a group's abutting: in a tied band as many behind each tie as
    # its reach holds
    per_tie = max(1, reach_nm // sense_nm) if tied else len(weights)
    senses = [list(range(k, min(k + per_tie, len(weights)))) for k in range(0, len(weights), per_tie)]
    if tied:
        main_widths = [w + tie[1] * (1 + (w > reach_nm)) for w in main_widths]
        diff_widths = [w + tie[1] * (1 + (w > reach_nm)) for w in diff_widths]
        sense_row_nm += tie[1] * len(senses)
    main_rows, diff_rows = _driver_rows(
        main_widths, diff_widths, (wide * outline[0], tall * outline[1]), row_nm, slice_ is not None, gap_nm
    )
    band_nm = (len(main_rows) + 2) * row_nm  # its sense inverters' row too
    rows_nm = max(_rows_width(main_widths, main_rows), _rows_width(diff_widths, diff_rows, gap_nm), sense_row_nm)
    room_nm = 0
    if slice_ is not None and wide * outline[0] >= rows_nm:
        # where the capacitors set the side's width (no driver row reaches past them), its last
        # stage's pieces and its drivers (wider than a piece) stand at its right edge, the seam
        # with the converter's other side, with no track free beyond them: two tracks of the metal
        # the drivers rise on are kept clear at each edge of the side
        room_nm = 2 * metal_tracks(pdk, f"M{slice_[0] - 1}")[0]
    # the stages' drivers and pieces between the states and the top plate
    state, top = Capdac.dac_state, Capdac.vdac
    far = Capdac.dac_state_diff if difference else None
    stages: list[_Stage] = []
    for stage, (main_key, diff_key) in enumerate(keys):
        main, main_drive = _driven(Capdac, f"main_{stage}", state[stage], _drive(*main_key, difference))
        diff, diff_drive = None, None
        if diff_key is not None:
            assert far is not None  # a difference key only where the array has difference capacitors
            diff, diff_drive = _driven(Capdac, f"diff_{stage}", far[stage], _drive(*diff_key, difference))
        sensed = driver(DriverParams(r_ohm=sense.r_ohm, invert=True))
        sense_inv = Capdac.add(
            sensed(A=main, Y=Capdac.dac_plate[stage], VDD=Capdac.vdd, VSS=Capdac.vss), name=f"sense_{stage}"
        )
        placed = _Stage(main_drive, diff_drive, [], sense_inv)
        for index, (main_u, diff_u) in enumerate(strips[stage]):
            name = f"Xc_{stage}_{index}"  # an instance of a subcircuit (the PDK's view) is X...
            # its neighbours in the row of capacitors (``_place``): its stage's pieces together, the
            # stages in order; a stage's bottom plates joined in the capacitors' channels
            left = Neighbour.JOINED if index else Neighbour.EDGE if stage == 0 else Neighbour.APART
            last = index == len(strips[stage]) - 1
            right = Neighbour.JOINED if not last else Neighbour.EDGE if stage == len(weights) - 1 else Neighbour.APART
            if diff is not None:
                # a strip shorter than the row's (a stage's last, of less load) in the row's ring
                load_f = (main_u + diff_u) * unit_f
                request = strip(
                    StripParams(
                        net_f=(main_u - diff_u) * unit_f,
                        whole_f=load_f,
                        layers=layers,
                        left=left,
                        right=right,
                        frame_f=frame_f if load_f < frame_f * (1 - 1e-9) else 0.0,
                    )
                )
                placed.pieces.append(Capdac.add(request(MAIN=main, DIFF=diff, TOP=top, SHIELD=Capdac.vss), name=name))
            else:
                left, right, above, below = _column_sides(columns, *at[(stage, index)])
                request = unit(
                    UnitParams(
                        c_f=main_u * unit_f,
                        layers=layers,
                        left=left,
                        right=right,
                        above=above,
                        below=below,
                        frame_f=frame_f,  # every row the height of a whole piece's
                        array=ArrayKind.COLUMNS,
                        pin_band_nm=band_nm,
                    )
                )
                placed.pieces.append(Capdac.add(request(INNER=main, TOP=top, SHIELD=Capdac.vss), name=name))
        stages.append(placed)
    grid = [[stages[stage].pieces[index] for stage, index in column] for column in columns] if columns else None
    # beyond the capacitors' ends, each band's rail beside their shield far enough from it that a
    # plate's route from its landing reaches the band (``_landing_gap_nm``)
    apart_nm = (0, 0)
    if slice_ is None and difference:
        pieces = [len(stage) for stage in strips]
        # the routes along the capacitors' end, less those over the band's own rows
        diff_along = _crossings(diff_widths, diff_rows, pieces, outline[0], gap_nm) - _ROUTES_OVER_ROW * len(diff_rows)
        main_along = _crossings(main_widths, main_rows, pieces, outline[0]) - _ROUTES_OVER_ROW * len(main_rows)
        apart_nm = (_landing_gap_nm(pdk, diff_along), _landing_gap_nm(pdk, main_along))
    ties = None
    if tied:
        wide_drivers = {
            d.name
            for stage, (main_key, diff_key) in zip(stages, keys, strict=True)
            for d, key in ((stage.main, main_key), (stage.diff, diff_key))
            if d is not None and key is not None and widths[key] > reach_nm
        }
        ties = (library_module(import_module(f"pdk.{pdk}.hdl21.cells"), tie[0]), wide_drivers)
    _place(Capdac, stages, grid, main_rows, diff_rows, gap_nm, room_nm, apart_nm, ties, senses)
    return Capdac
