"""The clock generators' targets (``python -m flow clkgen.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurement
from flow.analysis.studies import BASE_PATH
from flow.clkgen.analysis import MeasClkgen, analyze_clkgen_timing
from flow.clkgen.plots import plot_clkgen_frequency, plot_clkgen_supply, plot_clkgen_waveforms
from flow.comp.layout import PDKS
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every clock function over the supply and the period, in every PDK."""
    return sim.clkgen_characterization(new_run("sim", "clkgen", "characterization"))


def layout_nonoverlap() -> Path:
    """Non-overlapping clocks, from the hand-written floorplan, in every PDK."""
    return layout.clkgen_nonoverlap_all_pdks(new_run("layout", "clkgen", "nonoverlap"))


def layout_pulse() -> Path:
    """Rising-edge pulse, from the hand-written floorplan, in every PDK."""
    return layout.clkgen_pulse_all_pdks(new_run("layout", "clkgen", "pulse"))


def layout_gate() -> Path:
    """Clock gate, from the hand-written floorplan, in every PDK."""
    return layout.clkgen_gate_all_pdks(new_run("layout", "clkgen", "gate"))


def layout_all() -> Path:
    """Every clock generator layout above, each in every PDK."""
    return layout.all_clkgen_layouts(new_run("layout", "clkgen", "all"))


def sweep() -> None:
    """The clock generator sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["clkgen"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["clkgen"], 28)
    sweep_runner.table(["clkgen"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named clock functions' timing over supply and frequency, and their start through the enable, in every PDK."""
    output_dir = new_run("analysis", "clkgen")

    meas_read_dir = BASE_PATH / "build/sim/clkgen/clkgen_characterization/20261017_203403"
    cases = (
        ("nonoverlap", "nonoverlap: two-phase"),
        ("pulse", "pulse: rising-edge pulse"),
        ("gate", "gate: glitch-free gate"),
    )
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            for sweep, key in (
                ("supply", lambda item: float(item.param.vdd)),
                ("period", lambda item: -float(item.param.period_s)),
            ):
                measurements = []
                for path in sorted(meas_read_dir.glob(f"{pdk}/{name}/{sweep}/*/result.h5")):
                    measurement = read_measurement(path)
                    if not isinstance(measurement, MeasClkgen):
                        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasClkgen")
                    measurements.append(measurement)
                sweeps[name, sweep] = sorted(measurements, key=key)
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_clkgen_supply(
                [analyze_clkgen_timing(sweeps[name, "supply"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "clkgen_supply",
            ),
            *plot_clkgen_frequency(
                [analyze_clkgen_timing(sweeps[name, "period"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "clkgen_frequency",
            ),
            *plot_clkgen_waveforms(
                [
                    next(item for item in sweeps[name, "supply"] if item.info.readbacks["nominal"])
                    for name, _label in cases
                ],
                labels=labels,
                output_path=pdk_dir / "clkgen_waveforms",
            ),
        ]
    return tuple(artifacts)
