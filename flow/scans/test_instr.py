"""End-to-end test of the FRIDA laboratory instruments and cabling.

The Agilent 33250A drives scope CH1 with a sine wave, and output 1 of the
TTi QL355TP drives scope CH2 with a DC level. The scope triggers from CH1,
captures both inputs, and the test checks the measured frequency, amplitude,
offset, and DC voltage against the programmed values.

Run from the repository root with:

    uv run python -m flow.scans.test_instr

Both source outputs are disabled and reset to 0 V when the test exits,
including after a failed assertion or communication error.
"""

from __future__ import annotations

import time
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np

from basil.HL.tektronix_oscilloscope import response_value
from flow.circuit.measure import find_crossings
from flow.scans.instruments import instrument_dut
from flow.scans.plot import SubplotSpec, plot_frequency_domain_csv, plot_time_domain_csv, write_scope_csv
from flow.scans.scope import wait_for_scope_armed, wait_for_scope_capture

MAP_DIR = Path(__file__).resolve().parent
CAPTURE_DIR = Path("build/scope")

AWG_SCOPE_CHANNEL = 1
SUPPLY_SCOPE_CHANNEL = 2
SUPPLY_OUTPUT_CHANNEL = 1

AWG_FREQUENCY_HZ = 20.0e6
AWG_AMPLITUDE_VPP = 1.0
AWG_OFFSET_V = 0.6
SUPPLY_DC_V = 0.6
SUPPLY_CURRENT_LIMIT_A = 0.010

SCOPE_HORIZONTAL_SCALE_S = 200.0e-9
SCOPE_RECORD_LENGTH = 10_000
SCOPE_CH1_SCALE_V = 0.2
SCOPE_CH2_SCALE_V = 0.02
SCOPE_BANDWIDTH_HZ = 250.0e6
SCOPE_ARM_TRIGGER_LEVEL_V = 1.3
SETTLE_TIME_S = 0.2
CAPTURE_TIMEOUT_S = 5.0

AMPLITUDE_RELATIVE_TOLERANCE = 0.08
FREQUENCY_RELATIVE_TOLERANCE = 0.02
VOLTAGE_ABSOLUTE_TOLERANCE_V = 0.05

SCOPE_TRACKS = {
    AWG_SCOPE_CHANNEL: "awg_ch1",
    SUPPLY_SCOPE_CHANNEL: "supply_ch2",
}


def assert_close(
    label: str,
    measured: float,
    expected: float,
    *,
    relative_tolerance: float = 0.0,
    absolute_tolerance: float = 0.0,
) -> None:
    """Assert a measurement is within the requested absolute/relative limit."""
    error = abs(measured - expected)
    limit = max(absolute_tolerance, relative_tolerance * abs(expected))
    assert error <= limit, (
        f"{label}: measured {measured:g}, expected {expected:g}, "
        f"error {error:g} exceeds tolerance {limit:g}"
    )


def measure_capture(waveforms: dict[int, Any]) -> dict[str, float]:
    """Extract AWG sine parameters and the supply DC level from a capture."""
    awg_waveform = waveforms[AWG_SCOPE_CHANNEL]
    awg_signal = np.asarray(awg_waveform.data, dtype=float)
    awg_times = awg_waveform.x_scale.offset + np.arange(len(awg_signal)) * awg_waveform.x_scale.slope

    low_v, high_v = np.percentile(awg_signal, (0.5, 99.5))
    awg_offset_v = float((low_v + high_v) / 2.0)
    awg_amplitude_vpp = float(high_v - low_v)
    raw_crossings = find_crossings(awg_signal, awg_times, awg_offset_v, rising=True)
    minimum_crossing_separation_s = 0.75 / AWG_FREQUENCY_HZ
    rising_crossings = []
    for crossing in raw_crossings:
        if not rising_crossings or crossing - rising_crossings[-1] >= minimum_crossing_separation_s:
            rising_crossings.append(crossing)
    if len(rising_crossings) < 3:
        raise AssertionError(f"AWG waveform has only {len(rising_crossings)} rising crossings; expected at least 3")
    periods_s = np.diff(rising_crossings)
    awg_frequency_hz = float(1.0 / median(periods_s))

    supply_signal = np.asarray(waveforms[SUPPLY_SCOPE_CHANNEL].data, dtype=float)
    supply_dc_v = float(np.median(supply_signal))
    supply_rms_noise_v = float(np.sqrt(np.mean((supply_signal - np.mean(supply_signal)) ** 2)))

    return {
        "awg_frequency_hz": awg_frequency_hz,
        "awg_amplitude_vpp": awg_amplitude_vpp,
        "awg_offset_v": awg_offset_v,
        "supply_dc_v": supply_dc_v,
        "supply_rms_noise_v": supply_rms_noise_v,
    }


def save_capture(waveforms: dict[int, Any], measurements: dict[str, float]) -> None:
    """Save captured samples plus time-domain and spectrum plots."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    csv_path = CAPTURE_DIR / f"instruments_{timestamp}.csv"
    write_scope_csv(csv_path, waveforms, SCOPE_TRACKS)
    awg_info = (
        f"Nominal: AC {AWG_FREQUENCY_HZ / 1e6:.6g} MHz, {AWG_AMPLITUDE_VPP:.6g} Vpp, "
        f"{AWG_OFFSET_V:.6g} V DC",
        f"Measured: {measurements['awg_frequency_hz'] / 1e6:.6g} MHz, "
        f"{measurements['awg_amplitude_vpp']:.6g} Vpp, {measurements['awg_offset_v']:.6g} V DC",
    )
    supply_info = (
        f"Nominal: {SUPPLY_DC_V:.6g} V DC",
        f"Measured: {measurements['supply_dc_v']:.6g} V DC, "
        f"{measurements['supply_rms_noise_v'] * 1e3:.6g} mV RMS noise",
    )
    time_subplots = {
        f"{SCOPE_TRACKS[AWG_SCOPE_CHANNEL]}_v": SubplotSpec(
            ylabel="AWG CH1 (V)", info_lines=awg_info
        ),
        f"{SCOPE_TRACKS[SUPPLY_SCOPE_CHANNEL]}_v": SubplotSpec(
            ylabel="Supply CH2 (V)", info_lines=supply_info
        ),
    }
    spectrum_subplots = {
        f"{SCOPE_TRACKS[AWG_SCOPE_CHANNEL]}_v": SubplotSpec(
            ylabel="AWG CH1 (dBV)", info_lines=awg_info
        ),
        f"{SCOPE_TRACKS[SUPPLY_SCOPE_CHANNEL]}_v": SubplotSpec(
            ylabel="Supply CH2 (dBV)", info_lines=supply_info
        ),
    }
    plot_paths = plot_time_domain_csv(
        csv_path,
        time_subplots,
        title="Instrument loopback: AWG on CH1, supply on CH2",
    )
    for plot_path in plot_paths:
        print(f"Saved scope waveform plot: {plot_path}")
    spectrum_paths = plot_frequency_domain_csv(
        csv_path,
        spectrum_subplots,
        title="Instrument loopback spectrum: AWG on CH1, supply on CH2",
        max_frequency_hz=5.0 * AWG_FREQUENCY_HZ,
    )
    for plot_path in spectrum_paths:
        print(f"Saved scope spectrum plot: {plot_path}")


def read_scope_state(scope: Any) -> dict[str, Any]:
    """Read the scope settings changed by this test."""
    state = {
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
        "trigger_level_ch1": response_value(scope.get_trigger_level(channel=AWG_SCOPE_CHANNEL)),
    }
    for channel in SCOPE_TRACKS:
        state[f"ch{channel}_coupling"] = response_value(scope.get_coupling(channel=channel))
        state[f"ch{channel}_impedance"] = response_value(scope.get_impedance(channel=channel))
        state[f"ch{channel}_scale"] = response_value(scope.get_vertical_scale(channel=channel))
        state[f"ch{channel}_position"] = response_value(scope.get_vertical_position(channel=channel))
        state[f"ch{channel}_offset"] = response_value(scope.get_vertical_offset(channel=channel))
        state[f"ch{channel}_bandwidth"] = response_value(scope.get_bandwidth(channel=channel))
    return state


def restore_scope_state(scope: Any, state: dict[str, Any]) -> None:
    """Best-effort restoration of the settings captured by ``read_scope_state``."""
    try:
        scope.set_acquire_state("STOP")
        scope.set_acquire_mode(state["acquire_mode"])
        scope.set_horizontal_scale(state["horizontal_scale"])
        scope.set_horizontal_record_length(state["horizontal_record_length"])
        scope._intf.write(f"HORizontal:POSition {state['horizontal_position']}")
        scope.set_trigger_mode(state["trigger_mode"])
        scope.set_trigger_type(state["trigger_type"])
        scope._intf.write(f"TRIGger:A:EDGe:SOUrce {state['trigger_source']}")
        scope.set_trigger_edge_slope(state["trigger_slope"])
        scope.set_trigger_level(state["trigger_level_ch1"], channel=AWG_SCOPE_CHANNEL)
        for channel in SCOPE_TRACKS:
            scope.set_coupling(state[f"ch{channel}_coupling"], channel=channel)
            scope.set_impedance(state[f"ch{channel}_impedance"], channel=channel)
            scope.set_vertical_scale(state[f"ch{channel}_scale"], channel=channel)
            scope.set_vertical_position(state[f"ch{channel}_position"], channel=channel)
            scope.set_vertical_offset(state[f"ch{channel}_offset"], channel=channel)
            scope.set_bandwidth(state[f"ch{channel}_bandwidth"], channel=channel)
        scope.set_acquire_stop_after(state["acquire_stop_after"])
        scope.set_acquire_state(state["acquire_state"])
    except Exception as error:
        print(f"Warning: could not fully restore scope settings: {error}")


def main() -> None:
    awg_dut = instrument_dut(MAP_DIR / "map_awg.yaml")
    supply_dut = instrument_dut(MAP_DIR / "map_supply.yaml")
    scope_dut = instrument_dut(MAP_DIR / "map_scope.yaml")
    initialized_duts = []
    awg = supply = scope = None
    scope_state = None

    try:
        for dut in (awg_dut, supply_dut, scope_dut):
            dut.init()
            initialized_duts.append(dut)

        awg = awg_dut["awg"]
        supply = supply_dut["supply"]
        scope = scope_dut["scope"]
        print(f"AWG: {str(awg.get_name()).strip()}")
        print(f"Supply: {str(supply.get_name()).strip()}")
        print(f"Scope: {str(scope.get_name()).strip()}")

        awg.set_DC("DEF,DEF,0")
        awg.set_enable(0)
        supply.set_enable(False, channel=SUPPLY_OUTPUT_CHANNEL)
        supply.set_voltage(0.0, channel=SUPPLY_OUTPUT_CHANNEL)
        scope_state = read_scope_state(scope)

        scope.set_acquire_state("STOP")
        scope.set_acquire_mode("SAMPLE")
        scope.set_acquire_stop_after("SEQUENCE")
        scope.set_horizontal_scale(SCOPE_HORIZONTAL_SCALE_S)
        scope.set_horizontal_record_length(SCOPE_RECORD_LENGTH)
        scope._intf.write("HORizontal:POSition 50")
        scope.set_coupling("DC", channel=AWG_SCOPE_CHANNEL)
        scope.set_impedance(1.0e6, channel=AWG_SCOPE_CHANNEL)
        scope.set_vertical_scale(SCOPE_CH1_SCALE_V, channel=AWG_SCOPE_CHANNEL)
        scope.set_vertical_position(0, channel=AWG_SCOPE_CHANNEL)
        scope.set_vertical_offset(AWG_OFFSET_V, channel=AWG_SCOPE_CHANNEL)
        scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=AWG_SCOPE_CHANNEL)
        scope.set_coupling("DC", channel=SUPPLY_SCOPE_CHANNEL)
        scope.set_impedance(1.0e6, channel=SUPPLY_SCOPE_CHANNEL)
        scope.set_vertical_scale(SCOPE_CH2_SCALE_V, channel=SUPPLY_SCOPE_CHANNEL)
        scope.set_vertical_position(0, channel=SUPPLY_SCOPE_CHANNEL)
        scope.set_vertical_offset(SUPPLY_DC_V, channel=SUPPLY_SCOPE_CHANNEL)
        scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=SUPPLY_SCOPE_CHANNEL)
        scope.set_trigger_type("EDGE")
        scope.set_trigger_source(channel=AWG_SCOPE_CHANNEL)
        scope.set_trigger_edge_slope("RISE")
        scope.set_trigger_level(SCOPE_ARM_TRIGGER_LEVEL_V, channel=AWG_SCOPE_CHANNEL)
        scope.set_trigger_mode("NORMAL")

        awg.set_output_load("INFinity")
        awg.set_sin(f"{AWG_FREQUENCY_HZ},{AWG_AMPLITUDE_VPP},{AWG_OFFSET_V}")
        awg.set_enable(0)

        supply.set_current_limit(SUPPLY_CURRENT_LIMIT_A, channel=SUPPLY_OUTPUT_CHANNEL)
        supply.set_voltage(SUPPLY_DC_V, channel=SUPPLY_OUTPUT_CHANNEL)
        supply.set_enable(True, channel=SUPPLY_OUTPUT_CHANNEL)
        awg.set_enable(1)
        time.sleep(SETTLE_TIME_S)

        print(
            "Programmed AWG readback: "
            f"frequency={float(str(awg.get_frequency()).strip()):g} Hz, "
            f"amplitude={float(str(awg.get_voltage_high()).strip()) - float(str(awg.get_voltage_low()).strip()):g} Vpp, "
            f"offset={float(str(awg.get_voltage_offset()).strip()):g} V, "
            f"enabled={str(awg.get_enable()).strip()}"
        )
        print(
            "Programmed supply readback: "
            f"set={supply.get_set_voltage(SUPPLY_OUTPUT_CHANNEL):g} V, "
            f"measured={supply.get_voltage(SUPPLY_OUTPUT_CHANNEL):g} V"
        )

        # Let both sources settle before arming.  The initial trigger level is
        # above the AWG waveform, so lowering it after the scope reports ARMED
        # produces a fresh rising-edge trigger without capturing turn-on.
        scope.set_acquire_state("RUN")
        acquisition_count_before = wait_for_scope_armed(scope, timeout_s=CAPTURE_TIMEOUT_S)
        scope.set_trigger_level(AWG_OFFSET_V, channel=AWG_SCOPE_CHANNEL)
        wait_for_scope_capture(scope, acquisition_count_before, timeout_s=CAPTURE_TIMEOUT_S)
        waveforms = scope.get_waveforms(SCOPE_TRACKS)

        missing_channels = sorted(set(SCOPE_TRACKS).difference(waveforms))
        assert not missing_channels, f"scope did not return channels {missing_channels}"
        measurements = measure_capture(waveforms)
        print(
            "Scope measurements: "
            f"AWG={measurements['awg_frequency_hz']:.3f} Hz, "
            f"{measurements['awg_amplitude_vpp']:.4f} Vpp, "
            f"offset={measurements['awg_offset_v']:.4f} V; "
            f"supply={measurements['supply_dc_v']:.4f} V"
        )
        save_capture(waveforms, measurements)

        assert_close(
            "AWG frequency (Hz)",
            measurements["awg_frequency_hz"],
            AWG_FREQUENCY_HZ,
            relative_tolerance=FREQUENCY_RELATIVE_TOLERANCE,
        )
        assert_close(
            "AWG amplitude (Vpp)",
            measurements["awg_amplitude_vpp"],
            AWG_AMPLITUDE_VPP,
            relative_tolerance=AMPLITUDE_RELATIVE_TOLERANCE,
        )
        assert_close(
            "AWG offset (V)",
            measurements["awg_offset_v"],
            AWG_OFFSET_V,
            absolute_tolerance=VOLTAGE_ABSOLUTE_TOLERANCE_V,
        )
        assert_close(
            "Supply DC level (V)",
            measurements["supply_dc_v"],
            SUPPLY_DC_V,
            absolute_tolerance=VOLTAGE_ABSOLUTE_TOLERANCE_V,
        )

        print(
            "PASS: "
            f"AWG={measurements['awg_frequency_hz']:.3f} Hz, "
            f"{measurements['awg_amplitude_vpp']:.4f} Vpp, "
            f"offset={measurements['awg_offset_v']:.4f} V; "
            f"supply={measurements['supply_dc_v']:.4f} V"
        )
    finally:
        if awg is not None:
            try:
                awg.set_DC("DEF,DEF,0")
                awg.set_enable(0)
            except Exception as error:
                print(f"Warning: could not reset AWG output: {error}")
        if supply is not None:
            try:
                supply.set_enable(False, channel=SUPPLY_OUTPUT_CHANNEL)
                supply.set_voltage(0.0, channel=SUPPLY_OUTPUT_CHANNEL)
            except Exception as error:
                print(f"Warning: could not reset supply output {SUPPLY_OUTPUT_CHANNEL}: {error}")
        if scope is not None and scope_state is not None:
            restore_scope_state(scope, scope_state)
        for dut in reversed(initialized_duts):
            dut.close()


if __name__ == "__main__":
    main()
