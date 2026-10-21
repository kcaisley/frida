"""The MOSFET's targets (``python -m flow mosfet.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.io import read_measurement
from flow.analysis.studies import BASE_PATH
from flow.comp.layout import PDKS
from flow.mosfet.analysis import (
    MeasMosfetMismatch,
    MeasMosfetNoise,
    MeasMosfetOutput,
    MeasMosfetTranNoise,
    MeasMosfetTransfer,
    analyze_mosfet_mismatch,
    analyze_mosfet_noise,
    analyze_mosfet_output,
    analyze_mosfet_trannoise,
    analyze_mosfet_transfer,
)
from flow.mosfet.plots import (
    plot_mosfet_gm_id,
    plot_mosfet_mismatch,
    plot_mosfet_noise,
    plot_mosfet_output,
    plot_mosfet_simulators,
    plot_mosfet_trannoise,
    plot_mosfet_transfer,
)
from flow.sweep import runner as sweep_runner

from . import sim


def characterization() -> Path:
    """Every core device of every PDK at each length, in Spectre and, where the decks allow, ngspice."""
    return sim.mosfet_characterization(new_run("sim", "mosfet", "characterization"))


def sweep() -> None:
    """The MOSFET's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["mosfet"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["mosfet"], 28)
    sweep_runner.table(["mosfet"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def characterization_study() -> tuple[Path, ...]:
    """Compare every PDK's core MOSFETs over their lengths: Id-Vgs, gm/Id, Id-Vds, noise, transient
    noise and mismatch, in Spectre; and Spectre against ngspice where both run, per PDK."""
    output_dir = new_run("analysis", "mosfet")

    meas_read_dir = BASE_PATH / "build/sim/mosfet/mosfet_characterization/20261020_132427"
    kinds = {
        "transfer": MeasMosfetTransfer,
        "output": MeasMosfetOutput,
        "noise": MeasMosfetNoise,
        "trannoise": MeasMosfetTranNoise,
        "mismatch": MeasMosfetMismatch,
    }
    artifacts = []
    for pdk in PDKS:
        # simulator -> device -> its lengths, shortest first: each a kind -> measurement
        devices: dict[str, dict[str, list[dict]]] = {}
        for simulator in ("spectre", "ngspice"):
            runs = []
            for case in sorted((meas_read_dir / pdk / simulator).glob("*/")):
                run = {kind: read_measurement(case / f"{kind}.h5") for kind in kinds if (case / f"{kind}.h5").is_file()}
                for kind, measurement in run.items():
                    if not isinstance(measurement, kinds[kind]):
                        raise TypeError(
                            f"{case / kind} contains {type(measurement).__name__}, expected {kinds[kind].__name__}"
                        )
                runs.append(run)
            for run in sorted(runs, key=lambda run: run["transfer"].dut.l):
                devices.setdefault(simulator, {}).setdefault(run["transfer"].info.readbacks["device"], []).append(run)
        spectre = devices.get("spectre", {})
        if not spectre:
            continue
        labels = list(spectre)
        transfers = [[analyze_mosfet_transfer(run["transfer"]) for run in spectre[d]] for d in labels]
        noises = [[analyze_mosfet_noise(run["noise"]) for run in spectre[d]] for d in labels]
        # the output family and transient noise at the second length (twice the minimum)
        middle = [spectre[d][min(1, len(spectre[d]) - 1)] for d in labels]
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_mosfet_transfer(transfers, labels=labels, output_path=pdk_dir / "mosfet_transfer"),
            *plot_mosfet_gm_id(transfers, labels=labels, output_path=pdk_dir / "mosfet_gm_id"),
            *plot_mosfet_output(
                [analyze_mosfet_output(run["output"]) for run in middle],
                labels=labels,
                output_path=pdk_dir / "mosfet_output",
            ),
            *plot_mosfet_noise(
                noises,
                lengths_m=[[item.l_m for item in lengths] for lengths in transfers],
                labels=labels,
                output_path=pdk_dir / "mosfet_noise",
            ),
            *plot_mosfet_trannoise(
                [analyze_mosfet_trannoise(run["trannoise"]) for run in middle],
                noises=[analyze_mosfet_noise(run["noise"]) for run in middle],
                labels=labels,
                output_path=pdk_dir / "mosfet_trannoise",
            ),
        ]
        # a Monte Carlo where the PDK's decks hold mismatch statistics
        if all("mismatch" in run for d in labels for run in spectre[d]):
            mismatches = [
                [
                    analyze_mosfet_mismatch(run["mismatch"], transfer=transfer)
                    for run, transfer in zip(spectre[d], lengths, strict=True)
                ]
                for d, lengths in zip(labels, transfers, strict=True)
            ]
            artifacts += plot_mosfet_mismatch(
                mismatches, transfers=transfers, labels=labels, output_path=pdk_dir / "mosfet_mismatch"
            )
        ngspice = devices.get("ngspice", {})
        both = [d for d in labels if d in ngspice]
        if both:
            pairs = [(spectre[d][min(1, len(spectre[d]) - 1)], ngspice[d][min(1, len(ngspice[d]) - 1)]) for d in both]
            artifacts += plot_mosfet_simulators(
                [analyze_mosfet_transfer(s["transfer"]) for s, _n in pairs],
                ngspice=[analyze_mosfet_transfer(n["transfer"]) for _s, n in pairs],
                noise_spectre=[analyze_mosfet_noise(s["noise"]) for s, _n in pairs],
                noise_ngspice=[analyze_mosfet_noise(n["noise"]) for _s, n in pairs],
                labels=both,
                output_path=pdk_dir / "mosfet_simulators",
            )
    return tuple(artifacts)
