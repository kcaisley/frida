"""The charge-sensitive amplifiers' targets (``python -m flow csa.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurements
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.csa.analysis import MeasCsa, MeasCsaNoise, analyze_csa_noise, analyze_csa_pulse
from flow.csa.plots import plot_csa_charge, plot_csa_noise, plot_csa_pulse
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every amplifier's charge response and output noise, in every PDK."""
    return sim.csa_characterization(new_run("sim", "csa", "characterization"))


def layout_krum() -> Path:
    """NMOS input, Krummenacher feedback, from the hand-written floorplan, in every PDK."""
    return layout.csa_krum_all_pdks(new_run("layout", "csa", "krum"))


def layout_krum_pmos() -> Path:
    """PMOS input, Krummenacher feedback, from the hand-written floorplan, in every PDK."""
    return layout.csa_krum_pmos_all_pdks(new_run("layout", "csa", "krum_pmos"))


def layout_continuous() -> Path:
    """NMOS input, continuous feedback, from the hand-written floorplan, in every PDK."""
    return layout.csa_continuous_all_pdks(new_run("layout", "csa", "continuous"))


def layout_reset() -> Path:
    """NMOS input, reset feedback, from the hand-written floorplan, in every PDK."""
    return layout.csa_reset_all_pdks(new_run("layout", "csa", "reset"))


def layout_all() -> Path:
    """Every charge-sensitive amplifier layout above, each in every PDK."""
    return layout.all_csa_layouts(new_run("layout", "csa", "all"))


def sweep() -> None:
    """The charge-sensitive amplifier sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["csa"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["csa"], 28)
    sweep_runner.table(["csa"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named charge-sensitive amplifiers' responses to injected charge and their noise, in every PDK."""
    output_dir = new_run("analysis", "csa")

    meas_read_dir = BASE_PATH / "build/sim/csa/csa_characterization/20261019_011909"
    cases = (
        ("krum", "krum: NMOS input, Krummenacher"),
        ("krum_pmos", "krum_pmos: PMOS input, Krummenacher"),
        ("continuous", "continuous: NMOS input, long device"),
        ("reset", "reset: NMOS input, reset switch"),
    )
    artifacts = []
    for pdk in PDKS:
        pulses, noises, noise_labels = [], [], []
        for name, label in cases:
            pulses.append(analyze_csa_pulse(read_measurements(meas_read_dir, f"{pdk}/{name}/q*/result.h5", MeasCsa)))
            # the reset amplifier, open at rest, has no noise bench
            noise = read_measurements(meas_read_dir, f"{pdk}/{name}/noise/result.h5", MeasCsaNoise)
            if noise:
                noises.append(analyze_csa_noise(noise, pulse=pulses[-1]))
                noise_labels.append(label)
        labels = [label for _name, label in cases]
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_csa_pulse(pulses, labels=labels, output_path=pdk_dir / "csa_pulse"),
            *plot_csa_charge(pulses, labels=labels, output_path=pdk_dir / "csa_charge"),
            *plot_csa_noise(noises, labels=noise_labels, output_path=pdk_dir / "csa_noise"),
        ]
    return tuple(artifacts)
