"""The comparator's design space (``flow.sweep``): the characterization's six topologies at ten
sizes (seven around the short-channel base, three around FRIDA-1's long-channel comparator), in
every PDK.

Each instance at the nominal common mode (13/24 of its supply): the clock-to-decision delay and
energy per decision at 0.5 mV and 100 mV of input (the slowest and fastest response), the delay
over the input from 0.1 mV to 100 mV (its metastability), and the offset and input-referred noise
from a transient-noise S-curve (+-2 mV, 21 points, 40 decisions each). Over the common mode (3/8
to 5/8 of the supply) the S-curve again; over the supply (90 to 120 % of its own) the delay and
energy at both inputs. Clock: 1 ns reset and 6 ns evaluation, both doubled (up to 8 and 48 ns)
until the clock no longer cuts the latch short. Its noise-free metastability decisions (each input
after its negative, so that a reset which leaves the last decision shows) all resolve
(``MeasComp.resolved``: the latch's nodes half the supply apart at the evaluation's end), the next
clock leaves every one of them unchanged, and the delay at each positive input and at 10 uV (the
delay at 0.1 mV extrapolated by the regeneration time constant) to within 2 % (neither the reset
nor the evaluation shapes the result), the latch resolves those 10 uV within the evaluation, and
the nominal S-curve leaves at most 1 % of its decisions unresolved; the longest clock is taken as
it is. Every run of the instance takes that clock (``evaluation_time_s``), and a decision
unresolved is timed nowhere and left out of the S-curve, where more than 1 % of them give no noise
or offset. Eleven Spectre runs at that clock and a metastability run at the next, after a
metastability run (and where it passed, a nominal S-curve) at each faster one tried.
"""

from __future__ import annotations

import importlib
import math
from dataclasses import replace
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.sweep import Detail, Record

from . import sim
from .sim import TOPOLOGY_SIZES, CompTbParams, _run_comp_sim, comp_signal_names
from .subckt import Comp, CompParams, OutputStage, is_valid_comp_params, write_netlist

GENERATOR = Comp
# the characterization's six topologies (flow.comp.sim): the parameters that make each
STRUCTURES = list(sim.TOPOLOGIES.values())
STRUCTURE = (
    "comp_stages",
    "preamp_diff_xtors",
    "preamp_bias",
    "latch_outer_on_xtors",
    "latch_inner_on_xtors",
    "latch_outer_init_xtors",
    "latch_inner_init_xtors",
    "latch_tail_shared",
)
# the key devices' widths scaled together (x0.5 to x4), the input pair or the latch alone
# doubled, and the input pair and tail at twice their length, around the short-channel base
WIDTHS = ("diffpair_w", "tail_w", "rst_w", "latch_on_w", "latch_init_w", "srlatch_n_w", "srlatch_p_w")
# no width under 4 units: half of the 4-unit output latch would fall below the finest PDK's minimum width
X0P5 = {name: max(4, TOPOLOGY_SIZES[name] // 2) for name in WIDTHS}
X4 = {name: 4 * TOPOLOGY_SIZES[name] for name in WIDTHS}
# near FRIDA-1's hand-sized comparator (flow.comp.subckt.FRIDA1: a long, weak tail and long latch
# devices) in round multiples of the minimum, with its widths doubled and its lengths doubled, so
# every FRIDA-1 size falls inside the sweep's range
FRIDA1_LIKE = {
    "diffpair_w": 32,
    "diffpair_l": 4,
    "tail_w": 6,
    "tail_l": 16,
    "rst_w": 8,
    "rst_l": 1,
    "latch_on_w": 24,
    "latch_on_l": 6,
    "latch_init_w": 32,
    "latch_init_l": 16,
    "srlatch_n_w": 4,
    "srlatch_p_w": 8,
}
LENGTHS = ("diffpair_l", "tail_l", "rst_l", "latch_on_l", "latch_init_l")
FRIDA1_LIKE_LONG = {**FRIDA1_LIKE, **{name: 2 * FRIDA1_LIKE[name] for name in LENGTHS}}
SIZES = [
    X0P5,
    {},
    {name: 2 * TOPOLOGY_SIZES[name] for name in WIDTHS},
    X4,
    {"diffpair_w": 2 * TOPOLOGY_SIZES["diffpair_w"]},
    {name: 2 * TOPOLOGY_SIZES[name] for name in ("latch_on_w", "latch_init_w")},
    {"diffpair_l": 2 * TOPOLOGY_SIZES["diffpair_l"], "tail_l": 2 * TOPOLOGY_SIZES["tail_l"]},
    FRIDA1_LIKE,
    {**FRIDA1_LIKE, **{name: 2 * FRIDA1_LIKE[name] for name in WIDTHS}},
    FRIDA1_LIKE_LONG,
]


def comparator(structure: dict, sizes: dict | None = None) -> CompParams:
    """A comparator of the characterization's structure at ``sizes`` over its shared ones."""
    return CompParams(**structure, **{**TOPOLOGY_SIZES, **(sizes or {})})


def instances(pdk: str) -> list[CompParams]:
    """Every topology at every size, in every PDK."""
    comps = (comparator(structure, sizes) for structure in STRUCTURES for sizes in SIZES)
    return [comp for comp in comps if is_valid_comp_params(comp)]


NOMINAL_CM = 13 / 24
CM_SWEEP = (9 / 24, 11 / 24, 13 / 24, 15 / 24)
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
SMALL_V, LARGE_V = 0.5e-3, 100e-3
METASTABILITY_V = (0.1e-3, 0.3e-3, 1e-3, 3e-3, 10e-3, 30e-3, 100e-3)
# the metastability run's inputs, one decision each: each of METASTABILITY_V after its negative, so
# that every decision but the first follows one of the other sign (a latch the reset leaves holding
# its last decision, which inputs of one sign cannot show, decides it again, or late), and no input
# steps by more than twice the next one (the source settles within the reset)
METASTABILITY_RUN_V = tuple(v for value in METASTABILITY_V for v in (-value, value))
SCURVE_V = tuple(round(step * 0.2e-3, 6) for step in range(-10, 11))
# the clocks tried, fastest first: reset and evaluation, both doubled (a latch slow to regenerate is
# slow to reset too: after 12 or 24 ns of evaluation, 1 ns of reset leaves a FRIDA-1-like latch
# holding its last decision); the input the chosen clock's evaluation must resolve; and how far the
# next clock may move the chosen one's delay at any of METASTABILITY_V or at RESOLVED_V
CLOCKS_S = ((1e-9, 6e-9), (2e-9, 12e-9), (4e-9, 24e-9), (8e-9, 48e-9))
RESOLVED_V = 10e-6
SETTLED_RTOL = 0.02
UNRESOLVED_MAX = 0.01  # the S-curve fit's limit (flow.analysis.comp.analyze_comp_offset_noise)


def _measure(run_dir: Path, tb: CompTbParams, *, noise: bool):
    """One Spectre run of the comparator testbench, as a measurement."""

    from flow.circuit.results import convert_raw_comp_to_measurement, read_raw_transient

    raw, tb, readbacks = _run_comp_sim(
        run_dir,
        tb,
        candidate_id=run_dir.name,
        candidate_label=run_dir.name,
        topology_index=0,
        size_profile="sweep",
        noise=noise,
    )
    measurement = convert_raw_comp_to_measurement(
        read_raw_transient(raw), params=tb, raw_path=raw, signal_names=comp_signal_names()
    )
    raw.unlink()  # the measurement keeps the waveforms; a noise run's raw file is tens of MB
    return replace(measurement, info=replace(measurement.info, readbacks={**measurement.info.readbacks, **readbacks}))


def _unresolved(measurement) -> np.ndarray:
    """Per decision: the latch still undecided when it was read (``MeasComp.resolved``)."""

    if measurement.resolved is None:
        return np.zeros(len(measurement.decision), dtype=np.bool_)
    return ~np.asarray(measurement.resolved, dtype=np.bool_)


def characterize(run_dir: Path, pdk: str, comp: CompParams) -> Record:
    from flow.analysis.comp import analyze_comp_offset_noise
    from flow.analysis.io import write_measurement
    from flow.comp.analysis import analyze_comp_delay, analyze_comp_power, analyze_comp_timing

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)

    def bench(
        clock: tuple[float, float],
        vdd: float,
        cm: float,
        inputs: tuple[float, ...],
        conversions: int,
        spacing: float = 2e-12,
    ) -> CompTbParams:
        return CompTbParams(
            pdk=pdk,
            comp=comp,
            vdd=round(vdd, 4),
            vin_cm_values_v=(round(cm, 4),),
            vin_diff_values_v=inputs,
            conversions=conversions,
            waveform_sample_interval_s=spacing,
            reset_time_s=clock[0],
            evaluation_time_s=clock[1],
            transition_time_s=20e-12,
        )

    def delays(measurement):
        # timed only where the decision resolved (MeasComp.resolved): the timing's own test (0.1 V
        # apart at the record's end) and threshold (half the record's largest swing) time a latch the
        # evaluation cut short, early
        timing = analyze_comp_timing([measurement])
        timing = replace(timing, unresolved=timing.unresolved | _unresolved(measurement)[timing.trial_index])
        return analyze_comp_delay([measurement], timing=timing)

    def delay_energy(measurement) -> tuple[float, float]:
        delay = delays(measurement).delay_s
        return float(np.nanmax(delay)), float(analyze_comp_power([measurement]).energy_per_decision_j[0])

    def metastability_delays(delay) -> np.ndarray:
        # at each of METASTABILITY_V: the run's positive inputs
        return delay.delay_s[0][delay.vin_diff_v > 0]

    def regeneration_tau(delay) -> float:
        smallest = metastability_delays(delay)[:2]
        return float((smallest[0] - smallest[1]) / math.log(METASTABILITY_V[1] / METASTABILITY_V[0]))

    def screened(delay) -> np.ndarray:
        # the delays at METASTABILITY_V and, last, at RESOLVED_V (the smallest extrapolated by the
        # regeneration time constant)
        at = metastability_delays(delay)
        return np.append(at, at[0] + regeneration_tau(delay) * math.log(METASTABILITY_V[0] / RESOLVED_V))

    cm = NOMINAL_CM * supply
    screens = {}

    def screen(clock: tuple[float, float]):
        """The noise-free metastability run at a clock, with its delays (each clock's once)."""
        if clock not in screens:
            measurement = _measure(
                run_dir / "metastability" / f"{round(clock[1] * 1e9)}ns",
                bench(clock, supply, cm, METASTABILITY_RUN_V, 1),
                noise=False,
            )
            screens[clock] = measurement, delays(measurement)
        return screens[clock]

    def settled(clock: tuple[float, float], longer: tuple[float, float]) -> bool:
        """The clock cuts the latch short nowhere the longer one does not: every noise-free decision
        resolved and comes out as at the longer clock, the screened delays are the longer clock's to
        SETTLED_RTOL (the first decision's, from the operating point, is left out: it moves by a few %
        between clocks where nothing else does), and the evaluation resolves RESOLVED_V."""
        (meta, meta_delay), (reference, reference_delay) = screen(clock), screen(longer)
        delay_s = screened(meta_delay)
        return bool(
            not np.any(_unresolved(meta))
            and np.array_equal(meta.decision, reference.decision)
            and np.allclose(delay_s, screened(reference_delay), rtol=SETTLED_RTOL, atol=0.0)
            and delay_s[-1] <= clock[1]
        )

    nominal_folder = f"scurve_cm{round(NOMINAL_CM * 24)}"
    # the clock: the fastest that the next one shows does not cut the latch short (a reset that leaves
    # the last decision, or an evaluation that ends the latch's swing early, moves a decision or its
    # delay), and whose nominal S-curve leaves at most UNRESOLVED_MAX of its decisions unresolved; the
    # metastability runs (seconds) screen a clock before the S-curve (minutes) does
    for clock, longer in zip(CLOCKS_S, (*CLOCKS_S[1:], None), strict=True):
        if longer is not None and not settled(clock, longer):
            continue
        nominal = _measure(run_dir / nominal_folder, bench(clock, supply, cm, SCURVE_V, 40, 10e-12), noise=True)
        if longer is None or np.mean(_unresolved(nominal)) <= UNRESOLVED_MAX:
            break
    meta, meta_delay = screen(clock)

    waves = {}
    small = _measure(run_dir / "small", bench(clock, supply, cm, (SMALL_V,), 3), noise=False)
    large = _measure(run_dir / "large", bench(clock, supply, cm, (LARGE_V,), 3), noise=False)
    for name, folder, measurement in (
        ("0.5 mV input", "small", small),
        ("100 mV input", "large", large),
        ("metastability", "metastability", meta),
    ):
        path = run_dir / folder / "result.h5"
        write_measurement(path, measurement)
        waves[name] = str(path.relative_to(Path(__file__).resolve().parents[2]))
    delay_small, energy_small = delay_energy(small)
    delay_large, energy_large = delay_energy(large)

    scurves = {}
    for fraction in CM_SWEEP:
        measurement = (
            nominal
            if fraction == NOMINAL_CM
            else _measure(
                run_dir / f"scurve_cm{round(fraction * 24)}",
                bench(clock, supply, fraction * supply, SCURVE_V, 40, 10e-12),
                noise=True,
            )
        )
        scurves[fraction] = analyze_comp_offset_noise([measurement])
    # the nominal S-curve at each input: P(high) among the decisions that resolved (NaN where none
    # did), and the fraction that did not
    unresolved = _unresolved(nominal)
    probability, undecided = [], []
    for value in SCURVE_V:
        at = np.isclose(nominal.vin_diff_v, value, rtol=0.0, atol=1e-9)
        decided = at & ~unresolved
        probability.append(float(np.mean(nominal.decision[decided])) if np.any(decided) else math.nan)
        undecided.append(float(np.mean(unresolved[at])))

    supply_points = {}
    for factor in SUPPLY_SWEEP:
        vdd = factor * supply
        measurement = _measure(
            run_dir / f"supply_{round(factor * 100)}",
            bench(clock, vdd, NOMINAL_CM * vdd, (SMALL_V, LARGE_V), 2),
            noise=False,
        )
        delay = delays(measurement)
        supply_points[factor] = (
            float(delay.delay_s[0, 0]),
            float(delay.delay_s[0, -1]),
            float(analyze_comp_power([measurement]).energy_per_decision_j[0]),
        )

    fit = scurves[NOMINAL_CM]

    def valid(result) -> bool:
        return result.validity == "valid"

    details = [
        Detail(
            name="metastability",
            title="Delay over the input (nominal common mode)",
            x_label="Differential input (V)",
            y_label="Clock-to-decision delay (s)",
            x=list(METASTABILITY_V),
            series={"delay": list(metastability_delays(meta_delay))},
            x_log=True,
        ),
        Detail(
            name="noise_cm",
            title="Input-referred noise over the common mode",
            x_label="Input common mode (V)",
            y_label="Input-referred noise (V)",
            x=[fraction * supply for fraction in CM_SWEEP],
            series={"noise": [r.noise_sigma_v if valid(r) else math.nan for r in scurves.values()]},
        ),
        Detail(
            name="offset_cm",
            title="Offset over the common mode (no mismatch: systematic)",
            x_label="Input common mode (V)",
            y_label="Offset (V)",
            x=[fraction * supply for fraction in CM_SWEEP],
            series={"offset": [r.offset_v if valid(r) else math.nan for r in scurves.values()]},
        ),
        *(
            Detail(
                name=f"delay_supply_{label}",
                title=f"Delay at {text} over the supply",
                x_label="Supply over nominal",
                y_label="Clock-to-decision delay (s)",
                x=list(SUPPLY_SWEEP),
                series={"delay": [point[column] for point in supply_points.values()]},
            )
            for column, label, text in ((0, "0p5mv", "0.5 mV"), (1, "100mv", "100 mV"))
        ),
        Detail(
            name="energy_supply",
            title="Energy per decision over the supply",
            x_label="Supply over nominal",
            y_label="Energy per decision (J)",
            x=list(SUPPLY_SWEEP),
            series={"energy": [point[2] for point in supply_points.values()]},
        ),
        Detail(
            name="scurve",
            title="Decision probability (nominal common mode, transient noise)",
            x_label="Differential input (V)",
            y_label="P(high) of the resolved decisions",
            x=list(SCURVE_V),
            series={"P(high)": probability},
        ),
    ]
    if np.any(unresolved):
        details.append(
            Detail(
                name="scurve_unresolved",
                title="Unresolved decisions (nominal common mode, transient noise)",
                x_label="Differential input (V)",
                y_label="Fraction unresolved",
                x=list(SCURVE_V),
                series={"unresolved": undecided},
            )
        )
    return Record(
        metrics={
            "delay_0p5mv_s": delay_small,
            "delay_100mv_s": delay_large,
            # metastability: the slowest measured decision (0.1 mV) and the latch's regeneration time
            # constant, the delay's growth per e-fold fall of the input between the two smallest
            "delay_0p1mv_s": float(metastability_delays(meta_delay)[0]),
            "regeneration_tau_s": regeneration_tau(meta_delay),
            "energy_0p5mv_j": energy_small,
            "energy_100mv_j": energy_large,
            "noise_v": fit.noise_sigma_v if valid(fit) else math.nan,
            "offset_v": fit.offset_v if valid(fit) else math.nan,
            "noise_max_v": max((r.noise_sigma_v for r in scurves.values() if valid(r)), default=math.nan),
            # NaN where a supply's decision did not resolve
            "delay_max_supply_s": float(np.max([point[0] for point in supply_points.values()])),
            "evaluation_time_s": clock[1],  # its reset a sixth of it
            # of the nominal S-curve's decisions
            "unresolved_fraction": float(np.mean(unresolved)),
        },
        details=details,
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, comp: CompParams) -> Path:
    """The all-transistor netlist with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``), as ``flow.comp.layout`` lays out a comparator without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(
        CompParams(**{**comp.__dict__, "output_stage": OutputStage.TRANSISTORS}), out_dir / "comp_transistors.sp", logic
    )
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "comp.sp")


def layout_floorplan(out_dir: Path, pdk: str, comp: CompParams) -> tuple[Path, Path] | None:
    """The hand-written floorplan of the characterization's topology of the instance's structure
    (``design/layout/comp_<topology>.json``) with the netlist it places, the standard-cell output
    stage's (``flow.comp.layout``); None where it has none."""

    from flow.sweep.runner import hand_floorplan

    cases = {name: comparator(structure) for name, structure in sim.TOPOLOGIES.items()}
    floorplan = hand_floorplan("comp", comp, cases)
    if floorplan is None:
        return None
    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    stdcells = CompParams(**{**comp.__dict__, "output_stage": OutputStage.STDCELLS})
    return write_netlist(stdcells, out_dir / f"{floorplan.stem}.sp", logic), floorplan
