"""The OTA's targets (``python -m flow ota.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurements
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.ota.analysis import (
    MeasOta,
    MeasOtaTran,
    analyze_ota_ac,
    analyze_ota_distortion,
    analyze_ota_noise,
    analyze_ota_slew,
)
from flow.ota.plots import (
    plot_ota_bode,
    plot_ota_common_mode,
    plot_ota_distortion,
    plot_ota_noise,
    plot_ota_rejection,
    plot_ota_slew,
    plot_ota_supply,
)
from flow.sweep import runner as sweep_runner

from . import layout, sim


def characterization() -> Path:
    """Every OTA's AC, noise, step and sine over common mode and supply, in every PDK."""
    return sim.ota_characterization(new_run("sim", "ota", "characterization"))


def layout_five_t() -> Path:
    """The five-transistor OTA with NMOS input, in every PDK with every tool."""
    return layout.ota_five_t_all_pdks(new_run("layout", "ota", "five_t"))


def layout_five_t_pmos() -> Path:
    """The five-transistor OTA with PMOS input, in every PDK with every tool."""
    return layout.ota_five_t_pmos_all_pdks(new_run("layout", "ota", "five_t_pmos"))


def layout_telescopic() -> Path:
    """The telescopic cascode OTA, in every PDK with every tool."""
    return layout.ota_telescopic_all_pdks(new_run("layout", "ota", "telescopic"))


def layout_folded() -> Path:
    """The folded cascode OTA, in every PDK with every tool."""
    return layout.ota_folded_all_pdks(new_run("layout", "ota", "folded"))


def layout_self_biased() -> Path:
    """The self-biased complementary OTA, in every PDK with every tool."""
    return layout.ota_self_biased_all_pdks(new_run("layout", "ota", "self_biased"))


def layout_two_stage() -> Path:
    """The two-stage OTA, in every PDK with every tool."""
    return layout.ota_two_stage_all_pdks(new_run("layout", "ota", "two_stage"))


def layout_all() -> Path:
    """Every OTA layout above, each in every PDK."""
    return layout.all_ota_layouts(new_run("layout", "ota", "all"))


def sweep() -> None:
    """The OTA's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["ota"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["ota"], 28)
    sweep_runner.table(["ota"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare the named OTAs' open-loop response, rejection, input common-mode range, noise, and supply scaling, and the single-ended ones' unity-gain step and distortion, in every PDK."""
    output_dir = new_run("analysis", "ota")

    meas_read_dir = BASE_PATH / "build/sim/ota/ota_characterization/20261019_014526"
    cases = (
        ("five_t", "five_t: NMOS input"),
        ("five_t_pmos", "five_t_pmos: PMOS input"),
        ("self_biased", "self_biased: complementary"),
        ("telescopic", "telescopic: cascode"),
        ("folded", "folded: folded cascode"),
        ("two_stage", "two_stage: telescopic, CS"),
    )
    labels = [label for _name, label in cases]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in cases:
            for sweep, key in (
                ("vcm", lambda item: float(item.param.vcm)),
                ("supply", lambda item: float(item.param.vdd)),
            ):
                sweeps[name, sweep] = read_measurements(
                    meas_read_dir, f"{pdk}/{name}/{sweep}/*/result.h5", MeasOta, key=key
                )
        common_modes = [analyze_ota_ac(sweeps[name, "vcm"]) for name, _label in cases]
        nominals = [
            analyze_ota_ac([item for item in sweeps[name, "vcm"] if item.info.readbacks["nominal"]])
            for name, _label in cases
        ]
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_ota_bode(nominals, labels=labels, output_path=pdk_dir / "ota_bode"),
            *plot_ota_rejection(nominals, labels=labels, output_path=pdk_dir / "ota_rejection"),
            *plot_ota_common_mode(common_modes, labels=labels, output_path=pdk_dir / "ota_common_mode"),
            *plot_ota_noise(
                [
                    analyze_ota_noise(sweeps[name, "vcm"], ac=ac)
                    for (name, _label), ac in zip(cases, common_modes, strict=True)
                ],
                labels=labels,
                output_path=pdk_dir / "ota_noise",
            ),
            *plot_ota_supply(
                [analyze_ota_ac(sweeps[name, "supply"]) for name, _label in cases],
                labels=labels,
                output_path=pdk_dir / "ota_supply",
            ),
        ]
        # the unity-gain benches, which only the single-ended amplifiers have
        unity = {}
        for name, label in cases:
            for bench in ("step", "sine"):
                for measurement in read_measurements(meas_read_dir, f"{pdk}/{name}/{bench}/*/result.h5", MeasOtaTran):
                    unity[name, bench] = (measurement, label)
        steps = [unity[name, "step"] for name, _label in cases if (name, "step") in unity]
        sines = [unity[name, "sine"] for name, _label in cases if (name, "sine") in unity]
        artifacts += [
            *plot_ota_slew(
                [measurement for measurement, _label in steps],
                [analyze_ota_slew([measurement]) for measurement, _label in steps],
                labels=[label for _measurement, label in steps],
                output_path=pdk_dir / "ota_slew",
            ),
            *plot_ota_distortion(
                [analyze_ota_distortion([measurement]) for measurement, _label in sines],
                labels=[label for _measurement, label in sines],
                output_path=pdk_dir / "ota_distortion",
            ),
        ]
    return tuple(artifacts)
