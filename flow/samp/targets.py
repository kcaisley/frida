"""The sampler's targets (``python -m flow samp.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurement
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.samp.analysis import MeasSamp, analyze_samp_hold, analyze_samp_track
from flow.samp.plots import plot_samp_hold, plot_samp_resistance, plot_samp_supply, plot_samp_waveforms
from flow.sweep import runner as sweep_runner

from . import layout, sim


def frida1_transient() -> Path:
    """Five periods of the fabricated-size FRIDA-1 sampler's transient, in TSMC65."""
    return sim.frida1_transient(new_run("sim", "samp", "frida1_transient"))


def characterization() -> Path:
    """Every switch over its input level and over the supply, in every PDK."""
    return sim.samp_characterization(new_run("sim", "samp", "characterization"))


def layout_frida1() -> Path:
    """The FRIDA-1 transmission gate, in every PDK with every tool."""
    return layout.samp_frida1_all_pdks(new_run("layout", "samp", "frida1"))


def layout_tgate_dummy() -> Path:
    """The transmission gate with charge-injection dummies, in every PDK with every tool."""
    return layout.samp_tgate_dummy_all_pdks(new_run("layout", "samp", "tgate_dummy"))


def layout_bootstrap() -> Path:
    """The bootstrapped NMOS switch, in every PDK with every tool."""
    return layout.samp_bootstrap_all_pdks(new_run("layout", "samp", "bootstrap"))


def layout_nmos() -> Path:
    """The NMOS switch alone, in every PDK with every tool."""
    return layout.samp_nmos_all_pdks(new_run("layout", "samp", "nmos"))


def layout_all() -> Path:
    """Every sampler layout above, each in every PDK."""
    return layout.all_samp_layouts(new_run("layout", "samp", "all"))


def sweep() -> None:
    """The sampler's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["samp"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["samp"], 28)
    sweep_runner.table(["samp"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named sampling switches' resistance, hold effects and supply scaling, in every PDK."""
    output_dir = new_run("analysis", "samp")

    meas_read_dir = BASE_PATH / "build/sim/samp/samp_characterization/20261018_003412"
    cases = (
        ("frida1", "frida1: transmission gate"),
        ("tgate_dummy", "tgate_dummy: with dummies"),
        ("nmos", "nmos: NMOS switch"),
        ("bootstrap", "bootstrap: bootstrapped NMOS"),
    )
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            for sweep, key in (
                ("vin", lambda item: float(item.param.input_voltage)),
                ("supply", lambda item: float(item.param.vdd)),
            ):
                measurements = []
                for path in sorted(meas_read_dir.glob(f"{pdk}/{name}/{sweep}/*/result.h5")):
                    measurement = read_measurement(path)
                    if not isinstance(measurement, MeasSamp):
                        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasSamp")
                    measurements.append(measurement)
                sweeps[name, sweep] = sorted(measurements, key=key)
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_samp_resistance(
                [analyze_samp_track(sweeps[name, "vin"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "samp_resistance",
            ),
            *plot_samp_hold(
                [analyze_samp_hold(sweeps[name, "vin"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "samp_hold",
            ),
            *plot_samp_supply(
                [analyze_samp_track(sweeps[name, "supply"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "samp_supply",
            ),
            *plot_samp_waveforms(
                # each switch at its middle input level
                [sweeps[name, "vin"][len(sweeps[name, "vin"]) // 2] for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "samp_waveforms",
            ),
        ]
    return tuple(artifacts)
