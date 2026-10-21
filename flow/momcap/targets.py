"""The FMOM capacitor's targets (``python -m flow momcap.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import (
    read_measurement,
    write_analysis,
)
from flow.analysis.studies import BASE_PATH
from flow.momcap.analysis import MeasMomcap, analyze_momcap_fit
from flow.momcap.plots import plot_momcap_fit, plot_momcap_scaling, plot_momcap_spacing

from . import pex


def characterization() -> Path:
    """Every FMOM style at one to three metals over length and spacing, extracted in 3D in every PDK."""
    return pex.momcap_characterization(new_run("pex", "momcap", "characterization"))


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Fit every FMOM unit family's capacitance against its plate length and spacing, in every PDK
    (3D extraction: Calibre xACT, Quantus in LF150), and compare the fits across the PDKs; writes
    every fit as a result."""
    output_dir = new_run("analysis", "momcap")

    meas_read_dir = BASE_PATH / "build/pex/momcap/momcap_characterization/20261018_acc1"
    families = [(style, layers) for style in ("difference", "ring", "strip") for layers in (1, 2, 3)]
    artifacts = []
    fits, labels = [], []
    for pdk in ("tsmc28", "tsmc65", "tpsc65", "ihp130", "lf150", "tower180"):
        pdk_fits = []
        for style, layers in families:
            measurements = []
            for path in sorted(meas_read_dir.glob(f"{pdk}/{style}_{layers}l/*/*/result.h5")):
                measurement = read_measurement(path)
                if not isinstance(measurement, MeasMomcap):
                    raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasMomcap")
                measurements.append(measurement)
            fit = analyze_momcap_fit(measurements)
            artifacts.append(write_analysis(output_dir / pdk / f"momcap_fit_{style}_{layers}l.h5", fit))
            pdk_fits.append(fit)
        fits += pdk_fits
        labels += [pdk] * len(pdk_fits)
        artifacts += plot_momcap_fit(
            pdk_fits,
            title=f"FMOM capacitance against plate length in {pdk}",
            output_path=output_dir / pdk / "momcap_fit",
        )
        artifacts += plot_momcap_spacing(
            pdk_fits,
            title=f"FMOM capacitance per length against plate spacing in {pdk}",
            output_path=output_dir / pdk / "momcap_spacing",
        )
    artifacts += plot_momcap_scaling(fits, labels=labels, output_path=output_dir / "momcap_scaling")
    return tuple(artifacts)
