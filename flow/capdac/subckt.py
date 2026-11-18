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
quantization noise (``params._switched_f``), at a full scale of the DAC's reference, the PDK's
supply; a unit of weight is its share of it.

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
plate's load as the table draws it, ``_plate_loads``). A minimum-strength flip-flop drives each state at FO4:
the difference driver one inverter (the complement), the main driver's chain loading it with what
is left of four minimum inverters (``shared_fanin``); the difference drivers take the states on
an input of their own (``dac_state_diff``), the same flip-flops' outputs brought from outside the
side, so that the side's two bands of drivers share no wire.

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
    driver,
    driver_widths_nm,
    row_height_nm,
    shared_fanin,
)
from flow.layout.devices.mosfet.table import mosfet_table
from flow.layout.hdl21align import constraints as c
from flow.layout.hdl21align import place, row, rows
from flow.layout.package import metal_tracks, pdk_dir

from .params import Params, WeightImpl, WellTies, _pieces, _plates, _switched_f, _weights


@h.bundle
class Nets:
    """The side's stage states in, a bit per stage, C0 first; its top plate; the DAC's supply,
    which its drivers switch the bottom plates between (the ADC's DAC reference). A side of
    difference strips (DIFFERENCE_CAPS) has a second input of the same states, its difference
    drivers' (``dac_state_diff``), at the strips' far end, driven from outside the side, so that no
    wire of it runs between its two bands of drivers."""

    dac_state = h.Input(desc="The stage states, C0 first")
    vdac = h.Inout(desc="The top plate")
    vdd = h.Power(direction=h.PortDir.INOUT, desc="The DAC's supply, its reference")
    vss = h.Ground(direction=h.PortDir.INOUT, desc="The DAC's ground, the capacitors' shield")


def _drive_r_ohm(params: Params, share: float, load_f: float, pdk: str, invert: bool, fanin: float) -> float:
    """The on-resistance at most of a driver whose plate, of drawn load ``load_f`` (``_plate_loads``),
    is in a stage of ``share`` of the array's weight, so that the stage's step settles to half an
    LSB within ``settle_ps`` over ``settle_margin`` of its state's edge (the tables are the typical
    corner's). The step at the top plates, both sides', is 2 V w C_unit / C_top; half an LSB is
    FS / 2^N, FS = V W C_unit / C_top for the array's total weight W, so it takes k = ln(2^(N+1) w /
    W) time constants, about ln 4w: N ln 2 for the binary MSB, ln 4 for a unit. The edge passes the
    driver's chain first, each inner inverter one FO4 delay (it tapers at FO4; ``DriverRequest``);
    its last inverter swings the plate to mid-supply in ln 2 time constants of its switching
    resistance and settles the rest, k - ln 2 of them, at its on-resistance (in triode by then). A
    main and a difference driver at one time constant settle together, their residues cancelling as
    their steps do."""
    table = mosfet_table(pdk)
    # [Razavi-ADC] Sec. 8.2.2, p. 150: the DAC's settling time, here its budget
    budget_s = params.settle_ps * 1e-12 / params.settle_margin
    # [Razavi-Analog] Eq. (13.31), p. 552: a step settling as exp(-t / tau), k time constants to
    # come from the step to half an LSB
    constants = log(2 ** (params.bits + 1) * share)
    # not in the reference texts: a step through a switch is half done after ln 2 time constants;
    # the switch's resistance there its switching resistance, the kit's ``rho`` times its
    # on-resistance ([Razavi-Analog] Eq. (2.11), p. 15), the slower type's
    rho = max(
        table.switching_ohm[flavor(tp, MosVth.LOW)] / table.triode_ohm[flavor(tp, MosVth.LOW)]
        for tp in (MosType.NMOS, MosType.PMOS)
    )
    # the kit's own scale of the time constants, where the model misses its devices (its tech's
    # ``DRIVER_TAU_SCALE``, measured over modelled; 1 where it gives none)
    scale = getattr(import_module(f"pdk.{pdk}.layout.tech"), "DRIVER_TAU_SCALE", 1.0)
    per_ohm = load_f * (constants - log(2) + log(2) * rho) * scale
    # [Razavi-PLL] Sec. 1.4.1, p. 12: each inner inverter's gate delay, the kit's FO4 delay
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
    and twice their capacitance to each other (they swing apart). A difference plate is a strip's
    stub at the least where its piece is whole, the plates' share of the table's, not the design's."""
    table = momcap_table(pdk)
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
    top_f = sum(c_f for stage in drawn for piece in stage for pair, c_f in piece.items() if "TOP" in pair)

    if not difference:
        return [(_plate_load(stage, "INNER", None, top_f), None) for stage in drawn]
    return [(_plate_load(stage, "MAIN", "DIFF", top_f), _plate_load(stage, "DIFF", "MAIN", top_f)) for stage in drawn]


def _plate_load(stage: list[dict[frozenset[str], float]], plate: str, other: str | None, top_f: float) -> float:
    """One plate's load over a stage's pieces (``_plate_loads``): its capacitance to the top plate
    in series with the rest of the top plate's (``top_f``, all of it), its capacitances to the
    shield and the substrate, and twice its coupling to the ``other`` plate."""
    to_top = sum(piece.get(frozenset((plate, "TOP")), 0.0) for piece in stage)
    fixed = sum(piece.get(frozenset((plate, ground)), 0.0) for piece in stage for ground in ("SHIELD", "GROUND"))
    apart = sum(piece.get(frozenset((plate, other)), 0.0) for piece in stage) if other else 0.0
    # not in the reference texts: capacitors in series, and a coupling to a node swinging the
    # other way counted twice (Miller)
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
    outputs towards each other closer than a route can leave them."""
    return DriverParams(r_ohm=r_ohm, invert=invert, wide_input=difference, mirror=difference, fanin=fanin)


def _driven(module: h.Module, name: str, state: h.Signal, params: DriverParams) -> tuple[h.Signal, h.Instance]:
    """A bottom plate ``name`` and the driver request (``params``) that drives it from ``state``."""
    plate = module.add(h.Signal(), name=name)
    request = driver(params)
    drive = module.add(request(A=state, Y=plate, VDD=module.vdd, VSS=module.vss), name=f"drive_{name}")
    return plate, drive


@dataclass
class _Stage:
    """A stage as it is placed: its drivers and its pieces."""

    main: h.Instance
    diff: h.Instance | None
    pieces: list[h.Instance]


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
) -> tuple[int, int]:
    """The side's outline (nm, wide, tall) of the capacitors (``cap_nm``) and the driver bands'
    rows (``pair``), each ``row_nm`` tall: under the capacitors where they stack (``stacked``), else
    beyond their ends."""
    m, d = pair
    count = len(m) + len(d)
    width = max(cap_nm[0], _rows_width(main, m), _rows_width(diff, d, gap_nm))
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


def _side_nm(cap_nm: tuple[int, int], bands: tuple[list[int], list[int], int, bool, int]) -> tuple[int, int]:
    """The side's outline (nm, wide, tall): the capacitors ``cap_nm`` (wide, tall) and the driver
    bands ``_driver_rows`` stands them in, ``bands`` its main and difference drivers' widths, its
    rows' height, whether the capacitors stack over them and the difference drivers' gap."""
    main, diff, row_nm, stacked, gap_nm = bands
    pair = _driver_rows(main, diff, cap_nm, row_nm, stacked, gap_nm)
    return _extent(pair, main, diff, cap_nm, row_nm, stacked, gap_nm)


def _drawn(found: tuple[MomcapGeometry, FloorError | None], layers: int) -> bool:
    """Whether a capacitor's lookup draws it on ``layers`` metals, at no PDK's floor."""
    return found[0].layers == layers and found[1] is None


def _strip_length(
    pdk: str,
    layers: int,
    plates: list[list[tuple[float, float]]],
    unit_f: float,
    coarse: int,
    bands: tuple[list[int], list[int], int, bool, int],
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
    bands: tuple[list[int], list[int], int, bool, int],
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
    side: h.Module, cell: h.ExternalModule, drivers: tuple[h.Instance, ...], wide: set[str], name: str
) -> tuple[tuple[h.Instance, ...], list[c.Constraint]]:
    """A band row's drivers with the kit's well-tie cell ``cell`` abutting each on its left, and on
    its right too where the driver is wider than the ties' reach (its name in ``wide``): wherever
    ALIGN stands the row's drivers, none farther from a tie than the reach. The row's entries left
    to right and the abutments."""
    entries: list[h.Instance] = []
    abut: list[c.Constraint] = []
    for k, drv in enumerate(drivers):
        ties = [side.add(cell()(VDD=side.vdd, VSS=side.vss), name=f"Xtie_{name}_{k}")]
        group = [ties[0], drv]
        if drv.name in wide:
            ties.append(side.add(cell()(VDD=side.vdd, VSS=side.vss), name=f"Xtie_{name}_{k}r"))
            group.append(ties[1])
        entries += group
        abut.append(c.Order(tuple(group), c.OrderDirection.LEFT_TO_RIGHT, abut=True))
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
    apart_nm: int = 0,
    ties: tuple[h.ExternalModule, set[str]] | None = None,
) -> None:
    """The side's layout (``side``): its rows top first, its difference drivers, its capacitors, its
    main drivers, every stage's pieces together, its MSB on the left, outside.

    The side is one module so that the router joining a stage's pieces to its drivers sees both:
    ALIGN lays out and routes a module before its parent places anything beside or under it, so a
    module of the capacitors alone would wire a stage's pieces through the drivers it cannot see.
    The capacitors abut, neighbours sharing their ring walls (one top plate). Each band of drivers
    is tight, its rows abutting, its outer row on the side's edge: the main drivers' at the bottom,
    under the capacitors' main channels, the difference drivers' at the top, by their difference
    channels at the strips' far end, each band's drivers in a row on one line. Where the PDK's
    capacitors lie above the metals the rows route on (``stacked_over_rows``), they stand over both
    bands (``Stackup``), the rows between the bands left free (``flow.layout.step.free_rows``),
    the side routed up to the shield's metal, where the capacitors' bottom plates have their pins.
    Unit capacitors stand in a column array (``grid``, ``_columns``): its rows, top first, each
    row's units side by side and its columns' units one above the other, abutting. The drivers
    stand in ``main_rows`` and ``diff_rows`` (``_driver_rows``: stage indices, each band's row
    beside the capacitors last), the difference drivers ``gap_nm`` apart in their rows. Routing room
    at the side's left and right edges, ``room_nm``, kept clear of every instance inside the outline
    the routers keep to (its right edge is the seam with the converter's other side). Where the
    bands stand beyond the capacitors' ends, each band's row beside them ``apart_nm`` from them: a
    row's rail beside the capacitors' shield keeps its metals' space from it. ``ties``: the kit's
    well-tie cell, abutting each driver (``_tied_row``), and the drivers wider than its reach."""

    pdk = active_pdk()
    slice_ = stacked_over_rows(pdk, _array_layers(pdk)) if pdk else None
    caps = _ordered(stages, lambda stage: stage.pieces)
    drivers = _ordered(stages, lambda stage: [stage.main, stage.diff])
    # each band's rows from the side's edge in: the main band's bottom up, the difference band's top down
    mains = [_ordered([stages[i] for i in r], lambda stage: [stage.main]) for r in main_rows]
    diffs = [_ordered([stages[i] for i in r], lambda stage: [stage.diff]) for r in diff_rows]
    plain_diffs = [r for r in diffs if r]  # the difference drivers alone, spread apart
    tie_abut: list[c.Constraint] = []
    if ties is not None:
        cell, wide = ties
        for band, band_rows in (("main", mains), ("diff", diffs)):
            for k, r in enumerate(band_rows):
                entries, abut = _tied_row(side, cell, r, wide, f"{band}{k}")
                band_rows[k] = entries
                tie_abut += abut
                drivers += tuple(x for x in entries if all(x is not y for y in r))
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
    if apart_nm:
        inner += [c.Spread((*caps, *band), c.Axis.VERTICAL, apart_nm) for band in (diffs[-1:] + mains[:1]) if band]
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
    else:
        inner += room
    regions = [region for region in (*diffs, *cap_rows, *mains) if region]
    # not mirrored: a capacitor's channels meet its neighbours' as drawn, so ALIGN mirrors none
    place(side, rows(*(row(*region) for region in regions)), symmetric=False, constraints=tuple(inner))


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
    params: Params, pdk: str, weights: Sequence[float], loads: list[tuple[float, float | None]], difference: bool
) -> list[tuple[tuple[float, bool, float], tuple[float, bool, float] | None]]:
    """Each stage's drivers (on-resistance, inversion, fan-in), for its plates' ``loads``: the main
    plates' of its input, the difference plates' of its complement, both on the state's flip-flop:
    the difference driver first, the main chain on what is left of the flip-flop's FO4."""
    keys = []
    for weight, (main_f, diff_f) in zip(weights, loads, strict=True):
        share = weight / sum(weights)
        diff_key = None
        if difference and diff_f is not None:
            fanin = shared_fanin(pdk, [])
            diff_key = (_drive_r_ohm(params, share, diff_f, pdk, True, fanin), True, fanin)
        beside = [DriverRequest(diff_key[0], True, fanin=diff_key[2])] if diff_key else []
        fanin = shared_fanin(pdk, beside)
        keys.append(((_drive_r_ohm(params, share, main_f, pdk, False, fanin), False, fanin), diff_key))
    return keys


# a fresh module every call: resolving the requests in a PDK swaps them in place
@h.generator(enable_cache=False)
def netlist(params: Params) -> h.Module:
    """The side's stages: each stage's pieces between its bottom plates and the top plate, and the
    drivers of its main and (DIFFERENCE_CAPS) difference plates. A plate drawn as a difference stub
    alone has a driver sized for a unit of load."""
    weights = _weights(params)
    unit_f = _switched_f(params, _reference_v()) / sum(weights)
    whole_f = params.coarse_weight * unit_f
    pieces = [_pieces(params, weight) for weight in weights]
    plates = [[_plates(params, piece) for piece in stage] for stage in pieces]
    top_f = unit_f * sum(main + diff for stage in plates for main, diff in stage)
    difference = params.weight_impl is WeightImpl.DIFFERENCE_CAPS

    ports = dict(Nets.signals)
    ports["dac_state"] = replace(ports["dac_state"], width=len(weights))
    if difference:  # the difference drivers' own input of the states
        ports["dac_state_diff"] = replace(
            ports["dac_state"], name="dac_state_diff", desc="The stage states at the difference drivers, C0 first"
        )
    Capdac = module_from_ports("Capdac", ports)
    pdk = active_pdk()
    if pdk is None:
        raise RuntimeError(
            "the CDAC's layout plan takes its units' and drivers' sizes from the active PDK: none is set"
        )
    table, layers = momcap_table(pdk), _array_layers(pdk)
    # each stage's drivers sized for its plates' loads: first the design's (each plate in series
    # with the rest of the top plate), then those the drawn arrangement gives (``_plate_loads``: its
    # stubs and parasitics), until the arrangement, which the drivers' widths choose, stands still
    designed = [[max(unit_f, unit_f * sum(plate)) for plate in zip(*stage, strict=True)] for stage in plates]
    loads: list[tuple[float, float | None]] = [
        (main_f * (top_f - main_f) / top_f, diff_f * (top_f - diff_f) / top_f) for main_f, diff_f in designed
    ]
    for _attempt in range(3):
        keys = _keys(params, pdk, weights, loads, difference)
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
        bands = (main_widths, diff_widths, row_nm, slice_ is not None, gap_nm)
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
        if _keys(params, pdk, weights, drawn, difference) == keys:
            break
        loads = drawn
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
    if tied:
        main_widths = [w + tie[1] * (1 + (w > reach_nm)) for w in main_widths]
        diff_widths = [w + tie[1] * (1 + (w > reach_nm)) for w in diff_widths]
    main_rows, diff_rows = _driver_rows(
        main_widths, diff_widths, (wide * outline[0], tall * outline[1]), row_nm, slice_ is not None, gap_nm
    )
    band_nm = (len(main_rows) + 1) * row_nm
    rows_nm = max(_rows_width(main_widths, main_rows), _rows_width(diff_widths, diff_rows, gap_nm))
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
        placed = _Stage(main_drive, diff_drive, [])
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
    # beyond the capacitors' ends, a rail beside their shield (its M2 over its M1, where the rails carry
    # no taps) an M2 pitch from it
    apart_nm = metal_tracks(pdk, "M2")[0] if slice_ is None and difference else 0
    ties = None
    if tied:
        wide_drivers = {
            d.name
            for stage, (main_key, diff_key) in zip(stages, keys, strict=True)
            for d, key in ((stage.main, main_key), (stage.diff, diff_key))
            if d is not None and key is not None and widths[key] > reach_nm
        }
        ties = (library_module(import_module(f"pdk.{pdk}.hdl21.cells"), tie[0]), wide_drivers)
    _place(Capdac, stages, grid, main_rows, diff_rows, gap_nm, room_nm, apart_nm, ties)
    return Capdac
