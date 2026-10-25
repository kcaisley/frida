"""The ADC study's arrays sized through their extraction: each array's split and capacitance.

Every unit of an array is a row of the same length (``flow.caparray.layout``): a chunk of the
coarse weight is a unary row, one main finger of the coarse weight in units and no difference
finger, and a lighter chunk a length-scaled binary row, its main and difference fingers about the
coarse weight (Harpe, JSSC 2018: N_b = log2 of the coarse weight binary bits, the rest unary). A
unary row loads the top plate with what it switches; a binary row with the coarse weight in units
and two tails, whatever it switches. The edge dummies' fingers are tied to the top plate, and its
other load (the rings' coupling to the shield, the bar beside the array) grows with the rows and
their length. The converter's full scale, its reference across the switched share of that load,
falls with the binary rows (each costs a whole row for a fraction of one) and with a small unit (the
tails are a larger share).

Two constraints size every array, both on its own extracted top plate:

- its full scale at least ``MIN_FULL_SCALE`` of the reference;
- its sampled noise, both sides' kT/C, no more than its quantization noise at that full scale
  (``flow.caparray.subckt.total_capacitance_f``).

Every array's outline (one side's; the converter's two sit side by side) is drawn about ``ASPECT``
times as tall as wide, so that the pair is about square: the strips' pitch is the technology's, and
the split (the coarse weight, any integer from 8 to 512, ``COARSE_WEIGHTS``) sets the rows and,
with the capacitance, their length. Each array's own least switched capacitance is at the split
whose outline is nearest ``ASPECT`` among those whose least capacitance (the larger of the two
constraints') is within ``SPLIT_SLACK`` of any split's least. A resolution's least switched
capacitance is the largest of its arrays' (``resolution_minimums``). Each array at ``cap_scale``
switches that many times it, at the split whose outline is nearest ``ASPECT`` of those that keep
its full scale and its noise below 1/cap_scale of its quantization noise there (``design``). A
small array cannot reach the outline: the full scale wants many short rows, so it is as near as its
capacitance lets it be. From ``EXACT_UNARY_BITS`` (14 bits) the splits are powers of two and the
unary rows keep a difference finger of the tail, so that the tens of unary rows of a stage weigh
exactly the coarse weight each.

The capacitances are the PDK's FMOM model's (``RowModel``, from ``flow.caparray.layout``'s
geometry and ``_mom_fit``) corrected by each array's own extraction (``calibrated``): its binary
unit (exact by the strips' difference, whatever the fit), its unary row (one finger, its ends not
cancelled: its length is corrected to the coarse weight in binary units, at each split by the
array's newest extraction at it), its binary rows' fingers and its other load. ``extract_adc_arrays`` sizes every array from its newest earlier extraction (or
its resolution's binary array's), extracts it and sizes again from that, until every array keeps
its split, its step moves less than ``STEP_TOLERANCE``, its unary rows weigh the coarse weight
within ``UNARY_TOLERANCE`` and both constraints hold in its extraction (``SIZING_PASSES`` at most).
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, replace
from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np

from .layout import (
    ADC_ARRAYS,
    RADIX17,
    STACKED_METALS,
    CapArrayLayoutParams,
    _calc_unit_geometry,
    _mom_fit,
    _stacked,
    extract_array,
)
from .subckt import CapArrayConfig, _calc_weight_partitions, get_caparray_weights, total_capacitance_f

# every ADC array's differential full scale: at least this share of the reference
MIN_FULL_SCALE = 0.80
# the splits an array may take: its coarse weight, the unary row's weight (2^N_b where a power of
# two), integers from 8 to 512 about 9 % apart, so that its rows and their length come close to the
# outline it is drawn to (below 8, a row's tails outweigh what it switches)
COARSE_WEIGHTS = tuple(sorted({round(8 * 2 ** (k / 8)) for k in range(49)}))
# from this resolution a stage holds tens of unary rows, whose weight errors add: the splits are
# powers of two (every large stage unary rows alone, Harpe's segmentation) and a unary row keeps a
# difference finger of the tail, so its weight is exact by the strips' difference (the tails cost
# about 1.5 % of the full scale there); below it, any split and one-finger unary rows, for the full
# scale that their tails would cost
EXACT_UNARY_BITS = 14
POWER_OF_TWO_WEIGHTS = tuple(weight for weight in COARSE_WEIGHTS if weight & (weight - 1) == 0)


def exact_unary(cdac: CapArrayConfig) -> bool:
    """Whether the array's unary rows keep a difference finger (``EXACT_UNARY_BITS``)."""
    return cdac.n_dac + 1 >= EXACT_UNARY_BITS


def splits(cdac: CapArrayConfig) -> tuple[int, ...]:
    """The coarse weights the array may take: powers of two where its unary rows are exact."""
    return POWER_OF_TWO_WEIGHTS if exact_unary(cdac) else COARSE_WEIGHTS


# every array's outline (one side's: the converter's two sit side by side) about this many times as
# tall as wide, so that the pair is about square: its split sets its rows, its capacitance their
# length; an outline within ASPECT_TOLERANCE of it is on target
ASPECT = 2.0
ASPECT_TOLERANCE = 1.25
# an array's own least capacitance: at the split nearest the outline among those whose least
# capacitance is within this factor of any split's least
SPLIT_SLACK = 1.25
# the model sizes a resolution's least capacitance this much inside both constraints, and takes an
# array's split half as much inside, so that a step on the grid and the model's error still meet them
MARGIN = 0.01
# a pass's array is kept where the next sizing keeps its split and moves its step by no more than
# this share, its one-finger unary rows weigh the coarse weight within UNARY_TOLERANCE binary units,
# and its extraction meets both constraints
STEP_TOLERANCE = 0.03
UNARY_TOLERANCE = 0.25
SIZING_PASSES = 5
PDK = "tsmc65"
LAYERS = STACKED_METALS


def reference_v(pdk: str) -> float:
    """The converter's DAC reference in ``pdk``: its typical core supply (the ADC model's)."""
    import hdl21 as h

    return round(import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP), 4)


@dataclass(frozen=True)
class RowModel:
    """An array's rows as the PDK's FMOM model draws them, corrected by its extractions.

    A binary row of weight w switches w units and its ends' offset; it loads the top plate with
    its main and difference fingers, the coarse weight c in units and a tail each (its access and
    ends, ``tail_ff``). A unary row's one finger of length L switches and loads ``scale * slope * L
    + unary_ff`` (at a split extracted before, that extraction's scale and unary_ff:
    ``unary_by_split``), drawn to c units (``unary_length_nm``). The unit is ``scale`` times twice the step's
    finger. The top plate's other load is ``other_row_ff`` a placed row (the edge dummies too) and
    ``other_row_um_ff`` a micrometre of row, which is two tails, c steps of finger and its ends. The
    outline is the rows and two edge dummies a ``pitch_um`` apart, the top plate's stack and the
    shield taps beside them (``side_um``), and the top plate's bar over them (``bar_um``)."""

    slope_ff_um: float  # a finger's capacitance per length
    intercept_ff: float  # a finger's ends
    tail_ff: float  # a binary finger beyond its share of the c units: its tail, access and ends
    tail_um: float
    ends_um: float  # a row's length beyond its two fingers: three end gaps and two ring walls
    grid_nm: int
    pitch_um: float = 0.0  # a row's: the units share their ring walls
    outer_width_um: float = 0.0  # a unit's ring, its outer edges
    side_um: float = 0.0  # beside the array: the top plate's stack and the shield taps
    bar_um: float = 0.0  # above the rows: the top plate's bar beyond the top ring wall
    scale: float = 1.0  # the extracted slope over the fit's
    binary_offset_ff: float = 0.0  # a binary row's effective capacitance beyond its weight
    unary_ff: float | None = None  # a unary finger beyond its length's slope: its ends and access
    other_row_ff: float = 0.0
    other_row_um_ff: float = 0.0
    # each split's (coarse weight, scale, unary_ff) from the array's newest extraction at it: a
    # unary row weighs tens of units, so a fraction of a percent of scale between splits is a
    # tenth of a unit or more
    unary_by_split: tuple[tuple[int, float, float], ...] = ()

    def unit_ff(self, step_nm: float) -> float:
        """The unit at a weight step: twice the step of finger."""
        return 2 * self.scale * self.slope_ff_um * step_nm / 1000

    def row_um(self, coarse: int, step_nm: float) -> float:
        return 2 * (self.tail_um + coarse * step_nm / 1000) + self.ends_um

    def outline_um(self, rows: int, coarse: int, step_nm: float) -> tuple[float, float]:
        """The array's outline (width, height): its rows and two edge dummies, as
        ``flow.caparray.layout.outline_um`` draws it."""
        width = (rows + 1) * self.pitch_um + self.outer_width_um + self.side_um
        return width, self.row_um(coarse, step_nm) + self.bar_um

    @property
    def unary_ff_or_intercept(self) -> float:
        """A unary finger's capacitance beyond its length's slope: as extracted, else the fit's."""
        return self.intercept_ff if self.unary_ff is None else self.unary_ff

    def unary_fit(self, coarse: int) -> tuple[float, float]:
        """The scale and the unary finger's capacitance beyond its length's slope at the split
        ``coarse``: its own extraction's (``unary_by_split``), else the model's."""
        for split, scale, unary_ff in self.unary_by_split:
            if split == coarse:
                return scale, unary_ff
        return self.scale, self.unary_ff_or_intercept

    def unary_length_nm(self, coarse: int, step_nm: int) -> int:
        """A unary row's finger, on the grid, whose capacitance is the coarse weight in units."""
        scale, unary_ff = self.unary_fit(coarse)
        slope = scale * self.slope_ff_um
        length = (coarse * 2 * slope * step_nm / 1000 - unary_ff) / slope * 1000
        return int(round(length / self.grid_nm) * self.grid_nm)

    def unary_error_lsb(self, coarse: int, step_nm: int, length_nm: int) -> float:
        """A unary row's finger of ``length_nm`` less the coarse weight, in the unit at ``step_nm``."""
        scale, unary_ff = self.unary_fit(coarse)
        slope = scale * self.slope_ff_um
        return (slope * length_nm / 1000 + unary_ff) / (2 * slope * step_nm / 1000) - coarse


def row_model(pdk: str = PDK, layers: int | None = None) -> RowModel:
    """The PDK's rows at ``layers`` stacked metals (None: ``STACKED_METALS``), uncorrected."""
    params = _stacked(pdk, RADIX17, "rows", layers)
    geometry = _calc_unit_geometry(params)
    slope, intercept = _mom_fit(params, geometry.gap)
    return RowModel(
        slope_ff_um=slope,
        intercept_ff=intercept,
        tail_ff=slope * geometry.tail_length / 1000 + intercept,
        tail_um=geometry.tail_length / 1000,
        ends_um=(3 * geometry.end_gap + 2 * geometry.ring_width) / 1000,
        grid_nm=geometry.grid,
        pitch_um=geometry.unit_pitch / 1000,
        outer_width_um=geometry.outer_width / 1000,
        side_um=geometry.side_extension / 1000,
        bar_um=(geometry.via_landing - geometry.ring_width) / 1000,
    )


def rows(cdac: CapArrayConfig, coarse: int) -> tuple[int, int, int]:
    """The array's unary rows, binary rows and binary weight at a split: each stage's chunks of
    the coarse weight and its remainder."""
    chunks = [chunk for stage in _calc_weight_partitions(get_caparray_weights(cdac), coarse) for chunk in stage]
    binary = [chunk for chunk in chunks if chunk != coarse]
    return len(chunks) - len(binary), len(binary), sum(binary)


@dataclass(frozen=True)
class Prediction:
    rows: int
    step_nm: float
    row_um: float
    switched_f: float
    total_f: float
    reference_v: float
    width_um: float = math.nan
    height_um: float = math.nan

    @property
    def aspect(self) -> float:
        """The outline's height over its width."""
        return self.height_um / self.width_um

    @property
    def full_scale(self) -> float:
        """The full scale's share of the reference: the switched share of the top plate."""
        return self.switched_f / self.total_f

    def noise_ratio(self, adc_bits: int) -> float:
        """The sampled noise over the quantization noise at the full scale."""
        return total_capacitance_f(adc_bits, self.reference_v * self.full_scale) / self.total_f


def predict(
    cdac: CapArrayConfig,
    coarse: int,
    switched_f: float,
    model: RowModel,
    reference: float,
    step_nm: float | None = None,
) -> Prediction:
    """The array split at ``coarse`` switching about ``switched_f`` (or drawn at ``step_nm``)."""
    unary, binary, _binary_weight = rows(cdac, coarse)
    total_weight = sum(get_caparray_weights(cdac))
    if step_nm is None:
        unit_ff = (switched_f * 1e15 - binary * model.binary_offset_ff) / total_weight
        step_nm = unit_ff / (2 * model.scale * model.slope_ff_um) * 1000
    unit = model.unit_ff(step_nm)
    switched_ff = total_weight * unit + binary * model.binary_offset_ff
    row_um = model.row_um(coarse, step_nm)
    # every row the coarse weight in units; a binary row's (and an exact unary row's) two fingers a
    # tail each besides
    tailed = unary + binary if exact_unary(cdac) else binary
    fingers_ff = (unary + binary) * coarse * unit + tailed * 2 * model.tail_ff
    # the edge dummies are placed rows too
    other_ff = (unary + binary + 2) * (model.other_row_ff + model.other_row_um_ff * row_um)
    width, height = model.outline_um(unary + binary, coarse, step_nm)
    return Prediction(
        unary + binary, step_nm, row_um, switched_ff * 1e-15, (fingers_ff + other_ff) * 1e-15, reference, width, height
    )


def _off_outline(aspect: float) -> float:
    """How far an outline is from ``ASPECT``: the log of their ratio's magnitude."""
    return abs(math.log(aspect / ASPECT))


def _bisect(condition, low: float = 1e-16, high: float = 1e-9) -> float:
    """The least capacitance in [low, high] where the monotone ``condition`` holds (inf if never)."""
    if not condition(high):
        return math.inf
    for _ in range(80):
        middle = math.sqrt(low * high)
        low, high = (low, middle) if condition(middle) else (middle, high)
    return high


def least_switched_f(cdac: CapArrayConfig, coarse: int, model: RowModel, reference: float) -> dict[str, float]:
    """The least switched capacitance at which the array, split at ``coarse``, keeps its full scale
    (``full_scale``) and its noise below its quantization noise (``noise``): its full scale grows
    with the capacitance, its noise over its quantization noise falls."""
    bits = cdac.n_dac + 1
    return {
        "full_scale": _bisect(
            lambda c: predict(cdac, coarse, c, model, reference).full_scale >= MIN_FULL_SCALE + MARGIN
        ),
        "noise": _bisect(lambda c: predict(cdac, coarse, c, model, reference).noise_ratio(bits) <= 1 - MARGIN),
    }


def array_minimum(cdac: CapArrayConfig, model: RowModel, reference: float) -> dict[str, Any]:
    """The array's own least switched capacitance (at one kT/C minimum): at the split whose outline
    there is nearest ``ASPECT`` among those whose least capacitance is within ``SPLIT_SLACK`` of any
    split's least, and the constraint that sets it there."""
    unscaled = replace(cdac, cap_scale=1)
    needs = {coarse: least_switched_f(unscaled, coarse, model, reference) for coarse in splits(cdac)}
    least = min(max(need.values()) for need in needs.values())
    near = [coarse for coarse, need in needs.items() if max(need.values()) <= SPLIT_SLACK * least]
    aspects = {
        coarse: predict(unscaled, coarse, max(needs[coarse].values()), model, reference).aspect for coarse in near
    }
    coarse = min(near, key=lambda coarse: _off_outline(aspects[coarse]))
    binding = max(needs[coarse], key=needs[coarse].get)
    return {"switched_f": needs[coarse][binding], "coarse_weight": coarse, "set_by": binding, "aspect": aspects[coarse]}


def resolution_minimums(
    arrays: dict[str, CapArrayConfig], models: dict[str, RowModel], reference: float
) -> dict[int, dict[str, Any]]:
    """Each resolution's least switched capacitance: the largest of its arrays' own
    (``array_minimum``, each scheme whatever its scale), and what sets it (the array, its split and
    the constraint)."""
    minimums: dict[int, dict[str, Any]] = {}
    for name, cdac in arrays.items():
        bits = cdac.n_dac + 1
        own = {**array_minimum(cdac, models[name], reference), "array": name}
        if bits not in minimums or own["switched_f"] > minimums[bits]["switched_f"]:
            minimums[bits] = own
    return minimums


@dataclass(frozen=True)
class Design:
    """An array's split (its coarse weight), its weight step and its unary rows' finger (nm)."""

    coarse_weight: int
    weight_step: int
    unary_length: int


def design(cdac: CapArrayConfig, least_f: float, model: RowModel, reference: float) -> tuple[Design, Prediction] | None:
    """The array at ``cap_scale`` times its resolution's least switched capacitance, at the split
    (``splits``) whose outline is nearest ``ASPECT`` (the fewer rows where two are as near) of those
    that keep its full scale and its noise below 1/cap_scale of its quantization noise and whose
    one-finger unary rows, at most a binary row's two fingers long, weigh the coarse weight within
    ``UNARY_TOLERANCE`` (an exact unary row's, unary_length 0, weighs it by the strips' difference);
    its step on the grid. None where no split does."""
    switched_f = cdac.cap_scale * least_f
    bits = cdac.n_dac + 1
    exact = exact_unary(cdac)
    feasible = []
    for coarse in splits(cdac):
        guess = predict(cdac, coarse, switched_f, model, reference)
        nearest = max(1, round(guess.step_nm / model.grid_nm))
        # the nearest step on the grid, or one grid more where rounding down loses a constraint
        for step in (nearest * model.grid_nm, (nearest + 1) * model.grid_nm):
            drawn = predict(cdac, coarse, switched_f, model, reference, step_nm=step)
            # a unary finger at most a binary row's two fingers long: its weight there within tolerance
            longest = round(2 * (model.tail_um * 1000 + coarse * step))
            unary = 0 if exact else min(model.unary_length_nm(coarse, step), longest)
            error = 0.0 if exact else model.unary_error_lsb(coarse, step, unary)
            if (
                abs(error) <= UNARY_TOLERANCE
                and drawn.full_scale >= MIN_FULL_SCALE + MARGIN / 2
                and drawn.noise_ratio(bits) * cdac.cap_scale <= 1 - MARGIN / 2
            ):
                feasible.append((Design(coarse, step, unary), drawn))
                break
    if not feasible:
        return None
    return min(feasible, key=lambda option: (round(_off_outline(option[1].aspect), 3), option[1].rows))


def _drawn(work: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        json.loads((work / "geometry_manifest.json").read_text()),
        json.loads((work / "capacitance_table.json").read_text()),
    )


def stage_rows(manifest: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Each stage's unary rows, binary weight and binary rows as drawn (a unary row: a chunk of
    the coarse weight where the unary rows are one finger)."""
    coarse = manifest["unit_family"]["coarse_weight"]
    unary = bool(manifest["unit_family"].get("unary_length"))
    stages = manifest["partitioned_weights_by_stage"]
    is_unary = [[unary and chunk == coarse for chunk in stage] for stage in stages]
    return (
        np.asarray([sum(flags) for flags in is_unary], float),
        np.asarray(
            [sum(c for c, u in zip(s, f, strict=True) if not u) for s, f in zip(stages, is_unary, strict=True)], float
        ),
        np.asarray([sum(not u for u in flags) for flags in is_unary], float),
    )


def stage_fit(work: Path) -> dict[str, float]:
    """An extraction's unary row, unit and binary rows' offset: each stage's effective capacitance
    (main less difference) is its unary rows', its binary weight's and its binary rows' offset,
    fitted over every stage."""
    manifest, table = _drawn(work)
    unary, weight, binary = stage_rows(manifest)
    effective = np.asarray(table["main_by_stage_ff"]) - np.asarray(table["diff_by_stage_ff"])
    columns = [weight, binary] + ([unary] if unary.any() else [])
    solution, *_ = np.linalg.lstsq(np.column_stack(columns), effective, rcond=None)
    return {
        "unit_ff": float(solution[0]),
        "binary_offset_ff": float(solution[1]),
        "unary_ff": float(solution[2]) if unary.any() else math.nan,
    }


def other_load_shape(works: list[Path]) -> tuple[float, float] | None:
    """The top plate's other load (to the shield and to ground) per placed row and per placed row
    and micrometre of row, neither negative, fitted over extractions with tied edge dummies (every
    array's: rows from a few to hundreds of micrometres); None with fewer than two."""
    from scipy.optimize import nnls

    columns, others = [], []
    for work in works:
        manifest, table = _drawn(work)
        if not manifest["unit_family"].get("tied_dummies"):
            continue
        placed = manifest["placed_unit_count"]
        columns.append((placed, placed * manifest["derived_geometry_nm"]["outer_height"] / 1000))
        others.append(table["topplate_shield_ff"] + table["topplate_ground_ff"])
    if len(others) < 2:
        return None
    (per_row, per_um), _residual = nnls(np.asarray(columns, float), np.asarray(others, float))
    return float(per_row), float(per_um)


def calibrated(
    base: RowModel, work: Path, shape: tuple[float, float] | None = None, history: list[Path] | tuple = ()
) -> RowModel:
    """``base`` corrected by an extraction of the array in ``work`` (its manifest and capacitance
    table): its unit's slope, its binary rows' offset and fingers' tails, its unary finger's ends
    (and each split's scale and unary finger by the newest of them at it, ``unary_by_split``), and
    its top plate's other load: fitted per row and per micrometre of row, neither negative, over
    it and the array's ``history`` at the same split where their rows' lengths span a fifth or more,
    else ``shape`` (``other_load_shape``) scaled to it, or half each. A floating edge dummy's
    fingers are extracted to ground: where the dummies were not tied, the ground part is left out."""
    manifest, table = _drawn(work)
    family = manifest["unit_family"]
    coarse, step = family["coarse_weight"], manifest["derived_geometry_nm"]["weight_step"]
    fit = stage_fit(work)
    scale = fit["unit_ff"] / base.unit_ff(step)
    model = replace(base, scale=scale, binary_offset_ff=fit["binary_offset_ff"])
    unary, _weight, binary = stage_rows(manifest)
    unary_rows, binary_rows = int(unary.sum()), int(binary.sum())
    if unary_rows:
        model = replace(model, unary_ff=fit["unary_ff"] - scale * base.slope_ff_um * family["unary_length"] / 1000)
    # each split's unary rows by the newest extraction at it (the history oldest first)
    unary_points = [_unary_point(base, drawn) for drawn in (*history, work)]
    own = {point[0]: point for point in unary_points if point is not None}
    model = replace(model, unary_by_split=tuple(sorted(own.values())))
    fingers = table["main_ff"] + table["diff_ff"] - unary_rows * (fit["unary_ff"] if unary_rows else 0.0)
    model = replace(model, tail_ff=(fingers / binary_rows - coarse * fit["unit_ff"]) / 2)
    tied = family.get("tied_dummies")
    other = table["topplate_shield_ff"] + (table["topplate_ground_ff"] if tied else 0.0)
    placed = manifest["placed_unit_count"]
    length = manifest["derived_geometry_nm"]["outer_height"] / 1000
    same = [work, *(earlier for earlier in history if _same_split(earlier, work))]
    points = [_other_point(drawn) for drawn in same]
    lengths = [length_um for _placed, length_um, _other in points]
    if len(points) > 1 and max(lengths) >= 1.2 * min(lengths):
        from scipy.optimize import nnls

        columns = np.asarray([(placed_, placed_ * length_um) for placed_, length_um, _other in points], float)
        (per_row, per_um), _residual = nnls(columns, np.asarray([other_ for *_rest, other_ in points], float))
        return replace(model, other_row_ff=float(per_row), other_row_um_ff=float(per_um))
    per_row, per_um = shape if shape is not None and any(shape) else (1.0, 1.0 / length)
    own = other / (placed * (per_row + per_um * length))
    return replace(model, other_row_ff=own * per_row, other_row_um_ff=own * per_um)


def _unary_point(base: RowModel, work: Path) -> tuple[int, float, float] | None:
    """An extraction's split, scale and unary finger beyond its length's slope, where its unary
    rows are one finger."""
    manifest, _table = _drawn(work)
    family = manifest["unit_family"]
    if not family.get("unary_length") or not stage_rows(manifest)[0].any():
        return None
    fit = stage_fit(work)
    scale = fit["unit_ff"] / base.unit_ff(manifest["derived_geometry_nm"]["weight_step"])
    return family["coarse_weight"], scale, fit["unary_ff"] - scale * base.slope_ff_um * family["unary_length"] / 1000


def _same_split(one: Path, other: Path) -> bool:
    first, second = _drawn(one)[0]["unit_family"], _drawn(other)[0]["unit_family"]
    return first["coarse_weight"] == second["coarse_weight"] and bool(first.get("tied_dummies")) == bool(
        second.get("tied_dummies")
    )


def _other_point(work: Path) -> tuple[int, float, float]:
    """An extraction's placed rows, row length and the top plate's other load."""
    manifest, table = _drawn(work)
    tied = manifest["unit_family"].get("tied_dummies")
    other = table["topplate_shield_ff"] + (table["topplate_ground_ff"] if tied else 0.0)
    return manifest["placed_unit_count"], manifest["derived_geometry_nm"]["outer_height"] / 1000, other


def extractions(name: str, root: Path | None = None) -> list[Path]:
    """The array's extractions in its newest run that has any (its passes and its final, oldest
    first), or in ``root`` alone."""
    from .model import EXTRACTIONS

    runs = [root] if root is not None else sorted(EXTRACTIONS.glob("*"), reverse=True)
    for run in runs:
        tables = list((run / name / PDK).glob(f"{LAYERS}l*/capacitance_table.json"))
        if tables:
            return [table.parent for table in sorted(tables, key=lambda table: table.stat().st_mtime)]
    return []


def _earlier_model(base: RowModel, name: str, cdac: CapArrayConfig, shape=None) -> RowModel:
    """``base`` corrected by the newest earlier extractions of the array, or of its resolution's
    binary array at its scale; uncorrected where there is none (it only shortens the passes)."""
    for candidate in (name, f"{cdac.n_dac + 1}b_binary_x{cdac.cap_scale}"):
        works = extractions(candidate)
        for index in range(len(works) - 1, -1, -1):
            try:
                return calibrated(base, works[index], shape, works[:index])
            except (OSError, KeyError, ValueError, ZeroDivisionError, np.linalg.LinAlgError):
                continue
    return base


def _design_of(work: Path) -> Design:
    family = _drawn(work)[0]["unit_family"]
    return Design(family["coarse_weight"], family["weight_step"], family.get("unary_length") or 0)


def _all_extractions() -> list[Path]:
    from .model import EXTRACTIONS

    return [table.parent for table in EXTRACTIONS.glob(f"*/*/{PDK}/{LAYERS}l*/capacitance_table.json")]


def layout_params(name: str, cdac: CapArrayConfig, choice: Design) -> CapArrayLayoutParams:
    """The array drawn at its design: its unary rows one finger (or, unary_length 0, a main and a
    difference finger of the tail), its edge dummies tied."""
    params = _stacked(PDK, cdac, name, LAYERS)
    family = replace(
        params.family,
        coarse_weight=choice.coarse_weight,
        weight_step=choice.weight_step,
        tied_dummies=True,
        unary_length=choice.unary_length or None,
    )
    return replace(params, family=family)


def measured(work: Path, cdac: CapArrayConfig, reference: float) -> dict[str, Any]:
    """An extraction's split, rows and row length, switched capacitance, whole top-plate load,
    full scale, noise over quantization noise, and its unary rows' weight in its unit."""
    manifest, table = _drawn(work)
    load = table["main_ff"] + table["diff_ff"] + table["topplate_shield_ff"] + table["topplate_ground_ff"]
    full_scale = table["effective_ff"] / load
    unary, _weight, _binary = stage_rows(manifest)
    fit = stage_fit(work)
    coarse = manifest["unit_family"]["coarse_weight"]
    return {
        "coarse_weight": coarse,
        "binary_bits": int(math.log2(coarse)),
        "weight_step_nm": manifest["derived_geometry_nm"]["weight_step"],
        "unary_length_nm": manifest["unit_family"].get("unary_length"),
        "rows": manifest["physical_chunk_count"],
        "unary_rows": int(unary.sum()),
        "row_um": manifest["derived_geometry_nm"]["outer_height"] / 1000,
        "switched_ff": table["effective_ff"],
        "load_ff": load,
        "unit_ff": table["effective_ff"] / sum(manifest["weights_by_stage"]),
        # a unary row less the coarse weight, in the binary rows' unit
        "unary_error_lsb": fit["unary_ff"] / fit["unit_ff"] - coarse if unary.any() else 0.0,
        "full_scale": full_scale,
        "full_scale_v": reference * full_scale,
        # 1/cap_scale on target
        "noise_over_quantization": total_capacitance_f(cdac.n_dac + 1, reference * full_scale) / (load * 1e-15),
        # each stage's effective capacitance against its weight in the array's mean unit
        "stage_error_lsb": [
            (main - diff) / (table["effective_ff"] / sum(manifest["weights_by_stage"])) - weight
            for main, diff, weight in zip(
                table["main_by_stage_ff"], table["diff_by_stage_ff"], manifest["weights_by_stage"], strict=True
            )
        ],
    }


def _meets(entry: dict[str, Any], cdac: CapArrayConfig) -> bool:
    return (
        entry["full_scale"] >= MIN_FULL_SCALE
        and entry["noise_over_quantization"] * cdac.cap_scale <= 1
        and abs(entry["unary_error_lsb"]) <= UNARY_TOLERANCE
    )


def _extract_job(work: Path, name: str, cdac: CapArrayConfig, choice: Design, reference: float) -> dict[str, Any]:
    start = time.monotonic()
    result = extract_array(work, PDK, layout_params(name, cdac, choice))
    return {**result, **measured(work, cdac, reference), "seconds": time.monotonic() - start}


def _designs(
    arrays: dict[str, CapArrayConfig], models: dict[str, RowModel], reference: float
) -> tuple[dict[int, dict[str, Any]], dict[str, Design]]:
    minimums = resolution_minimums(arrays, models, reference)
    designs = {}
    for name, cdac in arrays.items():
        chosen = design(cdac, minimums[cdac.n_dac + 1]["switched_f"], models[name], reference)
        if chosen is None:
            raise ValueError(f"no split of {name} meets both constraints")
        designs[name] = chosen[0]
    return minimums, designs


def extract_adc_arrays(
    run_dir: Path, *, arrays: dict[str, CapArrayConfig] | None = None, workers: int = 16, seed: bool = True
) -> Path:
    """Size and extract the ADC study's arrays (``ADC_ARRAYS``, or ``arrays`` of them) at three
    metals in TSMC65, ``workers`` at a time, from the newest earlier run's extractions of them
    (``seed``: those of the same family, a holding one copied in rather than drawn again): each pass
    sizes every array from its extractions (``resolution_minimums``, ``design``) and extracts those no extraction holds for
    (``_holding``), into ``<name>/tsmc65/3l_pass<k>``, until none is left; each array's holding
    extraction is then its ``<name>/tsmc65/3l`` (``flow.caparray.model.CapArrayModel`` reads it),
    the others stay as passes. Writes ``summary.json``:
    each resolution's least switched capacitance and what sets it, each array's design, its
    extraction against both constraints, and its passes."""

    from concurrent.futures import ProcessPoolExecutor, as_completed
    from multiprocessing import get_context

    arrays = ADC_ARRAYS if arrays is None else arrays
    reference = reference_v(PDK)
    base = row_model()
    shape = other_load_shape(_all_extractions())
    # each array's extractions, in order: its design, directory and measurement; seeded with its
    # newest earlier run's of the same family (tied dummies), which hold where their design does
    passes: dict[str, list[tuple[Design, Path, dict[str, Any]]]] = {name: [] for name in arrays}
    history: dict[str, list[dict[str, Any]]] = {name: [] for name in arrays}
    models = {}
    for name, cdac in arrays.items():
        works = [
            work
            for work in (extractions(name) if seed else [])
            if work.parent.parent.parent != run_dir and _drawn(work)[0]["unit_family"].get("tied_dummies")
        ]
        for work in works:
            entry = {**measured(work, cdac, reference), "seeded_from": str(work.relative_to(work.parents[3]))}
            passes[name].append((_design_of(work), work, entry))
            history[name].append({"pass": "seed", **entry})
        models[name] = (
            calibrated(base, works[-1], shape, works[:-1]) if works else _earlier_model(base, name, cdac, shape)
        )
    summary: dict[str, Any] = {"min_full_scale": MIN_FULL_SCALE, "reference_v": reference}
    designs: dict[str, Design] = {}
    count = 0
    for index in range(SIZING_PASSES):
        minimums, designs = _designs(arrays, models, reference)
        summary["resolutions"] = {
            bits: {**entry, "switched_ff": entry["switched_f"] * 1e15} for bits, entry in minimums.items()
        }
        todo = {
            name: designs[name] for name, cdac in arrays.items() if _holding(passes[name], designs[name], cdac) is None
        }
        if not todo:
            break
        count += 1
        # the largest first: they take the longest
        order = sorted(todo, key=lambda name: -arrays[name].cap_scale * minimums[arrays[name].n_dac + 1]["switched_f"])
        with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(
                    _extract_job,
                    run_dir / name / PDK / f"{LAYERS}l_pass{index}",
                    name,
                    arrays[name],
                    todo[name],
                    reference,
                ): name
                for name in order
            }
            for future in as_completed(futures):
                name = futures[future]
                work = run_dir / name / PDK / f"{LAYERS}l_pass{index}"
                try:
                    entry = future.result()
                except Exception as error:  # noqa: BLE001 - every array reports its own failure
                    history[name].append({"pass": index, "error": str(error)[:500]})
                    continue
                passes[name].append((todo[name], work, entry))
                history[name].append({"pass": index, **{k: v for k, v in entry.items() if k != "stages"}})
                summary["arrays"] = _array_summary(arrays, _finals(arrays, passes, designs), history)
                (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        # the other load's shape over every extraction so far, each array corrected by its newest
        shape = other_load_shape(_all_extractions())
        summary["other_load_shape"] = shape
        for name in arrays:
            if passes[name]:
                try:
                    works = [work for _design, work, _entry in passes[name]]
                    models[name] = calibrated(base, works[-1], shape, works[:-1])
                except (KeyError, ValueError, ZeroDivisionError, np.linalg.LinAlgError) as error:
                    history[name].append({"pass": index, "calibration_error": str(error)[:200]})
    finals = _finals(arrays, passes, designs)
    for name, (_choice, work, _entry) in finals.items():
        final = run_dir / name / PDK / f"{LAYERS}l"
        if work.is_relative_to(run_dir):
            work.rename(final)
        else:  # a seed that holds: copied in, so that the newest run holds every array
            import shutil

            shutil.copytree(work, final)
    summary["arrays"] = _array_summary(arrays, finals, history, final=True)
    summary["passes"] = count
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return run_dir


def _holding(drawn: list[tuple[Design, Path, dict[str, Any]]], new: Design, cdac: CapArrayConfig):
    """The extraction of the array that holds for its ``new`` design, if one does: one of the same
    split and step (two designs alternating), or the last, at the same split, its step within
    ``STEP_TOLERANCE``; either meeting both constraints."""

    def alike(choice: Design) -> bool:  # the same split and the same unary rows (one finger or two)
        return choice.coarse_weight == new.coarse_weight and (choice.unary_length == 0) == (new.unary_length == 0)

    for choice, work, entry in drawn:
        if alike(choice) and choice.weight_step == new.weight_step and _meets(entry, cdac):
            return choice, work, entry
    if drawn:
        choice, work, entry = drawn[-1]
        if (
            alike(choice)
            and abs(new.weight_step - choice.weight_step) <= STEP_TOLERANCE * choice.weight_step
            and _meets(entry, cdac)
        ):
            return choice, work, entry
    return None


def _finals(arrays, passes, designs) -> dict[str, tuple[Design, Path, dict[str, Any]]]:
    """Each array's extraction that holds for its last design; else, at its design's split, of those
    meeting every tolerance the nearest its design's step, else of those keeping both constraints
    the one whose unary rows weigh nearest the coarse weight; else its last."""
    finals = {}
    for name, cdac in arrays.items():
        drawn = passes[name]
        if not drawn:
            continue
        holding = _holding(drawn, designs[name], cdac) if name in designs else None
        if holding or name not in designs:
            finals[name] = holding or drawn[-1]
            continue
        split = [
            entry
            for entry in drawn
            if entry[0].coarse_weight == designs[name].coarse_weight
            and (entry[0].unary_length == 0) == (designs[name].unary_length == 0)
        ] or drawn
        meeting = [entry for entry in split if _meets(entry[2], cdac)]
        keeping = [entry for entry in split if _meets({**entry[2], "unary_error_lsb": 0.0}, cdac)]
        if meeting:
            finals[name] = min(meeting, key=lambda entry: abs(entry[0].weight_step - designs[name].weight_step))
        elif keeping:
            finals[name] = min(keeping, key=lambda entry: abs(entry[2]["unary_error_lsb"]))
        else:
            finals[name] = drawn[-1]
    return finals


def _array_summary(arrays, drawn, history, final: bool = False) -> dict[str, Any]:
    summary = {}
    for name, cdac in arrays.items():
        if name not in drawn:
            summary[name] = {"error": "not extracted", "passes": history[name]}
            continue
        _choice, work, entry = drawn[name]
        summary[name] = {
            **entry,
            "directory": f"{LAYERS}l" if final else work.name,
            "drawn_in": entry.get("seeded_from", work.name),
            "meets": _meets(entry, cdac),
            "passes": history[name],
        }
    return summary


def designs_table(arrays: dict[str, CapArrayConfig] | None = None) -> list[dict[str, Any]]:
    """Each array's design as the model, corrected by the newest extraction of it, gives it: for a
    look before extracting."""
    arrays = ADC_ARRAYS if arrays is None else arrays
    reference = reference_v(PDK)
    base = row_model()
    shape = other_load_shape(_all_extractions())
    models = {name: _earlier_model(base, name, cdac, shape) for name, cdac in arrays.items()}
    minimums = resolution_minimums(arrays, models, reference)
    table = []
    for name, cdac in arrays.items():
        chosen = design(cdac, minimums[cdac.n_dac + 1]["switched_f"], models[name], reference)
        if chosen is None:
            table.append({"name": name, "error": "no split meets both"})
            continue
        choice, prediction = chosen
        table.append(
            {
                "name": name,
                **asdict(choice),
                "rows": prediction.rows,
                "row_um": prediction.row_um,
                "switched_ff": prediction.switched_f * 1e15,
                "load_ff": prediction.total_f * 1e15,
                "full_scale": prediction.full_scale,
                "noise_over_quantization": prediction.noise_ratio(cdac.n_dac + 1),
                "least": minimums[cdac.n_dac + 1],
            }
        )
    return table
