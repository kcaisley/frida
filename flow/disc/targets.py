"""The discriminators' targets (``python -m flow disc.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurements
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.disc.analysis import MeasDisc, analyze_disc_delay, analyze_disc_trip
from flow.disc.plots import plot_disc_delay, plot_disc_transfer
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every discriminator's response to a triangle and to steps, in every PDK."""
    return sim.disc_characterization(new_run("sim", "disc", "characterization"))


def layout_nmos() -> Path:
    """NMOS input pair, current-mirror load, from the hand-written floorplan, in every PDK."""
    return layout.disc_nmos_all_pdks(new_run("layout", "disc", "nmos"))


def layout_nmos_hyst() -> Path:
    """NMOS input pair, hysteresis, from the hand-written floorplan, in every PDK."""
    return layout.disc_nmos_hyst_all_pdks(new_run("layout", "disc", "nmos_hyst"))


def layout_pmos() -> Path:
    """PMOS input pair, current-mirror load, from the hand-written floorplan, in every PDK."""
    return layout.disc_pmos_all_pdks(new_run("layout", "disc", "pmos"))


def layout_pmos_hyst() -> Path:
    """PMOS input pair, hysteresis, from the hand-written floorplan, in every PDK."""
    return layout.disc_pmos_hyst_all_pdks(new_run("layout", "disc", "pmos_hyst"))


def layout_all() -> Path:
    """Every discriminator layout above, each in every PDK."""
    return layout.all_disc_layouts(new_run("layout", "disc", "all"))


def sweep() -> None:
    """The discriminator sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["disc"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["disc"], 28)
    sweep_runner.table(["disc"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named discriminators' trip points on a slow triangle and their delay over the overdrive, in every PDK."""
    output_dir = new_run("analysis", "disc")

    meas_read_dir = BASE_PATH / "build/sim/disc/disc_characterization/20261019_012953"
    cases = (
        ("nmos", "nmos: NMOS pair, mirror load"),
        ("nmos_hyst", "nmos_hyst: NMOS pair, hysteresis"),
        ("pmos", "pmos: PMOS pair, mirror load"),
        ("pmos_hyst", "pmos_hyst: PMOS pair, hysteresis"),
    )
    artifacts = []
    for pdk in PDKS:
        # a case missing its triangle or its steps loses that panel, not the study
        trips, trip_labels, delays, delay_labels = [], [], [], []
        for name, label in cases:
            ramp = read_measurements(meas_read_dir, f"{pdk}/{name}/ramp/result.h5", MeasDisc)
            steps = read_measurements(meas_read_dir, f"{pdk}/{name}/od*/result.h5", MeasDisc)
            if ramp:
                trips.append(analyze_disc_trip(ramp))
                trip_labels.append(label)
            if steps:
                delays.append(analyze_disc_delay(steps))
                delay_labels.append(label)
        pdk_dir = output_dir / pdk
        if trips:
            artifacts += plot_disc_transfer(trips, labels=trip_labels, output_path=pdk_dir / "disc_transfer")
        if delays:
            artifacts += plot_disc_delay(delays, labels=delay_labels, output_path=pdk_dir / "disc_delay")
    return tuple(artifacts)
