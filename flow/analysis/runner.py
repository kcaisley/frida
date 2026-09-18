"""Explicit, manually invoked measurement -> analysis -> plot pipelines.

Each function pins its accepted input files or measurement directories. Small
campaigns list every H5 file; large campaigns use a narrow glob within a named
directory. There is intentionally no automatic discovery of the newest run
directory or of analysis pipelines.

Run one named pipeline from the repository root with:

    uv run python -m flow.analysis.runner adc_sample_rate_study

A target name is required. Outputs go to a timestamped directory beneath
``build/analysis/<domain>``. Each runner selects its input directories in source.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import cast

import hdl21 as h
import matplotlib as mpl
import numpy as np

from flow.adc.sequences import SEQUENCES, AdcSequence, symbol256_init8_samp16_comp11110000_logic11000011
from flow.analysis.adc import (
    ADC_RAMP_RESET_EXCLUSION_CONVERSIONS,
    analyze_adc_cdac_settling,
    analyze_adc_code_distribution,
    analyze_adc_decision_paths,
    analyze_adc_dynamic,
    analyze_adc_dynamic_sweep,
    analyze_adc_noise_sweep,
    analyze_adc_nonlinearity,
    analyze_adc_power_sweep,
    analyze_adc_ramp,
    analyze_adc_timing_closure,
    analyze_adc_transfer,
)
from flow.analysis.calibration1 import analyze as analyze_calibration1
from flow.analysis.calibration2 import analyze as analyze_calibration2
from flow.analysis.calibration3 import analyze as analyze_calibration3
from flow.analysis.cdac import analyze_cdac_cap_mismatch_campaign
from flow.analysis.comp import (
    analyze_comp_candidate_sweep,
    analyze_comp_offset_noise,
    classify_comp_common_mode_validity,
)
from flow.analysis.io import read_measurement
from flow.analysis.plots import (
    plot_adc_calibration_weights,
    plot_adc_cdac_settling,
    plot_adc_code_distribution,
    plot_adc_decision_path_density,
    plot_adc_dynamic,
    plot_adc_dynamic_sweep,
    plot_adc_noise_distribution_sweep,
    plot_adc_noise_sweep,
    plot_adc_power_sweep,
    plot_adc_ramp_histogram,
    plot_adc_ramp_nonlinearity,
    plot_adc_ramp_transfer,
    plot_adc_static_nonlinearity,
    plot_adc_transfer,
    plot_cdac_cap_mismatch,
    plot_cdac_cap_mismatch_comparison,
    plot_comp_candidate_sweep,
    plot_comp_common_mode_campaign,
    plot_comp_noise_power_tradeoff,
    plot_comp_sampling_campaign,
    plot_waveforms,
)
from flow.analysis.types import (
    MeasAdcExt,
    MeasAdcInt,
    MeasCdacExt,
    MeasCompExt,
    MeasCompInt,
)
from flow.analysis.waveform import analyze_measurement_waveforms
from flow.scans.params import load_board_map

timing_sequences = tuple(
    sequence for name, sequence in SEQUENCES if name.startswith("symbol256_init8_samp16_comp11110000_")
)

BASE_PATH = Path(__file__).resolve().parents[2]


def adc_transfer_curve_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot known-voltage static transfer curves from MeasAdcExt DC steps.

    Coverage: the archived ADC00 campaign only; its selected directory is
    currently absent locally. Each settled DC step supplies a known voltage,
    including inputs beyond either rail. No voltage reconstruction or fit,
    calibration acquisition, or internal SPICE waveforms are used.
    """
    meas_read_dir = BASE_PATH / "build/scan_adc/20260818_135848"
    paths = sorted(meas_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
    if not paths:
        raise FileNotFoundError(meas_read_dir)
    groups = {}
    for path in paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdcExt):
            raise TypeError(f"expected MeasAdcExt: {path}")
        groups.setdefault(measurement.param.observed_adc, []).append(measurement)
    artifacts = []
    for adc_index, measurements in sorted(groups.items()):
        artifacts.extend(
            plot_adc_transfer(
                measurements,
                analyze_adc_transfer(measurements),
                output_path=output_dir / f"adc{adc_index:02d}_transfer_curve",
            )
        )
    return tuple(artifacts)


def adc_ramp_nonlinearity_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot code density and INL/DNL for the ADC00--ADC03 10-Hz sawtooth.

    Inputs are MeasAdcExt acquisitions, with uniform ramp occupancy assumed.
    Absolute input voltage is unused. Flyback-adjacent conversions and saturated
    endpoint bins are excluded from linearity; the full histogram stays visible.
    No CDAC calibration data or internal SPICE waveforms are required.
    """
    meas_read_dir = BASE_PATH / "build/scan_adc/20260812_011910"
    paths = sorted(meas_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
    if not paths:
        raise FileNotFoundError(meas_read_dir)
    artifacts = []
    for path in paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdcExt):
            raise TypeError(f"expected MeasAdcExt: {path}")
        stem = f"adc{measurement.param.observed_adc:02d}_{path.name.split('_', 1)[0]}"
        artifacts.extend(
            plot_adc_code_distribution(
                (measurement,),
                analyze_adc_code_distribution((measurement,)),
                output_path=output_dir / f"{stem}_code_density",
            )
        )
        artifacts.extend(
            plot_adc_static_nonlinearity(
                measurement,
                analyze_adc_nonlinearity(
                    measurement,
                    method="code_density",
                    ramp_reset_exclusion_conversions=ADC_RAMP_RESET_EXCLUSION_CONVERSIONS,
                ),
                output_path=output_dir / f"{stem}_inl_dnl",
            )
        )
    return tuple(artifacts)


def adc_calibration_study(output_dir: Path) -> tuple[Path, ...]:
    """Compare three calibration methods on the selected ADC00 measurements.

    Coverage: ADC00's known 10-Hz ramp (MeasAdcExt) and three reviewed CDAC
    threshold campaigns (MeasCdacExt). Calibration 1 extracts A-state threshold
    movements; calibrations 2/3 use ramp BOUT fits/prefix thresholds. The ramp
    validates the resulting decoders. No internal SPICE waveforms are needed.
    """

    ramp_meas_read_path = BASE_PATH / (
        "build/scan_adc/20260812_011910/"
        "0000_00_adc00_160mbd_pwl10hz_m1000top1000mv_logicp0sym_"
        "vcm600mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
    )
    measurement = read_measurement(ramp_meas_read_path)
    if not isinstance(measurement, MeasAdcExt):
        raise TypeError(f"{ramp_meas_read_path} contains {type(measurement).__name__}, expected MeasAdcExt")
    adc_index = int(measurement.param.observed_adc)
    board_id = measurement.param.board_id

    cdac_meas_read_dirs = tuple(
        BASE_PATH / "build/scan_cdac" / name for name in ("20260804_171234", "20260804_193030", "20260804_193631")
    )
    cdac_measurement_runs = []
    for meas_read_dir in cdac_meas_read_dirs:
        measurements = []
        for path in sorted(meas_read_dir.glob("*.h5")):
            cdac_measurement = read_measurement(path)
            if not isinstance(cdac_measurement, MeasCdacExt):
                raise TypeError(f"{path} contains {type(cdac_measurement).__name__}, expected MeasCdacExt")
            if cdac_measurement.param.observed_adc == adc_index:
                measurements.append(cdac_measurement)
        cdac_measurement_runs.append(tuple(measurements))

    comparator_calibrations = load_board_map()["boards"][board_id].get("comparator_calibration", {})
    comparator_offset_v = float(comparator_calibrations[adc_index]["offset_v"])
    cdac_groups, _cdac_analyses = analyze_cdac_cap_mismatch_campaign(
        cdac_measurement_runs,
        adc_indices=(adc_index,),
        board_id=board_id,
        comparator_offset_v_by_adc={adc_index: comparator_offset_v},
    )
    cdac_measurements = cdac_groups[0]

    nominal_ramp = analyze_adc_ramp(measurement)
    calibrations = (
        analyze_calibration1(
            cdac_measurements,
            comparator_offset_v=comparator_offset_v,
        ),
        analyze_calibration2(measurement, nominal_ramp),
        analyze_calibration3(measurement, nominal_ramp),
    )
    ramp = analyze_adc_ramp(measurement, calibrations=calibrations)

    artifacts = list(
        plot_adc_calibration_weights(
            calibrations,
            output_path=output_dir / f"adc{adc_index:02d}_calibration_weights",
        )
    )
    artifacts.extend(
        plot_adc_ramp_transfer(
            ramp,
            output_path=output_dir / f"adc{adc_index:02d}_calibration_transfer",
        )
    )
    artifacts.extend(
        plot_adc_ramp_histogram(
            ramp,
            output_path=output_dir / f"adc{adc_index:02d}_calibration_code_density",
        )
    )
    artifacts.extend(
        plot_adc_ramp_nonlinearity(
            ramp,
            output_path=output_dir / f"adc{adc_index:02d}_calibration_inl_dnl",
        )
    )

    calibration_by_method = {calibration.method: calibration for calibration in calibrations}
    metrics_path = output_dir / f"adc{adc_index:02d}_calibration_metrics.csv"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "decoding",
                "training_sample_count",
                "validation_sample_count",
                "weights_from_measurement",
                "output_gain",
                "output_offset_lsb",
                "maximum_abs_dnl_lsb",
                "maximum_abs_inl_lsb",
                "missing_codes",
                "maximum_transfer_reversal_lsb",
            )
        )
        for curve in ramp.curves:
            calibration = calibration_by_method.get(curve.decoding)
            writer.writerow(
                (
                    curve.decoding,
                    0 if calibration is None else calibration.training_sample_count,
                    0 if calibration is None else calibration.validation_sample_count,
                    0 if calibration is None else int(np.count_nonzero(calibration.measured_weight_mask)),
                    1.0 if calibration is None else calibration.output_gain,
                    0.0 if calibration is None else calibration.output_offset_lsb,
                    curve.maximum_abs_dnl,
                    curve.maximum_abs_inl,
                    curve.missing_codes,
                    curve.maximum_transfer_reversal_dout,
                )
            )
    artifacts.append(metrics_path)

    weights_path = output_dir / f"adc{adc_index:02d}_calibration_weights.csv"
    with weights_path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "decision_index",
                "ideal_weight_lsb",
                *(
                    field
                    for calibration in calibrations
                    for field in (
                        f"{calibration.method}_weight_lsb",
                        f"{calibration.method}_from_measurement",
                    )
                ),
            )
        )
        for decision_index in range(17):
            writer.writerow(
                (
                    decision_index,
                    calibrations[0].nominal_weights[decision_index],
                    *(
                        value
                        for calibration in calibrations
                        for value in (
                            calibration.calibrated_weights[decision_index],
                            bool(calibration.measured_weight_mask[decision_index]),
                        )
                    ),
                )
            )
    artifacts.append(weights_path)
    return tuple(artifacts)


def adc_sequence_study(output_dir: Path) -> tuple[Path, ...]:
    """Compare fixed-input sequence captures from measurement and PEX.

    Measurement coverage: ADC03's 56-pattern/control sweep at 10/6 MSPS active
    timing only. The 2-MSPS captures and other ADCs are not yet available for
    this sweep. Older ADC00/01 campaigns belong to the other studies.
    PEX coverage: seven FRIDA-1/2 flavors x four sequences, 50 mV input,
    160/100-ns periods. No slow 2-MSPS SPICE cases are selected.
    Trajectories/histograms use MeasAdcExt or MeasAdcInt DAQ data. Comparator,
    SAR/CDAC timing and clock plots use MeasAdcInt waveform records. Timing
    tables require 200 ps of setup before LOGIC and before the next COMP.
    """
    meas_read_dirs = (BASE_PATH / "build/scan_adc/20260915_111149",)
    sources = {}
    provenance = []
    for session, target, stamp, flavors in (
        (
            "frida-20260906_124441_733878",
            "frida1_fixed_input_noise",
            "20260906_125026",
            tuple(f"frida1_{layers}layer_radix{radix}" for layers in (1, 2) for radix in (17, 20)),
        ),
        (
            "frida-20260906_124442_994752",
            "frida2_fixed_input_noise",
            "20260906_124953",
            tuple(f"frida2_{layers}layer_radix17" for layers in (1, 2, 3)),
        ),
        (
            "frida-20260910_185707_055364",
            "frida1_fixed_input_noise_comp7of8",
            "20260910_185921",
            tuple(f"frida1_{layers}layer_radix{radix}" for layers in (1, 2) for radix in (17, 20)),
        ),
        (
            "frida-20260910_185757_562573",
            "frida2_fixed_input_noise_comp7of8",
            "20260910_190007",
            tuple(f"frida2_{layers}layer_radix17" for layers in (1, 2, 3)),
        ),
    ):
        timings = (
            ("continuous_100ns_comp7of8",)
            if target.endswith("comp7of8")
            else ("original", "extended_comp", "continuous_100ns")
        )
        campaign = BASE_PATH / "build/remote" / session
        for flavor in flavors:
            for timing in timings:
                name = f"{flavor}/{timing}/result.h5"
                path = campaign / "results/sim/adc" / target / stamp / name
                sources[name] = path
    if not sources:
        raise FileNotFoundError("no SPICE measurements in the selected sequence campaign")
    # Prefer the established three-layer reference; a collected single-family
    # campaign uses its first selected flavor for each sequence instead.
    sequence_cases = {}
    for name in sources:
        flavor, timing, _ = name.split("/")
        if timing not in sequence_cases or flavor == "frida2_3layer_radix17":
            sequence_cases[timing] = name
    for name, path in sources.items():
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        provenance.append(
            {"case": name, "source": str(path), "sha256": checksum, "sequence_plot": name in sequence_cases.values()}
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    record = output_dir / "sources.json"
    record.write_text(json.dumps(provenance, indent=2) + "\n")
    artifacts = []

    # Physical campaigns retain their own ADC/input/sequence identities.
    for meas_read_dir in meas_read_dirs:
        paths = sorted(meas_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
        if not paths:
            raise FileNotFoundError(meas_read_dir)
        groups = {}
        for path in paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdcExt):
                raise TypeError(f"expected MeasAdcExt: {path}")
            params = measurement.param.tb
            key = (measurement.param.observed_adc, float(params.vin_diff.dc), float(params.vin_cm.dc))
            groups.setdefault(key, []).append(measurement)
            stem = f"{meas_read_dir.name}_{path.name.split('_', 1)[0]}_adc{measurement.param.observed_adc:02d}"
            artifacts.extend(
                plot_adc_decision_path_density(
                    measurement,
                    analyze_adc_decision_paths(measurement, selection="all"),
                    output_path=output_dir / f"{stem}_trajectory",
                )
            )
            artifacts.extend(
                plot_adc_code_distribution(
                    (measurement,),
                    analyze_adc_code_distribution((measurement,)),
                    output_path=output_dir / f"{stem}_codes",
                )
            )
        for (adc_index, input_v, common_v), measurements in groups.items():
            labels = []
            sequences = []
            for measurement in measurements:
                params = measurement.param.tb
                sequence = AdcSequence.from_tb_params(params)

                # Compare complete rows relative to INIT; leave acquired patterns and data unchanged.
                sequence = sequence.relative_to_init()

                if sequence not in sequences:
                    sequences.append(sequence)
                labels.append(f"Sequence {sequences.index(sequence) + 1}")
            # Limit each overview to seven complete sequences, with all points visible.
            for page in range(0, len(sequences), 7):
                selected = [i for i, label in enumerate(labels) if page < int(label.split()[-1]) <= page + 7]
                group = [measurements[i] for i in selected]
                artifacts.extend(
                    plot_adc_noise_sweep(
                        group,
                        analyze_adc_noise_sweep(group),
                        series_labels=[labels[i] for i in selected],
                        rate_axis="sampling",
                        output_path=output_dir
                        / f"{meas_read_dir.name}_adc{adc_index:02d}_{input_v * 1e3:g}mv_{common_v * 1e3:g}cm_sequences{page // 7 + 1}",
                    )
                )
        del groups, measurements, measurement

    # Load, analyze and plot each case before releasing its waveform records.
    pex_groups = {}
    for index, source in enumerate(provenance, start=1):
        path = Path(cast(str, source["source"]))
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != source["sha256"]:
                raise ValueError(f"HDF5 checksum changed: {path}")
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdcInt):
            raise TypeError(f"expected MeasAdcInt: {path}")
        measurement = dataclasses.replace(
            measurement,
            info=dataclasses.replace(
                measurement.info, readbacks={**measurement.info.readbacks, "source_h5_sha256": source["sha256"]}
            ),
        )
        case = "_".join(Path(cast(str, source["case"])).parts[:-1])

        artifacts.extend(
            plot_adc_decision_path_density(
                measurement,
                analyze_adc_decision_paths(measurement, selection="all"),
                output_path=output_dir / f"spice_{case}_trajectory",
            )
        )
        artifacts.extend(
            plot_adc_cdac_settling(
                measurement,
                analyze_adc_cdac_settling(measurement),
                output_path=output_dir / f"spice_{case}_cdac_settling",
            )
        )
        artifacts.extend(
            plot_adc_code_distribution(
                (measurement,),
                analyze_adc_code_distribution((measurement,)),
                output_path=output_dir / f"spice_{case}_codes",
            )
        )
        timing = analyze_adc_timing_closure(
            measurement,
            required_logic_setup_s=200e-12,
            required_cdac_setup_s=200e-12,
        )
        timing_columns = {field.name: getattr(timing, field.name) for field in dataclasses.fields(timing)}
        timing_columns.update(
            {
                name: getattr(timing, name)
                for name in (
                    "internal_resolution_s",
                    "sr_response_s",
                    "logic_to_cdac_s",
                    "logic_setup_s",
                    "cdac_setup_s",
                    "logic_ready",
                    "cdac_applicable",
                    "cdac_ready",
                    "passed",
                )
            }
        )
        timing_path = output_dir / f"{case}_timing_closure.csv"
        with timing_path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(timing_columns)
            for row in range(len(timing.conversion_index)):
                writer.writerow([value if np.isscalar(value) else value[row] for value in timing_columns.values()])
        artifacts.append(timing_path)

        codes = output_dir / f"{case}_codes.txt"
        codes.write_text(
            "sample B0_to_B16 DOUT_decimal DOUT_12bit\n"
            + "".join(
                f"{index} {''.join(str(int(bit)) for bit in bits)} {int(code)} {int(code):012b}\n"
                for index, (bits, code) in enumerate(zip(measurement.daq.bout, measurement.daq.dout, strict=True))
            )
        )
        artifacts.append(codes)

        # One representative flavor supplies the four sequence clock diagrams.
        if source["sequence_plot"]:
            timing = Path(cast(str, source["case"])).parts[1]
            waveform = analyze_measurement_waveforms(
                measurement,
                record_index=1,
                reference_signal="seq_init",
                threshold_v=0.6,
                signal_names=("seq_init", "seq_samp", "seq_comp", "seq_logic"),
            )
            with mpl.rc_context({"axes.xmargin": 0.0}):
                artifacts.extend(
                    plot_waveforms(
                        dataclasses.replace(
                            waveform, title=timing.replace("_", " "), signal_names=("INIT", "SAMP", "COMP", "LOGIC")
                        ),
                        output_path=output_dir / f"sequence_{timing}",
                    )
                )
            sequence_record = output_dir / f"sequence_{timing}.json"
            sequence_record.write_text(
                json.dumps(
                    {
                        **source,
                        "source_raw": measurement.info.readbacks.get("raw_file"),
                        "time_reference": "second conversion SEQ_INIT rising at 0.6 V",
                        "conversion_index": 1,
                        "time_origin_s": waveform.time_origin_s,
                        "window_s": tuple(float(value) for value in waveform.time_s[[0, -1]]),
                    },
                    indent=2,
                )
                + "\n"
            )
            artifacts.append(sequence_record)
        print(f"Rendered {index}/{len(sources)} cases: {source['case']}", flush=True)
        flavor = Path(cast(str, source["case"])).parts[0]
        pex_groups.setdefault(flavor, []).append((Path(cast(str, source["case"])).parts[1], measurement))
        del measurement

    for flavor, cases in pex_groups.items():
        labels, measurements = zip(*cases, strict=True)
        artifacts.extend(
            plot_adc_noise_sweep(
                measurements,
                analyze_adc_noise_sweep(measurements),
                series_labels=labels,
                rate_axis="sampling",
                output_path=output_dir / f"spice_{flavor}_sequence_noise",
            )
        )
    del pex_groups

    for source in provenance:
        with Path(cast(str, source["source"])).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != source["sha256"]:
                raise RuntimeError(f"source changed during analysis: {source['source']}")

    # Keep every figure as a vector PDF and place exactly one on each slide.
    # Paths are relative so the output directory is a portable TeX source bundle.
    frames = []
    for artifact in artifacts:
        if artifact.suffix != ".pdf" or not artifact.stem.startswith(("spice_", "sequence_")):
            continue
        title = artifact.stem.replace("_", " ")
        for name in sorted(sources, key=len, reverse=True):
            case = "_".join(Path(name).parts[:-1])
            if artifact.stem.startswith(f"spice_{case}_"):
                title = case.replace("frida", "FRIDA-").replace("layer", "L").replace("radix", "R").replace("_", " ")
                break
        frames.append(
            "\\begin{frame}{" + title + "}\n\\centering\n"
            "\\includegraphics[width=\\linewidth,height=0.88\\textheight,keepaspectratio]{"
            + artifact.relative_to(output_dir).as_posix()
            + "}\n\\end{frame}\n"
        )
    tex = output_dir / "frida_2_vs_1.tex"
    tex.write_text(
        "\\documentclass[aspectratio=1610]{beamer}\n"
        "\\usepackage[T1]{fontenc}\n\\usepackage{lmodern}\n\\usepackage{graphicx}\n"
        "\\definecolor{NordBlue}{HTML}{5E81AC}\n"
        "\\setbeamercolor{frametitle}{fg=NordBlue}\n"
        "\\setbeamerfont{frametitle}{size=\\large}\n"
        "\\setbeamertemplate{navigation symbols}{}\n\\setbeamertemplate{footline}{}\n"
        "\\begin{document}\n" + "".join(frames) + "\\end{document}\n"
    )
    with (output_dir / "latexmk.log").open("w") as log:
        subprocess.run(
            ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", tex.name],
            cwd=output_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    return (*artifacts, record, tex, tex.with_suffix(".pdf"))


def adc_sample_rate_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot measured rate dependence for selected historical sequence patterns.

    Coverage: ADC00/01 50/100-mV DC and 10-kHz sine captures at 600-mV common
    mode, plus the control alignment in ADC00's 800-mV timing campaign.
    Only the historical fixed-input sequence is currently accepted; extend the
    explicit selection after validating additional patterns in the sequence study.
    Actual rates are 0.3125--6.25 MSPS (formerly labelled 0.5--10 active MSPS);
    an actual 10-MSPS sweep of accepted new patterns still needs acquisition.
    DC panels show noise-equivalent resolution; sine panels show spectral
    ENOB/SNDR. Inputs are MeasAdcExt; no PEX or internal waveforms are required.
    """
    dc_read_dirs = tuple(
        BASE_PATH / "build/scan_adc" / stamp
        for stamp in (
            "20260801_194930",
            "20260802_021624",
            "20260802_081407",
        )
    )
    sine_read_dir = BASE_PATH / "build/scan_adc/20260730_215145_complete"
    selected_sequences = (symbol256_init8_samp16_comp11110000_logic11000011,)

    # Give selected library recipes the same INIT reference as acquired rows.
    sequence_labels = {}
    for sequence in selected_sequences:
        relative_sequence = sequence.relative_to_init()
        sequence_labels[relative_sequence] = f"LOGIC {timing_sequences.index(sequence) + 1}/8"

    # Select and compare DC sweeps without changing their saved acquisition phase.
    artifacts = []
    for meas_read_dir in dc_read_dirs:
        paths = sorted(meas_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
        if not paths:
            raise FileNotFoundError(meas_read_dir)
        groups = {}
        for path in paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdcExt):
                raise TypeError(f"expected MeasAdcExt: {path}")
            params = measurement.param.tb
            if not isinstance(params.vin_diff, h.Vdc.Params):
                continue
            sequence = AdcSequence.from_tb_params(params)

            # Compare complete rows relative to INIT; leave acquired patterns and data unchanged.
            sequence = sequence.relative_to_init()

            if sequence not in sequence_labels:
                continue
            key = (measurement.param.observed_adc, float(params.vin_diff.dc), float(params.vin_cm.dc))
            groups.setdefault(key, []).append(measurement)
        if not groups:
            raise ValueError(f"no selected sequences in {meas_read_dir}")
        for (adc_index, input_v, common_v), measurements in sorted(groups.items()):
            labels = []
            for measurement in measurements:
                params = measurement.param.tb
                sequence = AdcSequence.from_tb_params(params)

                # Compare complete rows relative to INIT; leave acquired patterns and data unchanged.
                sequence = sequence.relative_to_init()

                labels.append(sequence_labels[sequence])
            stem = f"{meas_read_dir.name}_adc{adc_index:02d}_{input_v * 1e3:g}mv_{common_v * 1e3:g}cm"
            artifacts.extend(
                plot_adc_noise_sweep(
                    measurements,
                    analyze_adc_noise_sweep(measurements),
                    series_labels=labels,
                    rate_axis="sampling",
                    output_path=output_dir / f"{stem}_noise_vs_rate",
                )
            )
            for label in dict.fromkeys(labels):
                group = [m for m, name in zip(measurements, labels, strict=True) if name == label]
                artifacts.extend(
                    plot_adc_noise_distribution_sweep(
                        group,
                        analyze_adc_noise_sweep(group),
                        rate_axis="sampling",
                        output_path=output_dir / f"{stem}_logic{label.split()[-1].replace('/', 'of')}_distributions",
                    )
                )

    # Spectral results use the acquired sine, separately from DC noise estimates.
    paths = sorted(sine_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
    if not paths:
        raise FileNotFoundError(sine_read_dir)
    groups = {}
    for path in paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdcExt):
            raise TypeError(f"expected MeasAdcExt: {path}")
        params = measurement.param.tb
        if not isinstance(params.vin_diff, h.Vsin.Params):
            continue
        sequence = AdcSequence.from_tb_params(params)

        # Compare complete rows relative to INIT; leave acquired patterns and data unchanged.
        sequence = sequence.relative_to_init()

        if sequence not in sequence_labels:
            continue
        key = (measurement.param.observed_adc, sequence)
        groups.setdefault(key, []).append(measurement)
    for (adc_index, sequence), measurements in groups.items():
        sequence_name = sequence_labels[sequence].split()[-1].replace("/", "of")
        dynamic = analyze_adc_dynamic_sweep(measurements)
        artifacts.extend(
            plot_adc_dynamic_sweep(
                measurements,
                dynamic,
                x_axis="sample_rate",
                output_path=output_dir / f"adc{adc_index:02d}_logic{sequence_name}_spectral_vs_rate",
            )
        )
        # Retain individual spectral checks at the ends of the selected sweep.
        for index in dict.fromkeys((int(np.argmin(dynamic.sample_rate_hz)), int(np.argmax(dynamic.sample_rate_hz)))):
            measurement = measurements[index]
            artifacts.extend(
                plot_adc_dynamic(
                    measurement,
                    analyze_adc_dynamic(measurement),
                    output_path=output_dir
                    / f"adc{adc_index:02d}_logic{sequence_name}_{dynamic.sample_rate_hz[index] / 1e6:g}msps_spectrum",
                )
            )
    return tuple(artifacts)


def adc_power_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot three-rail power from instrumented fixed-input MeasAdcExt captures.

    Coverage: ADC00/01 50/100-mV DC at 600-mV common mode over actual
    0.3125--6.25 MSPS, plus ADC00 50-mV/700-mV-common reference points.
    Requires active and baseline voltage/current or power readbacks from the
    three Keithley supplies. Manual-supply runs and PEX are not selected;
    internal SPICE waveforms are unnecessary.
    """
    meas_read_dirs = tuple(
        BASE_PATH / "build/scan_adc" / stamp
        for stamp in (
            "20260801_194930",
            "20260802_021624",
            "20260819_113714",
        )
    )
    artifacts = []
    for meas_read_dir in meas_read_dirs:
        paths = sorted(meas_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
        if not paths:
            raise FileNotFoundError(meas_read_dir)
        groups = {}
        for path in paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdcExt):
                raise TypeError(f"expected MeasAdcExt: {path}")
            params = measurement.param.tb
            if not isinstance(params.vin_diff, h.Vdc.Params):
                continue
            sequence = AdcSequence.from_tb_params(params)

            # Compare complete rows relative to INIT; leave acquired patterns and data unchanged.
            sequence = sequence.relative_to_init()

            key = (measurement.param.observed_adc, float(params.vin_diff.dc), float(params.vin_cm.dc), sequence)
            groups.setdefault(key, []).append(measurement)
        for index, ((adc_index, input_v, common_v, _sequence), measurements) in enumerate(groups.items()):
            artifacts.extend(
                plot_adc_power_sweep(
                    measurements,
                    analyze_adc_power_sweep(measurements),
                    rate_axis="sampling",
                    output_path=output_dir
                    / f"{meas_read_dir.name}_adc{adc_index:02d}_{input_v * 1e3:g}mv_{common_v * 1e3:g}cm_{index}_power",
                )
            )
    return tuple(artifacts)


def comp_system_common_mode_study(output_dir: Path) -> tuple[Path, ...]:
    """Analyze and plot separate ADC00–ADC03 comparator common-mode campaigns."""

    meas_read_dir = BASE_PATH / "build/scan_comp/20260805_171216"
    measurements = []
    for path in sorted(meas_read_dir.glob("*.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasCompExt):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasCompExt")
        measurements.append(measurement)

    artifacts = []
    adc_indices = tuple(sorted({int(measurement.param.observed_adc) for measurement in measurements}))
    for adc_index in adc_indices:
        adc_measurements = [measurement for measurement in measurements if measurement.param.observed_adc == adc_index]
        grouped: dict[float, list[MeasCompExt]] = {}
        for measurement in adc_measurements:
            grouped.setdefault(float(measurement.param.tb.vin_cm.dc), []).append(measurement)
        groups = [grouped[value] for value in sorted(grouped)]
        analyses = [analyze_comp_offset_noise(group) for group in groups]
        analyses = list(classify_comp_common_mode_validity(groups, analyses))
        artifacts.extend(
            plot_comp_common_mode_campaign(
                groups,
                analyses,
                output_path=output_dir / f"adc{adc_index:02d}_comparator_common_mode",
            )
        )
    return tuple(artifacts)


def comp_system_sampling_noise_study(output_dir: Path) -> tuple[Path, ...]:
    """Analyze and plot separate ADC00–ADC03 track/hold comparator campaigns."""

    base_meas_read_dir = BASE_PATH / "build/scan_comp/20260805_183915"
    correction_meas_read_dir = BASE_PATH / "build/scan_comp/20260805_192902"
    base_measurements = []
    for path in sorted(base_meas_read_dir.glob("*.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasCompExt):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasCompExt")
        base_measurements.append(measurement)
    correction_measurements = []
    for path in sorted(correction_meas_read_dir.glob("*.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasCompExt):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasCompExt")
        correction_measurements.append(measurement)

    measurement_curve_keys = {
        (
            int(measurement.param.observed_adc),
            float(measurement.param.requested_dac_rail_percent),
            measurement.param.sampling_mode,
        )
        for measurement in correction_measurements
    }
    measurements = [
        measurement
        for measurement in base_measurements
        if (
            int(measurement.param.observed_adc),
            float(measurement.param.requested_dac_rail_percent),
            measurement.param.sampling_mode,
        )
        not in measurement_curve_keys
    ]
    measurements.extend(correction_measurements)

    artifacts = []
    adc_indices = tuple(sorted({int(measurement.param.observed_adc) for measurement in measurements}))
    for adc_index in adc_indices:
        adc_measurements = [measurement for measurement in measurements if measurement.param.observed_adc == adc_index]
        grouped: dict[tuple[float, str], list[MeasCompExt]] = {}
        for measurement in adc_measurements:
            group_key = (
                float(measurement.param.requested_dac_rail_percent),
                measurement.param.sampling_mode,
            )
            grouped.setdefault(group_key, []).append(measurement)
        groups = [grouped[key] for key in sorted(grouped)]
        analyses = [analyze_comp_offset_noise(group) for group in groups]
        artifacts.extend(
            plot_comp_sampling_campaign(
                groups,
                analyses,
                output_path=output_dir / f"adc{adc_index:02d}_comparator_sampling_noise",
            )
        )
    return tuple(artifacts)


def comp_candidate_sweep_study(output_dir: Path) -> tuple[Path, ...]:
    """Analyze the complete generated-comparator noise/power/timing campaign."""

    meas_read_dir = BASE_PATH / "build/comp/frida65_candidate_scurve_power/candidates"
    measurements = []
    for path in sorted(meas_read_dir.glob("*/result.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasCompInt):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasCompInt")
        measurements.append(measurement)
    analysis = analyze_comp_candidate_sweep(measurements)
    artifacts = list(
        plot_comp_candidate_sweep(
            measurements,
            analysis,
            output_path=output_dir / "comp_candidate_noise_power_settling",
        )
    )
    artifacts.extend(
        plot_comp_noise_power_tradeoff(
            analysis,
            output_path=output_dir / "comp_candidate_noise_power_tradeoff",
        )
    )
    csv_path = output_dir / "comp_candidate_noise_power_settling.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "area_order",
                "candidate_id",
                "candidate_label",
                "size_profile",
                "topology_index",
                "total_width_units",
                "total_active_area_units",
                "total_active_area_um2",
                "device_count",
                "comp_stages",
                "preamp_diff_xtors",
                "preamp_bias",
                "latch_inner_on_xtors",
                "latch_outer_on_xtors",
                "latch_inner_init_xtors",
                "latch_outer_init_xtors",
                "diffpair_w",
                "diffpair_l",
                "tail_w",
                "tail_l",
                "rst_w",
                "rst_l",
                "latch_on_w",
                "latch_on_l",
                "latch_init_w",
                "latch_init_l",
                "srlatch_n_w",
                "srlatch_p_w",
                "validity",
                "offset_v",
                "noise_sigma_v",
                "average_power_w",
                "energy_per_decision_j",
                "maximum_clock_to_decision_s",
                "maximum_settling_s",
                "unresolved_fraction",
            )
        )
        measurement_by_id = {
            str(measurement.info.readbacks["candidate_id"]): measurement for measurement in measurements
        }
        for index, candidate_id in enumerate(analysis.candidate_id):
            comp = measurement_by_id[candidate_id].param.comp
            writer.writerow(
                (
                    index,
                    candidate_id,
                    analysis.candidate_label[index],
                    analysis.size_profile[index],
                    analysis.topology_index[index],
                    analysis.total_width_units[index],
                    analysis.total_active_area_units[index],
                    analysis.total_active_area_um2[index],
                    analysis.device_count[index],
                    comp.comp_stages.name,
                    comp.preamp_diff_xtors.name,
                    comp.preamp_bias.name,
                    comp.latch_inner_on_xtors.name,
                    comp.latch_outer_on_xtors.name,
                    comp.latch_inner_init_xtors.name,
                    comp.latch_outer_init_xtors.name,
                    comp.diffpair_w,
                    comp.diffpair_l,
                    comp.tail_w,
                    comp.tail_l,
                    comp.rst_w,
                    comp.rst_l,
                    comp.latch_on_w,
                    comp.latch_on_l,
                    comp.latch_init_w,
                    comp.latch_init_l,
                    comp.srlatch_n_w,
                    comp.srlatch_p_w,
                    analysis.validity[index],
                    analysis.offset_v[index],
                    analysis.noise_sigma_v[index],
                    analysis.average_power_w[index],
                    analysis.energy_per_decision_j[index],
                    analysis.maximum_clock_to_decision_s[index],
                    analysis.maximum_settling_s[index],
                    analysis.unresolved_fraction[index],
                )
            )
    artifacts.append(csv_path)
    return tuple(artifacts)


def cdac_system_cap_mismatch_study(output_dir: Path) -> tuple[Path, ...]:
    """Extract and plot ADC00–ADC03 capacitor mismatch from A-to-B transitions."""

    meas_read_dirs = tuple(
        BASE_PATH / "build/scan_cdac" / name for name in ("20260804_171234", "20260804_193030", "20260804_193631")
    )
    measurement_runs = []
    for meas_read_dir in meas_read_dirs:
        measurements = []
        for path in sorted(meas_read_dir.glob("*.h5")):
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasCdacExt):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasCdacExt")
            measurements.append(measurement)
        measurement_runs.append(tuple(measurements))

    adc_indices = tuple(
        sorted(
            {int(measurement.param.observed_adc) for measurements in measurement_runs for measurement in measurements}
        )
    )
    board_id = measurement_runs[0][0].param.board_id
    comparator_calibrations = load_board_map()["boards"][board_id].get("comparator_calibration", {})
    adc_groups, analyses = analyze_cdac_cap_mismatch_campaign(
        measurement_runs,
        adc_indices=adc_indices,
        board_id=board_id,
        comparator_offset_v_by_adc={
            adc_index: float(comparator_calibrations[adc_index]["offset_v"]) for adc_index in adc_indices
        },
    )
    artifacts = []
    for adc_measurements, analysis in zip(adc_groups, analyses, strict=True):
        artifacts.extend(
            plot_cdac_cap_mismatch(
                adc_measurements,
                analysis,
                output_path=output_dir / f"adc{analysis.adc_index:02d}_cdac_cap_mismatch",
            )
        )
    artifacts.extend(
        plot_cdac_cap_mismatch_comparison(
            adc_groups,
            analyses,
            output_path=output_dir / "adc00_adc03_cdac_cap_mismatch_comparison",
        )
    )
    return tuple(artifacts)


def main() -> None:
    """Run one explicitly selected analysis pipeline."""
    targets: dict[str, Callable[[Path], tuple[Path, ...]]] = {
        target.__name__: target
        for target in (
            adc_transfer_curve_study,
            adc_ramp_nonlinearity_study,
            adc_calibration_study,
            adc_sequence_study,
            adc_sample_rate_study,
            adc_power_study,
            comp_system_common_mode_study,
            comp_system_sampling_noise_study,
            comp_candidate_sweep_study,
            cdac_system_cap_mismatch_study,
        )
    }

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(targets), help="analysis pipeline to run")
    args = parser.parse_args()

    domain = args.target.split("_", 1)[0] if args.target.startswith(("comp_", "cdac_")) else "adc"
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    output_dir = BASE_PATH / "build/analysis" / domain / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    print(f"Analysis output: {output_dir}")
    artifacts = targets[args.target](output_dir)
    print(f"Completed {args.target}: {len(artifacts)} artifacts")


if __name__ == "__main__":
    main()
