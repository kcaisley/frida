"""Measure the quiet THS4541 differential output using the configured vin_diff probe.

The Agilent 33250A applies the calibrated DC level required for zero
differential THS4541 output, the E3634A sets the output common mode to 0.7 V,
and the TDP3500 probe on CH1 measures ``Vin_p - Vin_n``. The scope uses its minimum accepted 20 MHz
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

import dataclasses
import json
import math
from pathlib import Path
from time import sleep, strftime
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest
from basil.HL.tektronix_oscilloscope import response_value
from PIL import Image

import flow.analysis.plots as analysis_plots
from flow.analysis.io import read_analysis, write_analysis
from flow.analysis.plots import plot_histogram, plot_spectrum, plot_waveforms
from flow.analysis.types import AnalysisScope
from flow.scans.scan_adc import convert_vdiff_input_to_awg_supply
from flow.scans.scope import ScopeConns, scope_analysis, wait_for_scope_armed

MAP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "build" / "test_noise"

TARGET_VDIFF_DC_V = 0.0
TARGET_VIN_CM_V = 0.7
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

    scope_conns = ScopeConns(ch1="vin_diff")  # TDP3500 across the differential input
    vin_diff_channel = scope_conns.channels["vin_diff"]

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
        probe_type = str(scope._intf.query(f"CH{vin_diff_channel}:PROBE:ID:TYPE?")).strip().strip('"')
        probe_resistance_ohm = float(response_value(scope._intf.query(f"CH{vin_diff_channel}:PROBE:RESISTANCE?")))
        probe_gain = float(response_value(scope._intf.query(f"CH{vin_diff_channel}:PROBE:GAIN?")))
        print(f"AWG: {awg_id}")
        print(f"VIN_CM supply: {supply_id}")
        print(f"Scope: {scope_id}")
        print(
            f"Scope CH{vin_diff_channel}: probe={probe_type}, input_resistance={probe_resistance_ohm:g} ohm, gain={probe_gain:g}"
        )
        if probe_type.upper() != "TDP3500" or probe_resistance_ohm < 10.0e3:
            raise RuntimeError(
                "scope differential-input channel does not have the expected high-impedance TDP3500 probe"
            )

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
            "trigger_level": response_value(scope.get_trigger_level(channel=vin_diff_channel)),
            "coupling": response_value(scope.get_coupling(channel=vin_diff_channel)),
            "impedance": response_value(scope.get_impedance(channel=vin_diff_channel)),
            "vertical_scale": response_value(scope.get_vertical_scale(channel=vin_diff_channel)),
            "vertical_position": response_value(scope.get_vertical_position(channel=vin_diff_channel)),
            "vertical_offset": response_value(scope.get_vertical_offset(channel=vin_diff_channel)),
            "bandwidth": response_value(scope.get_bandwidth(channel=vin_diff_channel)),
            "display": response_value(scope._intf.query(f"DISplay:GLObal:CH{vin_diff_channel}:STATE?")),
        }

        scope.set_acquire_state("STOP")
        scope.set_acquire_mode("SAMPLE")
        scope.set_acquire_stop_after("SEQUENCE")
        scope.set_horizontal_scale(SCOPE_HORIZONTAL_SCALE_S)
        scope.set_horizontal_record_length(SCOPE_RECORD_LENGTH)
        scope._intf.write("HORizontal:POSition 50")
        scope._intf.write(f"DISplay:GLObal:CH{vin_diff_channel}:STATE ON")
        scope.set_coupling("DC", channel=vin_diff_channel)
        scope.set_vertical_position(0.0, channel=vin_diff_channel)
        scope.set_vertical_offset(0.0, channel=vin_diff_channel)
        scope.set_vertical_scale(SCOPE_COARSE_VERTICAL_SCALE_V, channel=vin_diff_channel)
        scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=vin_diff_channel)
        scope.set_trigger_type("EDGE")
        scope.set_trigger_source(channel=vin_diff_channel)
        scope.set_trigger_edge_slope("RISE")
        scope.set_trigger_level(1.5, channel=vin_diff_channel)
        scope.set_trigger_mode("NORMAL")
        accepted_bandwidth_hz = float(response_value(scope.get_bandwidth(channel=vin_diff_channel)))
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
        coarse_waveforms = scope.get_waveforms((vin_diff_channel,))
        if vin_diff_channel not in coarse_waveforms:
            raise RuntimeError("scope did not return the coarse differential-input channel waveform")
        coarse_samples_v = np.asarray(coarse_waveforms[vin_diff_channel].data, dtype=np.float64)
        coarse_mean_v = float(np.mean(coarse_samples_v))
        print(
            f"Coarse CH{vin_diff_channel}: mean={coarse_mean_v * 1e3:.3f} mV, RMS={np.std(coarse_samples_v) * 1e3:.3f} mV"
        )

        scope.set_vertical_offset(coarse_mean_v, channel=vin_diff_channel)
        scope.set_vertical_scale(SCOPE_FINE_VERTICAL_SCALE_V, channel=vin_diff_channel)
        scope.set_trigger_level(1.5, channel=vin_diff_channel)
        accepted_vertical_scale_v = float(response_value(scope.get_vertical_scale(channel=vin_diff_channel)))
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
            waveforms = scope.get_waveforms((vin_diff_channel,))
            if vin_diff_channel not in waveforms:
                raise RuntimeError("scope did not return the fine differential-output waveform")
            waveform = waveforms[vin_diff_channel]
            samples_v = np.asarray(waveform.data, dtype=np.float64)
            if len(samples_v) != accepted_record_length:
                raise RuntimeError(
                    f"scope returned {len(samples_v)} samples, "
                    f"expected its accepted record length {accepted_record_length}"
                )

            analysis = scope_analysis(
                waveforms,
                scope_conns,
                name=(f"{probe_type}, {accepted_vertical_scale_v * 1e3:g} mV/div"),
                bandwidth_hz=accepted_bandwidth_hz,
            )
            mean_v = analysis.mean_v["vin_diff"]
            print(
                f"DC-null iteration {dc_null_iteration}: "
                f"AWG={awg_dc_set_v * 1e3:.6f} mV, "
                f"differential mean={mean_v * 1e3:.6f} mV"
            )
            if abs(mean_v - TARGET_VDIFF_DC_V) <= DC_NULL_TOLERANCE_V:
                break
            if dc_null_iteration == MAX_DC_NULL_ITERATIONS:
                break

            commanded_vdiff_dc_v += TARGET_VDIFF_DC_V - mean_v
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
            scope.set_vertical_offset(TARGET_VDIFF_DC_V, channel=vin_diff_channel)
            scope.set_trigger_level(1.5, channel=vin_diff_channel)
            awg.set_enable(1)
            sleep(SETTLE_TIME_S)

        clipped = float(np.max(np.abs(samples_v - mean_v))) >= 4.5 * accepted_vertical_scale_v
        analysis_path = write_analysis(run_dir / "scope.h5", analysis)
        plot_paths = (
            *plot_histogram(
                analysis, title="THS4541 quiet-output distribution", output_path=run_dir / "noise_histogram"
            ),
            *plot_spectrum([analysis], title="THS4541 quiet-output spectrum", output_path=run_dir / "noise_spectrum"),
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
            "measured_vdiff_mean_v": mean_v,
            "measured_noise_rms_v": analysis.ac_rms_v["vin_diff"],
            "fft_integrated_noise_rms_v": analysis.spectrum_rms_v["vin_diff"],
            "scope_analysis_h5": str(analysis_path),
            "plots": [str(path) for path in plot_paths],
        }
        summary_path = run_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"Saved summary: {summary_path}")
        print(
            f"Fine differential output: mean={mean_v * 1e3:.6f} mV, "
            f"time RMS={analysis.ac_rms_v['vin_diff'] * 1e3:.6f} mV, "
            f"FFT-integrated RMS={analysis.spectrum_rms_v['vin_diff'] * 1e3:.6f} mV"
        )
        print(f"Artifacts: {run_dir}")
        if clipped:
            raise RuntimeError(
                "fine differential-input channel waveform approaches the scope range limit; artifacts were retained"
            )
        if abs(mean_v - TARGET_VDIFF_DC_V) > DC_NULL_TOLERANCE_V:
            raise RuntimeError(
                f"differential-output mean {mean_v:g} V remains outside the {DC_NULL_TOLERANCE_V:g} V DC-null tolerance"
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
                scope.set_trigger_level(scope_state["trigger_level"], channel=vin_diff_channel)
                scope.set_coupling(scope_state["coupling"], channel=vin_diff_channel)
                scope.set_impedance(scope_state["impedance"], channel=vin_diff_channel)
                scope.set_vertical_scale(scope_state["vertical_scale"], channel=vin_diff_channel)
                scope.set_vertical_position(scope_state["vertical_position"], channel=vin_diff_channel)
                scope.set_vertical_offset(scope_state["vertical_offset"], channel=vin_diff_channel)
                scope.set_bandwidth(scope_state["bandwidth"], channel=vin_diff_channel)
                scope._intf.write(f"DISplay:GLObal:CH{vin_diff_channel}:STATE {scope_state['display']}")
                scope.set_acquire_stop_after(scope_state["acquire_stop_after"])
                scope.set_acquire_state(scope_state["acquire_state"])
            except Exception as error:  # noqa: BLE001 - best-effort state restoration
                print(f"WARNING: could not fully restore scope settings: {error}")
        for dut in reversed(initialized_duts):
            dut.close()


@pytest.mark.hw
@pytest.mark.parametrize(
    ("scope_conns", "volts_per_div", "title"),
    (
        # Each probe's signal and ground clipped together at a board ground pin.
        pytest.param(ScopeConns(ch1="ch1_short", ch2="ch2_short"), 1.0e-3, "Measurement floor", id="step0_floor"),
        # Same floor with the passive hook probes at 1X, tips clipped to their ground leads.
        pytest.param(
            ScopeConns(ch1="ch1_short", ch2="ch2_short"),
            1.0e-3,
            "Measurement floor, passive probes (1X)",
            id="step0_floor_probes",
        ),
        # 1.2 V supply at the perfboard divider input: VDD and VSS against board ground.
        # 5 mV/div: the supply carries spikes beyond 10 mV that clip at 1-2 mV/div.
        pytest.param(ScopeConns(ch1="vdd_div", ch2="vss_div"), 5.0e-3, "Divider supply", id="step1_supply_div"),
        # VOCM node of the THS4541 (amp mode, 1k + 1k divider).
        pytest.param(ScopeConns(ch1="vocm"), 1.0e-3, "Amplifier common-mode reference", id="step2_vocm"),
        # Perfboard divider outputs V+ and V-.
        pytest.param(ScopeConns(ch1="vin_p_div", ch2="vin_n_div"), 1.0e-3, "Divider outputs", id="step3_divider_out"),
        # AWG output at the board's single-ended input.
        pytest.param(ScopeConns(ch1="vin_p_ext"), 1.0e-3, "AWG output", id="step4_awg_out"),
        # THS4541 outputs, amplifier side of R25/R26.
        pytest.param(ScopeConns(ch1="vout_p_amp", ch2="vout_n_amp"), 1.0e-3, "Amplifier outputs", id="step5_amp_out"),
        # ADC input pins across C6 with the amplifier driving them.
        pytest.param(
            ScopeConns(ch1="vin_p", ch2="vin_n"), 1.0e-3, "ADC inputs, amplifier driven", id="step6_adc_pins_amp"
        ),
        # ADC input pins across the 1 uF with the perfboard divider driving them.
        pytest.param(
            ScopeConns(ch1="vin_p", ch2="vin_n"), 1.0e-3, "ADC inputs, divider driven", id="step7_adc_pins_bypass"
        ),
    ),
)
def test_input_chain_noise(
    request: pytest.FixtureRequest,
    scope_conns: ScopeConns,
    volts_per_div: float,
    title: str,
) -> None:
    """Capture one probe position of the ADC input-chain noise study.

    Coax probes into CH1 (and CH2), 1 MOhm AC coupling, the step's V/div,
    20 MHz limit, and High Res. A slow 100 ms record at 12.5 MS/s resolves mains
    lines and the ADC's filtered band; a fast 1 ms record at 1.25 GS/s covers
    the 20 MHz band. Two channels add their difference and common-mode average
    as derived traces, plotted separately from the single-ended traces. Each
    record is saved as an AnalysisScope with spectra, histograms, traces, and
    a scope screenshot under ``build/test_noise/<timestamp>/<step>``. Select
    one step, for example::

        uv run pytest -q -s -m hw flow/scans/test_noise.py -k step0_floor

    The scope is left in the fast configuration for live inspection.
    """
    import pyvisa
    from basil.dut import Dut
    from pyvisa.resources import MessageBasedResource

    step = request.node.callspec.id
    channels = scope_conns.channels
    differential, common_mode = {}, {}
    if len(channels) == 2:
        p_name, n_name = channels
        differential = {f"{p_name}-{n_name}": (p_name, n_name)}
        common_mode = {f"cm({p_name}, {n_name})": (p_name, n_name)}
    run_dir = OUTPUT_DIR / strftime("%Y%m%d_%H%M%S") / step
    run_dir.mkdir(parents=True)

    scope_dut = Dut(str(MAP_DIR / "map_scope.yaml"))
    scope_dut.init()
    # Basil holds the raw socket; screenshot transfer needs VXI-11, which ends binary reads.
    vxi = cast(
        MessageBasedResource,
        pyvisa.ResourceManager("@py").open_resource("TCPIP0::192.168.10.60::inst0::INSTR", timeout=20000),
    )
    try:
        scope = scope_dut["scope"]
        scope.set_acquire_state("STOP")
        for channel in range(1, 5):
            scope._intf.write(f"DISplay:GLObal:CH{channel}:STATE {'ON' if channel in channels.values() else 'OFF'}")
        for channel in channels.values():
            scope.set_impedance("1E6", channel=channel)
            scope.set_coupling("AC", channel=channel)
            scope.set_vertical_scale(volts_per_div, channel=channel)
            scope.set_bandwidth(20.0e6, channel=channel)
            scope.set_vertical_offset(0.0, channel=channel)
            scope.set_vertical_position(0.0, channel=channel)
        sources = [f"CH{channel}" for channel in channels.values()]
        if differential:
            if "MATH1" not in scope._intf.query("MATH:LIST?"):
                scope._intf.write('MATH:ADDNew "MATH1"')
            scope._intf.write('MATH:MATH1:DEFine "CH{}-CH{}"'.format(*channels.values()))
            scope._intf.write("DISplay:GLObal:MATH1:STATE ON")
            sources.insert(0, "MATH1")
        # MEASUrement:DELETEALL is ignored by this firmware; delete each measurement.
        for name in scope._intf.query("MEASUrement:LIST?").strip().split(","):
            if name.startswith("MEAS"):
                scope._intf.write(f'MEASUrement:DELete "{name}"')
        for index, source in enumerate(sources, start=1):
            scope._intf.write("MEASUrement:ADDMEAS ACRMS")
            scope._intf.write(f"MEASUrement:MEAS{index}:SOUrce1 {source}")
        scope.set_acquire_mode("HIRes")
        scope.set_acquire_stop_after("RUNSTop")
        scope.set_trigger_mode("AUTO")
        scope._intf.write("HORizontal:MODE MANual")

        captures = {}
        for capture, sample_rate_hz, settle_s, spectrum_span_hz in (
            ("slow", 12.5e6, 20.0, 5.0e3),
            ("fast", 1.25e9, 12.0, 20.0e6),
        ):
            for channel in channels.values():
                scope._intf.write(f"CH{channel}:SV:STATE ON")
                scope._intf.write(f"CH{channel}:SV:CENTERFrequency {spectrum_span_hz / 2}")
            scope._intf.write(f"SV:SPAN {spectrum_span_hz}")
            scope._intf.write("SV:RBWMode AUTOMATIC")
            scope._intf.write(f"HORizontal:MODE:SAMPLERate {sample_rate_hz}")
            scope.set_horizontal_record_length(1_250_000)
            scope.set_acquire_state("RUN")
            sleep(2.0)
            scope._intf.write("CLEAR")
            sleep(settle_s)
            scope_acrms_v = {
                source: float(scope._intf.query(f"MEASUrement:MEAS{index}:RESUlts:ALLAcqs:MEAN?"))
                for index, source in enumerate(sources, start=1)
            }
            vxi.write('SAVE:IMAGe "C:/m2cz/noise.png"')
            vxi.query("*OPC?")
            vxi.write('FILESystem:READFile "C:/m2cz/noise.png"')
            (run_dir / f"scope_{capture}.png").write_bytes(vxi.read_raw())
            # The front end as the scope accepted it; High Res at 12.5 MS/s
            # reports its narrower actual bandwidth (about 5 MHz).
            first_channel = next(iter(channels.values()))
            bandwidth_hz = float(response_value(scope._intf.query(f"CH{first_channel}:BANdwidth:ACTual?")))
            termination_ohm = float(response_value(scope.get_impedance(channel=first_channel)))
            coupling = str(response_value(scope.get_coupling(channel=first_channel)))
            accepted_volts_per_div = float(response_value(scope.get_vertical_scale(channel=first_channel)))
            waveforms = scope.get_waveforms(tuple(channels.values()))
            analysis = scope_analysis(
                waveforms,
                scope_conns,
                name=(
                    f"{termination_ohm / 1e6:g} MΩ {coupling}"
                    if termination_ohm >= 1e3
                    else f"{termination_ohm:g} Ω {coupling}"
                )
                + f", {accepted_volts_per_div * 1e3:g} mV/div",
                bandwidth_hz=bandwidth_hz,
                differential=differential,
                common_mode=common_mode,
            )
            write_analysis(run_dir / f"{capture}.h5", analysis)
            plot_histogram(
                analysis,
                title=f"Noise distribution, {capture} capture – {title}",
                output_path=run_dir / f"histogram_{capture}",
            )
            plot_waveforms(
                analysis.wave,
                title=f"Traces, {capture} capture – {title}",
                output_path=run_dir / f"traces_{capture}",
            )
            captures[capture] = (analysis, scope_acrms_v)

        scopes = [captures["slow"][0], captures["fast"][0]]
        plot_spectrum(
            scopes,
            title=f"Single-ended noise spectral density – {title}",
            signals={name: name for name in channels},
            output_path=run_dir / "spectrum_single",
        )
        # Two channels: the difference the ADC converts and the common mode it rejects.
        if differential:
            plot_spectrum(
                scopes,
                title=f"Differential noise spectral density – {title}",
                signals={name: name for name in differential},
                output_path=run_dir / "spectrum_diff",
            )
            plot_spectrum(
                scopes,
                title=f"Common-mode noise spectral density – {title}",
                signals={name: name for name in common_mode},
                output_path=run_dir / "spectrum_common",
            )
    finally:
        vxi.close()
        scope_dut.close()

    print(f"{step} -> {run_dir}")
    for capture, (analysis, scope_acrms_v) in captures.items():
        print(f"  {capture}: " + ", ".join(f"{name} {rms_v * 1e6:.1f} uV" for name, rms_v in analysis.ac_rms_v.items()))
        for name, channel in channels.items():
            # The screen spans five divisions either side of the centered trace.
            peak_v = float(np.max(np.abs(analysis.wave.v[name][0] - analysis.mean_v[name])))
            assert peak_v < 4.5 * volts_per_div, f"{capture} {name} approaches the screen range ({peak_v * 1e3:.2f} mV)"
            # One record against the scope's average over many; bursty rails differ by a few percent.
            assert analysis.ac_rms_v[name] == pytest.approx(scope_acrms_v[f"CH{channel}"], rel=0.1)


def test_scope_analysis_recovers_gaussian_rms_tone_and_derived_traces(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    sample_rate_hz = 100.0e6
    sample_count = 100_000
    time_s = np.arange(sample_count) / sample_rate_hz
    noise_rms_v = 0.5e-3
    tone_frequency_hz = 2.0e6
    p_v = (
        12.0e-3 + rng.normal(0.0, noise_rms_v, sample_count) + 0.2e-3 * np.sin(2.0 * np.pi * tone_frequency_hz * time_s)
    )
    n_v = rng.normal(0.0, noise_rms_v, sample_count)
    x_scale = SimpleNamespace(offset=0.0, slope=1.0 / sample_rate_hz)
    waveforms = {1: SimpleNamespace(data=p_v, x_scale=x_scale), 2: SimpleNamespace(data=n_v, x_scale=x_scale)}

    analysis = scope_analysis(
        waveforms,
        ScopeConns(ch1="vin_p", ch2="vin_n"),
        name="synthetic, 1 MΩ AC, 1 mV/div",
        bandwidth_hz=SCOPE_BANDWIDTH_HZ,
        differential={"vin_diff": ("vin_p", "vin_n")},
        common_mode={"vin_cm": ("vin_p", "vin_n")},
    )

    assert set(analysis.wave.v) == {"vin_p", "vin_n", "vin_diff", "vin_cm"}
    assert analysis.mean_v["vin_cm"] == pytest.approx(6.0e-3, abs=10e-6)
    assert analysis.ac_rms_v["vin_cm"] == pytest.approx(
        np.sqrt(2.0 * noise_rms_v**2 + (0.2e-3) ** 2 / 2.0) / 2.0, rel=0.02
    )
    assert analysis.mean_v["vin_p"] == pytest.approx(12.0e-3, abs=10e-6)
    assert analysis.ac_rms_v["vin_p"] == pytest.approx(np.sqrt(noise_rms_v**2 + (0.2e-3) ** 2 / 2.0), rel=0.02)
    assert analysis.ac_rms_v["vin_diff"] == pytest.approx(np.sqrt(2.0 * noise_rms_v**2 + (0.2e-3) ** 2 / 2.0), rel=0.02)
    for name, rms_v in analysis.spectrum_rms_v.items():
        assert rms_v == pytest.approx(analysis.ac_rms_v[name], rel=0.03)
    assert analysis.sample_rate_hz == pytest.approx(sample_rate_hz)

    restored = read_analysis(write_analysis(tmp_path / "scope.h5", analysis))
    with pytest.raises(ValueError, match="cannot contain '/'"):
        write_analysis(tmp_path / "slash.h5", dataclasses.replace(analysis, ac_rms_v={"(p+n)/2": 1.0}))
    assert isinstance(restored, AnalysisScope)
    assert restored.name == analysis.name
    assert restored.ac_rms_v == pytest.approx(analysis.ac_rms_v)
    np.testing.assert_array_equal(restored.wave.v["vin_diff"], analysis.wave.v["vin_diff"])


def test_scope_noise_plots_are_exact_16_by_9(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_plots, "PLOT_PNGS", True)
    rng = np.random.default_rng(8)
    x_scale = SimpleNamespace(offset=0.0, slope=10.0e-9)
    waveforms = {
        channel: SimpleNamespace(data=rng.normal(10.0e-3, 0.5e-3, 10_000), x_scale=x_scale) for channel in (1, 2)
    }
    analysis = scope_analysis(
        waveforms,
        ScopeConns(ch1="vin_p", ch2="vin_n"),
        name="synthetic",
        bandwidth_hz=SCOPE_BANDWIDTH_HZ,
        differential={"vin_diff": ("vin_p", "vin_n")},
    )

    for paths in (
        plot_histogram(analysis, title="Distribution", output_path=tmp_path / "histogram"),
        plot_spectrum([analysis, analysis], title="Spectrum", output_path=tmp_path / "spectrum"),
        plot_waveforms(analysis.wave, title="Traces", output_path=tmp_path / "traces"),
    ):
        assert tuple(path.suffix for path in paths) == (".png", ".pdf")
        assert Image.open(paths[0]).size == (4800, 2700)
