"""The phase interpolator's targets (``python -m flow pi.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurement
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.pi.analysis import MeasPi, analyze_pi_linearity, analyze_pi_phase
from flow.pi.plots import plot_pi_frequency, plot_pi_transfer, plot_pi_waveforms
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every phase interpolator over the phase spacing and the period, in every PDK."""
    return sim.pi_characterization(new_run("sim", "pi", "characterization"))


def layout_cmos_half() -> Path:
    """The CMOS interpolator at equal weights, in every PDK with every tool."""
    return layout.pi_cmos_half_all_pdks(new_run("layout", "pi", "cmos_half"))


def layout_cmos_quarter() -> Path:
    """The CMOS interpolator at three-to-one weights, in every PDK with every tool."""
    return layout.pi_cmos_quarter_all_pdks(new_run("layout", "pi", "cmos_quarter"))


def layout_cml_half() -> Path:
    """The CML interpolator at equal tails, in every PDK with every tool."""
    return layout.pi_cml_half_all_pdks(new_run("layout", "pi", "cml_half"))


def layout_cml_quarter() -> Path:
    """The CML interpolator at three-to-one tails, in every PDK with every tool."""
    return layout.pi_cml_quarter_all_pdks(new_run("layout", "pi", "cml_quarter"))


def layout_all() -> Path:
    """Every phase interpolator layout above, each in every PDK."""
    return layout.all_pi_layouts(new_run("layout", "pi", "all"))


def sweep() -> None:
    """The phase interpolator's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["pi"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["pi"], 28)
    sweep_runner.table(["pi"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named phase interpolators' transfer, linearity, and frequency response, in every PDK."""
    output_dir = new_run("analysis", "pi")

    meas_read_dir = BASE_PATH / "build/sim/pi/pi_characterization/20261017_203146"
    cases = (
        ("cmos_half", "cmos_half: CMOS, 2 and 2 slices"),
        ("cmos_quarter", "cmos_quarter: CMOS, 3 and 1 slices"),
        ("cml_half", "cml_half: CML, 2 and 2 tails"),
        ("cml_quarter", "cml_quarter: CML, 3 and 1 tails"),
    )
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            for sweep, key in (
                ("spacing", lambda item: float(item.param.spacing_deg)),
                ("period", lambda item: -float(item.param.period_s)),
            ):
                measurements = []
                for path in sorted(meas_read_dir.glob(f"{pdk}/{name}/{sweep}/*/result.h5")):
                    measurement = read_measurement(path)
                    if not isinstance(measurement, MeasPi):
                        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasPi")
                    measurements.append(measurement)
                sweeps[name, sweep] = sorted(measurements, key=key)
        phases = [analyze_pi_phase(sweeps[name, "spacing"]) for name, _label in cases]
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_pi_transfer(
                phases,
                [
                    analyze_pi_linearity(sweeps[name, "spacing"], phase=phase)
                    for (name, _label), phase in zip(cases, phases, strict=True)
                ],
                labels=labels,
                output_path=pdk_dir / "pi_transfer",
            ),
            *plot_pi_frequency(
                [analyze_pi_phase(sweeps[name, "period"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "pi_frequency",
            ),
            *plot_pi_waveforms(
                [
                    next(item for item in sweeps[name, "spacing"] if item.info.readbacks["nominal"])
                    for name, _label in cases
                ],
                labels=labels,
                output_path=pdk_dir / "pi_waveforms",
            ),
        ]
    return tuple(artifacts)
