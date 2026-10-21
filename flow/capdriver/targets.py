"""The capacitor driver's targets (``python -m flow capdriver.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurements
from flow.analysis.studies import BASE_PATH
from flow.capdriver.analysis import MeasCapdriver, analyze_capdriver_drive
from flow.capdriver.plots import plot_capdriver_load, plot_capdriver_supply
from flow.comp.layout import PDKS
from flow.sweep import runner as sweep_runner

from . import layout, sim


def _unmade(*parts: str) -> Path:
    """A fresh run directory's path, not made: the driver's layout makes its own (and refuses an existing one)."""
    run_dir = new_run(*parts)
    run_dir.rmdir()
    return run_dir


def characterization() -> Path:
    """Every drive weight over the load and the supply, in every PDK."""
    return sim.capdriver_characterization(new_run("sim", "capdriver", "characterization"))


def layout_frida1() -> Path:
    """FRIDA-1's capacitor driver exported from ``build/frida-1.gds``, then its DRC and LVS."""
    return layout.frida1(_unmade("layout", "capdriver", "frida1"))


def sweep() -> None:
    """The capacitor driver's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["capdriver"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["capdriver"], 28)
    sweep_runner.table(["capdriver"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the capacitor driver's drive bands over the load and the supply, in every PDK."""
    output_dir = new_run("analysis", "capdriver")

    meas_read_dir = BASE_PATH / "build/sim/capdriver/capdriver_characterization/20261019_234512"
    cases = (("x1", "x1: drive band 1"), ("x2", "x2: drive band 2"), ("x4", "x4: drive band 4"))
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            for sweep, key in (
                ("load", lambda item: float(item.param.cload)),
                ("supply", lambda item: float(item.param.vdd)),
            ):
                sweeps[name, sweep] = read_measurements(
                    meas_read_dir, f"{pdk}/{name}/{sweep}/*/result.h5", MeasCapdriver, key=key
                )
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_capdriver_load(
                [analyze_capdriver_drive(sweeps[name, "load"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "capdriver_load",
            ),
            *plot_capdriver_supply(
                [analyze_capdriver_drive(sweeps[name, "supply"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "capdriver_supply",
            ),
        ]
    return tuple(artifacts)
