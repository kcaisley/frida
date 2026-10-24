"""The ADC's targets (``python -m flow adc.<target>``)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import hdl21 as h
import matplotlib as mpl
import numpy as np

from flow import comp, new_run
from flow.adc.assembly import layout_run
from flow.adc.sequences import (
    SEQUENCES,
    AdcSequence,
    symbol256_init8_samp16_comp11110000_logic11000011,
)
from flow.analysis import calc
from flow.analysis.adc import (
    analyze_adc_cdac_settling,
    analyze_adc_code_density_nonlinearity,
    analyze_adc_code_distribution,
    analyze_adc_code_spectrum,
    analyze_adc_decision_paths,
    analyze_adc_dynamic,
    analyze_adc_interferer,
    analyze_adc_noise,
    analyze_adc_operating_conditions,
    analyze_adc_power,
    analyze_adc_ramp,
    analyze_adc_timing_closure,
    analyze_adc_timing_summary,
    analyze_adc_transfer,
)
from flow.analysis.calibration1 import analyze_adc_calibration1
from flow.analysis.calibration2 import analyze_adc_calibration2
from flow.analysis.calibration3 import analyze_adc_calibration3
from flow.analysis.cdac import analyze_cdac_cap_mismatch, analyze_cdac_decisions, analyze_cdac_transition
from flow.analysis.io import (
    read_analysis,
    read_extracted_calibration,
    read_measurement,
    read_measurement_param,
    write_analysis,
)
from flow.analysis.plots import (
    plot_adc_calibration_weights,
    plot_adc_cdac_settling,
    plot_adc_code_distribution,
    plot_adc_code_noise,
    plot_adc_code_spectrum,
    plot_adc_conversion_energy,
    plot_adc_decision_path_density,
    plot_adc_dynamic,
    plot_adc_dynamic_sweep,
    plot_adc_interferer,
    plot_adc_noise_distribution_sweep,
    plot_adc_noise_sweep,
    plot_adc_power_sweep,
    plot_adc_ramp_histogram,
    plot_adc_ramp_nonlinearity,
    plot_adc_ramp_transfer,
    plot_adc_sequence_chip_overview,
    plot_adc_sequence_enob,
    plot_adc_static_nonlinearity,
    plot_adc_transfer,
    plot_waveforms,
    style_measurement_text,
)
from flow.analysis.studies import BASE_PATH, timing_sequences
from flow.analysis.types import (
    AnalysisCdacCapMismatch,
    MeasAdc,
    MeasCdac,
)
from flow.scans.params import load_board_map
from flow.sweep import runner as sweep_runner

from . import layout, sim


def _sim_run(target: str) -> Path:
    """``build/sim/adc/<stamp>_<target>``, made: where the ADC's simulations have always gone."""
    run_dir = new_run("sim", "adc")
    return run_dir.rename(run_dir.with_name(f"{run_dir.name}_{target}"))


def _unmade(*parts: str) -> Path:
    """A fresh run directory's path, not made: the ADC layouts make their own (and refuse an existing one)."""
    run_dir = new_run(*parts)
    run_dir.rmdir()
    return run_dir


def hdl21_sample_rate() -> Path:
    """The generated ADC at 2, 6 and 10 MS/s with a 50 mV input, in TSMC65."""
    return sim.hdl21_sample_rate(_sim_run("hdl21_sample_rate"))


def hdl21_transfer_curve() -> Path:
    """The generated ADC's transfer curve from -750 mV to +750 mV in 10 mV steps, in TSMC65."""
    return sim.hdl21_transfer_curve(_sim_run("hdl21_transfer_curve"))


def frida1_sequence() -> Path:
    """Seven continuous timing recipes on FRIDA-1's four extracted ADC flavors."""
    return sim.frida1_sequence(_sim_run("frida1_sequence"))


def frida1_sample_rate() -> Path:
    """FRIDA-1's four extracted ADC flavors at 2, 6 and 10 MS/s."""
    return sim.frida1_sample_rate(_sim_run("frida1_sample_rate"))


def frida1_transfer_curve() -> Path:
    """FRIDA-1's extracted ADC from -750 mV to +750 mV in 10 mV steps."""
    return sim.frida1_transfer_curve(_sim_run("frida1_transfer_curve"))


def frida1_supply_noise() -> Path:
    """FRIDA-1's extracted ADC at its 15 rate and supply-noise combinations."""
    return sim.frida1_supply_noise(_sim_run("frida1_supply_noise"))


def frida2_sequence() -> Path:
    """Named continuous timing recipes on FRIDA-2's three radix-17 stacks."""
    return sim.frida2_sequence(_sim_run("frida2_sequence"))


def layout_frida1_1layer_radix17() -> Path:
    """FRIDA-1's one-metal radix-17 ADC, its array regenerated, signed off and extracted (TSMC65)."""
    return layout.frida1_1layer_radix17(_unmade("layout", "adc", "frida1_1layer_radix17"))


def layout_frida1_1layer_radix20() -> Path:
    """FRIDA-1's one-metal radix-20 ADC, its array regenerated, signed off and extracted (TSMC65)."""
    return layout.frida1_1layer_radix20(_unmade("layout", "adc", "frida1_1layer_radix20"))


def layout_frida1_2layer_radix17() -> Path:
    """FRIDA-1's two-metal radix-17 ADC, its array regenerated, signed off and extracted (TSMC65)."""
    return layout.frida1_2layer_radix17(_unmade("layout", "adc", "frida1_2layer_radix17"))


def layout_frida1_2layer_radix20() -> Path:
    """FRIDA-1's two-metal radix-20 ADC, its array regenerated, signed off and extracted (TSMC65)."""
    return layout.frida1_2layer_radix20(_unmade("layout", "adc", "frida1_2layer_radix20"))


def layout_frida2_1layer_radix17() -> Path:
    """FRIDA-2's ADC with the one-metal radix-17 array, signed off and extracted (TSMC65)."""
    return layout.frida2_1layer_radix17(_unmade("layout", "adc", "frida2_1layer_radix17"))


def layout_frida2_2layer_radix17() -> Path:
    """FRIDA-2's ADC with the two-metal radix-17 array, signed off and extracted (TSMC65)."""
    return layout.frida2_2layer_radix17(_unmade("layout", "adc", "frida2_2layer_radix17"))


def layout_frida2_3layer_radix17() -> Path:
    """FRIDA-2's ADC with the three-metal radix-17 array, signed off and extracted (TSMC65)."""
    return layout.frida2_3layer_radix17(_unmade("layout", "adc", "frida2_3layer_radix17"))


def layout_all() -> Path:
    """Every ADC layout above, each into its own directory of one run."""
    return layout.all_adcs(new_run("layout", "adc", "all"))


def sweep() -> None:
    """The ADC's sweep in a fresh run, every PDK: characterized, its blocks' layouts placed side by
    side (``flow.adc.assembly``: nothing routed yet), tabulated."""
    sweep_runner.run(["adc"], sweep_runner.PDKS, 50)
    layout_run(sweep_runner.newest_run("adc"))
    sweep_runner.table(["adc"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def transfer_curve_study() -> tuple[Path, ...]:
    """Plot known-voltage static transfer curves from MeasAdc DC steps.

    Coverage: the archived ADC00 campaign only; its selected directory is
    currently absent locally. Each settled DC step supplies a known voltage,
    including inputs beyond either rail. No voltage reconstruction or fit,
    calibration acquisition, or internal SPICE waveforms are used.
    """
    output_dir = new_run("analysis", "adc")
    meas_read_dir = BASE_PATH / "build/scan_adc/20260818_135848"
    paths = sorted(meas_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
    if not paths:
        raise FileNotFoundError(meas_read_dir)
    groups: dict[int | None, list[MeasAdc]] = {}
    for path in paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        groups.setdefault(measurement.index, []).append(measurement)
    artifacts = []
    for adc_index, measurements in sorted(groups.items(), key=lambda item: item[0] or 0):
        artifacts.extend(
            plot_adc_transfer(
                measurements,
                analyze_adc_transfer(measurements),
                output_path=output_dir / f"adc{adc_index or 0:02d}_transfer_curve",
            )
        )
    return tuple(artifacts)


def ramp_nonlinearity_study() -> tuple[Path, ...]:
    """Plot code density and INL/DNL for the ADC00--ADC03 10-Hz sawtooth.

    Inputs are MeasAdc acquisitions, with uniform ramp occupancy assumed.
    Absolute input voltage is unused. Conversions next to each ramp wrap and
    saturated endpoint bins are excluded from linearity; the full histogram
    stays visible. No CDAC calibration data or internal SPICE waveforms are
    required.
    """
    output_dir = new_run("analysis", "adc")
    meas_read_dir = BASE_PATH / "build/scan_adc/20260812_011910"
    paths = sorted(meas_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
    if not paths:
        raise FileNotFoundError(meas_read_dir)
    artifacts = []
    for path in paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        stem = f"adc{measurement.index or 0:02d}_{path.name.split('_', 1)[0]}"
        artifacts.extend(
            plot_adc_code_distribution(
                (measurement,),
                analyze_adc_code_distribution((measurement,)),
                output_path=output_dir / f"{stem}_code_density",
            )
        )
        ramp = analyze_adc_ramp(measurement)
        artifacts.extend(
            plot_adc_static_nonlinearity(
                measurement,
                analyze_adc_code_density_nonlinearity(measurement, ramp=ramp),
                output_path=output_dir / f"{stem}_inl_dnl",
            )
        )
    return tuple(artifacts)


def behavioral_nonlinearity_study() -> tuple[Path, ...]:
    """Plot code density and INL/DNL of the behavioral FRIDA-2 three-layer sawtooth.

    The inputs are the held-out behavioral MeasAdc ramp captures from
    ``flow.scans.scan_behavioral``: 1,000,000 conversions each at 10 MS/s over
    eight full-scale sawtooth periods, switching the reviewed three-layer PEX
    capacitances. Seed 0 has no random capacitor mismatch; seeds 1--4 are
    Monte Carlo draws with Harpe (0.10 %·sqrt(fF)) and Tripathi
    (0.85 %·sqrt(fF)) unit mismatch. Each INL/DNL and code-density plot shows
    the capture decoded with the ideal design weights and with the
    PEX-extracted weights, the best estimate before mismatch.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_114121_frida2_ramp_code_density"
    artifacts = []
    for path in sorted(read_dir.glob("seed[0-9][0-9]_ac[0-9][0-9][0-9]_check.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        extracted = read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)
        ramps = (analyze_adc_ramp(measurement), analyze_adc_ramp(measurement, calibration=extracted))
        stem = f"frida2_3layer_behavioral_{path.stem}"
        artifacts.extend(
            plot_adc_ramp_histogram(ramps, output_path=output_dir / f"{stem}_code_density", msmt=measurement)
        )
        artifacts.extend(
            plot_adc_ramp_nonlinearity(ramps, output_path=output_dir / f"{stem}_inl_dnl", msmt=measurement)
        )
    return tuple(artifacts)


def behavioral_energy_study() -> tuple[Path, ...]:
    """Plot behavioral FRIDA-2 three-layer energy per conversion versus DC input.

    Inputs are 129 behavioral MeasAdc DC captures across the full scale, 2,000
    conversions each, with the PEX capacitances and the default alternating
    A-state. The model computes VDD_DAC; the comparator and logic rails use
    PEX-measured energy per conversion, so they are flat in input.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_232352_frida2_energy_vs_input"
    measurements = []
    for path in sorted(read_dir.glob("[0-9][0-9][0-9]_vin*.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        measurements.append(measurement)
    return plot_adc_conversion_energy(
        measurements,
        [analyze_adc_power(measurement) for measurement in measurements],
        output_path=output_dir / "frida2_3layer_behavioral_energy_vs_input",
    )


def behavioral_sample_rate_study() -> tuple[Path, ...]:
    """Plot behavioral FRIDA-2 three-layer power and spectral ENOB versus rate.

    Inputs are nine behavioral MeasAdc sine captures (-0.5 dBFS, 8,192
    conversions) with the 160-symbol recipe at 0.2-6.4 GBd, i.e. 1.25-40 MS/s.
    VDD_DAC charge is computed; comparator, logic, and driver energies and
    leakage are fitted to the FRIDA-2 three-layer PEX transient. Each rail's
    static and dynamic power are drawn as one band. ENOB uses the PEX-extracted weights and
    is limited by the assumed 0.2-ns CDAC settling time constant at high rates.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_232349_frida2_sample_rate"
    measurements = []
    for path in sorted(read_dir.glob("[0-9][0-9][0-9][0-9]mbd.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        measurements.append(measurement)
    return (
        *plot_adc_power_sweep(
            measurements,
            [analyze_adc_power(measurement) for measurement in measurements],
            output_path=output_dir / "frida2_3layer_behavioral_power_vs_rate",
            rate_axis="sampling",
            merge_static=True,
        ),
        *plot_adc_dynamic_sweep(
            measurements,
            [
                analyze_adc_dynamic(
                    measurement,
                    calibration=read_extracted_calibration(
                        Path(str(measurement.info.readbacks["cap_table"])), measurement
                    ),
                )
                for measurement in measurements
            ],
            output_path=output_dir / "frida2_3layer_behavioral_enob_vs_rate",
            x_axis="sample_rate",
        ),
    )


def behavioral_trajectory_study() -> tuple[Path, ...]:
    """Show redundant SAR decision paths recovering from a random first decision.

    The input is one behavioral MeasAdc: 2,000 conversions at 10 MS/s of a 0-V
    input, on the C0 threshold, with every noise source. B0 goes either way,
    and the later redundant stages bring both branches to the same codes.
    """
    output_dir = new_run("analysis", "adc")
    path = BASE_PATH / "build/scan_behavioral/20261010_114637_frida2_trajectory/trajectory_0mv.h5"
    measurement = read_measurement(path)
    if not isinstance(measurement, MeasAdc):
        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
    paths = analyze_adc_decision_paths(measurement)
    return plot_adc_decision_path_density(
        measurement, paths, output_path=output_dir / "frida2_3layer_behavioral_trajectory_density"
    )


def behavioral_calibration_study() -> tuple[Path, ...]:
    """Calibrate behavioral FRIDA-2 three-layer captures from a known ramp and check on fresh data.

    Each capacitor draw has a training and a held-out ramp capture (eight
    periods, 1,000,000 conversions, same capacitors, independent noise).
    Calibration 1 learns BOUT weights from the same draw's behavioral CDAC
    A-to-B switching curves, and calibrations 2 and 3 from the training
    capture alone; the held-out capture is then decoded with the nominal design
    weights, the PEX-extracted weights, and all three learned weight sets.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_114121_frida2_ramp_code_density"
    cdac_dir = BASE_PATH / "build/scan_behavioral/20261010_114043_frida2_cdac_ab"
    artifacts = []
    for train_path in sorted(read_dir.glob("seed[0-9][0-9]_ac[0-9][0-9][0-9]_train.h5")):
        check_path = train_path.with_name(train_path.name.replace("_train", "_check"))
        train, check = read_measurement(train_path), read_measurement(check_path)
        if not isinstance(train, MeasAdc) or not isinstance(check, MeasAdc):
            raise TypeError(f"{train_path} and {check_path} must both contain MeasAdc")
        train_ramp = analyze_adc_ramp(train)
        # Calibration 1 learns from the same draw's CDAC A-to-B switching curves.
        draw_dir = cdac_dir / train_path.stem.removesuffix("_train")
        comparator = read_analysis(draw_dir / "comparator.h5")
        if not isinstance(comparator, comp.AnalysisDecisions):
            raise TypeError(f"{draw_dir} must hold one comp.AnalysisDecisions and MeasCdac switching curves")
        curves: list[MeasCdac] = []
        for curve_path in sorted(draw_dir.glob("cdac_*.h5")):
            curve = read_measurement(curve_path)
            if not isinstance(curve, MeasCdac):
                raise TypeError(f"{draw_dir} must hold one comp.AnalysisDecisions and MeasCdac switching curves")
            curves.append(curve)
        transitions = [
            analyze_cdac_transition([curve], offset=comp.analyze_offset_noise([analyze_cdac_decisions([curve])]))
            for curve in curves
        ]
        cap_mismatch = analyze_cdac_cap_mismatch(
            curves, transitions=transitions, comparator=comp.analyze_offset_noise([comparator])
        )
        learned = (
            analyze_adc_calibration1(curves, cap_mismatch=cap_mismatch),
            analyze_adc_calibration2(train, ramp=train_ramp),
            analyze_adc_calibration3(train, ramp=train_ramp),
        )
        extracted = read_extracted_calibration(Path(str(check.info.readbacks["cap_table"])), check)
        ramps = [analyze_adc_ramp(check)] + [
            analyze_adc_ramp(check, calibration=calibration) for calibration in (extracted, *learned)
        ]
        stem = f"frida2_3layer_behavioral_{train_path.stem.removesuffix('_train')}"
        artifacts.extend(
            plot_adc_calibration_weights((extracted, *learned), output_path=output_dir / f"{stem}_weights")
        )
        artifacts.extend(
            plot_adc_ramp_nonlinearity(
                ramps, output_path=output_dir / f"{stem}_calibrated_inl_dnl", msmt=check, stacked=True
            )
        )
        artifacts.extend(
            plot_adc_ramp_histogram(ramps, output_path=output_dir / f"{stem}_calibrated_code_density", msmt=check)
        )
    return tuple(artifacts)


def behavioral_architecture_study() -> tuple[Path, ...]:
    """Compare held-out ramp linearity of redundant and binary, unit-length and unit-element arrays.

    Inputs are the behavioral architecture-variant captures: for each array
    and capacitor draw a training and a held-out eight-period ramp. The
    held-out ramp is decoded with the nominal design weights and with
    calibrations 2 and 3 learned from the training ramp alone.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_115333_architecture_variants"
    artifacts = []
    for variant_dir in sorted(path for path in read_dir.iterdir() if path.is_dir()):
        for train_path in sorted(variant_dir.glob("seed[0-9][0-9]_ac[0-9][0-9][0-9]_train.h5")):
            check_path = train_path.with_name(train_path.name.replace("_train", "_check"))
            train, check = read_measurement(train_path), read_measurement(check_path)
            if not isinstance(train, MeasAdc) or not isinstance(check, MeasAdc):
                raise TypeError(f"{train_path} and {check_path} must both contain MeasAdc")
            train_ramp = analyze_adc_ramp(train)
            learned = (
                analyze_adc_calibration2(train, ramp=train_ramp),
                analyze_adc_calibration3(train, ramp=train_ramp),
            )
            ramps = [analyze_adc_ramp(check)] + [
                analyze_adc_ramp(check, calibration=calibration) for calibration in learned
            ]
            stem = f"{variant_dir.name}_{train_path.stem.removesuffix('_train')}"
            artifacts.extend(plot_adc_ramp_nonlinearity(ramps, output_path=output_dir / f"{stem}_inl_dnl", msmt=check))
            artifacts.extend(plot_adc_calibration_weights(learned, output_path=output_dir / f"{stem}_weights"))
    return tuple(artifacts)


def behavioral_noise_spectrum_study() -> tuple[Path, ...]:
    """Overlay the output-code noise spectral density of each behavioral noise source.

    Inputs are three behavioral MeasAdc fixed-input captures (50 mV, 10 MS/s,
    100,000 conversions): the sampling switch's kT/C alone, the comparator
    alone, and the total ADC with both.
    Codes are decoded with the PEX-extracted weights.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_114609_frida2_noise_sources"
    labels = {
        "sampling": "Sampling switch (kT/C)",
        "comparator": "Comparator",
        "baseline": "Total ADC",
    }
    spectra = []
    for name in labels:
        path = read_dir / f"noise_{name}.h5"
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        calibration = read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)
        spectra.append(analyze_adc_code_spectrum(measurement, calibration=calibration))
    return plot_adc_code_spectrum(
        spectra,
        labels=tuple(labels.values()),
        title="FRIDA-2 three-layer behavioral noise sources",
        output_path=output_dir / "frida2_3layer_behavioral_noise_spectrum",
    )


def behavioral_input_frequency_study() -> tuple[Path, ...]:
    """Plot spectral ENOB and SNDR versus input frequency at 2, 6, and 10 MS/s.

    Inputs are 27 behavioral MeasAdc sine captures (-0.5 dBFS, nine input
    frequencies up to Nyquist per rate, 8,192 conversions) with every noise
    source, the input-dependent sampler, and the PEX-extracted decoding. The
    10-MS/s captures nearest DC and Nyquist also get their own spectra.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_114623_frida2_input_frequency"
    measurements, dynamics = [], []
    for path in sorted(read_dir.glob("[0-9][0-9][0-9][0-9]mbd_[0-9][0-9][0-9][0-9]cycles.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        calibration = read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)
        measurements.append(measurement)
        dynamics.append(analyze_adc_dynamic(measurement, calibration=calibration))
    artifacts = list(
        plot_adc_dynamic_sweep(
            measurements,
            dynamics,
            output_path=output_dir / "frida2_3layer_behavioral_enob_vs_input_frequency",
            x_axis="input_frequency",
        )
    )
    at_10_msps = [index for index, dynamic in enumerate(dynamics) if round(dynamic.sample_rate_hz) == 10_000_000]
    for label, index in (("low", at_10_msps[0]), ("nyquist", at_10_msps[-1])):
        artifacts.extend(
            plot_adc_dynamic(
                measurements[index],
                dynamics[index],
                output_path=output_dir / f"frida2_3layer_behavioral_10msps_{label}_spectrum",
            )
        )
    return tuple(artifacts)


def calibration_study() -> tuple[Path, ...]:
    """Compare three calibration methods on the selected ADC00 measurements.

    Coverage: ADC00's known 10-Hz ramp (MeasAdc), three reviewed CDAC
    threshold campaigns (MeasCdac), and the accepted comparator
    characterization (comp.AnalysisDecisions). Calibration 1 extracts A-state threshold
    movements; calibrations 2/3 use ramp BOUT fits/prefix thresholds. The ramp
    validates the resulting decoders. No internal SPICE waveforms are needed.
    """
    output_dir = new_run("analysis", "adc")

    ramp_path = BASE_PATH / (
        "build/scan_adc/20260812_011910/"
        "0000_00_adc00_160mbd_pwl10hz_m1000top1000mv_logicp0sym_"
        "vcm600mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
    )
    measurement = read_measurement(ramp_path)
    if not isinstance(measurement, MeasAdc):
        raise TypeError(f"{ramp_path} contains {type(measurement).__name__}, expected MeasAdc")
    adc_index = measurement.index
    if adc_index is None:
        raise ValueError("calibration study requires an observed ADC")
    # Comparator characterizations: the reviewed 800-mV campaigns behind the
    # board inventory's accepted comparator calibration, with every coarse and
    # fine trial. Each one is the reference point of its ADC's CDAC steps.
    comparator_read_dirs = {
        0: BASE_PATH / "build/scan_comp/20260804_051653",
        1: BASE_PATH / "build/scan_comp/20260804_053759",
        2: BASE_PATH / "build/scan_comp/20260804_051653",
        3: BASE_PATH / "build/scan_comp/20260804_054953",
    }
    # CDAC A-to-B runs, in acquisition order. Each later run atomically replaces
    # every point of the same ADC, side, element, direction, and diffcaps curve;
    # physical points from distinct acquisition sessions are never combined.
    selected_curves: dict[tuple[int, str, int, str, int], list[MeasCdac]] = {}
    for run_name in ("20260804_171234", "20260804_193030", "20260804_193631"):
        grouped_in_run: dict[tuple[int, str, int, str, int], list[MeasCdac]] = {}
        for path in sorted((BASE_PATH / "build/scan_cdac" / run_name).glob("*.h5")):
            cdac_point = read_measurement(path)
            if not isinstance(cdac_point, MeasCdac):
                raise TypeError(f"{path} contains {type(cdac_point).__name__}, expected MeasCdac")
            params = cdac_point.param
            if params.observed_adc != adc_index:
                continue
            if params.campaign != "cdac_ab":
                raise ValueError("CDAC campaign contains a point outside campaign='cdac_ab'")
            readbacks = cdac_point.info.readbacks
            if int(readbacks.get("fastrx_lost_count", 0)) or int(readbacks.get("spi_mismatches", 0)):
                raise ValueError("CDAC campaign contains a corrupt physical capture")
            if (
                params.observed_adc is None
                or params.cdac_side is None
                or params.cdac_element is None
                or params.cdac_direction is None
            ):
                raise ValueError("CDAC measurement is missing its ADC, side, element, or direction")
            curve_key = (
                params.observed_adc,
                params.cdac_side,
                params.cdac_element,
                params.cdac_direction,
                params.tb.dac_diffcaps,
            )
            grouped_in_run.setdefault(curve_key, []).append(cdac_point)
        for curve_key, curve in grouped_in_run.items():
            physical = [point for point in curve if point.info.backend == "physical"]
            if physical:
                session_ids = {point.info.readbacks.get("acquisition_session_id") for point in physical}
                completed = [point for point in physical if point.info.readbacks.get("curve_complete") is True]
                latest_timestamp = max(point.info.timestamp_utc for point in physical)
                if (
                    len(physical) != len(curve)
                    or None in session_ids
                    or len(session_ids) != 1
                    or len(completed) != 1
                    or completed[0].info.timestamp_utc != latest_timestamp
                ):
                    raise ValueError(f"CDAC campaign contains an incomplete or mixed-session curve {curve_key}")
        selected_curves.update(grouped_in_run)
    cdac_measurements: dict[int, list[MeasCdac]] = {}
    cap_mismatch: dict[int, AnalysisCdacCapMismatch] = {}
    for adc_index in sorted({curve_key[0] for curve_key in selected_curves}):
        comparator_measurements = []
        for path in sorted(comparator_read_dirs[adc_index].glob(f"*adc{adc_index:02d}*.h5")):
            comparator_point = read_analysis(path)
            if not isinstance(comparator_point, comp.AnalysisDecisions):
                raise TypeError(f"{path} contains {type(comparator_point).__name__}, expected comp.AnalysisDecisions")
            comparator_measurements.append(comparator_point)
        transitions = []
        cdac_measurements[adc_index] = []
        for curve_key in sorted(key for key in selected_curves if key[0] == adc_index):
            curve = selected_curves[curve_key]
            cdac_measurements[adc_index].extend(curve)
            # Fit the fine sweep stage where the curve has one.
            fit_points = [point for point in curve if point.param.sweep_stage == "fine"] or curve
            transitions.append(
                analyze_cdac_transition(
                    fit_points, offset=comp.analyze_offset_noise([analyze_cdac_decisions(fit_points)])
                )
            )
        cap_mismatch[adc_index] = analyze_cdac_cap_mismatch(
            cdac_measurements[adc_index],
            transitions=transitions,
            comparator=comp.analyze_offset_noise(comparator_measurements),
        )

    nominal_ramp = analyze_adc_ramp(measurement)
    calibrations = (
        analyze_adc_calibration1(cdac_measurements[adc_index], cap_mismatch=cap_mismatch[adc_index]),
        analyze_adc_calibration2(measurement, ramp=nominal_ramp),
        analyze_adc_calibration3(measurement, ramp=nominal_ramp),
    )
    ramps = (nominal_ramp, *(analyze_adc_ramp(measurement, calibration=calibration) for calibration in calibrations))

    stem = f"adc{adc_index:02d}"
    return (
        *plot_adc_calibration_weights(calibrations, output_path=output_dir / f"{stem}_calibration_weights"),
        *plot_adc_ramp_transfer(ramps, output_path=output_dir / f"{stem}_calibration_transfer"),
        *plot_adc_ramp_histogram(ramps, output_path=output_dir / f"{stem}_calibration_code_density"),
        *plot_adc_ramp_nonlinearity(ramps, output_path=output_dir / f"{stem}_calibration_inl_dnl"),
    )


def sequence_study() -> tuple[Path, ...]:
    """Compare 29 continuous recipes on 16 ADCs at 2/6/10 MSPS and selected PEX cases.

    Physical captures are the corrected 160-symbol, 100,000-conversion
    fixed-input campaign. The selected PEX cases cover the same seven
    continuous recipes on four FRIDA-1 and three FRIDA-2 flavors at 1600 MBd.
    Physical and PEX captures go through the same per-capture noise analysis
    and per-ADC (or per-flavor) operating-condition analysis; PEX cases also
    get timing closure. Operating-condition and timing-summary results are
    saved as analysis HDF5 files beside the figures.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_adc/20260926_172920_adc_sequence_static"
    paths = sorted(read_dir.glob("[0-9][0-9][0-9][0-9]_capture.h5"))
    # The pinned physical captures predate the wider INIT-associated LOGIC pulse.
    catalogue = tuple(
        dataclasses.replace(sequence, logic="00010000" + sequence.logic[8:])
        for name, sequence in SEQUENCES
        if name.startswith("symbol160_init4_samp20_")
    )
    paths_by_adc: dict[int, list[Path]] = {}
    for path in paths:
        paths_by_adc.setdefault(read_measurement_param(path).observed_adc, []).append(path)

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[Path] = []
    conditions = []
    board_map = load_board_map()
    for adc_index, adc_paths in sorted(paths_by_adc.items()):
        measurements = []
        for path in adc_paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdc):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
            measurements.append(measurement)
        result = analyze_adc_operating_conditions(
            measurements, noise=[analyze_adc_noise(measurement) for measurement in measurements]
        )
        del measurements
        conditions.append(result)
        artifacts.append(write_analysis(output_dir / f"adc{adc_index:02d}_operating_conditions.h5", result))
        layers = board_map["adc_layers"]
        artifacts.extend(
            plot_adc_sequence_enob(
                result,
                sequences=catalogue,
                adc_label=(
                    f"ADC{adc_index:02d} · {board_map['adc_channels'][adc_index]}"
                    + (f" · {layers[adc_index]} layer" if adc_index in layers else "")
                ),
                output_path=output_dir / f"adc{adc_index:02d}_sequence_enob",
            )
        )
    artifacts.extend(
        plot_adc_sequence_chip_overview(
            conditions,
            sequences=catalogue,
            title=f"{len(conditions)} ADCs · fixed 50 mV input · continuous 160-symbol sequence comparison",
            output_path=output_dir / "all_adc_sequence_overview",
        )
    )

    timings = (
        "symbol160_init4_samp20_comp11110000_logic00001111",
        "symbol160_init4_samp20_comp11110000_logic10000111",
        "symbol160_init4_samp20_comp11111000_logic10000111",
        "symbol160_init4_samp20_comp11111000_logic11000011",
        "symbol160_init4_samp20_comp11111100_logic11000011",
        "symbol160_init4_samp20_comp11111100_logic11100001",
        "symbol160_init4_samp20_comp11111110_logic11100001",
    )
    campaigns = (
        (
            "frida-20260926_215421_042700",
            "20260926_221031_frida1_sequence",
            tuple(f"frida1_{layers}layer_radix{radix}" for layers in (1, 2) for radix in (17, 20)),
        ),
        (
            "frida-20260926_215427_988306",
            "20260926_221039_frida2_sequence",
            tuple(f"frida2_{layers}layer_radix17" for layers in (1, 2, 3)),
        ),
    )
    # One representative flavor supplies the seven sequence clock diagrams.
    sequence_plot_flavor = "frida2_3layer_radix17"
    for session, stamp, flavors in campaigns:
        for flavor in flavors:
            measurements = []
            for timing in timings:
                path = BASE_PATH / "build/remote" / session / "results/sim/adc" / stamp / flavor / timing / "result.h5"
                measurement = read_measurement(path)
                if not isinstance(measurement, MeasAdc):
                    raise TypeError(f"expected MeasAdc: {path}")
                case = f"{flavor}_{timing}"
                artifacts.extend(
                    plot_adc_decision_path_density(
                        measurement,
                        analyze_adc_decision_paths(measurement),
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
                closure = analyze_adc_timing_closure(measurement)
                artifacts.append(
                    write_analysis(
                        output_dir / f"{case}_timing_summary.h5",
                        analyze_adc_timing_summary(measurement, closure=closure),
                    )
                )
                if flavor == sequence_plot_flavor and measurement.wave is not None:
                    # Show the second saved conversion from its INIT rise.
                    wave = measurement.wave
                    init_rise_s = calc.cross(wave.v["seq_init"][1], wave.time_s, 0.6, edge="rising", initial_high=True)
                    if not len(init_rise_s):
                        raise ValueError(f"{case} has no INIT rise in its second record")
                    with mpl.rc_context({"axes.xmargin": 0.0}):
                        artifacts.extend(
                            plot_waveforms(
                                wave,
                                record=1,
                                time_origin_s=float(init_rise_s[0]),
                                signals={
                                    "seq_init": "INIT",
                                    "seq_samp": "SAMP",
                                    "seq_comp": "COMP",
                                    "seq_logic": "LOGIC",
                                },
                                title=timing.replace("_", " "),
                                setup_lines=style_measurement_text(measurement),
                                output_path=output_dir / f"sequence_{timing}",
                            )
                        )
                print(f"Rendered PEX case {case}", flush=True)
                measurements.append(measurement)
            noise = [analyze_adc_noise(measurement) for measurement in measurements]
            artifacts.append(
                write_analysis(
                    output_dir / f"spice_{flavor}_operating_conditions.h5",
                    analyze_adc_operating_conditions(measurements, noise=noise),
                )
            )
            artifacts.extend(
                plot_adc_noise_sweep(
                    measurements,
                    noise,
                    series_labels=timings,
                    rate_axis="sampling",
                    output_path=output_dir / f"spice_{flavor}_sequence_noise",
                )
            )
            del measurements, noise
    return tuple(artifacts)


def interferer_study() -> tuple[Path, ...]:
    """Locate the 6-8 MHz interferer in the output-code spectra and its amplifier-supply A/B test.

    Labels follow the interferer-hunt deck: test #4 is the 8 Oct scope re-run,
    tests #12--#15 the 9 Oct runs A/B/C/D. They share one fixed 50-mV
    input on ADC00--03, seven 160-symbol sequences at 2/6/10 MSPS, and 100,000
    conversions per capture. A and D have the THS4541 supplies unplugged or
    turned down and lack the interferer; B and C have them on, with the
    amplifier enabled and disabled. Every capture gets a code spectrum; each
    run's ADCs get an alias search over their 4of8 captures at three rates.
    Without the interferer, that search settles on slow drift near DC. The figures overlay
    the four ADCs per run for the 4of8 recipe and the runs for ADC00, and split
    ADC00's slowest 4of8 capture into lines and broadband noise per run.
    """
    output_dir = new_run("analysis", "adc")
    runs = {
        "Test #4": "20261008_204141_adc_sequence_static",
        "Test #12: amp supplies unplugged": "20261009_105940_adc_sequence_static",
        "Test #13: amp supplies on, enabled": "20261009_110638_adc_sequence_static",
        "Test #14: amp supplies on, disabled": "20261009_110933_adc_sequence_static",
        "Test #15: amp supplies turned down": "20261009_153529_adc_sequence_static",
    }
    shown = dict(SEQUENCES)["symbol160_init4_samp20_comp11110000_logic10000111"]
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[Path] = []
    comparison = []
    for run, folder in runs.items():
        stem = folder.removesuffix("_adc_sequence_static")
        measurements_by_adc: dict[int, list[MeasAdc]] = {}
        for path in sorted((BASE_PATH / "build/scan_adc" / folder).glob("[0-9][0-9][0-9][0-9]_capture.h5")):
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdc):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
            measurements_by_adc.setdefault(measurement.param.observed_adc, []).append(measurement)
        shown_spectra = []
        interferers = []
        for adc_index, measurements in sorted(measurements_by_adc.items()):
            spectra = [analyze_adc_code_spectrum(measurement) for measurement in measurements]
            # Search one recipe, whose three rates were captured minutes apart: over
            # all recipes, the drifting interferer smears and a fixed 7.143-MHz line
            # (2856 kHz at 10 MSPS) wins instead.
            selected = [index for index, spectrum in enumerate(spectra) if spectrum.sequence == shown]
            interferer = analyze_adc_interferer(
                [measurements[index] for index in selected], spectra=[spectra[index] for index in selected]
            )
            interferers.append(interferer)
            artifacts.append(write_analysis(output_dir / f"{stem}_adc{adc_index:02d}_interferer.h5", interferer))
            shown_spectra.extend(spectrum for spectrum in spectra if spectrum.sequence == shown)
            if adc_index == 0:
                # The variance split of ADC00 at the slowest rate, codes and spectrum together.
                candidates = [pair for pair in zip(measurements, spectra, strict=True) if pair[1].sequence == shown]
                measurement, spectrum = candidates[int(np.argmin([pair[1].sample_rate_hz for pair in candidates]))]
                artifacts.extend(
                    plot_adc_code_noise(
                        measurement,
                        spectrum,
                        title=f"ADC00 code noise, {spectrum.sample_rate_hz / 1e6:g} MSPS, 4of8 recipe · {run}",
                        output_path=output_dir / f"{stem}_adc00_code_noise",
                    )
                )
        comparison.extend((run, spectrum) for spectrum in shown_spectra if spectrum.index == 0)
        artifacts.extend(
            plot_adc_code_spectrum(
                shown_spectra,
                title=f"Output-code spectra, 4of8 recipe · {run}",
                output_path=output_dir / f"{stem}_code_spectra",
            )
        )
        artifacts.extend(
            plot_adc_interferer(
                interferers,
                title=f"Interferer frequency from its aliases · {run}",
                output_path=output_dir / f"{stem}_interferer",
            )
        )
    artifacts.extend(
        plot_adc_code_spectrum(
            [spectrum for _run, spectrum in comparison],
            labels=[run.split(":")[0] for run, _spectrum in comparison],
            title="ADC00 output-code spectra, 4of8 recipe · amplifier-supply A/B",
            output_path=output_dir / "amp_supply_code_spectra",
        )
    )
    return tuple(artifacts)


def sample_rate_study() -> tuple[Path, ...]:
    """Plot measured rate dependence for selected historical sequence patterns.

    Coverage: ADC00/01 50/100-mV DC and 10-kHz sine captures at 600-mV common
    mode, plus the control alignment in ADC00's 800-mV timing campaign.
    Only the historical fixed-input sequence is currently accepted; extend the
    explicit selection after validating additional patterns in the sequence study.
    Actual rates are 0.3125--6.25 MSPS (formerly labelled 0.5--10 active MSPS);
    an actual 10-MSPS sweep of accepted new patterns still needs acquisition.
    DC panels show noise-equivalent resolution; sine panels show spectral
    ENOB/SNDR. Inputs are MeasAdc; no PEX or internal waveforms are required.
    """
    output_dir = new_run("analysis", "adc")
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
        groups: dict[tuple[int | None, float, float], list[MeasAdc]] = {}
        for path in paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdc):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
            params = measurement.tb
            if not isinstance(params.vin_diff, h.Vdc.Params):
                continue
            # Compare complete rows relative to INIT; leave acquired patterns and data unchanged.
            sequence = AdcSequence.from_tb_params(params).relative_to_init()
            if sequence not in sequence_labels:
                continue
            key = (measurement.index, float(params.vin_diff.dc), float(params.vin_cm.dc))
            groups.setdefault(key, []).append(measurement)
        if not groups:
            raise ValueError(f"no selected sequences in {meas_read_dir}")
        for (adc_index, input_v, common_v), measurements in sorted(groups.items(), key=lambda item: str(item[0])):
            labels = [
                sequence_labels[AdcSequence.from_tb_params(measurement.tb).relative_to_init()]
                for measurement in measurements
            ]
            noise = [analyze_adc_noise(measurement) for measurement in measurements]
            stem = f"{meas_read_dir.name}_adc{adc_index or 0:02d}_{input_v * 1e3:g}mv_{common_v * 1e3:g}cm"
            artifacts.extend(
                plot_adc_noise_sweep(
                    measurements,
                    noise,
                    series_labels=labels,
                    rate_axis="sampling",
                    output_path=output_dir / f"{stem}_noise_vs_rate",
                )
            )
            for label in dict.fromkeys(labels):
                selected = [index for index, name in enumerate(labels) if name == label]
                artifacts.extend(
                    plot_adc_noise_distribution_sweep(
                        [measurements[index] for index in selected],
                        [noise[index] for index in selected],
                        rate_axis="sampling",
                        output_path=output_dir / f"{stem}_logic{label.split()[-1].replace('/', 'of')}_distributions",
                    )
                )

    # Spectral results use the acquired sine, separately from DC noise estimates.
    paths = sorted(sine_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
    if not paths:
        raise FileNotFoundError(sine_read_dir)
    sine_groups: dict[tuple[int | None, AdcSequence], list[MeasAdc]] = {}
    for path in paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        params = measurement.tb
        if not isinstance(params.vin_diff, h.Vsin.Params):
            continue
        # Compare complete rows relative to INIT; leave acquired patterns and data unchanged.
        sequence = AdcSequence.from_tb_params(params).relative_to_init()
        if sequence not in sequence_labels:
            continue
        sine_groups.setdefault((measurement.index, sequence), []).append(measurement)
    for (adc_index, sequence), measurements in sine_groups.items():
        sequence_name = sequence_labels[sequence].split()[-1].replace("/", "of")
        dynamic = [analyze_adc_dynamic(measurement) for measurement in measurements]
        stem = f"adc{adc_index or 0:02d}_logic{sequence_name}"
        artifacts.extend(
            plot_adc_dynamic_sweep(
                measurements,
                dynamic,
                x_axis="sample_rate",
                output_path=output_dir / f"{stem}_spectral_vs_rate",
            )
        )
        # Retain individual spectral checks at the ends of the selected sweep.
        rates = [result.sample_rate_hz for result in dynamic]
        for index in dict.fromkeys((rates.index(min(rates)), rates.index(max(rates)))):
            artifacts.extend(
                plot_adc_dynamic(
                    measurements[index],
                    dynamic[index],
                    # A decimal point would read as a file suffix; write 0.3125 as 0p3125.
                    output_path=output_dir / f"{stem}_{f'{rates[index] / 1e6:g}'.replace('.', 'p')}msps_spectrum",
                )
            )
    return tuple(artifacts)


def power_study() -> tuple[Path, ...]:
    """Plot three-rail power from instrumented fixed-input MeasAdc captures.

    Coverage: ADC00/01 50/100-mV DC at 600-mV common mode over actual
    0.3125--6.25 MSPS, plus ADC00 50-mV/700-mV-common reference points.
    Requires active and baseline voltage/current or power readbacks from the
    three Keithley supplies. Manual-supply runs and PEX are not selected;
    internal SPICE waveforms are unnecessary.
    """
    output_dir = new_run("analysis", "adc")
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
        groups: dict[tuple[int | None, float, float, AdcSequence], list[MeasAdc]] = {}
        for path in paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdc):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
            params = measurement.tb
            if not isinstance(params.vin_diff, h.Vdc.Params):
                continue
            # Compare complete rows relative to INIT; leave acquired patterns and data unchanged.
            sequence = AdcSequence.from_tb_params(params).relative_to_init()
            key = (measurement.index, float(params.vin_diff.dc), float(params.vin_cm.dc), sequence)
            groups.setdefault(key, []).append(measurement)
        for index, ((adc_index, input_v, common_v, _sequence), measurements) in enumerate(groups.items()):
            artifacts.extend(
                plot_adc_power_sweep(
                    measurements,
                    [analyze_adc_power(measurement) for measurement in measurements],
                    rate_axis="sampling",
                    output_path=output_dir
                    / f"{meas_read_dir.name}_adc{adc_index or 0:02d}_{input_v * 1e3:g}mv_{common_v * 1e3:g}cm_{index}_power",
                )
            )
    return tuple(artifacts)
