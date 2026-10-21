"""The followers' targets (``python -m flow follower.<target>``)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from flow import new_run
from flow.analysis.io import read_measurements
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.follower.analysis import (
    MeasFollower,
    MeasFollowerStep,
    analyze_follower_impedance,
    analyze_follower_slew,
    analyze_follower_transfer,
)
from flow.follower.plots import (
    plot_follower_bandwidth,
    plot_follower_psrr,
    plot_follower_response,
    plot_follower_slew,
    plot_follower_transfer,
)
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every follower's transfer, input and output AC and step, in every PDK."""
    return sim.follower_characterization(new_run("sim", "follower", "characterization"))


def layout_source() -> Path:
    """NMOS source follower, from the hand-written floorplan, in every PDK."""
    return layout.follower_source_all_pdks(new_run("layout", "follower", "source"))


def layout_source_pmos() -> Path:
    """PMOS source follower, from the hand-written floorplan, in every PDK."""
    return layout.follower_source_pmos_all_pdks(new_run("layout", "follower", "source_pmos"))


def layout_flipped() -> Path:
    """NMOS flipped voltage follower, from the hand-written floorplan, in every PDK."""
    return layout.follower_flipped_all_pdks(new_run("layout", "follower", "flipped"))


def layout_flipped_pmos() -> Path:
    """PMOS flipped voltage follower with an output sink, from the hand-written floorplan, in every PDK."""
    return layout.follower_flipped_pmos_all_pdks(new_run("layout", "follower", "flipped_pmos"))


def layout_all() -> Path:
    """Every follower layout above, each in every PDK."""
    return layout.all_follower_layouts(new_run("layout", "follower", "all"))


def sweep() -> None:
    """The follower sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["follower"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["follower"], 28)
    sweep_runner.table(["follower"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named followers' transfer, bandwidth, output impedance and PSRR over the input level, and their step response, in every PDK."""
    output_dir = new_run("analysis", "follower")

    meas_read_dir = BASE_PATH / "build/sim/follower/follower_characterization/20261019_003545"
    cases = (
        ("source", "source: NMOS"),
        ("source_pmos", "source_pmos: PMOS"),
        ("flipped", "flipped: NMOS flipped"),
        ("flipped_pmos", "flipped_pmos: PMOS flipped, sink"),
    )
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps, steps = {}, {}
        for name, _label in cases:
            for stimulus in ("input", "output"):
                sweeps[name, stimulus] = read_measurements(
                    meas_read_dir,
                    f"{pdk}/{name}/{stimulus}/*/result.h5",
                    MeasFollower,
                    key=lambda item: float(item.param.vin),
                )
            steps[name] = read_measurements(meas_read_dir, f"{pdk}/{name}/step/*/result.h5", MeasFollowerStep)
        transfers = [analyze_follower_transfer(sweeps[name, "input"]) for name, _label in cases]
        impedances = [analyze_follower_impedance(sweeps[name, "output"]) for name, _label in cases]
        # each case's frequency response where it follows best (its input of highest gain): a fixed
        # fraction of the supply leaves some PDK's flipped followers outside their range
        best_vin = [float(transfer.vin_v[np.argmax(transfer.gain_v_per_v)]) for transfer in transfers]
        nominal = {
            stimulus: [
                [item for item in sweeps[name, stimulus] if float(item.param.vin) == vin]
                for (name, _label), vin in zip(cases, best_vin, strict=True)
            ]
            for stimulus in ("input", "output")
        }
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_follower_transfer(transfers, labels=labels, output_path=pdk_dir / "follower_transfer"),
            *plot_follower_bandwidth(transfers, impedances, labels=labels, output_path=pdk_dir / "follower_bandwidth"),
            *plot_follower_response(
                [analyze_follower_transfer(items) for items in nominal["input"]],
                [analyze_follower_impedance(items) for items in nominal["output"]],
                labels=labels,
                output_path=pdk_dir / "follower_response",
            ),
            *plot_follower_psrr(transfers, labels=labels, output_path=pdk_dir / "follower_psrr"),
            *plot_follower_slew(
                [steps[name][0] for name, _label in cases],
                [analyze_follower_slew(steps[name]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "follower_slew",
            ),
        ]
    return tuple(artifacts)
