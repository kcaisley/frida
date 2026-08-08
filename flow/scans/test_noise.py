"""Measure the quiet THS4541 differential output with the CH1 probe.

The Agilent 33250A is held at a literal 0 V DC output, the E3634A sets the
THS4541 output common mode to 0.8 V, and the TDP3500 differential probe on
MSO54 CH1 measures ``Vin_p - Vin_n``. CH1 uses its minimum accepted 20 MHz
bandwidth and minimum accepted 2.5 mV/div scale for the final capture. The
MSO54 may quantize the requested 100 ksample record to a longer supported
length; the accepted value is preserved in the summary.

Run from the repository root with:

    uv run pytest -q -s -m hw flow/scans/test_noise.py

The run saves its raw waveform, a JSON summary, and a 16:9 Gaussian/FFT plot
under ``build/loopback_noise``. The AWG and VIN_CM outputs are disabled
and reset to 0 V on every exit; changed scope settings are restored.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from time import sleep, strftime

import matplotlib.pyplot as plt
import numpy as np
import pytest
from basil.HL.tektronix_oscilloscope import response_value
from PIL import Image
from scipy.signal import welch

from flow.analysis.plots import (
    DETAILED_16_9_FIGSIZE,
    LEGEND_FACE_COLOR,
    NORD_BLUE,
    NORD_GREEN,
    NORD_RED,
    PLOT_FACE_COLOR,
    PLOT_STYLE,
    PNG_DPI,
    SPINE_COLOR,
    style_ax,
    style_grid,
    style_legend,
)
from flow.scans.scan_adc import convert_vdiff_input_to_awg_supply
from flow.scans.scope import wait_for_scope_armed, write_scope_csv

MAP_DIR = Path(__file__).resolve().parent
CAPTURE_DIR = Path(__file__).resolve().parents[2] / "build" / "loopback_noise"

AWG_DC_V = 0.0
TARGET_VIN_CM_V = 0.8
VIN_CM_CURRENT_LIMIT_A = 10.0e-3
SETTLE_TIME_S = 0.5

SCOPE_CHANNEL = 1
SCOPE_TRACKS = {SCOPE_CHANNEL: "vdiff_ch1"}
SCOPE_BANDWIDTH_HZ = 20.0e6
SCOPE_RECORD_LENGTH = 100_000
SCOPE_HORIZONTAL_SCALE_S = 1.0e-3
SCOPE_COARSE_VERTICAL_SCALE_V = 50.0e-3
SCOPE_FINE_VERTICAL_SCALE_V = 2.5e-3
SCOPE_ACQUISITION_SETTLE_S = 0.2
SCOPE_ARM_TIMEOUT_S = 5.0


@dataclass(frozen=True, slots=True)
class DiffampNoiseAnalysis:
    """Gaussian and spectral characterization of one quiet waveform."""

    mean_v: float
    noise_rms_v: float
    sample_rate_hz: float
    frequency_hz: np.ndarray
    amplitude_spectral_density_v_per_sqrt_hz: np.ndarray
    integrated_fft_noise_rms_v: float
    strongest_bin_frequency_hz: float
    strongest_bin_asd_v_per_sqrt_hz: float


def analyze_diffamp_noise(
    samples_v: np.ndarray,
    *,
    sample_interval_s: float,
) -> DiffampNoiseAnalysis:
    """Fit a Gaussian width and Welch-averaged one-sided FFT noise density."""

    samples = np.asarray(samples_v, dtype=np.float64)
    if samples.ndim != 1 or len(samples) < 256:
        raise ValueError("diff-amp noise analysis requires at least 256 one-dimensional samples")
    if np.any(~np.isfinite(samples)):
        raise ValueError("diff-amp noise samples must be finite")
    if not math.isfinite(sample_interval_s) or sample_interval_s <= 0.0:
        raise ValueError("sample interval must be finite and positive")

    mean_v = float(np.mean(samples))
    centered_v = samples - mean_v
    noise_rms_v = float(np.sqrt(np.mean(centered_v**2)))
    sample_rate_hz = 1.0 / sample_interval_s
    segment_length = min(262_144, len(centered_v))
    frequency_hz, power_spectral_density_v2_per_hz = welch(
        centered_v,
        fs=sample_rate_hz,
        window="hann",
        nperseg=segment_length,
        noverlap=segment_length // 2,
        detrend=False,
        return_onesided=True,
        scaling="density",
    )
    amplitude_spectral_density_v_per_sqrt_hz = np.sqrt(np.maximum(power_spectral_density_v2_per_hz, 0.0))
    integrated_fft_noise_rms_v = float(np.sqrt(np.trapezoid(power_spectral_density_v2_per_hz, frequency_hz)))
    strongest_index = 1 + int(np.argmax(amplitude_spectral_density_v_per_sqrt_hz[1:]))
    return DiffampNoiseAnalysis(
        mean_v=mean_v,
        noise_rms_v=noise_rms_v,
        sample_rate_hz=sample_rate_hz,
        frequency_hz=frequency_hz,
        amplitude_spectral_density_v_per_sqrt_hz=amplitude_spectral_density_v_per_sqrt_hz,
        integrated_fft_noise_rms_v=integrated_fft_noise_rms_v,
        strongest_bin_frequency_hz=float(frequency_hz[strongest_index]),
        strongest_bin_asd_v_per_sqrt_hz=float(amplitude_spectral_density_v_per_sqrt_hz[strongest_index]),
    )


def plot_diffamp_noise(
    samples_v: np.ndarray,
    analysis: DiffampNoiseAnalysis,
    *,
    scope_bandwidth_hz: float,
    output_path: Path,
) -> tuple[Path, ...]:
    """Plot the centered voltage histogram and FFT-derived noise density."""

    centered_mv = (np.asarray(samples_v) - analysis.mean_v) * 1e3
    noise_rms_mv = analysis.noise_rms_v * 1e3
    gaussian_x_mv = np.linspace(-5.0 * noise_rms_mv, 5.0 * noise_rms_mv, 1001)
    gaussian_density_per_mv = np.exp(-0.5 * (gaussian_x_mv / noise_rms_mv) ** 2) / (noise_rms_mv * np.sqrt(2.0 * np.pi))

    with plt.rc_context(PLOT_STYLE):
        fig, (histogram_ax, fft_ax) = plt.subplots(1, 2, figsize=DETAILED_16_9_FIGSIZE)
        histogram_ax.hist(
            centered_mv,
            bins=120,
            density=True,
            color=NORD_BLUE,
            alpha=0.75,
            edgecolor=PLOT_FACE_COLOR,
            linewidth=0.35,
            label="Measured CH1 samples",
        )
        histogram_ax.plot(
            gaussian_x_mv,
            gaussian_density_per_mv,
            color=NORD_RED,
            linewidth=1.8,
            label=f"Gaussian fit: mean = 0, noise RMS = {noise_rms_mv:.3f} mV",
        )
        histogram_ax.axvline(0.0, color=SPINE_COLOR, linestyle=":", linewidth=0.8)
        histogram_ax.set_xlabel("CH1 differential noise about its mean (mV)")
        histogram_ax.set_ylabel("Probability density (1/mV)")
        histogram_ax.set_title("Diff-amp output noise distribution")
        style_legend(histogram_ax, loc="upper left")
        histogram_ax.text(
            0.98,
            0.98,
            "\n".join(
                (
                    f"Raw DC mean: {analysis.mean_v * 1e3:.3f} mV",
                    f"Time-domain RMS: {noise_rms_mv:.3f} mV",
                    f"Samples: {len(centered_mv):,}",
                    f"Sample rate: {analysis.sample_rate_hz / 1e6:.3f} MS/s",
                    f"Scope bandwidth: {scope_bandwidth_hz / 1e6:.3f} MHz",
                )
            ),
            transform=histogram_ax.transAxes,
            horizontalalignment="right",
            verticalalignment="top",
            fontsize="small",
            bbox={
                "boxstyle": "round,pad=0.35",
                "facecolor": LEGEND_FACE_COLOR,
                "edgecolor": SPINE_COLOR,
                "alpha": 0.9,
                "linewidth": 0.8,
            },
        )

        positive_frequency = analysis.frequency_hz > 0.0
        fft_ax.loglog(
            analysis.frequency_hz[positive_frequency],
            analysis.amplitude_spectral_density_v_per_sqrt_hz[positive_frequency] * 1e6,
            color=NORD_GREEN,
            linewidth=1.0,
            label="Welch-averaged one-sided FFT",
        )
        fft_ax.axvline(
            scope_bandwidth_hz,
            color=NORD_RED,
            linestyle="--",
            linewidth=0.9,
            label=f"CH1 bandwidth = {scope_bandwidth_hz / 1e6:g} MHz",
        )
        fft_ax.set_xlabel("Frequency (Hz)")
        fft_ax.set_ylabel("Amplitude spectral density (uV/sqrt(Hz))")
        fft_ax.set_title("Diff-amp output noise spectrum")
        style_legend(fft_ax, loc="lower left")
        fft_ax.text(
            0.98,
            0.98,
            "\n".join(
                (
                    f"FFT-integrated RMS: {analysis.integrated_fft_noise_rms_v * 1e3:.3f} mV",
                    f"Strongest non-DC bin: {analysis.strongest_bin_frequency_hz / 1e3:.3f} kHz",
                    "Scope and TDP3500 noise are not de-embedded",
                )
            ),
            transform=fft_ax.transAxes,
            horizontalalignment="right",
            verticalalignment="top",
            fontsize="small",
            bbox={
                "boxstyle": "round,pad=0.35",
                "facecolor": LEGEND_FACE_COLOR,
                "edgecolor": SPINE_COLOR,
                "alpha": 0.9,
                "linewidth": 0.8,
            },
        )

        for ax in (histogram_ax, fft_ax):
            style_ax(ax)
            style_grid(ax)
        fig.suptitle("THS4541 quiet-output loopback: AWG = 0 V DC, Vin_cm = 0.8 V")
        fig.tight_layout()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        paths = []
        for suffix in ("png", "pdf", "svg"):
            path = output_path.with_suffix(f".{suffix}")
            fig.savefig(
                path,
                facecolor=PLOT_FACE_COLOR,
                dpi=PNG_DPI if suffix == "png" else None,
                bbox_inches=None,
            )
            paths.append(path)
        plt.close(fig)
    return tuple(paths)


@pytest.mark.hw
def test_diffamp_noise_loopback() -> None:
    """Configure the bench, acquire one quiet waveform, and save its analysis."""

    calibrated_awg_zero_v, vin_cm_supply_v = convert_vdiff_input_to_awg_supply(
        0.0,
        TARGET_VIN_CM_V,
    )
    if not 0.0 <= vin_cm_supply_v <= 1.2:
        raise ValueError(f"calibrated VIN_CM supply setpoint {vin_cm_supply_v:g} V is unsafe")

    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    awg_dut = Dut(str(MAP_DIR / "map_awg.yaml"))
    supply_dut = Dut(str(MAP_DIR / "map_supply.yaml"))
    scope_dut = Dut(str(MAP_DIR / "map_scope.yaml"))
    initialized_duts = []
    awg = supply = scope = None
    scope_state = None
    run_timestamp = strftime("%Y%m%d_%H%M%S")
    run_dir = CAPTURE_DIR / run_timestamp

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

        scope_dut.init()
        initialized_duts.append(scope_dut)
        scope = scope_dut["scope"]

        awg_id = str(awg.get_name()).strip()
        supply_id = str(supply.get_name()).strip()
        scope_id = str(scope.get_name()).strip()
        probe_type = str(scope._intf.query("CH1:PROBE:ID:TYPE?")).strip().strip('"')
        probe_resistance_ohm = float(response_value(scope._intf.query("CH1:PROBE:RESISTANCE?")))
        probe_gain = float(response_value(scope._intf.query("CH1:PROBE:GAIN?")))
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
            "display": response_value(scope._intf.query("DISplay:GLObal:CH1:STATE?")),
        }

        scope.set_acquire_state("STOP")
        scope.set_acquire_mode("SAMPLE")
        scope.set_acquire_stop_after("RUNSTOP")
        scope.set_horizontal_scale(SCOPE_HORIZONTAL_SCALE_S)
        scope.set_horizontal_record_length(SCOPE_RECORD_LENGTH)
        scope._intf.write("HORizontal:POSition 50")
        scope._intf.write("DISplay:GLObal:CH1:STATE ON")
        scope.set_coupling("DC", channel=SCOPE_CHANNEL)
        scope.set_vertical_position(0.0, channel=SCOPE_CHANNEL)
        scope.set_vertical_offset(0.0, channel=SCOPE_CHANNEL)
        scope.set_vertical_scale(SCOPE_COARSE_VERTICAL_SCALE_V, channel=SCOPE_CHANNEL)
        scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=SCOPE_CHANNEL)
        scope.set_trigger_type("EDGE")
        scope.set_trigger_source(channel=SCOPE_CHANNEL)
        scope.set_trigger_edge_slope("RISE")
        scope.set_trigger_level(0.0, channel=SCOPE_CHANNEL)
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
        awg.set_DC(f"DEF,DEF,{AWG_DC_V}")
        awg.set_enable(1)
        sleep(SETTLE_TIME_S)
        awg_offset_read_v = float(str(awg.get_voltage_offset()).strip().split(",")[0])
        if abs(awg_offset_read_v - AWG_DC_V) > 0.5e-3:
            raise RuntimeError(f"AWG DC readback is {awg_offset_read_v:g} V, expected {AWG_DC_V:g} V")

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
        scope.set_trigger_level(coarse_mean_v, channel=SCOPE_CHANNEL)
        accepted_vertical_scale_v = float(response_value(scope.get_vertical_scale(channel=SCOPE_CHANNEL)))
        if accepted_vertical_scale_v != SCOPE_FINE_VERTICAL_SCALE_V:
            raise RuntimeError(
                f"scope accepted {accepted_vertical_scale_v:g} V/div instead of {SCOPE_FINE_VERTICAL_SCALE_V:g} V/div"
            )

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
            raise RuntimeError("scope did not return the fine CH1 waveform")
        waveform = waveforms[SCOPE_CHANNEL]
        samples_v = np.asarray(waveform.data, dtype=np.float64)
        if len(samples_v) != accepted_record_length:
            raise RuntimeError(
                f"scope returned {len(samples_v)} samples, expected its accepted record length {accepted_record_length}"
            )

        analysis = analyze_diffamp_noise(
            samples_v,
            sample_interval_s=float(waveform.x_scale.slope),
        )
        clipped = float(np.max(np.abs(samples_v - analysis.mean_v))) >= 4.5 * accepted_vertical_scale_v
        run_dir.mkdir(parents=True, exist_ok=True)
        waveform_path = write_scope_csv(run_dir / "waveform.csv", waveforms, SCOPE_TRACKS)
        plot_paths = plot_diffamp_noise(
            samples_v,
            analysis,
            scope_bandwidth_hz=accepted_bandwidth_hz,
            output_path=run_dir / "noise_gaussian_fft",
        )
        summary = {
            "timestamp": run_timestamp,
            "awg_identity": awg_id,
            "awg_dc_set_v": AWG_DC_V,
            "awg_dc_read_v": awg_offset_read_v,
            "calibrated_awg_voltage_for_zero_vdiff_v": calibrated_awg_zero_v,
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
            "strongest_non_dc_bin_frequency_hz": analysis.strongest_bin_frequency_hz,
            "strongest_non_dc_bin_asd_v_per_sqrt_hz": analysis.strongest_bin_asd_v_per_sqrt_hz,
            "waveform_csv": str(waveform_path),
            "plots": [str(path) for path in plot_paths],
            "measurement_note": "CH1 result includes TDP3500 and MSO54 measurement noise",
        }
        summary_path = run_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        print(f"Saved summary: {summary_path}")
        print(
            f"Fine CH1: mean={analysis.mean_v * 1e3:.6f} mV, "
            f"time RMS={analysis.noise_rms_v * 1e3:.6f} mV, "
            f"FFT-integrated RMS={analysis.integrated_fft_noise_rms_v * 1e3:.6f} mV"
        )
        print(f"Artifacts: {run_dir}")
        if clipped:
            raise RuntimeError("fine CH1 waveform approaches the scope range limit; artifacts were retained")
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
                scope._intf.write(f"DISplay:GLObal:CH1:STATE {scope_state['display']}")
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

    analysis = analyze_diffamp_noise(samples_v, sample_interval_s=1.0 / sample_rate_hz)

    assert analysis.mean_v == pytest.approx(12.0e-3, abs=10e-6)
    assert analysis.noise_rms_v == pytest.approx(np.sqrt(noise_rms_v**2 + (0.2e-3) ** 2 / 2.0), rel=0.02)
    assert analysis.integrated_fft_noise_rms_v == pytest.approx(analysis.noise_rms_v, rel=0.03)
    assert analysis.strongest_bin_frequency_hz == pytest.approx(tone_frequency_hz, rel=0.002)


def test_diffamp_noise_plot_is_exact_16_by_9(tmp_path: Path) -> None:
    rng = np.random.default_rng(8)
    samples_v = rng.normal(10.0e-3, 0.5e-3, 10_000)
    analysis = analyze_diffamp_noise(samples_v, sample_interval_s=10.0e-9)

    paths = plot_diffamp_noise(
        samples_v,
        analysis,
        scope_bandwidth_hz=20.0e6,
        output_path=tmp_path / "noise",
    )

    assert tuple(path.suffix for path in paths) == (".png", ".pdf", ".svg")
    assert Image.open(paths[0]).size == (3200, 1800)
