"""The ring amplifier's targets (``python -m flow ringamp.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurement
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.ringamp.analysis import MeasRingamp, analyze_ringamp_settling, analyze_ringamp_transfer
from flow.ringamp.plots import plot_ringamp_deadzone, plot_ringamp_step, plot_ringamp_transfer, plot_ringamp_waveforms
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Both ring amplifiers open and closed loop over dead-zone bias and step, in every PDK."""
    return sim.ringamp_characterization(new_run("sim", "ringamp", "characterization"))


def layout_se() -> Path:
    """The single-ended ring amplifier, in every PDK with every tool."""
    return layout.ringamp_se_all_pdks(new_run("layout", "ringamp", "se"))


def layout_se_strong() -> Path:
    """The ring amplifier with the stronger output stage, in every PDK with every tool."""
    return layout.ringamp_se_strong_all_pdks(new_run("layout", "ringamp", "se_strong"))


def layout_all() -> Path:
    """Every ring amplifier layout above, each in every PDK."""
    return layout.all_ringamp_layouts(new_run("layout", "ringamp", "all"))


def sweep() -> None:
    """The ring amplifier's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["ringamp"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["ringamp"], 28)
    sweep_runner.table(["ringamp"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named ring amplifiers' open-loop transfer and closed-loop settling over dead zone and step, in every PDK."""
    output_dir = new_run("analysis", "ringamp")

    meas_read_dir = BASE_PATH / "build/sim/ringamp/ringamp_characterization/20261017_203658"
    cases = (("se", "se: single-ended"), ("se_strong", "se_strong: twice the output stage"))
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            for sweep, key in (
                ("open", lambda item: float(item.param.biasn)),
                ("deadzone", lambda item: float(item.param.biasn)),
                ("step", lambda item: float(item.param.step_v)),
            ):
                measurements = []
                for path in sorted(meas_read_dir.glob(f"{pdk}/{name}/{sweep}/*/result.h5")):
                    measurement = read_measurement(path)
                    if not isinstance(measurement, MeasRingamp):
                        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasRingamp")
                    measurements.append(measurement)
                sweeps[name, sweep] = sorted(measurements, key=key)
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_ringamp_transfer(
                [analyze_ringamp_transfer(sweeps[name, "open"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "ringamp_transfer",
            ),
            *plot_ringamp_deadzone(
                [analyze_ringamp_settling(sweeps[name, "deadzone"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "ringamp_deadzone",
            ),
            *plot_ringamp_step(
                [analyze_ringamp_settling(sweeps[name, "step"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "ringamp_step",
            ),
            *plot_ringamp_waveforms(
                [sweeps[name, "step"] for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "ringamp_waveforms",
            ),
        ]
    return tuple(artifacts)
