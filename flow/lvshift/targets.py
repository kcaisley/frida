"""The level shifter's targets (``python -m flow lvshift.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurement
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.lvshift.analysis import MeasLvShift, analyze_lvshift_switching
from flow.lvshift.plots import plot_lvshift_vdd, plot_lvshift_vddl, plot_lvshift_waveforms
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every level shifter over the input and the output supply, in every PDK."""
    return sim.lvshift_characterization(new_run("sim", "lvshift", "characterization"))


def layout_core() -> Path:
    """The cross-coupled level shifter core, in every PDK with every tool."""
    return layout.lvshift_core_all_pdks(new_run("layout", "lvshift", "core"))


def layout_single_rst() -> Path:
    """The level shifter with an input inverter and reset, in every PDK with every tool."""
    return layout.lvshift_single_rst_all_pdks(new_run("layout", "lvshift", "single_rst"))


def layout_buffered() -> Path:
    """The level shifter with input and output inverters, in every PDK with every tool."""
    return layout.lvshift_buffered_all_pdks(new_run("layout", "lvshift", "buffered"))


def layout_all() -> Path:
    """Every level shifter layout above, each in every PDK."""
    return layout.all_lvshift_layouts(new_run("layout", "lvshift", "all"))


def sweep() -> None:
    """The level shifter's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["lvshift"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["lvshift"], 28)
    sweep_runner.table(["lvshift"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named level shifters over the input and output supplies, in every PDK."""
    output_dir = new_run("analysis", "lvshift")

    meas_read_dir = BASE_PATH / "build/sim/lvshift/lvshift_characterization/20261017_204643"
    cases = (
        ("core", "core: differential input"),
        ("single_rst", "single_rst: inverter, reset"),
        ("buffered", "buffered: in and out inverters"),
    )
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            for sweep, key in (
                ("vddl", lambda item: float(item.param.vddl)),
                ("vdd", lambda item: float(item.param.vdd)),
            ):
                measurements = []
                for path in sorted(meas_read_dir.glob(f"{pdk}/{name}/{sweep}/*/result.h5")):
                    measurement = read_measurement(path)
                    if not isinstance(measurement, MeasLvShift):
                        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasLvShift")
                    measurements.append(measurement)
                sweeps[name, sweep] = sorted(measurements, key=key)
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_lvshift_vddl(
                [analyze_lvshift_switching(sweeps[name, "vddl"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "lvshift_vddl",
            ),
            *plot_lvshift_vdd(
                [analyze_lvshift_switching(sweeps[name, "vdd"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "lvshift_vdd",
            ),
            *plot_lvshift_waveforms(
                [
                    next(item for item in sweeps[name, "vddl"] if item.info.readbacks["nominal"])
                    for name, _label in cases
                ],
                labels=labels,
                output_path=pdk_dir / "lvshift_waveforms",
            ),
        ]
    return tuple(artifacts)
