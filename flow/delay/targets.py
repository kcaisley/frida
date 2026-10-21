"""The delay lines' and rings' targets (``python -m flow delay.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurement
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.delay.analysis import MeasDelay, analyze_delay_oscillation, analyze_delay_propagation
from flow.delay.plots import (
    plot_delay_line_control,
    plot_delay_line_supply,
    plot_delay_ring_control,
    plot_delay_ring_supply,
)
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every delay line and ring at every supply and control point, in every PDK."""
    return sim.delay_characterization(new_run("sim", "delay", "characterization"))


def layout_ring5() -> Path:
    """Five-stage inverter ring, from the hand-written floorplan, in every PDK."""
    return layout.delay_ring5_all_pdks(new_run("layout", "delay", "ring5"))


def layout_ring5_starved() -> Path:
    """Five-stage current-starved ring, from the hand-written floorplan, in every PDK."""
    return layout.delay_ring5_starved_all_pdks(new_run("layout", "delay", "ring5_starved"))


def layout_ring4_coupled() -> Path:
    """Four-stage coupled ring with injection, from the hand-written floorplan, in every PDK."""
    return layout.delay_ring4_coupled_all_pdks(new_run("layout", "delay", "ring4_coupled"))


def layout_ring4_tail() -> Path:
    """Four-stage coupled ring on a shared tail, from the hand-written floorplan, in every PDK."""
    return layout.delay_ring4_tail_all_pdks(new_run("layout", "delay", "ring4_tail"))


def layout_chain4() -> Path:
    """Four-stage inverter delay line, from the hand-written floorplan, in every PDK."""
    return layout.delay_chain4_all_pdks(new_run("layout", "delay", "chain4"))


def layout_chain2_coupled() -> Path:
    """Two-stage coupled differential buffer, from the hand-written floorplan, in every PDK."""
    return layout.delay_chain2_coupled_all_pdks(new_run("layout", "delay", "chain2_coupled"))


def layout_chain4_starved() -> Path:
    """Four-stage current-starved delay line, from the hand-written floorplan, in every PDK."""
    return layout.delay_chain4_starved_all_pdks(new_run("layout", "delay", "chain4_starved"))


def layout_all() -> Path:
    """Every delay line and ring layout above, each in every PDK."""
    return layout.all_delay_layouts(new_run("layout", "delay", "all"))


def sweep() -> None:
    """The delay line and ring sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["delay"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["delay"], 28)
    sweep_runner.table(["delay"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named rings' frequency and energy, and the delay lines' delay, over supply and control, in every PDK."""
    output_dir = new_run("analysis", "delay")

    meas_read_dir = BASE_PATH / "build/sim/delay/delay_characterization/20261017_203820"
    rings = (
        ("ring5", "ring5: inverter"),
        ("ring5_starved", "ring5_starved: current starved"),
        ("ring4_coupled", "ring4_coupled: coupled pseudo-differential"),
        ("ring4_tail", "ring4_tail: coupled on a shared tail"),
    )
    lines = (
        ("chain4", "chain4: inverter"),
        ("chain2_coupled", "chain2_coupled: coupled differential"),
        ("chain4_starved", "chain4_starved: current starved"),
    )
    ring_labels = [label for _name, label in rings]
    line_labels = [label for _name, label in lines]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in (*rings, *lines):
            for sweep, key in (
                ("supply", lambda item: float(item.param.vdd)),
                ("control", lambda item: float(item.param.control_v)),
            ):
                measurements = []
                for path in sorted(meas_read_dir.glob(f"{pdk}/{name}/{sweep}/*/result.h5")):
                    measurement = read_measurement(path)
                    if not isinstance(measurement, MeasDelay):
                        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasDelay")
                    measurements.append(measurement)
                sweeps[name, sweep] = sorted(measurements, key=key)
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_delay_ring_supply(
                [analyze_delay_oscillation(sweeps[name, "supply"]) for name, _label in rings],
                labels=ring_labels,
                output_path=pdk_dir / "delay_ring_supply",
            ),
            *plot_delay_ring_control(
                [analyze_delay_oscillation(sweeps[name, "control"]) for name, _label in rings],
                labels=ring_labels,
                output_path=pdk_dir / "delay_ring_control",
            ),
            *plot_delay_line_supply(
                [analyze_delay_propagation(sweeps[name, "supply"]) for name, _label in lines],
                labels=line_labels,
                output_path=pdk_dir / "delay_line_supply",
            ),
            *plot_delay_line_control(
                [analyze_delay_propagation(sweeps[name, "control"]) for name, _label in lines],
                labels=line_labels,
                output_path=pdk_dir / "delay_line_control",
            ),
        ]
    return tuple(artifacts)
