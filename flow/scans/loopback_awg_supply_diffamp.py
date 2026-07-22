"""Check calibrated AWG and VIN_CM control through the THS4541 input path.

The Agilent 33250A applies a 1 MHz sine to the single-ended THS4541 input,
the E3634A sets its output common mode, and the differential probe on MSO54
CH1 measures ``Vin_p - Vin_n``. Seven safe amplitude/common-mode combinations
are captured. Each differential amplitude, frequency, and E3634A voltage
readback must agree with its target to 0.5%.

CH1 is differential and therefore cannot independently measure output common
mode. The VIN_CM assertion checks the calibrated E3634A readback as a proxy;
verifying actual ADC-side common mode requires probing Vin_p and Vin_n relative
to ground.

Run from the repository root with:

    uv run python -m flow.scans.loopback_awg_supply_diffamp

The AWG and VIN_CM outputs are disabled and reset to 0 V when the check exits,
including after an assertion or communication failure. The three ASIC supply
SMUs are not accessed by this loopback.
"""

from __future__ import annotations

import csv
from pathlib import Path
from statistics import median
from time import sleep, strftime

import numpy as np
import pytest

from basil.HL.tektronix_oscilloscope import response_value
from flow.circuit.measure import find_crossings
from flow.scans.plot import SubplotSpec, plot_time_domain_csv, write_scope_csv
from flow.scans.scan_adc import convert_vdiff_input_to_awg_supply
from flow.scans.scope import wait_for_scope_armed

MAP_DIR = Path(__file__).resolve().parent
CAPTURE_DIR = Path(__file__).resolve().parents[2] / "build" / "loopback_awg_supply_diffamp"

AWG_FREQUENCY_HZ = 1.0e6
VIN_CM_CURRENT_LIMIT_A = 10.0e-3
SCOPE_CHANNEL = 1
SCOPE_TRACKS = {SCOPE_CHANNEL: "vdiff_ch1"}

# Values in this table are sine peak amplitudes: for example 1.0 V means a
# differential waveform from -1.0 V to +1.0 V, or 2.0 Vpp. The full-scale
# case is restricted to 0.6 V common mode so each ADC input remains in the
# 0.1--1.1 V range. The smaller amplitudes exercise all three common modes.
TEST_POINTS = (
    (0.2, 0.4),
    (0.2, 0.6),
    (0.2, 0.8),
    (0.5, 0.4),
    (0.5, 0.6),
    (0.5, 0.8),
    (1.0, 0.6),
)

RELATIVE_TOLERANCE = 0.005
VDIFF_OFFSET_ABSOLUTE_TOLERANCE_V = 5.0e-3
AWG_PROGRAMMING_ABSOLUTE_TOLERANCE_V = 0.5e-3
MAX_ADC_INPUT_V = 1.2
MAX_VDIFF_PEAK_V = 1.0
MAX_ABSOLUTE_AWG_V = 2.25

SETTLE_TIME_S = 0.5
SCOPE_ACQUISITION_SETTLE_S = 0.2
SCOPE_ARM_TIMEOUT_S = 5.0
SCOPE_HORIZONTAL_SCALE_S = 5.0e-6
SCOPE_RECORD_LENGTH = 10_000
SCOPE_BANDWIDTH_HZ = 250.0e6
SCOPE_COARSE_VERTICAL_SCALE_V = 0.4


def main() -> None:
    # Validate every requested output condition before opening or changing an
    # instrument. Vin_p and Vin_n each span Vin_cm +/- Vdiff_peak/2.
    for vdiff_peak_v, vin_cm_v in TEST_POINTS:
        adc_input_min_v = vin_cm_v - vdiff_peak_v / 2.0
        adc_input_max_v = vin_cm_v + vdiff_peak_v / 2.0
        if not 0.0 < vdiff_peak_v <= MAX_VDIFF_PEAK_V:
            raise ValueError(f"Vdiff peak {vdiff_peak_v:g} V must be in 0..{MAX_VDIFF_PEAK_V:g} V")
        if not 0.0 <= adc_input_min_v <= adc_input_max_v <= MAX_ADC_INPUT_V:
            raise ValueError(
                f"Vdiff peak {vdiff_peak_v:g} V at Vin_cm={vin_cm_v:g} V "
                f"would put an ADC input outside 0..{MAX_ADC_INPUT_V:g} V"
            )
        if vdiff_peak_v == MAX_VDIFF_PEAK_V and vin_cm_v != 0.6:
            raise ValueError("the 1 V differential peak is only allowed at 0.6 V common mode")

        awg_for_positive_vdiff_v, vin_cm_supply_v = convert_vdiff_input_to_awg_supply(vdiff_peak_v, vin_cm_v)
        awg_for_negative_vdiff_v, negative_peak_supply_v = convert_vdiff_input_to_awg_supply(-vdiff_peak_v, vin_cm_v)
        if vin_cm_supply_v != pytest.approx(negative_peak_supply_v):
            raise ValueError("VIN_CM conversion unexpectedly depends on differential voltage")
        if not 0.0 <= vin_cm_supply_v <= MAX_ADC_INPUT_V:
            raise ValueError(f"calibrated VIN_CM supply setpoint {vin_cm_supply_v:g} V is unsafe")
        if max(abs(awg_for_positive_vdiff_v), abs(awg_for_negative_vdiff_v)) > MAX_ABSOLUTE_AWG_V:
            raise ValueError(f"calibrated AWG waveform exceeds the validated +/-{MAX_ABSOLUTE_AWG_V:g} V range")

    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    awg_dut = Dut(str(MAP_DIR / "map_awg.yaml"))
    supply_dut = Dut(str(MAP_DIR / "map_supply.yaml"))
    scope_dut = Dut(str(MAP_DIR / "map_scope.yaml"))
    initialized_duts = []
    awg = None
    supply = None
    scope = None
    scope_state = None
    run_timestamp = strftime("%Y%m%d_%H%M%S")
    summary_rows: list[dict[str, float | str | int]] = []

    try:
        # Initialize each source and immediately make it safe before changing
        # any range or waveform. All later hardware operations remain visible
        # here as direct Basil calls.
        awg_dut.init()
        initialized_duts.append(awg_dut)
        awg = awg_dut["awg"]
        awg.set_DC("DEF,DEF,0")
        awg.set_enable(0)

        supply_dut.init()
        initialized_duts.append(supply_dut)
        supply = supply_dut["vocm_supply"]
        supply.set_enable(0)
        supply.set_voltage(0.0)

        scope_dut.init()
        initialized_duts.append(scope_dut)
        scope = scope_dut["scope"]

        print(f"AWG: {str(awg.get_name()).strip()}")
        print(f"VIN_CM supply: {str(supply.get_name()).strip()}")
        print(f"Scope: {str(scope.get_name()).strip()}")

        probe_type = str(scope._intf.query(f"CH{SCOPE_CHANNEL}:PROBE:ID:TYPE?")).strip().strip('"')
        probe_resistance_ohm = float(response_value(scope._intf.query(f"CH{SCOPE_CHANNEL}:PROBE:RESISTANCE?")))
        probe_gain = float(response_value(scope._intf.query(f"CH{SCOPE_CHANNEL}:PROBE:GAIN?")))
        print(
            f"Scope CH{SCOPE_CHANNEL}: probe={probe_type}, "
            f"input_resistance={probe_resistance_ohm:g} ohm, gain={probe_gain:g}"
        )
        if probe_type.upper() != "TDP3500":
            raise RuntimeError(f"scope CH{SCOPE_CHANNEL} has {probe_type!r}; connect the TDP3500 differential probe")
        if probe_resistance_ohm < 10.0e3:
            raise RuntimeError(f"unexpected TDP3500 input resistance {probe_resistance_ohm:g} ohm")

        # Save each scope setting changed below. The TDP3500 requires the
        # scope's internal 50-ohm termination, so this loopback deliberately
        # does not request a 1-Mohm scope input.
        scope_state = {
            "acquire_state": response_value(scope.get_acquire_state()),
            "acquire_stop_after": response_value(scope.get_acquire_stop_after()),
            "acquire_mode": response_value(scope.get_acquire_mode()),
            "horizontal_scale": response_value(scope.get_horizontal_scale()),
            "horizontal_record_length": response_value(scope.get_horizontal_record_length()),
            "horizontal_position": response_value(scope._intf.query("HORizontal:POSition?")),
            "trigger_mode": response_value(scope.get_trigger_mode()),
            "trigger_type": response_value(scope.get_trigger_type()),
            "trigger_source": response_value(scope.get_triggr_source()),
            "trigger_slope": response_value(scope.get_trigger_edge_slope()),
            "trigger_level": response_value(scope.get_trigger_level(channel=SCOPE_CHANNEL)),
            "coupling": response_value(scope.get_coupling(channel=SCOPE_CHANNEL)),
            "impedance": response_value(scope.get_impedance(channel=SCOPE_CHANNEL)),
            "vertical_scale": response_value(scope.get_vertical_scale(channel=SCOPE_CHANNEL)),
            "vertical_position": response_value(scope.get_vertical_position(channel=SCOPE_CHANNEL)),
            "vertical_offset": response_value(scope.get_vertical_offset(channel=SCOPE_CHANNEL)),
            "bandwidth": response_value(scope.get_bandwidth(channel=SCOPE_CHANNEL)),
            "display": response_value(scope._intf.query(f"DISplay:GLObal:CH{SCOPE_CHANNEL}:STATE?")),
        }

        scope.set_acquire_state("STOP")
        scope.set_acquire_mode("SAMPLE")
        scope.set_acquire_stop_after("RUNSTOP")
        scope.set_horizontal_scale(SCOPE_HORIZONTAL_SCALE_S)
        scope.set_horizontal_record_length(SCOPE_RECORD_LENGTH)
        scope._intf.write("HORizontal:POSition 50")
        scope._intf.write(f"DISplay:GLObal:CH{SCOPE_CHANNEL}:STATE ON")
        scope.set_coupling("DC", channel=SCOPE_CHANNEL)
        scope.set_vertical_position(0, channel=SCOPE_CHANNEL)
        scope.set_vertical_offset(0.0, channel=SCOPE_CHANNEL)
        scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=SCOPE_CHANNEL)
        scope.set_trigger_type("EDGE")
        scope.set_trigger_source(channel=SCOPE_CHANNEL)
        scope.set_trigger_edge_slope("RISE")
        scope.set_trigger_mode("NORMAL")

        supply.set_voltage_range("P25V")
        supply.set_current_limit(VIN_CM_CURRENT_LIMIT_A)
        assert float(supply.get_current_limit()) == pytest.approx(
            VIN_CM_CURRENT_LIMIT_A,
            rel=RELATIVE_TOLERANCE,
        )
        awg.set_output_load("INFinity")
        awg.set_voltage_unit("VPP")
        awg.set_output_polarity("NORMal")
        assert float(str(awg.get_output_load()).strip().split(",")[0]) >= 1.0e6
        assert str(awg.get_voltage_unit()).strip().upper() == "VPP"
        assert str(awg.get_output_polarity()).strip().upper().startswith("NORM")

        for test_index, (vdiff_peak_v, vin_cm_v) in enumerate(TEST_POINTS, start=1):
            target_vdiff_vpp = 2.0 * vdiff_peak_v
            adc_input_min_v = vin_cm_v - vdiff_peak_v / 2.0
            adc_input_max_v = vin_cm_v + vdiff_peak_v / 2.0

            # Evaluate the software calibration at both sine extrema. Its
            # midpoint and separation are the AWG offset and Vpp required to
            # produce the requested ADC-side differential sine.
            awg_for_positive_vdiff_v, vin_cm_supply_v = convert_vdiff_input_to_awg_supply(vdiff_peak_v, vin_cm_v)
            awg_for_negative_vdiff_v, negative_peak_supply_v = convert_vdiff_input_to_awg_supply(
                -vdiff_peak_v, vin_cm_v
            )
            assert vin_cm_supply_v == pytest.approx(negative_peak_supply_v)
            awg_offset_v = (awg_for_positive_vdiff_v + awg_for_negative_vdiff_v) / 2.0
            awg_amplitude_vpp = abs(awg_for_negative_vdiff_v - awg_for_positive_vdiff_v)

            print(
                f"\n[{test_index}/{len(TEST_POINTS)}] "
                f"target Vdiff=+/-{vdiff_peak_v:.3f} V "
                f"({target_vdiff_vpp:.3f} Vpp), Vin_cm={vin_cm_v:.3f} V"
            )
            print(
                f"  implied Vin_p/Vin_n range={adc_input_min_v:.3f}.."
                f"{adc_input_max_v:.3f} V; AWG={awg_amplitude_vpp:.6f} Vpp "
                f"at {awg_offset_v:.6f} V; VIN_CM supply={vin_cm_supply_v:.6f} V"
            )

            # Disable the AWG while moving both stimulus setpoints. Program
            # and verify the VIN_CM source before enabling the sine wave.
            awg.set_enable(0)
            supply.set_voltage(vin_cm_supply_v)
            supply.set_enable(1)
            sleep(SETTLE_TIME_S)

            vin_cm_programmed_v = float(supply.get_set_voltage())
            vin_cm_measured_v = float(supply.get_voltage())
            vin_cm_measured_a = float(supply.get_current())
            assert vin_cm_programmed_v == pytest.approx(
                vin_cm_supply_v,
                rel=RELATIVE_TOLERANCE,
            )
            # This is the calibrated supply readback, not an independent
            # measurement of ADC-side common mode.
            assert abs(vin_cm_measured_a) < VIN_CM_CURRENT_LIMIT_A

            awg.set_sin(f"{AWG_FREQUENCY_HZ},{awg_amplitude_vpp},{awg_offset_v}")
            awg_function = str(awg.get_function()).strip().strip('"')
            awg_frequency_readback_hz = float(awg.get_frequency())
            awg_offset_readback_v = float(str(awg.get_voltage_offset()).strip().split(",")[0])
            awg_high_readback_v = float(awg.get_voltage_high())
            awg_low_readback_v = float(awg.get_voltage_low())
            awg_amplitude_readback_vpp = awg_high_readback_v - awg_low_readback_v
            if not awg_function.upper().startswith("SIN"):
                raise RuntimeError(f"AWG did not enter sine mode: {awg_function!r}")
            assert awg_frequency_readback_hz == pytest.approx(
                AWG_FREQUENCY_HZ,
                rel=RELATIVE_TOLERANCE,
            )
            assert awg_amplitude_readback_vpp == pytest.approx(
                awg_amplitude_vpp,
                rel=RELATIVE_TOLERANCE,
            )
            assert awg_offset_readback_v == pytest.approx(
                awg_offset_v,
                rel=RELATIVE_TOLERANCE,
                abs=AWG_PROGRAMMING_ABSOLUTE_TOLERANCE_V,
            )
            if max(abs(awg_low_readback_v), abs(awg_high_readback_v)) > MAX_ABSOLUTE_AWG_V:
                raise RuntimeError(
                    "unsafe AWG level readback before enable: "
                    f"low={awg_low_readback_v:g} V, high={awg_high_readback_v:g} V"
                )

            # First capture on a wide vertical range to find the actual
            # differential DC center. Common-mode-dependent differential offset
            # is one of the effects this loopback is intended to reveal.
            scope.set_vertical_scale(
                SCOPE_COARSE_VERTICAL_SCALE_V,
                channel=SCOPE_CHANNEL,
            )
            scope.set_vertical_offset(0.0, channel=SCOPE_CHANNEL)
            scope.set_trigger_level(
                1.5,
                channel=SCOPE_CHANNEL,
            )
            scope.set_acquire_state("STOP")
            scope._intf.write("ACQuire:NUMACq:RESET")
            scope.set_acquire_state("RUN")
            wait_for_scope_armed(scope, timeout_s=SCOPE_ARM_TIMEOUT_S)
            awg.set_enable(1)
            sleep(SETTLE_TIME_S)
            scope.force_trigger()
            sleep(SCOPE_ACQUISITION_SETTLE_S)
            scope.set_acquire_state("STOP")

            coarse_waveforms = scope.get_waveforms((SCOPE_CHANNEL,))
            if SCOPE_CHANNEL not in coarse_waveforms:
                raise RuntimeError(f"scope did not return coarse CH{SCOPE_CHANNEL}")
            coarse_waveform = coarse_waveforms[SCOPE_CHANNEL]
            coarse_samples = np.asarray(coarse_waveform.data, dtype=float)
            if coarse_samples.size == 0:
                raise RuntimeError(f"scope returned an empty coarse CH{SCOPE_CHANNEL} waveform")
            coarse_low_v, coarse_high_v = np.percentile(coarse_samples, (0.5, 99.5))
            coarse_offset_v = float((coarse_low_v + coarse_high_v) / 2.0)
            coarse_vpp = float(coarse_high_v - coarse_low_v)
            print(f"  coarse scope: offset={coarse_offset_v:.6f} V, Vpp={coarse_vpp:.6f} V")
            if coarse_vpp == 0.0:
                coarse_name = (
                    f"coarse_vdiff{round(1e3 * vdiff_peak_v):04d}mvpeak_"
                    f"vcm{round(1e3 * vin_cm_v):04d}mv_{run_timestamp}.csv"
                )
                coarse_path = CAPTURE_DIR / coarse_name
                write_scope_csv(coarse_path, coarse_waveforms, SCOPE_TRACKS)
                raise AssertionError(f"coarse CH{SCOPE_CHANNEL} capture is flat; saved {coarse_path}")

            # Center a second acquisition on the measured offset and use about
            # eight divisions for the requested Vpp. This preserves resolution
            # for the 0.5% amplitude assertion without assuming zero offset.
            scope.set_vertical_offset(coarse_offset_v, channel=SCOPE_CHANNEL)
            scope.set_vertical_scale(
                target_vdiff_vpp / 8.0,
                channel=SCOPE_CHANNEL,
            )
            scope.set_trigger_level(
                coarse_offset_v + 2.0 * vdiff_peak_v,
                channel=SCOPE_CHANNEL,
            )
            scope.set_acquire_state("STOP")
            scope._intf.write("ACQuire:NUMACq:RESET")
            scope.set_acquire_state("RUN")
            wait_for_scope_armed(scope, timeout_s=SCOPE_ARM_TIMEOUT_S)
            scope.force_trigger()
            sleep(SCOPE_ACQUISITION_SETTLE_S)
            scope.set_acquire_state("STOP")

            waveforms = scope.get_waveforms((SCOPE_CHANNEL,))
            awg.set_enable(0)
            if SCOPE_CHANNEL not in waveforms:
                raise RuntimeError(f"scope did not return fine CH{SCOPE_CHANNEL}")
            waveform = waveforms[SCOPE_CHANNEL]
            samples = np.asarray(waveform.data, dtype=float)
            if samples.size == 0:
                raise RuntimeError(f"scope returned an empty CH{SCOPE_CHANNEL} waveform")
            times = waveform.x_scale.offset + np.arange(samples.size) * waveform.x_scale.slope
            low_v, high_v = np.percentile(samples, (0.5, 99.5))
            crossing_level_v = float((low_v + high_v) / 2.0)

            point_name = f"vdiff{round(1e3 * vdiff_peak_v):04d}mvpeak_vcm{round(1e3 * vin_cm_v):04d}mv_{run_timestamp}"
            csv_path = CAPTURE_DIR / f"{point_name}.csv"
            # Save the raw capture before analysis so a failed assertion still
            # leaves the exact waveform available for diagnosis.
            write_scope_csv(csv_path, waveforms, SCOPE_TRACKS)
            print(f"  saved {samples.size} samples spanning {times[-1] - times[0]:.9g} s: {csv_path}")

            raw_crossings = find_crossings(
                samples,
                times,
                crossing_level_v,
                rising=True,
            )
            minimum_crossing_separation_s = 0.75 / AWG_FREQUENCY_HZ
            rising_crossings = []
            for crossing in raw_crossings:
                if not rising_crossings or crossing - rising_crossings[-1] >= minimum_crossing_separation_s:
                    rising_crossings.append(crossing)
            if len(rising_crossings) < 3:
                raise AssertionError(f"scope CH{SCOPE_CHANNEL} has only {len(rising_crossings)} rising crossings")
            measured_frequency_hz = float(1.0 / median(np.diff(rising_crossings)))

            # Fit the DC term and fundamental sine independently. Percentile
            # extrema are useful for finding crossings, but would mix even
            # harmonics and digitizer noise into the reported amplitude and
            # differential offset.
            fit_matrix = np.column_stack(
                (
                    np.ones_like(times),
                    np.sin(2.0 * np.pi * measured_frequency_hz * times),
                    np.cos(2.0 * np.pi * measured_frequency_hz * times),
                )
            )
            fit_coefficients = np.linalg.lstsq(
                fit_matrix,
                samples,
                rcond=None,
            )[0]
            fitted_samples = fit_matrix @ fit_coefficients
            measured_vdiff_offset_v = float(fit_coefficients[0])
            measured_vdiff_vpp = float(2.0 * np.hypot(fit_coefficients[1], fit_coefficients[2]))
            measured_residual_rms_v = float(np.sqrt(np.mean((samples - fitted_samples) ** 2)))

            plot_paths = plot_time_domain_csv(
                csv_path,
                {
                    "vdiff_ch1_v": SubplotSpec(
                        ylabel="CH1 differential voltage (V)",
                        info_lines=(
                            f"Target: {AWG_FREQUENCY_HZ / 1e6:.6f} MHz, +/-{vdiff_peak_v:.6f} V ({target_vdiff_vpp:.6f} Vpp)",
                            f"Target Vin_cm: {vin_cm_v:.6f} V; implied inputs: {adc_input_min_v:.6f}..{adc_input_max_v:.6f} V",
                            f"AWG: {awg_amplitude_vpp:.6f} Vpp, {awg_offset_v:.6f} V offset",
                            f"VIN_CM proxy: set={vin_cm_supply_v:.6f} V, read={vin_cm_measured_v:.6f} V",
                            f"Measured: {measured_frequency_hz / 1e6:.6f} MHz, {measured_vdiff_vpp:.6f} Vpp, {measured_vdiff_offset_v:.6f} V offset",
                            f"Sine-fit residual: {measured_residual_rms_v * 1e3:.3f} mV RMS",
                        ),
                    )
                },
                title=(f"THS4541 differential loopback: Vdiff=+/-{vdiff_peak_v:g} V, Vin_cm={vin_cm_v:g} V"),
            )
            for plot_path in plot_paths:
                print(f"  saved waveform plot: {plot_path}")

            print(
                f"  analyzed: scope={measured_frequency_hz / 1e6:.6f} MHz, "
                f"{measured_vdiff_vpp:.6f} Vpp, "
                f"offset={measured_vdiff_offset_v:.6f} V; "
                f"fit residual={measured_residual_rms_v * 1e3:.3f} mV RMS; "
                f"VIN_CM proxy={vin_cm_measured_v:.6f} V"
            )
            summary_rows.append(
                {
                    "test_index": test_index,
                    "target_vdiff_peak_v": vdiff_peak_v,
                    "target_vdiff_vpp": target_vdiff_vpp,
                    "target_vin_cm_v": vin_cm_v,
                    "adc_input_min_v": adc_input_min_v,
                    "adc_input_max_v": adc_input_max_v,
                    "awg_frequency_hz": awg_frequency_readback_hz,
                    "awg_amplitude_vpp": awg_amplitude_readback_vpp,
                    "awg_offset_v": awg_offset_readback_v,
                    "vin_cm_supply_set_v": vin_cm_programmed_v,
                    "vin_cm_supply_read_v": vin_cm_measured_v,
                    "vin_cm_supply_current_a": vin_cm_measured_a,
                    "measured_frequency_hz": measured_frequency_hz,
                    "measured_vdiff_vpp": measured_vdiff_vpp,
                    "measured_vdiff_offset_v": measured_vdiff_offset_v,
                    "measured_residual_rms_v": measured_residual_rms_v,
                    "frequency_relative_error": measured_frequency_hz / AWG_FREQUENCY_HZ - 1.0,
                    "vdiff_vpp_relative_error": measured_vdiff_vpp / target_vdiff_vpp - 1.0,
                    "vin_cm_relative_error": vin_cm_measured_v / vin_cm_v - 1.0,
                    "frequency_within_tolerance": abs(measured_frequency_hz / AWG_FREQUENCY_HZ - 1.0)
                    <= RELATIVE_TOLERANCE,
                    "vdiff_vpp_within_tolerance": abs(measured_vdiff_vpp / target_vdiff_vpp - 1.0)
                    <= RELATIVE_TOLERANCE,
                    "vin_cm_within_tolerance": abs(vin_cm_measured_v / vin_cm_v - 1.0) <= RELATIVE_TOLERANCE,
                    "vdiff_offset_within_tolerance": abs(measured_vdiff_offset_v) <= VDIFF_OFFSET_ABSOLUTE_TOLERANCE_V,
                    "scope_csv": str(csv_path),
                }
            )

        summary_path = CAPTURE_DIR / f"summary_{run_timestamp}.csv"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("w", newline="") as summary_file:
            writer = csv.DictWriter(
                summary_file,
                fieldnames=list(summary_rows[0]),
            )
            writer.writeheader()
            writer.writerows(summary_rows)
        print(f"Saved loopback summary: {summary_path}")

        # Pytest's comparison objects provide concise, value-rich failure
        # reports even though this guarded loopback is run as a module. Run the
        # accuracy checks only after every point and its artifacts are saved.
        for row in summary_rows:
            label = (
                f"point {row['test_index']} (Vdiff={row['target_vdiff_vpp']} Vpp, Vin_cm={row['target_vin_cm_v']} V)"
            )
            assert row["vin_cm_supply_read_v"] == pytest.approx(
                row["target_vin_cm_v"],
                rel=RELATIVE_TOLERANCE,
            ), (
                f"{label}: VIN_CM proxy measured {row['vin_cm_supply_read_v']} V, "
                f"expected {row['target_vin_cm_v']} V within 0.5%"
            )
            assert row["measured_frequency_hz"] == pytest.approx(
                AWG_FREQUENCY_HZ,
                rel=RELATIVE_TOLERANCE,
            ), f"{label}: measured {row['measured_frequency_hz']} Hz, expected {AWG_FREQUENCY_HZ} Hz within 0.5%"
            assert row["measured_vdiff_vpp"] == pytest.approx(
                row["target_vdiff_vpp"],
                rel=RELATIVE_TOLERANCE,
            ), f"{label}: measured {row['measured_vdiff_vpp']} Vpp, expected {row['target_vdiff_vpp']} Vpp within 0.5%"
            # Relative error is undefined for the intended zero differential
            # DC offset, so constrain it separately to 5 mV.
            assert row["measured_vdiff_offset_v"] == pytest.approx(
                0.0,
                abs=VDIFF_OFFSET_ABSOLUTE_TOLERANCE_V,
            ), (
                f"{label}: measured differential offset "
                f"{row['measured_vdiff_offset_v']} V, expected 0 V +/- "
                f"{VDIFF_OFFSET_ABSOLUTE_TOLERANCE_V} V"
            )
        print(f"\nPASS: all {len(TEST_POINTS)} differential-amplifier points passed")
    finally:
        # Make both physical sources safe before restoring display settings or
        # closing instrument sessions.
        if awg is not None:
            try:
                awg.set_DC("DEF,DEF,0")
                # APPLy:DC enables the 33250A output, so disabling must be the
                # final operation in this shutdown sequence.
                awg.set_enable(0)
            except Exception as error:
                print(f"WARNING: could not disable and zero the AWG: {error}")

        if supply is not None:
            try:
                supply.set_enable(0)
                supply.set_voltage(0.0)
            except Exception as error:
                print(f"WARNING: could not disable and zero VIN_CM: {error}")

        if scope is not None and scope_state is not None:
            try:
                scope.set_acquire_state("STOP")
                scope.set_acquire_mode(scope_state["acquire_mode"])
                scope.set_horizontal_scale(scope_state["horizontal_scale"])
                scope.set_horizontal_record_length(scope_state["horizontal_record_length"])
                scope._intf.write(f"HORizontal:POSition {scope_state['horizontal_position']}")
                scope.set_trigger_mode(scope_state["trigger_mode"])
                scope.set_trigger_type(scope_state["trigger_type"])
                scope._intf.write(f"TRIGger:A:EDGe:SOUrce {scope_state['trigger_source']}")
                scope.set_trigger_edge_slope(scope_state["trigger_slope"])
                scope.set_trigger_level(
                    scope_state["trigger_level"],
                    channel=SCOPE_CHANNEL,
                )
                scope.set_coupling(scope_state["coupling"], channel=SCOPE_CHANNEL)
                scope.set_impedance(
                    scope_state["impedance"],
                    channel=SCOPE_CHANNEL,
                )
                scope.set_vertical_scale(
                    scope_state["vertical_scale"],
                    channel=SCOPE_CHANNEL,
                )
                scope.set_vertical_position(
                    scope_state["vertical_position"],
                    channel=SCOPE_CHANNEL,
                )
                scope.set_vertical_offset(
                    scope_state["vertical_offset"],
                    channel=SCOPE_CHANNEL,
                )
                scope.set_bandwidth(
                    scope_state["bandwidth"],
                    channel=SCOPE_CHANNEL,
                )
                scope._intf.write(f"DISplay:GLObal:CH{SCOPE_CHANNEL}:STATE {scope_state['display']}")
                scope.set_acquire_stop_after(scope_state["acquire_stop_after"])
                scope.set_acquire_state(scope_state["acquire_state"])
            except Exception as error:
                print(f"WARNING: could not fully restore scope settings: {error}")

        for dut in reversed(initialized_duts):
            dut.close()


if __name__ == "__main__":
    main()
