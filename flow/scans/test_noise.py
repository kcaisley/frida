"""Measure the quiet THS4541 differential output with the CH1 probe.

The Agilent 33250A applies the calibrated DC level required for zero
differential THS4541 output, the E3634A sets the output common mode to 0.8 V,
and the TDP3500 differential probe on MSO54 CH1 measures ``Vin_p - Vin_n``.
CH1 uses its minimum accepted 20 MHz
bandwidth and minimum accepted 2.5 mV/div scale for the final capture. The
MSO54 may quantize the requested 100 ksample record to a longer supported
length; the accepted value is preserved in the summary.

Run from the repository root with:

    uv run pytest -q -s -m hw flow/scans/test_noise.py

The run saves its raw waveform, a JSON summary, and a 16:9 Gaussian/FFT plot
under ``build/test_noise/<timestamp>``. The ASIC rails are powered at 1.2 V with
500 uA compliance before either input source is enabled. The AWG, VIN_CM, and
ASIC supplies are disabled and reset to 0 V on every exit; changed scope
settings are restored.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from time import sleep, strftime

import numpy as np
import pytest
from basil.HL.tektronix_oscilloscope import response_value
from PIL import Image

from flow.analysis.diffamp import analyze_diffamp_noise
from flow.analysis.plots import plot_diffamp_noise
from flow.scans.scan_adc import convert_vdiff_input_to_awg_supply
from flow.scans.scope import FRIDA_SCOPE_CHANNELS, wait_for_scope_armed, write_scope_csv

MAP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "build" / "test_noise"

TARGET_VDIFF_DC_V = 0.0
TARGET_VIN_CM_V = 0.8
VIN_CM_CURRENT_LIMIT_A = 10.0e-3
ASIC_SUPPLY_V = 1.2
SMU_VOLTAGE_RANGE_V = 2.0
SMU_CURRENT_COMPLIANCE_A = 500.0e-6
SMU_MINIMUM_LOADED_V = 1.15
SMU_SETTLE_TIME_S = 0.5
SETTLE_TIME_S = 0.5
DC_NULL_TOLERANCE_V = 0.25e-3
MAX_DC_NULL_ITERATIONS = 3
MAX_ABSOLUTE_AWG_DC_V = 2.25

SCOPE_CHANNEL = FRIDA_SCOPE_CHANNELS["adc_vdiff"]
SCOPE_TRACKS = {SCOPE_CHANNEL: "vdiff_ch1"}
SCOPE_BANDWIDTH_HZ = 20.0e6
SCOPE_RECORD_LENGTH = 100_000
SCOPE_HORIZONTAL_SCALE_S = 1.0e-3
SCOPE_COARSE_VERTICAL_SCALE_V = 50.0e-3
SCOPE_FINE_VERTICAL_SCALE_V = 2.5e-3
SCOPE_ACQUISITION_SETTLE_S = 0.2
SCOPE_ARM_TIMEOUT_S = 5.0


@pytest.mark.hw
def test_diffamp_noise_loopback(linux_gpib_interface: None) -> None:
    """Configure the bench, acquire one quiet waveform, and save its analysis."""

    if not 0.0 < ASIC_SUPPLY_V <= 1.2:
        raise ValueError("ASIC supply voltage must remain in 0..1.2 V")
    if not 0.0 < SMU_CURRENT_COMPLIANCE_A <= 500.0e-6:
        raise ValueError("ASIC current compliance must remain in 0..500 uA")

    calibrated_awg_zero_v, vin_cm_supply_v = convert_vdiff_input_to_awg_supply(
        TARGET_VDIFF_DC_V,
        TARGET_VIN_CM_V,
    )
    if not 0.0 <= vin_cm_supply_v <= 1.2:
        raise ValueError(f"calibrated VIN_CM supply setpoint {vin_cm_supply_v:g} V is unsafe")

    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    awg_dut = Dut(str(MAP_DIR / "map_awg.yaml"))
    supply_dut = Dut(str(MAP_DIR / "map_supply.yaml"))
    smu_dut = Dut(str(MAP_DIR / "map_smu.yaml"))
    scope_dut = Dut(str(MAP_DIR / "map_scope.yaml"))
    initialized_duts = []
    awg = supply = scope = None
    smus = []
    scope_state = None
    run_timestamp = strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / run_timestamp
    run_dir.mkdir(parents=True, exist_ok=False)

    try:
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

        smu_dut.init()
        initialized_duts.append(smu_dut)
        smus = [
            (smu_dut["smu1"], "VDD_A"),
            (smu_dut["smu2"], "VDD_D"),
            (smu_dut["smu3"], "VDD_DAC"),
        ]
        for smu, _rail in smus:
            smu.off()
            smu.set_voltage(0.0)
        for smu, rail in smus:
            smu.source_volt()
            smu.four_wire_off()
            smu.set_voltage_range(SMU_VOLTAGE_RANGE_V)
            smu.set_current_limit(SMU_CURRENT_COMPLIANCE_A)
            smu.current_sense_autorange_on()
            smu.set_current_nplc(10.0)
            smu.autozero_on()
            smu.set_voltage(ASIC_SUPPLY_V)
            programmed_voltage_v = float(smu.get_source_voltage())
            programmed_compliance_a = float(smu.get_current_limit())
            if not 0.0 < programmed_voltage_v <= ASIC_SUPPLY_V:
                raise RuntimeError(f"{rail}: unsafe voltage setpoint readback {programmed_voltage_v:g} V")
            if not 0.0 < programmed_compliance_a <= SMU_CURRENT_COMPLIANCE_A:
                raise RuntimeError(f"{rail}: unsafe current-compliance readback {programmed_compliance_a:g} A")
        for smu, _rail in smus:
            smu.on()
        sleep(SMU_SETTLE_TIME_S)
        for smu, rail in smus:
            measured_voltage_v = float(smu.get_voltage())
            measured_current_a = float(smu.get_current())
            print(f"{rail}: {measured_voltage_v:.6f} V, {measured_current_a * 1e6:.3f} uA")
            if not SMU_MINIMUM_LOADED_V <= measured_voltage_v <= ASIC_SUPPLY_V + 5.0e-3:
                raise RuntimeError(f"{rail}: unsafe or compliance-limited voltage {measured_voltage_v:g} V")
            if abs(measured_current_a) >= SMU_CURRENT_COMPLIANCE_A:
                raise RuntimeError(f"{rail}: measured current {measured_current_a:g} A reached compliance")

        scope_dut.init()
        initialized_duts.append(scope_dut)
        scope = scope_dut["scope"]

        awg_id = str(awg.get_name()).strip()
        supply_id = str(supply.get_name()).strip()
        scope_id = str(scope.get_name()).strip()
        probe_type = str(scope._intf.query(f"CH{SCOPE_CHANNEL}:PROBE:ID:TYPE?")).strip().strip('"')
        probe_resistance_ohm = float(response_value(scope._intf.query(f"CH{SCOPE_CHANNEL}:PROBE:RESISTANCE?")))
        probe_gain = float(response_value(scope._intf.query(f"CH{SCOPE_CHANNEL}:PROBE:GAIN?")))
        print(f"AWG: {awg_id}")
        print(f"VIN_CM supply: {supply_id}")
        print(f"Scope: {scope_id}")
        print(f"Scope CH1: probe={probe_type}, input_resistance={probe_resistance_ohm:g} ohm, gain={probe_gain:g}")
        if probe_type.upper() != "TDP3500" or probe_resistance_ohm < 10.0e3:
            raise RuntimeError("scope CH1 does not have the expected high-impedance TDP3500 probe")

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
        scope.set_acquire_stop_after("SEQUENCE")
        scope.set_horizontal_scale(SCOPE_HORIZONTAL_SCALE_S)
        scope.set_horizontal_record_length(SCOPE_RECORD_LENGTH)
        scope._intf.write("HORizontal:POSition 50")
        scope._intf.write(f"DISplay:GLObal:CH{SCOPE_CHANNEL}:STATE ON")
        scope.set_coupling("DC", channel=SCOPE_CHANNEL)
        scope.set_vertical_position(0.0, channel=SCOPE_CHANNEL)
        scope.set_vertical_offset(0.0, channel=SCOPE_CHANNEL)
        scope.set_vertical_scale(SCOPE_COARSE_VERTICAL_SCALE_V, channel=SCOPE_CHANNEL)
        scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=SCOPE_CHANNEL)
        scope.set_trigger_type("EDGE")
        scope.set_trigger_source(channel=SCOPE_CHANNEL)
        scope.set_trigger_edge_slope("RISE")
        scope.set_trigger_level(1.5, channel=SCOPE_CHANNEL)
        scope.set_trigger_mode("NORMAL")
        accepted_bandwidth_hz = float(response_value(scope.get_bandwidth(channel=SCOPE_CHANNEL)))
        accepted_record_length = int(float(response_value(scope.get_horizontal_record_length())))
        if accepted_bandwidth_hz != SCOPE_BANDWIDTH_HZ:
            raise RuntimeError(f"scope accepted {accepted_bandwidth_hz:g} Hz instead of {SCOPE_BANDWIDTH_HZ:g} Hz")

        supply.set_voltage_range("P25V")
        supply.set_current_limit(VIN_CM_CURRENT_LIMIT_A)
        supply.set_voltage(vin_cm_supply_v)
        supply.set_enable(1)
        sleep(SETTLE_TIME_S)
        vin_cm_read_v = float(supply.get_voltage())
        vin_cm_current_a = float(supply.get_current())
        if abs(vin_cm_current_a) >= VIN_CM_CURRENT_LIMIT_A:
            raise RuntimeError(f"VIN_CM current {vin_cm_current_a:g} A reached its safety limit")

        awg.set_output_load("INFinity")
        awg.set_voltage_unit("VPP")
        awg.set_output_polarity("NORMal")
        commanded_vdiff_dc_v = TARGET_VDIFF_DC_V
        awg_dc_set_v = calibrated_awg_zero_v
        awg.set_DC(f"DEF,DEF,{awg_dc_set_v}")
        awg.set_enable(1)
        sleep(SETTLE_TIME_S)
        awg_offset_read_v = float(str(awg.get_voltage_offset()).strip().split(",")[0])
        if abs(awg_offset_read_v - awg_dc_set_v) > 0.5e-3:
            raise RuntimeError(f"AWG DC readback is {awg_offset_read_v:g} V, expected {awg_dc_set_v:g} V")

        scope.set_acquire_state("STOP")
        scope._intf.write("ACQuire:NUMACq:RESET")
        scope._intf.query("*OPC?")
        scope.set_acquire_state("RUN")
        wait_for_scope_armed(scope, timeout_s=SCOPE_ARM_TIMEOUT_S)
        scope.force_trigger()
        sleep(SCOPE_ACQUISITION_SETTLE_S)
        scope.set_acquire_state("STOP")
        coarse_waveforms = scope.get_waveforms((SCOPE_CHANNEL,))
        if SCOPE_CHANNEL not in coarse_waveforms:
            raise RuntimeError("scope did not return the coarse CH1 waveform")
        coarse_samples_v = np.asarray(coarse_waveforms[SCOPE_CHANNEL].data, dtype=np.float64)
        coarse_mean_v = float(np.mean(coarse_samples_v))
        print(f"Coarse CH1: mean={coarse_mean_v * 1e3:.3f} mV, RMS={np.std(coarse_samples_v) * 1e3:.3f} mV")

        scope.set_vertical_offset(coarse_mean_v, channel=SCOPE_CHANNEL)
        scope.set_vertical_scale(SCOPE_FINE_VERTICAL_SCALE_V, channel=SCOPE_CHANNEL)
        scope.set_trigger_level(1.5, channel=SCOPE_CHANNEL)
        accepted_vertical_scale_v = float(response_value(scope.get_vertical_scale(channel=SCOPE_CHANNEL)))
        if accepted_vertical_scale_v != SCOPE_FINE_VERTICAL_SCALE_V:
            raise RuntimeError(
                f"scope accepted {accepted_vertical_scale_v:g} V/div instead of {SCOPE_FINE_VERTICAL_SCALE_V:g} V/div"
            )

        for dc_null_iteration in range(1, MAX_DC_NULL_ITERATIONS + 1):
            scope.set_acquire_state("STOP")
            scope._intf.write("ACQuire:NUMACq:RESET")
            scope._intf.query("*OPC?")
            scope.set_acquire_state("RUN")
            wait_for_scope_armed(scope, timeout_s=SCOPE_ARM_TIMEOUT_S)
            scope.force_trigger()
            sleep(SCOPE_ACQUISITION_SETTLE_S)
            scope.set_acquire_state("STOP")
            waveforms = scope.get_waveforms((SCOPE_CHANNEL,))
            if SCOPE_CHANNEL not in waveforms:
                raise RuntimeError("scope did not return the fine differential-output waveform")
            waveform = waveforms[SCOPE_CHANNEL]
            samples_v = np.asarray(waveform.data, dtype=np.float64)
            if len(samples_v) != accepted_record_length:
                raise RuntimeError(
                    f"scope returned {len(samples_v)} samples, "
                    f"expected its accepted record length {accepted_record_length}"
                )

            analysis = analyze_diffamp_noise(
                samples_v,
                sample_interval_s=float(waveform.x_scale.slope),
                measurement_bandwidth_hz=accepted_bandwidth_hz,
            )
            print(
                f"DC-null iteration {dc_null_iteration}: "
                f"AWG={awg_dc_set_v * 1e3:.6f} mV, "
                f"differential mean={analysis.mean_v * 1e3:.6f} mV"
            )
            if abs(analysis.mean_v - TARGET_VDIFF_DC_V) <= DC_NULL_TOLERANCE_V:
                break
            if dc_null_iteration == MAX_DC_NULL_ITERATIONS:
                break

            commanded_vdiff_dc_v += TARGET_VDIFF_DC_V - analysis.mean_v
            awg_dc_set_v, adjusted_supply_v = convert_vdiff_input_to_awg_supply(
                commanded_vdiff_dc_v,
                TARGET_VIN_CM_V,
            )
            if not math.isclose(adjusted_supply_v, vin_cm_supply_v, abs_tol=1.0e-12):
                raise RuntimeError("Vin_cm calibration changed during differential-output DC nulling")
            if abs(awg_dc_set_v) > MAX_ABSOLUTE_AWG_DC_V:
                raise RuntimeError(f"unsafe AWG DC nulling request {awg_dc_set_v:g} V")
            awg.set_enable(0)
            awg.set_DC(f"DEF,DEF,{awg_dc_set_v}")
            awg_offset_read_v = float(str(awg.get_voltage_offset()).strip().split(",")[0])
            if abs(awg_offset_read_v - awg_dc_set_v) > 0.5e-3:
                raise RuntimeError(f"AWG DC readback is {awg_offset_read_v:g} V, expected {awg_dc_set_v:g} V")
            scope.set_vertical_offset(TARGET_VDIFF_DC_V, channel=SCOPE_CHANNEL)
            scope.set_trigger_level(1.5, channel=SCOPE_CHANNEL)
            awg.set_enable(1)
            sleep(SETTLE_TIME_S)

        clipped = float(np.max(np.abs(samples_v - analysis.mean_v))) >= 4.5 * accepted_vertical_scale_v
        waveform_path = write_scope_csv(run_dir / "waveform.csv", waveforms, SCOPE_TRACKS)
        plot_paths = plot_diffamp_noise(
            analysis,
            output_path=run_dir / "noise_gaussian_fft",
        )
        summary = {
            "timestamp": run_timestamp,
            "awg_identity": awg_id,
            "target_vdiff_dc_v": TARGET_VDIFF_DC_V,
            "commanded_vdiff_dc_v": commanded_vdiff_dc_v,
            "initial_awg_dc_set_v": calibrated_awg_zero_v,
            "awg_dc_set_v": awg_dc_set_v,
            "awg_dc_read_v": awg_offset_read_v,
            "dc_null_iterations": dc_null_iteration,
            "dc_null_tolerance_v": DC_NULL_TOLERANCE_V,
            "target_vin_cm_v": TARGET_VIN_CM_V,
            "vin_cm_supply_set_v": vin_cm_supply_v,
            "vin_cm_supply_read_v": vin_cm_read_v,
            "vin_cm_supply_current_a": vin_cm_current_a,
            "scope_identity": scope_id,
            "scope_probe": probe_type,
            "scope_probe_gain": probe_gain,
            "scope_bandwidth_hz": accepted_bandwidth_hz,
            "scope_vertical_scale_v_per_div": accepted_vertical_scale_v,
            "scope_record_length_requested": SCOPE_RECORD_LENGTH,
            "scope_record_length_accepted": accepted_record_length,
            "scope_sample_count": len(samples_v),
            "scope_sample_rate_hz": analysis.sample_rate_hz,
            "scope_capture_clipped": clipped,
            "measured_vdiff_mean_v": analysis.mean_v,
            "measured_noise_rms_v": analysis.noise_rms_v,
            "fft_integrated_noise_rms_v": analysis.integrated_fft_noise_rms_v,
            "waveform_csv": str(waveform_path),
            "plots": [str(path) for path in plot_paths],
        }
        summary_path = run_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"Saved summary: {summary_path}")
        print(
            f"Fine differential output: mean={analysis.mean_v * 1e3:.6f} mV, "
            f"time RMS={analysis.noise_rms_v * 1e3:.6f} mV, "
            f"FFT-integrated RMS={analysis.integrated_fft_noise_rms_v * 1e3:.6f} mV"
        )
        print(f"Artifacts: {run_dir}")
        if clipped:
            raise RuntimeError("fine CH1 waveform approaches the scope range limit; artifacts were retained")
        if abs(analysis.mean_v - TARGET_VDIFF_DC_V) > DC_NULL_TOLERANCE_V:
            raise RuntimeError(
                f"differential-output mean {analysis.mean_v:g} V remains outside "
                f"the {DC_NULL_TOLERANCE_V:g} V DC-null tolerance"
            )
    finally:
        if awg is not None:
            try:
                awg.set_DC("DEF,DEF,0")
                awg.set_enable(0)
            except Exception as error:  # noqa: BLE001 - best-effort safety shutdown
                print(f"WARNING: could not disable and zero the AWG: {error}")
        if supply is not None:
            try:
                supply.set_enable(0)
                supply.set_voltage(0.0)
            except Exception as error:  # noqa: BLE001 - best-effort safety shutdown
                print(f"WARNING: could not disable and zero VIN_CM: {error}")

        for smu, rail in smus:
            try:
                smu.off()
                smu.set_voltage(0.0)
            except Exception as error:  # noqa: BLE001 - best-effort safety shutdown
                print(f"WARNING: could not disable and zero {rail}: {error}")
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
                scope.set_trigger_level(scope_state["trigger_level"], channel=SCOPE_CHANNEL)
                scope.set_coupling(scope_state["coupling"], channel=SCOPE_CHANNEL)
                scope.set_impedance(scope_state["impedance"], channel=SCOPE_CHANNEL)
                scope.set_vertical_scale(scope_state["vertical_scale"], channel=SCOPE_CHANNEL)
                scope.set_vertical_position(scope_state["vertical_position"], channel=SCOPE_CHANNEL)
                scope.set_vertical_offset(scope_state["vertical_offset"], channel=SCOPE_CHANNEL)
                scope.set_bandwidth(scope_state["bandwidth"], channel=SCOPE_CHANNEL)
                scope._intf.write(f"DISplay:GLObal:CH{SCOPE_CHANNEL}:STATE {scope_state['display']}")
                scope.set_acquire_stop_after(scope_state["acquire_stop_after"])
                scope.set_acquire_state(scope_state["acquire_state"])
            except Exception as error:  # noqa: BLE001 - best-effort state restoration
                print(f"WARNING: could not fully restore scope settings: {error}")
        for dut in reversed(initialized_duts):
            dut.close()


def test_diffamp_noise_analysis_recovers_gaussian_rms_and_tone() -> None:
    rng = np.random.default_rng(7)
    sample_rate_hz = 100.0e6
    sample_count = 100_000
    time_s = np.arange(sample_count) / sample_rate_hz
    noise_rms_v = 0.5e-3
    tone_frequency_hz = 2.0e6
    samples_v = (
        12.0e-3 + rng.normal(0.0, noise_rms_v, sample_count) + 0.2e-3 * np.sin(2.0 * np.pi * tone_frequency_hz * time_s)
    )

    analysis = analyze_diffamp_noise(
        samples_v,
        sample_interval_s=1.0 / sample_rate_hz,
        measurement_bandwidth_hz=SCOPE_BANDWIDTH_HZ,
    )

    assert analysis.mean_v == pytest.approx(12.0e-3, abs=10e-6)
    assert analysis.noise_rms_v == pytest.approx(np.sqrt(noise_rms_v**2 + (0.2e-3) ** 2 / 2.0), rel=0.02)
    assert analysis.integrated_fft_noise_rms_v == pytest.approx(analysis.noise_rms_v, rel=0.03)


def test_diffamp_noise_plot_is_exact_16_by_9(tmp_path: Path) -> None:
    rng = np.random.default_rng(8)
    samples_v = rng.normal(10.0e-3, 0.5e-3, 10_000)
    analysis = analyze_diffamp_noise(
        samples_v,
        sample_interval_s=10.0e-9,
        measurement_bandwidth_hz=SCOPE_BANDWIDTH_HZ,
    )

    paths = plot_diffamp_noise(
        analysis,
        output_path=tmp_path / "noise",
    )

    assert tuple(path.suffix for path in paths) == (".png", ".pdf")
    assert Image.open(paths[0]).size == (4800, 2700)
