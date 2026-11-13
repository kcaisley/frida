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
remainder below it. Each piece is a request for a capacitor (``flow.layout.devices.momcap``): a
difference strip of its weight in a strip as long as a whole one (DIFFERENCE_CAPS), or a unit
capacitor of its weight (UNIT_CAPS). A stage's main bottom plates follow its state and its
difference plates the complement, each through a request for a driver
(``flow.layout.devices.mosfet``) of the resistance that settles the stage's step to half an LSB
within ``settle_ps`` over ``settle_margin``. A minimum-strength flip-flop drives each state at FO4:
the difference driver one inverter (the complement), the main driver's chain loading it with what
is left of four minimum inverters (``shared_fanin``).

The netlist holds no PDK's dimensions: every request is an ideal device, so it simulates as it is,
and ``flow.layout.devices.device.resolve`` makes each the PDK's own from its precharacterized
tables: a strip's or a unit's finger lengths, a driver's inverters' widths.

The generator states its layout as it builds (``_place``, ``flow.layout.hdl21align``, after
Fritchman's AlignHdl21): rows of its own instances, which ALIGN places as stated, each driver a cell
of its own rows.
"""

import json
import math
from dataclasses import dataclass, replace
from importlib import import_module
from math import log

import hdl21 as h

from flow.circuit.ports import module_from_ports
from flow.layout.devices.device import active_pdk
from flow.layout.devices.momcap.geometry import ArrayKind, Neighbour
from flow.layout.devices.momcap.netlist import StripParams, UnitParams, array_outline_nm, strip, unit
from flow.layout.devices.momcap.table import momcap_table, stacked_over_rows
from flow.layout.devices.mosfet.netlist import (
    DriverParams,
    DriverRequest,
    driver,
    driver_widths_nm,
    row_height_nm,
    shared_fanin,
)
from flow.layout.hdl21align import constraints as c
from flow.layout.hdl21align import place, row, rows
from flow.layout.package import metal_tracks, pdk_dir

from .params import Params, WeightImpl, _pieces, _plates, _switched_f, _weights


@h.bundle
class Nets:
    """The side's stage states in, a bit per stage, C0 first; its top plate; the DAC's supply,
    which its drivers switch the bottom plates between (the ADC's DAC reference)."""

    dac_state = h.Input(desc="The stage states, C0 first")
    vdac = h.Inout(desc="The top plate")
    vdd = h.Power(direction=h.PortDir.INOUT, desc="The DAC's supply, its reference")
    vss = h.Ground(direction=h.PortDir.INOUT, desc="The DAC's ground, the capacitors' shield")


def _drive_r_ohm(params: Params, share: float, plate_f: float, top_f: float) -> float:
    """The resistance at most of a driver of a plate of ``plate_f`` in a stage of ``share`` of the
    array's weight, which settles the stage's step to half an LSB within ``settle_ps`` over
    ``settle_margin`` (the tables are the typical corner's). The step at the top plates, both
    sides', is 2 V w C_unit / C_top; half an LSB is FS / 2^N, FS = V W C_unit / C_top for the
    array's total weight W, so it takes ln(2^(N+1) w / W) time constants, about ln 4w: N ln 2 for
    the binary MSB, ln 4 for a unit. The plate sees the rest of the top plate in series. A main and
    a difference driver at one time constant settle together, their residues cancelling as their
    steps do."""
    constants = log(2 ** (params.bits + 1) * share)
    load_f = plate_f * (top_f - plate_f) / top_f
    return params.settle_ps * 1e-12 / params.settle_margin / constants / load_f


def _reference_v() -> float:
    """The DAC's reference: the active PDK's typical supply."""
    pdk = h.pdk.default()
    if pdk is None:
        raise RuntimeError("the CDAC's netlist takes its reference from the active PDK: none is set")
    site = import_module(".site", pdk.__package__)
    return site.install.supply_voltage(h.pdk.Corner.TYP)


def _drive(r_ohm: float, invert: bool, fanin: float, difference: bool) -> DriverParams:
    """A driver's request as the side draws it: in a strip side (DIFFERENCE_CAPS) its input bar
    spans its first cell, where a state runs the strips' length to the main driver at one end
    and the difference driver at the other, and a router reaches each from above on M3 among
    the other stages' runs; in a column side its chain never mirrored, where two chains side by
    side would turn their outputs towards each other closer than a route can leave them."""
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


def _packed(widths: list[int], capacity: int) -> list[list[int]]:
    """Drivers ``widths`` wide (nm) in rows no wider than ``capacity``: the widest first, each into the
    first row it fits; each row in the stages' order, the widest driver's first."""
    rows: list[list[int]] = []
    for i in sorted(range(len(widths)), key=lambda i: (-widths[i], i)):
        for r in rows:
            if sum(widths[j] for j in r) + widths[i] <= capacity:
                r.append(i)
                break
        else:
            rows.append([i])
    return [sorted(r) for r in rows]


def _driver_rows(
    main: list[int], diff: list[int], cap_nm: tuple[int, int], row_nm: int, gap_nm: int = 0
) -> tuple[list[list[int]], list[list[int]]]:
    """The rows the main and the difference drivers (their widths, nm, in the stages' order; no
    difference drivers: none) stand in, as stage indices: the main rows from the one under the
    capacitors up, the difference rows from the top down.

    Each row every so many stages in their order: of the outlines the capacitors (``cap_nm``, wide,
    tall) and the rows (each ``row_nm`` tall) take together, the least; of those, the fewest rows.
    In a strip side (difference drivers on its top edge too), where that leaves more than one row
    of a single driver (a main driver wider than the strips, which every other stage's would only
    widen), ALIGN's placement cannot solve the many rows: the main drivers are packed instead,
    into rows as wide as the widest of the capacitors and the drivers (``_packed``). The difference rows then once more, their drivers
    ``gap_nm`` apart in a row: a difference driver stands over other stages' strips, its output's
    few exits up to them taken by its own state's drop and the strips' landing stubs unless its
    neighbour stands a track off. Of the outlines on the rows' grid the least; of those, two rows
    or more (the stages alternating between them, more exits again); of those, the fewest."""
    best = None
    for k in range(1, len(main) + 1):
        for k_d in range(1, len(diff) + 1) if diff else (0,):
            widest = max(
                cap_nm[0], _rows_width(main, _strided(len(main), k)), _rows_width(diff, _strided(len(diff), k_d))
            )
            area = widest * max(cap_nm[1], (k + k_d) * row_nm)
            if best is None or (area, k + k_d) < best[0]:
                best = ((area, k + k_d), (k, k_d))
    assert best is not None
    k, k_d = best[1]
    main_rows = _strided(len(main), k)
    if diff and sum(len(r) == 1 for r in main_rows) > 1:
        main_rows = _packed(main, max(cap_nm[0], *main))
    diff_rows = _strided(len(diff), k_d) if diff else []
    if diff:
        tall = -(-cap_nm[1] // row_nm)
        width = max(cap_nm[0], _rows_width(main, main_rows))
        diff_rows = _strided(
            len(diff),
            min(
                range(1, len(diff) + 1),
                key=lambda r: _diff_outline(diff, r, width, max(tall, len(main_rows) + r), row_nm, gap_nm),
            ),
        )
    return main_rows, diff_rows


def _diff_outline(diff: list[int], rows: int, width: int, tall: int, row_nm: int, gap_nm: int) -> tuple[int, bool, int]:
    """The difference drivers ``diff`` (their widths, nm) in ``rows`` rows (``_strided``), ``gap_nm``
    apart in a row, beside rows at least ``width`` wide, ``tall`` rows of ``row_nm`` in all: their
    outline's area, then whether they take fewer than two rows, then the rows (``_driver_rows``'s
    order: the least area, two rows or more, the fewest)."""
    return max(width, _rows_width(diff, _strided(len(diff), rows), gap_nm)) * row_nm * tall, rows < 2, rows


def _grid_rows(count: int, unit_nm: tuple[int, int]) -> int:
    """A unit-capacitor array's rows: of ``count`` units ``unit_nm`` (wide, tall) each, the array
    nearest two to one tall to wide."""
    wide, tall = unit_nm
    return min(range(1, count + 1), key=lambda rows: abs(math.log(rows * tall / (-(-count // rows) * wide) / 2)))


def _columns(pieces: list[tuple[int, ...]], rows: int) -> list[list[tuple[int, int]]]:
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
) -> None:
    """The side's layout (``side``): its rows top first, its difference drivers, its capacitors, its
    main drivers, every stage's pieces together, its MSB on the left, outside.

    The side is one module so that the router joining a stage's pieces to its drivers sees both:
    ALIGN lays out and routes a module before its parent places anything beside or under it, so a
    module of the capacitors alone would wire a stage's pieces through the drivers it cannot see.
    The capacitors abut, neighbours sharing their ring walls (one top plate). Where the PDK's
    capacitors lie above the metals the rows route on (``stacked_over_rows``), they stand over the
    drivers (``Stackup``): on the side's bottom edge with the main drivers, the difference drivers
    on its top edge (above the capacitors' ends, or beyond them where the capacitors are shorter
    than both rows), the side routed up to the shield's metal, where the capacitors' bottom plates
    have their pins. Unit capacitors stand in a column array (``grid``, ``_columns``): its rows,
    top first, each row's units side by side and its columns' units one above the other, abutting.
    The drivers stand in ``main_rows`` and ``diff_rows`` (``_driver_rows``: stage indices, the main
    rows from the one under the capacitors' main channel up, the difference rows from the top
    down), the difference drivers ``gap_nm`` apart in their rows."""

    pdk = active_pdk()
    slice_ = stacked_over_rows(pdk, _array_layers(pdk)) if pdk else None
    diff = _ordered(stages, lambda stage: [stage.diff])
    caps = _ordered(stages, lambda stage: stage.pieces)
    main = _ordered(stages, lambda stage: [stage.main])
    # the drivers' rows, top first, the main drivers' bottom one under the capacitors' main channel
    mains = [_ordered([stages[i] for i in r], lambda stage: [stage.main]) for r in reversed(main_rows)]
    diffs = [_ordered([stages[i] for i in r], lambda stage: [stage.diff]) for r in diff_rows]
    lower = mains[-1]
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
        inner += [c.Spread(tuple(r), c.Axis.HORIZONTAL, gap_nm) for r in diffs if len(r) > 1]
    if slice_ is not None:
        shield, top = slice_
        inner += [
            c.PlaceOnBoundary(south=(*bottom, *lower), north=diffs[0] if diffs else ()),
            c.Route(max_layer=shield),
            # the top plate unrouted: the capacitors' top plates join where they abut (their
            # shared ring walls), and their pins lie above the metals the side routes on, where
            # the router tried and failed each one in turn
            c.DoNotRoute((side.vdac,)),
            # routing room at the side's edges (``room_nm``; its right edge is the seam with the
            # converter's other side, its mirror image), kept clear of every instance, inside the
            # outline the routers keep to
            *((c.Boundary(halo_horizontal_um=room_nm / 1000),) if room_nm else ()),
            # last: a Stackup lifts the non-overlap ALIGN's consistency check holds
            # (flow/layout/make_design.py), which then re-checks the whole cell at once
            # the capacitors from the metal under their shield (their channels' landings), the
            # drivers below it (their cells and chains route on M1 and M2 alone)
            c.Stackup(caps, min_layer=shield - 1, max_layer=top),
            c.Stackup((*diff, *main), max_layer=shield - 2),
        ]
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
    Capdac = module_from_ports("Capdac", ports)
    pdk = active_pdk()
    if pdk is None:
        raise RuntimeError(
            "the CDAC's layout plan takes its units' and drivers' sizes from the active PDK: none is set"
        )
    # the capacitors' unit as drawn (a whole piece's), its outline; unit capacitors in a column
    # array (``_columns``) of the rows nearest two to one: each piece's column, row and neighbours
    table, layers = momcap_table(pdk), _array_layers(pdk)
    drawn = table.strip(layers, whole_f, whole_f)[0] if difference else table.unit(layers, whole_f, exact=True)[0]
    outline = array_outline_nm(pdk, drawn)
    columns = []
    if not difference:
        columns = _columns([tuple(stage) for stage in pieces], _grid_rows(sum(map(len, pieces)), outline))
    at = {piece: (col, row) for col, column in enumerate(columns) for row, piece in enumerate(column)}
    # each stage's drivers: the main plates' of its input, the difference plates' of its complement,
    # both on the state's flip-flop: the difference driver first, the main chain on what is left of
    # the flip-flop's FO4
    keys: list[tuple[tuple[float, bool, float], tuple[float, bool, float] | None]] = []
    for stage, weight in enumerate(weights):
        share = weight / sum(weights)
        main_f, diff_f = (max(unit_f, unit_f * sum(plate)) for plate in zip(*plates[stage], strict=True))
        diff_key = (_drive_r_ohm(params, share, diff_f, top_f), True, shared_fanin(pdk, [])) if difference else None
        beside = [DriverRequest(diff_key[0], True, fanin=diff_key[2])] if diff_key else []
        keys.append(((_drive_r_ohm(params, share, main_f, top_f), False, shared_fanin(pdk, beside)), diff_key))
    drives = sorted({key for pair in keys for key in pair if key is not None})

    # the drivers' widths as drawn and the rows they stand in, of the outline the capacitors and the
    # rows take together the least; a column unit's strip has its pins in the
    # rows' band and a row above it, where the drivers reach it from below
    requests = [
        DriverRequest(d.r_ohm, d.invert, d.wide_input, d.mirror, d.fanin)
        for d in (_drive(*key, difference) for key in drives)
    ]
    widths = dict(zip(drives, driver_widths_nm(pdk, requests), strict=True))
    wide, tall = (len(columns), max(map(len, columns))) if columns else (sum(map(len, pieces)), 1)
    row_nm = row_height_nm(pdk)
    # a routing track between neighbouring difference drivers, on the metal the drivers rise on to
    # the capacitors standing over them (``_driver_rows``)
    slice_ = stacked_over_rows(pdk, layers)
    gap_nm = metal_tracks(pdk, f"M{slice_[0] - 1}")[0] if difference and slice_ is not None else 0
    main_rows, diff_rows = _driver_rows(
        [widths[main] for main, _ in keys],
        [widths[diff] for _, diff in keys if diff is not None],
        (wide * outline[0], tall * outline[1]),
        row_nm,
        gap_nm,
    )
    band_nm = (len(main_rows) + len(diff_rows) + 1) * row_nm
    # where the capacitors set the side's width (no driver row reaches past them), its last stage's
    # pieces and its drivers (wider than a piece, one in every row) stand at its right edge, the
    # seam with the converter's other side, with no track free beyond them: two tracks of the metal
    # the drivers rise on are kept clear at each edge of the side
    rows_nm = max(
        _rows_width([widths[main] for main, _ in keys], main_rows),
        _rows_width([widths[diff] for _, diff in keys if diff is not None], diff_rows, gap_nm),
    )
    room_nm = 0
    if slice_ is not None and wide * outline[0] >= rows_nm:
        room_nm = 2 * metal_tracks(pdk, f"M{slice_[0] - 1}")[0]
    # the stages' drivers and pieces between the states and the top plate
    state, top = Capdac.dac_state, Capdac.vdac
    stages: list[_Stage] = []
    for stage, (main_key, diff_key) in enumerate(keys):
        main, main_drive = _driven(Capdac, f"main_{stage}", state[stage], _drive(*main_key, difference))
        diff, diff_drive = None, None
        if diff_key is not None:
            diff, diff_drive = _driven(Capdac, f"diff_{stage}", state[stage], _drive(*diff_key, difference))
        placed = _Stage(main_drive, diff_drive, [])
        for index, piece in enumerate(pieces[stage]):
            name = f"Xc_{stage}_{index}"  # an instance of a subcircuit (the PDK's view) is X...
            # its neighbours in the row of capacitors (``_place``): its stage's pieces together, the
            # stages in order; a stage's bottom plates joined in the capacitors' channels
            left = Neighbour.JOINED if index else Neighbour.EDGE if stage == 0 else Neighbour.APART
            last = index == len(pieces[stage]) - 1
            right = Neighbour.JOINED if not last else Neighbour.EDGE if stage == len(weights) - 1 else Neighbour.APART
            if diff is not None:
                request = strip(
                    StripParams(net_f=piece * unit_f, whole_f=whole_f, layers=layers, left=left, right=right)
                )
                placed.pieces.append(Capdac.add(request(MAIN=main, DIFF=diff, TOP=top, SHIELD=Capdac.vss), name=name))
            else:
                left, right, above, below = _column_sides(columns, *at[(stage, index)])
                request = unit(
                    UnitParams(
                        c_f=piece * unit_f,
                        layers=layers,
                        left=left,
                        right=right,
                        above=above,
                        below=below,
                        frame_f=whole_f,  # every row the height of a whole piece's
                        array=ArrayKind.COLUMNS,
                        pin_band_nm=band_nm,
                    )
                )
                placed.pieces.append(Capdac.add(request(INNER=main, TOP=top, SHIELD=Capdac.vss), name=name))
        stages.append(placed)
    grid = [[stages[stage].pieces[index] for stage, index in column] for column in columns] if columns else None
    _place(Capdac, stages, grid, main_rows, diff_rows, gap_nm, room_nm)
    return Capdac
