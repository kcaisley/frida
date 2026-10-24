"""The clock generator's design space (``flow.sweep``): the characterization's three clock functions
at their delay chain's length and output drive, in every PDK.

The functions are built of the PDK's library cells, so their sizing is the delay chain (1 to 8
inverter pairs: the non-overlap gap, the pulse's width) and the output inverter's drive (1, 4 or
8). A function takes only the sizes that change it: the non-overlapping clocks have no output
inverter, the clock gate no delay chain.

Each instance at the core supply and a 1 ns clock: clk-to-outp delay, outp's high width, the gaps
between the outputs, outp's pulses before the enable, the energy per cycle; over the supply (90
to 120 % of its own) the same; over the clock period (2 ns to 100 ps) the duty, the share of
periods that pulse and the energy, and the highest frequency that pulses every period. Eleven
Spectre runs, under a minute.
"""

from __future__ import annotations

import importlib
import math
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.pipeline import Plot, Record

from .sim import ClkgenTbParams, _run_clkgen_sim, clkgen_signal_names
from .subckt import CASES, Clkgen, ClkgenParams, Function, is_valid_clkgen_params

GENERATOR = Clkgen
# the characterization's functions (flow.clkgen.subckt.CASES), each with its own delay chain
STRUCTURE = ("function",)
FUNCTIONS = [{"function": case.function, "delay": case.delay} for case in CASES.values()]
# the delay chain from one to eight inverter pairs (output drive 4), and the output drive 1 or 8
# at the function's own chain
SIZES = [{"delay": delay} for delay in (1, 2, 3, 4, 6, 8)] + [{"drive": 1}, {"drive": 8}]
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
NOMINAL_PERIOD_S = 1e-9
PERIOD_SWEEP_S = (2e-9, 1e-9, 700e-12, 500e-12, 300e-12, 200e-12, 150e-12, 100e-12)


def instances(pdk: str) -> list[ClkgenParams]:
    """Every function at every chain and drive it has (the non-overlapping clocks no output
    inverter, the gate no delay chain), in every PDK."""
    clkgens = (
        ClkgenParams(**{**function, **sizes})
        for function in FUNCTIONS
        for sizes in SIZES
        if not (function["function"] == Function.NONOVERLAP and "drive" in sizes)
        and not (function["function"] == Function.GATE and sizes.get("delay", 1) != 1)
    )
    return [clkgen for clkgen in clkgens if is_valid_clkgen_params(clkgen)]


def _measure(run_dir: Path, tb: ClkgenTbParams):
    """One Spectre run of the clock testbench, as a measurement."""

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave
    from flow.clkgen.analysis import MeasClkgen

    raw = _run_clkgen_sim(run_dir, tb)
    interval = tb.waveform_sample_interval_s
    wave, points = read_transient_wave(raw, clkgen_signal_names(), interval, supply_rails=("vdd",))
    measurement = MeasClkgen(
        group=None,
        index=None,
        dut=tb.clkgen,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
            instruments={"simulator": "Spectre"},
            readbacks={
                "pdk": tb.pdk,
                "raw_points": points,
                "waveform_sample_interval_s": interval,
                "supply_current_convention": "positive_current_draw",
            },
        ),
        param=tb,
        trial_index=np.arange(1, dtype=np.int64),
        wave=wave,
    )
    raw.unlink()  # the measurement keeps the waveforms
    return measurement


def characterize(run_dir: Path, pdk: str, clkgen: ClkgenParams) -> Record:
    from flow.analysis.io import write_measurement
    from flow.clkgen.analysis import analyze_clkgen_timing

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)

    def bench(vdd: float, period: float) -> ClkgenTbParams:
        return ClkgenTbParams(
            pdk=pdk, clkgen=clkgen, vdd=round(vdd, 4), period_s=period, transition_time_s=min(30e-12, period / 8)
        )

    supplies = [
        _measure(run_dir / f"supply_{round(factor * 100)}", bench(factor * supply, NOMINAL_PERIOD_S))
        for factor in SUPPLY_SWEEP
    ]
    nominal = supplies[SUPPLY_SWEEP.index(1.0)]
    periods = [
        nominal
        if period == NOMINAL_PERIOD_S
        else _measure(run_dir / f"period_{round(period * 1e12)}ps", bench(supply, period))
        for period in PERIOD_SWEEP_S
    ]
    waves = {}
    for name, folder, measurement in (
        ("nominal", "supply_100", nominal),
        (f"{PERIOD_SWEEP_S[-1] * 1e12:g} ps clock", f"period_{round(PERIOD_SWEEP_S[-1] * 1e12)}ps", periods[-1]),
    ):
        path = run_dir / folder / "result.h5"
        write_measurement(path, measurement)
        waves[name] = str(path.relative_to(Path(__file__).resolve().parents[2]))

    over_supply = analyze_clkgen_timing(supplies)
    over_period = analyze_clkgen_timing(periods)
    at = SUPPLY_SWEEP.index(1.0)
    frequency = 1 / over_period.period_s
    pulsing = frequency[over_period.pulse_fraction == 1.0]

    return Record(
        metrics={
            "delay_s": float(over_supply.delay_s[at]),
            "high_width_s": float(over_supply.high_width_s[at]),
            "rise_gap_s": float(over_supply.rise_gap_s[at]),
            "fall_gap_s": float(over_supply.fall_gap_s[at]),
            "pulses_before_enable": float(over_supply.pulses_before_enable[at]),
            "energy_per_cycle_j": float(over_supply.energy_per_cycle_j[at]),
            "fmax_hz": float(np.max(pulsing)) if len(pulsing) else math.nan,
            "delay_max_supply_s": float(np.nanmax(over_supply.delay_s)),
        },
        details=[
            Plot(
                name="timing_supply",
                title="Delay, outp's width and the output gaps over the supply (1 ns clock)",
                x_label="Supply over nominal",
                y_label="Time (s)",
                x=list(SUPPLY_SWEEP),
                series={
                    "clk to outp": list(over_supply.delay_s),
                    "outp high": list(over_supply.high_width_s),
                    "outp to outn": list(over_supply.rise_gap_s),
                    "outn to outp": list(over_supply.fall_gap_s),
                },
            ),
            Plot(
                name="energy_supply",
                title="Energy per cycle over the supply (1 ns clock)",
                x_label="Supply over nominal",
                y_label="Energy per cycle (J)",
                x=list(SUPPLY_SWEEP),
                series={"energy": list(over_supply.energy_per_cycle_j)},
            ),
            Plot(
                name="pulsing_frequency",
                title="outp's duty and the periods pulsing over the clock frequency",
                x_label="Clock frequency (Hz)",
                y_label="Share",
                x=list(frequency),
                series={"outp duty": list(over_period.duty_cycle), "periods pulsing": list(over_period.pulse_fraction)},
                x_log=True,
            ),
            Plot(
                name="timing_frequency",
                title="Delay and outp's width over the clock frequency",
                x_label="Clock frequency (Hz)",
                y_label="Time (s)",
                x=list(frequency),
                series={"clk to outp": list(over_period.delay_s), "outp high": list(over_period.high_width_s)},
                x_log=True,
            ),
            Plot(
                name="energy_frequency",
                title="Energy per cycle over the clock frequency",
                x_label="Clock frequency (Hz)",
                y_label="Energy per cycle (J)",
                x=list(frequency),
                series={"energy": list(over_period.energy_per_cycle_j)},
                x_log=True,
            ),
        ],
        waves=waves,
    )
