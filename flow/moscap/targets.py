"""The MOS capacitor's targets (``python -m flow moscap.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurement
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.moscap.analysis import MeasMosCap, analyze_moscap_cv
from flow.moscap.plots import plot_moscap_cv, plot_moscap_frequency, plot_moscap_quality
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every MOS capacitor's C-V over its bias, in every PDK."""
    return sim.moscap_characterization(new_run("sim", "moscap", "characterization"))


def layout_decap_n() -> Path:
    """The two-unit NMOS decap, in every PDK with every tool."""
    return layout.moscap_decap_n_all_pdks(new_run("layout", "moscap", "decap_n"))


def layout_decap_np() -> Path:
    """The complementary (NMOS and PMOS) decap, in every PDK with every tool."""
    return layout.moscap_decap_np_all_pdks(new_run("layout", "moscap", "decap_np"))


def layout_cap_n() -> Path:
    """The two-net NMOS capacitor, in every PDK with every tool."""
    return layout.moscap_cap_n_all_pdks(new_run("layout", "moscap", "cap_n"))


def layout_cap_p() -> Path:
    """The two-net PMOS capacitor, in every PDK with every tool."""
    return layout.moscap_cap_p_all_pdks(new_run("layout", "moscap", "cap_p"))


def layout_all() -> Path:
    """Every MOS capacitor layout above, each in every PDK."""
    return layout.all_moscap_layouts(new_run("layout", "moscap", "all"))


def sweep() -> None:
    """The MOS capacitor's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["moscap"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["moscap"], 28)
    sweep_runner.table(["moscap"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named MOS capacitors' C-V, leakage, and loss over bias and frequency, in every PDK."""
    output_dir = new_run("analysis", "moscap")

    meas_read_dir = BASE_PATH / "build/sim/moscap/moscap_characterization/20261017_202605"
    cases = (
        ("decap_n", "decap_n: NMOS decap"),
        ("decap_np", "decap_np: NMOS and PMOS decap"),
        ("cap_n", "cap_n: NMOS two-net"),
        ("cap_p", "cap_p: PMOS two-net"),
    )
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            measurements = []
            for path in sorted(meas_read_dir.glob(f"{pdk}/{name}/*/result.h5")):
                measurement = read_measurement(path)
                if not isinstance(measurement, MeasMosCap):
                    raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasMosCap")
                measurements.append(measurement)
            sweeps[name] = sorted(measurements, key=lambda item: int(item.info.readbacks["bias_mv"]))
        cvs = [analyze_moscap_cv(sweeps[name]) for name, _label in cases]
        # each case at its working bias: a decap at the core supply, a capacitor in inversion
        nominal = [
            analyze_moscap_cv([item for item in sweeps[name] if item.info.readbacks["nominal"]])
            for name, _label in cases
        ]
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_moscap_cv(cvs, labels=labels, output_path=pdk_dir / "moscap_cv"),
            *plot_moscap_frequency(nominal, labels=labels, output_path=pdk_dir / "moscap_frequency"),
            *plot_moscap_quality(cvs, labels=labels, output_path=pdk_dir / "moscap_quality"),
        ]
    return tuple(artifacts)
