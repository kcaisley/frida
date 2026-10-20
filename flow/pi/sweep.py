"""The phase interpolators' design space (``flow.sweep``): the characterization's four
interpolators at seven sizings (a CML interpolator has no output inverter to size: six), in
every PDK.

Each instance at the nominal point (a 400 ps period, phase B a quarter period behind A, its own
core supply): the output's delay and phase behind A, swing, duty cycle, supply current and
energy per period. A CML tail unit's current scales with its width (10 uA at the generator's
default). Over the phase spacing (0 to 180 degrees) the output phase and the linearity fit up to
quadrature (slope against B's weight share, intrinsic delay, INL); over the period (1 ns to
100 ps) the output phase and swing; over the supply (90 to 120 % of its own) the delay and swing.
Twenty-three Spectre runs, about a minute in all.
"""

from __future__ import annotations

import importlib
import math
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.sweep import Detail, Record

from .sim import (
    NOMINAL_PERIOD_S,
    NOMINAL_SPACING_DEG,
    PERIOD_SWEEP_S,
    SPACING_SWEEP_DEG,
    PiTbParams,
    _run_pi_sim,
    pi_signal_names,
)
from .subckt import CASES, Pi, PiParams, Style, is_valid_pi_params, write_netlist

GENERATOR = Pi
TOPOLOGIES = {
    name: {"style": case.style, "weight_a": case.weight_a, "weight_b": case.weight_b} for name, case in CASES.items()
}
# the key devices' widths scaled together (x0.5 to x4), the slices (CML: the input pairs and
# loads) or the output inverter alone doubled, and every device at twice its length
DEFAULT = PiParams()
WIDTHS = ("n_w", "p_w", "out_n_w", "out_p_w", "tail_w")
SIZINGS = {
    "x0.5": {name: getattr(DEFAULT, name) // 2 for name in WIDTHS},
    "x1": {},
    "x2": {name: 2 * getattr(DEFAULT, name) for name in WIDTHS},
    "x4": {name: 4 * getattr(DEFAULT, name) for name in WIDTHS},
    "slice_x2": {"n_w": 2 * DEFAULT.n_w, "p_w": 2 * DEFAULT.p_w},
    "out_x2": {"out_n_w": 2 * DEFAULT.out_n_w, "out_p_w": 2 * DEFAULT.out_p_w},
    "long": {"l": 2 * DEFAULT.l, "tail_l": 2 * DEFAULT.tail_l},
}
NOMINAL_UNIT_CURRENT_A = PiTbParams().unit_current_a
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)


def params(pdk: str, topology: str, sizing: str) -> PiParams | None:
    pi = PiParams(**TOPOLOGIES[topology], **SIZINGS[sizing])
    if pi.style == Style.CML and sizing == "out_x2":
        return None  # a CML interpolator has no output inverter: the same as x1
    return pi if is_valid_pi_params(pi) else None


def _measure(run_dir: Path, tb: PiTbParams):
    """One Spectre transient of the interpolator testbench, as a measurement."""

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave

    from .analysis import MeasPi

    raw = _run_pi_sim(run_dir, tb)
    wave, points = read_transient_wave(raw, pi_signal_names(), tb.waveform_sample_interval_s, supply_rails=("vdd",))
    info = MeasInfo(
        backend="spice",
        timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
        instruments={"simulator": "Spectre"},
        readbacks={"raw_points": points, "supply_current_convention": "positive_current_draw"},
    )
    raw.unlink()  # the measurement keeps the waveforms
    return MeasPi(
        group=None, index=None, dut=tb.pi, info=info, param=tb, trial_index=np.arange(1, dtype=np.int64), wave=wave
    )


def characterize(run_dir: Path, pdk: str, pi: PiParams) -> Record:
    from flow.analysis.io import write_measurement

    from .analysis import analyze_pi_linearity, analyze_pi_phase

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    unit = NOMINAL_UNIT_CURRENT_A * pi.tail_w / DEFAULT.tail_w

    def point(folder: str, vdd: float, period: float, spacing: float):
        # the CML phases across the supply's top third; the edges a quarter period, as an
        # interpolator's slewed inputs
        tb = PiTbParams(
            pdk=pdk,
            pi=pi,
            vdd=round(vdd, 4),
            cml_low=round(2 * vdd / 3, 4),
            unit_current_a=unit,
            period_s=period,
            spacing_deg=spacing,
            transition_time_s=period / 4,
        )
        return _measure(run_dir / folder, tb)

    spacings = {
        spacing: point(f"spacing_{round(spacing)}deg", supply, NOMINAL_PERIOD_S, spacing)
        for spacing in SPACING_SWEEP_DEG
    }
    nominal = spacings[NOMINAL_SPACING_DEG]
    periods = {
        period: nominal
        if period == NOMINAL_PERIOD_S
        else point(f"period_{round(period * 1e12)}ps", supply, period, NOMINAL_SPACING_DEG)
        for period in PERIOD_SWEEP_S
    }
    supplies = {
        factor: nominal
        if factor == 1.0
        else point(f"supply_{round(factor * 100)}", factor * supply, NOMINAL_PERIOD_S, NOMINAL_SPACING_DEG)
        for factor in SUPPLY_SWEEP
    }
    waves = {}
    for label, folder, measurement in (
        ("90 degrees, 400 ps", "spacing_90deg", nominal),
        ("90 degrees, 100 ps", "period_100ps", periods[100e-12]),
    ):
        path = run_dir / folder / "result.h5"
        write_measurement(path, measurement)
        waves[label] = str(path.relative_to(Path(__file__).resolve().parents[2]))
    over_spacing = analyze_pi_phase(list(spacings.values()))
    over_period = analyze_pi_phase(list(periods.values()))
    over_supply = analyze_pi_phase(list(supplies.values()))
    at = analyze_pi_phase([nominal])
    try:
        linearity = analyze_pi_linearity(list(spacings.values()), phase=over_spacing)
        slope, intrinsic, inl = linearity.slope, linearity.intrinsic_delay_s, linearity.inl_deg
        inl_max = linearity.max_inl_deg
    except ValueError:  # fewer than three spacings up to quadrature where the output crossed
        slope, intrinsic, inl_max = math.nan, math.nan, math.nan
        inl = np.full(len(SPACING_SWEEP_DEG), math.nan)
    ideal = pi.weight_b / (pi.weight_a + pi.weight_b)
    crossing = np.isfinite(over_period.delay_s)
    frequency = list(1 / over_period.period_s)
    spacing = list(over_spacing.spacing_deg)
    fitted = over_spacing.spacing_deg <= 90.0  # beyond quadrature an interpolator follows one phase

    return Record(
        metrics={
            "delay_s": float(at.delay_s[0]),
            "phase_deg": float(at.output_phase_deg[0]),
            "swing_v": float(at.swing_v[0]),
            "duty_cycle": float(at.duty_cycle[0]),
            "supply_current_a": float(at.supply_current_a[0]),
            "energy_per_cycle_j": float(at.supply_current_a[0]) * supply * NOMINAL_PERIOD_S,
            "slope": slope,
            "slope_error": slope / ideal - 1,
            "delay_intrinsic_s": intrinsic,
            "inl_max_deg": inl_max,
            "fmax_hz": float(np.max(1 / over_period.period_s[crossing])) if crossing.any() else math.nan,
            "delay_max_supply_s": float(np.nanmax(over_supply.delay_s))
            if np.isfinite(over_supply.delay_s).any()
            else math.nan,
        },
        details=[
            Detail(
                name="transfer",
                title="Output phase over the phase spacing (400 ps period)",
                x_label="Phase B behind A (deg)",
                y_label="Output phase behind A (deg)",
                x=spacing,
                series={
                    "output": list(over_spacing.output_phase_deg),
                    # B's weight share of the spacing, through the fit's intrinsic delay
                    "ideal": [360 * intrinsic / NOMINAL_PERIOD_S + ideal * value for value in spacing],
                },
            ),
            Detail(
                name="inl",
                title="Deviation from the linear fit up to quadrature",
                x_label="Phase B behind A (deg)",
                y_label="INL (deg)",
                x=list(over_spacing.spacing_deg[fitted]),
                series={"INL": list(inl[fitted])},
            ),
            Detail(
                name="phase_frequency",
                title="Output phase over the frequency (quadrature)",
                x_label="Phase frequency (Hz)",
                y_label="Output phase behind A (deg)",
                x=frequency,
                series={"output": list(over_period.output_phase_deg)},
                x_log=True,
            ),
            Detail(
                name="swing_frequency",
                title="Swing over the frequency (quadrature)",
                x_label="Phase frequency (Hz)",
                y_label="Swing, half the differential peak-to-peak (V)",
                x=frequency,
                series={"swing": list(over_period.swing_v)},
                x_log=True,
            ),
            Detail(
                name="delay_supply",
                title="Delay over the supply",
                x_label="Supply over nominal",
                y_label="Delay behind A (s)",
                x=list(SUPPLY_SWEEP),
                series={"delay": list(over_supply.delay_s)},
            ),
            Detail(
                name="swing_supply",
                title="Swing over the supply",
                x_label="Supply over nominal",
                y_label="Swing, half the differential peak-to-peak (V)",
                x=list(SUPPLY_SWEEP),
                series={"swing": list(over_supply.swing_v)},
            ),
        ],
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, pi: PiParams) -> Path:
    """The transistor netlist with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``), for ALIGN to lay out without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(pi, out_dir / "pi_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "pi.sp")
