"""The cascode bias generators' targets (``python -m flow bias.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurements
from flow.analysis.studies import BASE_PATH
from flow.bias.analysis import MeasBias, analyze_bias_mirror
from flow.bias.plots import plot_bias_mirror, plot_bias_reference, plot_bias_supply
from flow.comp.layout import PDKS
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every bias generator over the reference current and the supply, in every PDK."""
    return sim.bias_characterization(new_run("sim", "bias", "characterization"))


def layout_wide() -> Path:
    """Wide-swing cascode gates, from the hand-written floorplan, in every PDK."""
    return layout.bias_wide_all_pdks(new_run("layout", "bias", "wide"))


def layout_margin() -> Path:
    """Margin cascode gates, from the hand-written floorplan, in every PDK."""
    return layout.bias_margin_all_pdks(new_run("layout", "bias", "margin"))


def layout_all() -> Path:
    """Every cascode bias layout above, each in every PDK."""
    return layout.all_bias_layouts(new_run("layout", "bias", "all"))


def sweep() -> None:
    """The cascode bias sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["bias"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["bias"], 28)
    sweep_runner.table(["bias"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named cascode bias generators' test mirrors over the reference current and the supply, in every PDK."""
    output_dir = new_run("analysis", "bias")

    meas_read_dir = BASE_PATH / "build/sim/bias/bias_characterization/20261019_022652"
    cases = (("wide", "wide: a quarter-strength diode"), ("margin", "margin: a sixteenth"))
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            for sweep, key in (
                ("iref", lambda item: float(item.param.iref)),
                ("supply", lambda item: float(item.param.vdd)),
            ):
                sweeps[name, sweep] = read_measurements(
                    meas_read_dir, f"{pdk}/{name}/{sweep}/*/result.h5", MeasBias, key=key
                )
        mirrors = [analyze_bias_mirror(sweeps[name, "iref"]) for name, _label in cases]
        supplies = [analyze_bias_mirror(sweeps[name, "supply"]) for name, _label in cases]
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_bias_mirror(mirrors, labels=labels, output_path=pdk_dir / "bias_mirror"),
            *plot_bias_reference(mirrors, labels=labels, output_path=pdk_dir / "bias_reference"),
            *plot_bias_supply(supplies, labels=labels, output_path=pdk_dir / "bias_supply"),
        ]
    return tuple(artifacts)
