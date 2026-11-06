"""The ADC's targets (``python -m flow adc.<target>``)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import hdl21 as h

from flow import capdac, comp, new_run
from flow.adc.sim import (
    SEQUENCES,
    AdcSequence,
    symbol256_init8_samp16_comp11110000_logic11000011,
)
from flow.analysis import calc
from flow.analysis.io import (
    read_analysis,
    read_extracted_calibration,
    read_measurement,
    read_measurement_param,
    write_analysis,
)
from flow.analysis.studies import BASE_PATH
from flow.analysis.types import MeasAdc, MeasCdac
from flow.plot import render
from flow.sweep import runner as sweep_runner

from . import layout
from . import sweep as adc_sweep  # the module; ``sweep`` is this file's sweep target
from .analysis import (
    analyze_calibration1,
    analyze_calibration2,
    analyze_calibration3,
    analyze_cdac_settling,
    analyze_code_spectrum,
    analyze_decision_paths,
    analyze_dynamic,
    analyze_energy,
    analyze_input_noise,
    analyze_interferer,
    analyze_noise,
    analyze_operating_conditions,
    analyze_power,
    analyze_ramp,
    analyze_sequence_map,
    analyze_sequencer,
    analyze_switching,
    analyze_timing_closure,
    analyze_timing_summary,
    analyze_transfer,
)
from .plots import (
    plot_calibration_weights,
    plot_cdac_settling_first,
    plot_cdac_settling_last,
    plot_cdac_settling_middle,
    plot_code_density,
    plot_codes_rate,
    plot_dnl,
    plot_dnl_calibrated,
    plot_energy_dac_input,
    plot_energy_input,
    plot_enob_fin,
    plot_enob_rate,
    plot_inl,
    plot_inl_calibrated,
    plot_interferer,
    plot_interferer_lines,
    plot_noise_enob_rate,
    plot_noise_input,
    plot_noise_rate,
    plot_noise_spectrum,
    plot_power_rate,
    plot_ramp_transfer,
    plot_sequence_enob,
    plot_sequence_plausible,
    plot_sequence_shift,
    plot_sequencer,
    plot_spectrum_low,
    plot_spectrum_nyquist,
    plot_trajectory,
    plot_trajectory_codes,
    plot_trajectory_final,
    plot_transfer,
)
from .types import AnalysisCalibration, AnalysisDecisionPaths, AnalysisRamp, AnalysisSequenceMap


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
    return adc_sweep.hdl21_sample_rate(_sim_run("hdl21_sample_rate"))


def hdl21_transfer_curve() -> Path:
    """The generated ADC's transfer curve from -750 mV to +750 mV in 10 mV steps, in TSMC65."""
    return adc_sweep.hdl21_transfer_curve(_sim_run("hdl21_transfer_curve"))


def frida1_sequence() -> Path:
    """Seven continuous timing recipes on FRIDA-1's four extracted ADC flavors."""
    return adc_sweep.frida1_sequence(_sim_run("frida1_sequence"))


def frida1_sample_rate() -> Path:
    """FRIDA-1's four extracted ADC flavors at 2, 6 and 10 MS/s."""
    return adc_sweep.frida1_sample_rate(_sim_run("frida1_sample_rate"))


def frida1_transfer_curve() -> Path:
    """FRIDA-1's extracted ADC from -750 mV to +750 mV in 10 mV steps."""
    return adc_sweep.frida1_transfer_curve(_sim_run("frida1_transfer_curve"))


def frida1_supply_noise() -> Path:
    """FRIDA-1's extracted ADC at its 15 rate and supply-noise combinations."""
    return adc_sweep.frida1_supply_noise(_sim_run("frida1_supply_noise"))


def layout_frida1_1layer_radix17() -> Path:
    """FRIDA-1's one-metal radix-17 ADC as fabricated, signed off and extracted (TSMC65)."""
    return layout.frida1_1layer_radix17(_unmade("layout", "adc", "frida1_1layer_radix17"))


def layout_frida1_1layer_radix20() -> Path:
    """FRIDA-1's one-metal radix-20 ADC as fabricated, signed off and extracted (TSMC65)."""
    return layout.frida1_1layer_radix20(_unmade("layout", "adc", "frida1_1layer_radix20"))


def layout_frida1_2layer_radix17() -> Path:
    """FRIDA-1's two-metal radix-17 ADC as fabricated, signed off and extracted (TSMC65)."""
    return layout.frida1_2layer_radix17(_unmade("layout", "adc", "frida1_2layer_radix17"))


def layout_frida1_2layer_radix20() -> Path:
    """FRIDA-1's two-metal radix-20 ADC as fabricated, signed off and extracted (TSMC65)."""
    return layout.frida1_2layer_radix20(_unmade("layout", "adc", "frida1_2layer_radix20"))


def layout_all() -> Path:
    """FRIDA-1's four layouts above, each into its own directory of one run."""
    return layout.all_adcs(new_run("layout", "adc", "all"))


def sweep() -> None:
    """The ADC's sweep in a fresh run, every PDK: characterized, its blocks' layouts placed side by
    side (``flow.adc.layout.layout_run``: nothing routed yet), tabulated."""
    sweep_runner.run(["adc"], sweep_runner.PDKS, 50)
    layout.layout_run(sweep_runner.newest_run("adc"))
    sweep_runner.table(["adc"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>; the figures the
# record has too are its specs (flow.adc.plots), drawn by flow.plot.render, one curve a figure


def _ramp_figures(ramp: AnalysisRamp, output_dir: Path, stem: str) -> list[Path]:
    """One decoding of a ramp drawn as the record draws it: its code density, INL and DNL (the design
    weights' figures, or the calibrated ones for any other weights), each into
    ``<stem>_<figure>_<decoding>``, the decoding ``design`` or the weights' method."""
    design = ramp.decoding == "uncalibrated_dout"
    figures = {
        "code_density": plot_code_density(ramp),
        "inl": plot_inl(ramp) if design else plot_inl_calibrated(ramp),
        "dnl": plot_dnl(ramp) if design else plot_dnl_calibrated(ramp),
    }
    return [
        path
        for name, figure in figures.items()
        for path in render(figure, output_dir / f"{stem}_{name}_{_decoding(ramp)}")
    ]


def _decoding(ramp: AnalysisRamp) -> str:
    """A ramp's decoding as its figures' files name it: ``design``, or the weights' method."""
    return "design" if ramp.decoding == "uncalibrated_dout" else ramp.decoding


def _path_figures(paths: AnalysisDecisionPaths, output_dir: Path, stem: str) -> list[Path]:
    """The decision paths at one input as the record draws them: over the whole conversion, over the
    last decisions and the codes they end on, each into ``<stem>_<figure>``."""
    figures = (plot_trajectory(paths), plot_trajectory_final(paths), plot_trajectory_codes(paths))
    return [path for figure in figures for path in render(figure, output_dir / f"{stem}_{figure.name}")]


def _sequence_figures(sequences: AnalysisSequenceMap, output_dir: Path, stem: str) -> list[Path]:
    """Operating conditions over sequence and symbol rate as their maps: the ENOB, how many ADCs give
    plausible codes and how far the mean code moves, each into ``<stem>_<figure>``."""
    figures = (plot_sequence_enob(sequences), plot_sequence_plausible(sequences), plot_sequence_shift(sequences))
    return [path for figure in figures for path in render(figure, output_dir / f"{stem}_{figure.name}")]


def _weight_figures(calibrations: Sequence[AnalysisCalibration], output_dir: Path, stem: str) -> list[Path]:
    """Each calibration's weights' error against the design's, as the record draws the extracted
    array's, into ``<stem>_<method>``."""
    return [
        path
        for calibration in calibrations
        for path in render(plot_calibration_weights(calibration), output_dir / f"{stem}_{calibration.method}")
    ]


def transfer_curve_study() -> tuple[Path, ...]:
    """Plot known-voltage static transfer curves from MeasAdc DC steps.

    Coverage: the archived ADC00 campaign only; its selected directory is
    currently absent locally. Each settled DC step supplies a known voltage,
    including inputs beyond either rail. No voltage reconstruction or fit,
    calibration acquisition, or internal SPICE waveforms are used. Each ADC
    gets its mean code over the input (``adc<NN>_transfer_curve``) and the
    record's output-code noise over the input (``adc<NN>_noise_input``).
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
        stem = f"adc{adc_index or 0:02d}"
        artifacts.extend(render(plot_transfer(analyze_transfer(measurements)), output_dir / f"{stem}_transfer_curve"))
        artifacts.extend(
            render(plot_noise_input(analyze_input_noise(measurements)), output_dir / f"{stem}_noise_input")
        )
    return tuple(artifacts)


def ramp_nonlinearity_study() -> tuple[Path, ...]:
    """Plot code density and INL/DNL for the ADC00--ADC03 10-Hz sawtooth.

    Inputs are MeasAdc acquisitions, with uniform ramp occupancy assumed.
    Absolute input voltage is unused. Conversions next to each ramp wrap and
    the saturated end codes are excluded from the linearity and from the
    code density, which shows the codes the ramp grades (the ramp's figures,
    ``_ramp_figures``). No CDAC calibration data or internal SPICE waveforms
    are required.
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
        artifacts.extend(_ramp_figures(analyze_ramp(measurement), output_dir, stem))
    return tuple(artifacts)


def behavioral_nonlinearity_study() -> tuple[Path, ...]:
    """Plot code density and INL/DNL of the behavioral FRIDA-2 three-layer sawtooth.

    The inputs are the held-out behavioral MeasAdc ramp captures from
    ``flow.scans.scan_behavioral``: 1,000,000 conversions each at 10 MS/s over
    eight full-scale sawtooth periods, switching the reviewed three-layer PEX
    capacitances. Seed 0 has no random capacitor mismatch; seeds 1--4 are
    Monte Carlo draws with an assumed 0.10 %·sqrt(fF) and Tripathi
    and Murmann's 0.85 %·sqrt(fF) unit mismatch. Each capture is decoded with the ideal
    design weights and with the PEX-extracted weights, the best estimate
    before mismatch, and each decoding gets its code-density, INL and DNL
    figures.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_114121_frida2_ramp_code_density"
    artifacts = []
    for path in sorted(read_dir.glob("seed[0-9][0-9]_ac[0-9][0-9][0-9]_check.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        extracted = read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)
        stem = f"frida2_3layer_behavioral_{path.stem}"
        for ramp in (analyze_ramp(measurement), analyze_ramp(measurement, calibration=extracted)):
            artifacts.extend(_ramp_figures(ramp, output_dir, stem))
    return tuple(artifacts)


def behavioral_energy_study() -> tuple[Path, ...]:
    """Plot behavioral FRIDA-2 three-layer energy per conversion versus DC input.

    Inputs are 129 behavioral MeasAdc DC captures across the full scale, 2,000
    conversions each, with the PEX capacitances and the default alternating
    A-state. The model computes VDD_DAC; the comparator and logic rails use
    PEX-measured energy per conversion, so they are flat in input. The
    record's two figures: every rail's energy, and the DAC's (VDD_DAC) alone.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_232352_frida2_energy_vs_input"
    measurements = []
    for path in sorted(read_dir.glob("[0-9][0-9][0-9]_vin*.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        measurements.append(measurement)
    # the captures in input order, the figures' x
    measurements.sort(key=lambda measurement: calc.average(measurement.vin_diff_v))
    energy = analyze_energy(measurements, power=[analyze_power(measurement) for measurement in measurements])
    return (
        *render(plot_energy_input(energy), output_dir / "frida2_3layer_behavioral_energy_vs_input"),
        *render(plot_energy_dac_input(energy), output_dir / "frida2_3layer_behavioral_dac_energy_vs_input"),
    )


def behavioral_sample_rate_study() -> tuple[Path, ...]:
    """Plot behavioral FRIDA-2 three-layer power and spectral ENOB versus rate.

    Inputs are nine behavioral MeasAdc sine captures (-0.5 dBFS, 8,192
    conversions) with the 160-symbol recipe at 0.2-6.4 GBd, i.e. 1.25-40 MS/s.
    VDD_DAC charge is computed; comparator, logic, and driver energies and
    leakage are fitted to the FRIDA-2 three-layer PEX transient. The supply
    power is the record's, every rail's together. ENOB, the record's (the
    spectral ENOB referred to full scale, ``flow.adc.plots``), uses the
    PEX-extracted weights and is limited by the assumed 0.2-ns CDAC settling
    time constant at high rates.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_232349_frida2_sample_rate"
    measurements = []
    for path in sorted(read_dir.glob("[0-9][0-9][0-9][0-9]mbd.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        measurements.append(measurement)
    powers = sorted(
        (analyze_power(measurement) for measurement in measurements), key=lambda power: power.sample_rate_hz
    )
    return (
        *render(plot_power_rate(powers), output_dir / "frida2_3layer_behavioral_power_vs_rate"),
        *render(
            plot_enob_rate(
                sorted(
                    (
                        analyze_dynamic(
                            measurement,
                            calibration=read_extracted_calibration(
                                Path(str(measurement.info.readbacks["cap_table"])), measurement
                            ),
                        )
                        for measurement in measurements
                    ),
                    key=lambda dynamic: dynamic.sample_rate_hz,
                )
            ),
            output_dir / "frida2_3layer_behavioral_enob_vs_rate",
        ),
    )


def behavioral_trajectory_study() -> tuple[Path, ...]:
    """Show redundant SAR decision paths recovering from a random first decision.

    The input is one behavioral MeasAdc: 2,000 conversions at 10 MS/s of a 0-V
    input, on the C0 threshold, with every noise source. B0 goes either way,
    and the later redundant stages bring both branches to the same codes: the
    distinct paths, each weighted by its conversions, over the whole
    conversion and over its last decisions, and the codes they end on.
    """
    output_dir = new_run("analysis", "adc")
    path = BASE_PATH / "build/scan_behavioral/20261010_114637_frida2_trajectory/trajectory_0mv.h5"
    measurement = read_measurement(path)
    if not isinstance(measurement, MeasAdc):
        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
    return tuple(_path_figures(analyze_decision_paths(measurement), output_dir, "frida2_3layer_behavioral"))


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
        train_ramp = analyze_ramp(train)
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
        # each curve as the CDAC sees it, its transition from its S-curve fit (capdac's analyses)
        switching = [analyze_switching(curve) for curve in curves]
        transitions = [
            capdac.analyze_transition([point], offset=comp.analyze_offset_noise([capdac.analyze_decisions([point])]))
            for point in switching
        ]
        cap_mismatch = capdac.analyze_cap_mismatch(
            switching, transitions=transitions, comparator=comp.analyze_offset_noise([comparator])
        )
        learned = (
            analyze_calibration1(curves, cap_mismatch=cap_mismatch),
            analyze_calibration2(train, ramp=train_ramp),
            analyze_calibration3(train, ramp=train_ramp),
        )
        extracted = read_extracted_calibration(Path(str(check.info.readbacks["cap_table"])), check)
        ramps = [analyze_ramp(check)] + [
            analyze_ramp(check, calibration=calibration) for calibration in (extracted, *learned)
        ]
        stem = f"frida2_3layer_behavioral_{train_path.stem.removesuffix('_train')}"
        artifacts.extend(_weight_figures((extracted, *learned), output_dir, f"{stem}_weights"))
        for ramp in ramps:
            artifacts.extend(_ramp_figures(ramp, output_dir, stem))
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
            train_ramp = analyze_ramp(train)
            learned = (
                analyze_calibration2(train, ramp=train_ramp),
                analyze_calibration3(train, ramp=train_ramp),
            )
            ramps = [analyze_ramp(check)] + [analyze_ramp(check, calibration=calibration) for calibration in learned]
            stem = f"{variant_dir.name}_{train_path.stem.removesuffix('_train')}"
            for ramp in ramps:
                artifacts.extend(_ramp_figures(ramp, output_dir, stem))
            artifacts.extend(_weight_figures(learned, output_dir, f"{stem}_weights"))
    return tuple(artifacts)


def behavioral_noise_spectrum_study() -> tuple[Path, ...]:
    """Draw the output-code noise spectral density of each behavioral noise source, a figure each.

    Inputs are three behavioral MeasAdc fixed-input captures (50 mV, 10 MS/s,
    100,000 conversions): the sampling switch's kT/C alone (``sampling``),
    the comparator alone (``comparator``), and the total ADC with both
    (``baseline``), each figure named by its capture. Codes are decoded with
    the PEX-extracted weights.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_114609_frida2_noise_sources"
    artifacts = []
    for name in ("sampling", "comparator", "baseline"):
        path = read_dir / f"noise_{name}.h5"
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        calibration = read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)
        spectrum = analyze_code_spectrum(measurement, calibration=calibration)
        artifacts.extend(
            render(plot_noise_spectrum(spectrum), output_dir / f"frida2_3layer_behavioral_noise_spectrum_{name}")
        )
    return tuple(artifacts)


def behavioral_input_frequency_study() -> tuple[Path, ...]:
    """Plot spectral ENOB versus input frequency at 2, 6, and 10 MS/s, a figure a rate.

    Inputs are 27 behavioral MeasAdc sine captures (-0.5 dBFS, nine input
    frequencies up to Nyquist per rate, 8,192 conversions) with every noise
    source, the input-dependent sampler, and the PEX-extracted decoding. The
    ENOB is the record's (referred to full scale, over the input frequency
    relative to the rate). The 10-MS/s captures nearest DC and Nyquist also
    get their own spectra.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_114623_frida2_input_frequency"
    dynamics = []
    for path in sorted(read_dir.glob("[0-9][0-9][0-9][0-9]mbd_[0-9][0-9][0-9][0-9]cycles.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        calibration = read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)
        dynamics.append(analyze_dynamic(measurement, calibration=calibration))
    artifacts = []
    for rate_hz in sorted({round(dynamic.sample_rate_hz) for dynamic in dynamics}):
        at_rate = sorted(
            (dynamic for dynamic in dynamics if round(dynamic.sample_rate_hz) == rate_hz),
            key=lambda dynamic: dynamic.input_frequency_hz,
        )
        stem = f"frida2_3layer_behavioral_enob_vs_input_frequency_{rate_hz / 1e6:g}msps".replace(".", "p")
        artifacts.extend(render(plot_enob_fin(at_rate), output_dir / stem))
        if rate_hz == 10_000_000:
            artifacts.extend(
                render(plot_spectrum_low(at_rate[0]), output_dir / "frida2_3layer_behavioral_10msps_low_spectrum")
            )
            artifacts.extend(
                render(
                    plot_spectrum_nyquist(at_rate[-1]), output_dir / "frida2_3layer_behavioral_10msps_nyquist_spectrum"
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
    cap_mismatch: dict[int, capdac.AnalysisCapMismatch] = {}
    for adc_index in sorted({curve_key[0] for curve_key in selected_curves}):
        comparator_measurements = []
        for path in sorted(comparator_read_dirs[adc_index].glob(f"*adc{adc_index:02d}*.h5")):
            comparator_point = read_analysis(path)
            if not isinstance(comparator_point, comp.AnalysisDecisions):
                raise TypeError(f"{path} contains {type(comparator_point).__name__}, expected comp.AnalysisDecisions")
            comparator_measurements.append(comparator_point)
        transitions = []
        switching = []
        cdac_measurements[adc_index] = []
        for curve_key in sorted(key for key in selected_curves if key[0] == adc_index):
            curve = selected_curves[curve_key]
            cdac_measurements[adc_index].extend(curve)
            # each point as the CDAC sees it; the curve's fit from its fine sweep stage where it has one
            points = [analyze_switching(point) for point in curve]
            switching.extend(points)
            fit_points = [
                point
                for point, measurement in zip(points, curve, strict=True)
                if measurement.param.sweep_stage == "fine"
            ] or points
            transitions.append(
                capdac.analyze_transition(
                    fit_points, offset=comp.analyze_offset_noise([capdac.analyze_decisions(fit_points)])
                )
            )
        cap_mismatch[adc_index] = capdac.analyze_cap_mismatch(
            switching,
            transitions=transitions,
            comparator=comp.analyze_offset_noise(comparator_measurements),
        )

    nominal_ramp = analyze_ramp(measurement)
    calibrations = (
        analyze_calibration1(cdac_measurements[adc_index], cap_mismatch=cap_mismatch[adc_index]),
        analyze_calibration2(measurement, ramp=nominal_ramp),
        analyze_calibration3(measurement, ramp=nominal_ramp),
    )
    ramps = (nominal_ramp, *(analyze_ramp(measurement, calibration=calibration) for calibration in calibrations))

    stem = f"adc{adc_index:02d}"
    return (
        *_weight_figures(calibrations, output_dir, f"{stem}_calibration_weights"),
        *(
            path
            for ramp in ramps
            for path in render(
                plot_ramp_transfer(ramp), output_dir / f"{stem}_calibration_ramp_transfer_{_decoding(ramp)}"
            )
        ),
        *(path for ramp in ramps for path in _ramp_figures(ramp, output_dir, f"{stem}_calibration")),
    )


def system_cap_mismatch_study() -> tuple[Path, ...]:
    """Extract ADC00–ADC03 capacitor mismatch from A-to-B transitions (capdac's analyses, each point
    as ``analyze_switching`` gives it) and draw each ADC's stages (capdac's specs: the effective
    fraction, its error from the design's, the P/N asymmetry, the difference plates, the main plates
    and the direction bias), ``adc<NN>_<figure>``."""
    output_dir = new_run("analysis", "adc")

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
    cap_mismatch: dict[int, capdac.AnalysisCapMismatch] = {}
    for adc_index in sorted({curve_key[0] for curve_key in selected_curves}):
        comparator_measurements = []
        for path in sorted(comparator_read_dirs[adc_index].glob(f"*adc{adc_index:02d}*.h5")):
            comparator_point = read_analysis(path)
            if not isinstance(comparator_point, comp.AnalysisDecisions):
                raise TypeError(f"{path} contains {type(comparator_point).__name__}, expected comp.AnalysisDecisions")
            comparator_measurements.append(comparator_point)
        transitions = []
        switching = []
        for curve_key in sorted(key for key in selected_curves if key[0] == adc_index):
            curve = selected_curves[curve_key]
            # each point as the CDAC sees it; the curve's fit from its fine sweep stage where it has one
            points = [analyze_switching(point) for point in curve]
            switching.extend(points)
            fit_points = [
                point
                for point, measurement in zip(points, curve, strict=True)
                if measurement.param.sweep_stage == "fine"
            ] or points
            transitions.append(
                capdac.analyze_transition(
                    fit_points, offset=comp.analyze_offset_noise([capdac.analyze_decisions(fit_points)])
                )
            )
        cap_mismatch[adc_index] = capdac.analyze_cap_mismatch(
            switching,
            transitions=transitions,
            comparator=comp.analyze_offset_noise(comparator_measurements),
        )
    figures = (
        capdac.plot_fraction_stage,
        capdac.plot_fraction_error_stage,
        capdac.plot_asymmetry_stage,
        capdac.plot_separation_stage,
        capdac.plot_main_stage,
        capdac.plot_bias_stage,
    )
    return tuple(
        path
        for adc_index, analysis in cap_mismatch.items()
        for figure in figures
        for path in render(figure(analysis), output_dir / f"adc{adc_index:02d}_{figure.__name__.removeprefix('plot_')}")
    )


def sequence_study() -> tuple[Path, ...]:
    """Compare 29 continuous recipes on 16 ADCs at 2/6/10 MSPS and selected PEX cases.

    Physical captures are the corrected 160-symbol, 100,000-conversion
    fixed-input campaign. The selected PEX cases cover the same seven
    continuous recipes on four FRIDA-1 and three FRIDA-2 flavors at 1600 MBd.
    Physical and PEX captures go through the same per-capture noise analysis
    and per-ADC (or per-flavor) operating-condition analysis; PEX cases also
    get timing closure. Operating-condition and timing-summary results are
    saved as analysis HDF5 files beside the figures. Each ADC, the chip's 16
    ADCs together and each PEX flavor get the maps over sequence and rate
    (``<adcNN|all_adc|spice_flavor>_sequence_enob``, ``_plausible``,
    ``_shift``): the noise-equivalent ENOB, a sequence a column named by its
    decision word, in the order the captures hold them.
    """
    output_dir = new_run("analysis", "adc")
    read_dir = BASE_PATH / "build/scan_adc/20260926_172920_adc_sequence_static"
    paths = sorted(read_dir.glob("[0-9][0-9][0-9][0-9]_capture.h5"))
    paths_by_adc: dict[int, list[Path]] = {}
    for path in paths:
        paths_by_adc.setdefault(read_measurement_param(path).observed_adc, []).append(path)

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[Path] = []
    conditions = []
    for adc_index, adc_paths in sorted(paths_by_adc.items()):
        measurements = []
        for path in adc_paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdc):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
            measurements.append(measurement)
        result = analyze_operating_conditions(
            measurements, noise=[analyze_noise(measurement) for measurement in measurements]
        )
        del measurements
        conditions.append(result)
        artifacts.append(write_analysis(output_dir / f"adc{adc_index:02d}_operating_conditions.h5", result))
        artifacts.extend(_sequence_figures(analyze_sequence_map([result]), output_dir, f"adc{adc_index:02d}"))
    # the chip: a cell's median ENOB where three quarters of the ADCs are plausible there
    artifacts.extend(_sequence_figures(analyze_sequence_map(conditions), output_dir, "all_adc"))

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
                # the decision paths, and the codes the case's conversions end on at its one input
                artifacts.extend(_path_figures(analyze_decision_paths(measurement), output_dir, f"spice_{case}"))
                # the top plates' settling at the first, middle and last stage, a figure each
                settling = analyze_cdac_settling(measurement)
                for figure in (
                    plot_cdac_settling_first(settling),
                    plot_cdac_settling_middle(settling),
                    plot_cdac_settling_last(settling),
                ):
                    artifacts.extend(render(figure, output_dir / f"spice_{case}_{figure.name}"))
                closure = analyze_timing_closure(measurement)
                artifacts.append(
                    write_analysis(
                        output_dir / f"{case}_timing_summary.h5",
                        analyze_timing_summary(measurement, closure=closure),
                    )
                )
                if flavor == sequence_plot_flavor:
                    # the timing's clock diagram: its programmed sequence over one period
                    artifacts.extend(
                        render(plot_sequencer(analyze_sequencer(measurement)), output_dir / f"sequence_{timing}")
                    )
                print(f"Rendered PEX case {case}", flush=True)
                measurements.append(measurement)
            noise = [analyze_noise(measurement) for measurement in measurements]
            flavor_conditions = analyze_operating_conditions(measurements, noise=noise)
            artifacts.append(write_analysis(output_dir / f"spice_{flavor}_operating_conditions.h5", flavor_conditions))
            # the flavor's timings at its one rate, as the chip's maps
            artifacts.extend(
                _sequence_figures(analyze_sequence_map([flavor_conditions]), output_dir, f"spice_{flavor}")
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
    Without the interferer, that search settles on slow drift near DC. Each
    4of8 capture's code spectrum is a figure of its own (``<run>_adc<NN>_<rate>msps_code_spectrum``:
    the record's, its white floor, its lines and the split of its variance
    into lines and broadband noise marked), and so is each ADC's alias search:
    its score over the candidate frequency, the best marked
    (``<run>_adc<NN>_interferer``), and the strongest line at each rate
    (``<run>_adc<NN>_interferer_lines``).
    """
    output_dir = new_run("analysis", "adc")
    # the deck's test labels, by run
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
    for folder in runs.values():
        stem = folder.removesuffix("_adc_sequence_static")
        measurements_by_adc: dict[int, list[MeasAdc]] = {}
        for path in sorted((BASE_PATH / "build/scan_adc" / folder).glob("[0-9][0-9][0-9][0-9]_capture.h5")):
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdc):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
            measurements_by_adc.setdefault(measurement.param.observed_adc, []).append(measurement)
        for adc_index, measurements in sorted(measurements_by_adc.items()):
            spectra = [analyze_code_spectrum(measurement) for measurement in measurements]
            # Search one recipe, whose three rates were captured minutes apart: over
            # all recipes, the drifting interferer smears and a fixed 7.143-MHz line
            # (2856 kHz at 10 MSPS) wins instead.
            selected = [index for index, spectrum in enumerate(spectra) if spectrum.sequence == shown]
            interferer = analyze_interferer(
                [measurements[index] for index in selected], spectra=[spectra[index] for index in selected]
            )
            artifacts.append(write_analysis(output_dir / f"{stem}_adc{adc_index:02d}_interferer.h5", interferer))
            for figure in (plot_interferer(interferer), plot_interferer_lines(interferer)):
                artifacts.extend(render(figure, output_dir / f"{stem}_adc{adc_index:02d}_{figure.name}"))
            for index in selected:
                # A decimal point would read as a file suffix; write 0.3125 as 0p3125.
                rate = f"{spectra[index].sample_rate_hz / 1e6:g}".replace(".", "p")
                artifacts.extend(
                    render(
                        plot_noise_spectrum(spectra[index]),
                        output_dir / f"{stem}_adc{adc_index:02d}_{rate}msps_code_spectrum",
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
    Each DC sweep's captures of one LOGIC timing, in rate order, give its
    noise, noise-equivalent ENOB and codes over the rate
    (``<stem>_logic<n>of8_noise_rate``, ``_noise_enob_rate``, ``_codes_rate``);
    the sines show the record's ENOB over the rate (the spectral ENOB referred
    to full scale) and the spectra at the sweep's two ends. Inputs are MeasAdc;
    no PEX or internal waveforms are required.
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

    # Give selected library recipes the same INIT reference as acquired rows, each labelled by its
    # LOGIC timing among the 256-symbol recipe's at comparator timing 11110000 (LOGIC n/8)
    timings = [sequence for name, sequence in SEQUENCES if name.startswith("symbol256_init8_samp16_comp11110000_")]
    sequence_labels = {}
    for sequence in selected_sequences:
        relative_sequence = sequence.relative_to_init()
        sequence_labels[relative_sequence] = f"LOGIC {timings.index(sequence) + 1}/8"

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
            noise = [analyze_noise(measurement) for measurement in measurements]
            stem = f"{meas_read_dir.name}_adc{adc_index or 0:02d}_{input_v * 1e3:g}mv_{common_v * 1e3:g}cm"
            for label in dict.fromkeys(labels):
                # one LOGIC timing's captures in rate order, a figure each quantity
                selected = sorted(
                    (noise[index] for index, name in enumerate(labels) if name == label),
                    key=lambda result: result.sample_rate_hz,
                )
                timing = f"{stem}_logic{label.split()[-1].replace('/', 'of')}"
                for figure in (plot_noise_rate(selected), plot_noise_enob_rate(selected), plot_codes_rate(selected)):
                    artifacts.extend(render(figure, output_dir / f"{timing}_{figure.name}"))

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
        dynamic = sorted(
            (analyze_dynamic(measurement) for measurement in measurements), key=lambda result: result.sample_rate_hz
        )
        stem = f"adc{adc_index or 0:02d}_logic{sequence_name}"
        artifacts.extend(render(plot_enob_rate(dynamic), output_dir / f"{stem}_spectral_vs_rate"))
        # Retain individual spectral checks at the ends of the selected sweep (its sine far below Nyquist).
        for result in dynamic[:1] + dynamic[1:][-1:]:
            # A decimal point would read as a file suffix; write 0.3125 as 0p3125.
            rate = f"{result.sample_rate_hz / 1e6:g}".replace(".", "p")
            artifacts.extend(render(plot_spectrum_low(result), output_dir / f"{stem}_{rate}msps_spectrum"))
    return tuple(artifacts)


def power_study() -> tuple[Path, ...]:
    """Plot the supply power from instrumented fixed-input MeasAdc captures over the rate.

    Coverage: ADC00/01 50/100-mV DC at 600-mV common mode over actual
    0.3125--6.25 MSPS, plus ADC00 50-mV/700-mV-common reference points.
    Requires active and baseline voltage/current or power readbacks from the
    three Keithley supplies, summed into the record's supply power over the
    rate. Manual-supply runs and PEX are not selected; internal SPICE
    waveforms are unnecessary.
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
            powers = sorted(
                (analyze_power(measurement) for measurement in measurements), key=lambda power: power.sample_rate_hz
            )
            artifacts.extend(
                render(
                    plot_power_rate(powers),
                    output_dir
                    / f"{meas_read_dir.name}_adc{adc_index or 0:02d}_{input_v * 1e3:g}mv_{common_v * 1e3:g}cm_{index}_power",
                )
            )
    return tuple(artifacts)
