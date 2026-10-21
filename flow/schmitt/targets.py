"""The Schmitt trigger's targets (``python -m flow schmitt.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurements
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.schmitt.analysis import MeasSchmitt, analyze_schmitt_delay, analyze_schmitt_trip
from flow.schmitt.plots import plot_schmitt_supply, plot_schmitt_transfer
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every Schmitt trigger's triangle over the supply and its step, in every PDK."""
    return sim.schmitt_characterization(new_run("sim", "schmitt", "characterization"))


def layout_inv() -> Path:
    """The inverting Schmitt trigger, in every PDK with every tool."""
    return layout.schmitt_inv_all_pdks(new_run("layout", "schmitt", "inv"))


def layout_inv_wide() -> Path:
    """The inverting Schmitt trigger with stronger feedback, in every PDK with every tool."""
    return layout.schmitt_inv_wide_all_pdks(new_run("layout", "schmitt", "inv_wide"))


def layout_buffer() -> Path:
    """The non-inverting Schmitt buffer, in every PDK with every tool."""
    return layout.schmitt_buffer_all_pdks(new_run("layout", "schmitt", "buffer"))


def layout_all() -> Path:
    """Every Schmitt trigger layout above, each in every PDK."""
    return layout.all_schmitt_layouts(new_run("layout", "schmitt", "all"))


def sweep() -> None:
    """The Schmitt trigger's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["schmitt"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["schmitt"], 28)
    sweep_runner.table(["schmitt"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named Schmitt triggers' trip points over the supply and their step delays, in every PDK."""
    output_dir = new_run("analysis", "schmitt")

    meas_read_dir = BASE_PATH / "build/sim/schmitt/schmitt_characterization/20261019_020145"
    cases = (
        ("inv", "inv: inverting"),
        ("inv_wide", "inv_wide: stronger feedback"),
        ("buffer", "buffer: non-inverting"),
    )
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            for sweep in ("supply", "step"):
                sweeps[name, sweep] = read_measurements(meas_read_dir, f"{pdk}/{name}/{sweep}/*/result.h5", MeasSchmitt)
        trips = [analyze_schmitt_trip(sweeps[name, "supply"]) for name, _label in cases]
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_schmitt_transfer(
                trips,
                [analyze_schmitt_delay(sweeps[name, "step"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "schmitt_transfer",
            ),
            *plot_schmitt_supply(trips, labels=labels, output_path=pdk_dir / "schmitt_supply"),
        ]
    return tuple(artifacts)
