"""The CML gates' targets (``python -m flow cml.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurement
from flow.analysis.studies import BASE_PATH
from flow.cml.analysis import MeasCml, analyze_cml_switching
from flow.cml.plots import plot_cml_frequency, plot_cml_tail, plot_cml_waveforms
from flow.comp.layout import PDKS
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every CML gate over the clock period and the tail current, in every PDK."""
    return sim.cml_characterization(new_run("sim", "cml", "characterization"))


def layout_buffer() -> Path:
    """NMOS-input buffer, from the hand-written floorplan, in every PDK."""
    return layout.cml_buffer_all_pdks(new_run("layout", "cml", "buffer"))


def layout_buffer_pmos() -> Path:
    """PMOS-input buffer, from the hand-written floorplan, in every PDK."""
    return layout.cml_buffer_pmos_all_pdks(new_run("layout", "cml", "buffer_pmos"))


def layout_latch() -> Path:
    """Latch, from the hand-written floorplan, in every PDK."""
    return layout.cml_latch_all_pdks(new_run("layout", "cml", "latch"))


def layout_divider() -> Path:
    """Divide-by-two, from the hand-written floorplan, in every PDK."""
    return layout.cml_divider_all_pdks(new_run("layout", "cml", "divider"))


def layout_xor() -> Path:
    """XOR, from the hand-written floorplan, in every PDK."""
    return layout.cml_xor_all_pdks(new_run("layout", "cml", "xor"))


def layout_all() -> Path:
    """Every CML layout above, each in every PDK."""
    return layout.all_cml_layouts(new_run("layout", "cml", "all"))


def sweep() -> None:
    """The CML sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["cml"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["cml"], 28)
    sweep_runner.table(["cml"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named CML gates' swing, delay and speed over frequency and tail current, in every PDK."""
    output_dir = new_run("analysis", "cml")

    meas_read_dir = BASE_PATH / "build/sim/cml/cml_characterization/20261017_202919"
    cases = (
        ("buffer", "buffer: NMOS input"),
        ("buffer_pmos", "buffer_pmos: PMOS input"),
        ("xor", "xor"),
        ("latch", "latch: triode loads"),
        ("divider", "divider: two latches"),
    )
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            for sweep, key in (
                ("period", lambda item: -float(item.param.clock_period_s)),
                ("tail", lambda item: float(item.param.tail_current_a)),
            ):
                measurements = []
                for path in sorted(meas_read_dir.glob(f"{pdk}/{name}/{sweep}/*/result.h5")):
                    measurement = read_measurement(path)
                    if not isinstance(measurement, MeasCml):
                        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasCml")
                    measurements.append(measurement)
                sweeps[name, sweep] = sorted(measurements, key=key)
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_cml_frequency(
                [analyze_cml_switching(sweeps[name, "period"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "cml_frequency",
            ),
            *plot_cml_tail(
                [analyze_cml_switching(sweeps[name, "tail"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "cml_tail",
            ),
            *plot_cml_waveforms(
                [
                    next(item for item in sweeps[name, "period"] if item.info.readbacks["nominal"])
                    for name, _label in cases
                ],
                labels=labels,
                output_path=pdk_dir / "cml_waveforms",
            ),
        ]
    return tuple(artifacts)
