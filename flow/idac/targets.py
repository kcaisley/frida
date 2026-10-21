"""The current sources' targets (``python -m flow idac.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurement
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.idac.analysis import MeasIdac, analyze_idac_output, analyze_idac_steering
from flow.idac.plots import plot_idac_bias, plot_idac_iv, plot_idac_steering
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every unit's output over its reference current and enable state, in every PDK."""
    return sim.idac_characterization(new_run("sim", "idac", "characterization"))


def layout_nmos_switched() -> Path:
    """Two switched NMOS units, from the hand-written floorplan, in every PDK."""
    return layout.idac_nmos_switched_all_pdks(new_run("layout", "idac", "nmos_switched"))


def layout_pmos_steer_cas() -> Path:
    """Cascoded steered PMOS unit, from the hand-written floorplan, in every PDK."""
    return layout.idac_pmos_steer_cas_all_pdks(new_run("layout", "idac", "pmos_steer_cas"))


def layout_nmos_steer() -> Path:
    """Four steered NMOS units, from the hand-written floorplan, in every PDK."""
    return layout.idac_nmos_steer_all_pdks(new_run("layout", "idac", "nmos_steer"))


def layout_pmos_mirror() -> Path:
    """PMOS bias mirror, from the hand-written floorplan, in every PDK."""
    return layout.idac_pmos_mirror_all_pdks(new_run("layout", "idac", "pmos_mirror"))


def layout_all() -> Path:
    """Every current source layout above, each in every PDK."""
    return layout.all_idac_layouts(new_run("layout", "idac", "all"))


def sweep() -> None:
    """The current source sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["idac"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["idac"], 28)
    sweep_runner.table(["idac"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named current source units' output characteristic, reference range, and switching, in every PDK."""
    output_dir = new_run("analysis", "idac")

    meas_read_dir = BASE_PATH / "build/sim/idac/idac_characterization/20261017_202758"
    cases = (
        ("nmos_switched", "nmos_switched: 2 NMOS units, switched"),
        ("pmos_steer_cas", "pmos_steer_cas: PMOS cascode, steered"),
        ("nmos_steer", "nmos_steer: 4 NMOS units, steered"),
        ("pmos_mirror", "pmos_mirror: PMOS mirror, cascode"),
    )
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            for state in ("on", "off"):
                measurements = []
                for path in sorted(meas_read_dir.glob(f"{pdk}/{name}/{state}/*/result.h5")):
                    measurement = read_measurement(path)
                    if not isinstance(measurement, MeasIdac):
                        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasIdac")
                    measurements.append(measurement)
                sweeps[name, state] = sorted(measurements, key=lambda item: float(item.param.iref))
        outputs = [analyze_idac_output(sweeps[name, "on"]) for name, _label in cases]
        switched = [
            (name, label, output) for (name, label), output in zip(cases, outputs, strict=True) if sweeps[name, "off"]
        ]
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_idac_iv(
                [
                    analyze_idac_output([item for item in sweeps[name, "on"] if item.info.readbacks["nominal"]])
                    for name, _label in cases
                ],
                labels=labels,
                output_path=pdk_dir / "idac_iv",
            ),
            *plot_idac_bias(outputs, labels=labels, output_path=pdk_dir / "idac_bias"),
            *plot_idac_steering(
                [analyze_idac_steering(sweeps[name, "off"], on=output) for name, _label, output in switched],
                labels=[label for _name, label, _output in switched],
                output_path=pdk_dir / "idac_steering",
            ),
        ]
    return tuple(artifacts)
