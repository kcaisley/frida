"""Typed OTA measurements, results, and analyses.

A ``MeasOta`` is one operating point, AC response, transfer-function (``xf``) and noise analysis
of the OTA testbench: the differential output per volt of differential input, magnitude and
unwrapped phase, and the output noise density, at each frequency; and at ``outp`` alone, the
output per volt of differential input, of input common mode and of supply, the rejections'
ingredients. Its operating point (supply current, output and load bias voltages) is in the run
readbacks. The figures are Usb2Phy's op-amp bench's (DC gain, unity-gain bandwidth, phase margin)
and the group's archived amplifier benches' (gain-bandwidth product, gain margin, PSRR, CMRR),
each a calculator function of ``flow.analysis.calc``. A ``MeasOtaTran`` is the unity-gain bench's
transient (LF-Monopix2 ``TB_AnaBuffer``): ``outp``'s response to a large input step (slew rate,
settling, overshoot) or to a sine (harmonic distortion).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, check_identity, measurement_identity
from flow.ota.sim import OtaTbParams
from flow.ota.subckt import OtaNets, OtaParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasOta(Meas):
    """OTA AC response and output noise at one supply and input common mode: one row per frequency."""

    dut: OtaParams
    param: OtaTbParams
    frequency_hz: np.ndarray
    gain_v_per_v: np.ndarray
    phase_deg: np.ndarray
    output_noise_v_rthz: np.ndarray
    outp_gain_v_per_v: np.ndarray
    common_mode_gain_v_per_v: np.ndarray
    supply_gain_v_per_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisOtaAc(Analysis):
    """OTA small-signal figures at each measured point.

    ``gain_db`` and ``phase_deg`` hold the response, one row per point and one column per
    ``frequency_hz``. ``dc_gain_db`` is the gain at the lowest frequency, ``ugbw_hz`` the
    first unity-gain crossing (``unityGainFreq``), ``phase_margin_deg`` 180° plus the phase
    there relative to the lowest frequency (``phaseMargin``); NaN where the gain never reaches
    unity. ``bandwidth_hz`` is the -3 dB frequency (``bandwidth``), ``gbw_hz`` the DC gain times
    it (``gainBwProd``), ``gain_margin_db`` how far below unity the gain is where the phase has
    turned 180° (``gainMargin``, positive when stable; NaN for a response that never turns so
    far). ``psrr_db`` and ``cmrr_db`` (per point and frequency) are the differential gain at
    ``outp`` over the gain there from the supply and from the input common mode, and
    ``low_psrr_db`` / ``low_cmrr_db`` their values at the lowest frequency. Both are taken at
    ``outp``, the only output of a single-ended amplifier and one side of a differential one,
    whose differential output rejects both perfectly without mismatch. Every figure is NaN where
    the ideal common-mode feedback drives vbp beyond the rails: no real feedback holds the
    output common mode there (a folded cascode at the lowest supplies).
    """

    vdd_v: np.ndarray
    vcm_v: np.ndarray
    frequency_hz: np.ndarray
    gain_db: np.ndarray
    phase_deg: np.ndarray
    dc_gain_db: np.ndarray
    ugbw_hz: np.ndarray
    phase_margin_deg: np.ndarray
    bandwidth_hz: np.ndarray
    gbw_hz: np.ndarray
    gain_margin_db: np.ndarray
    psrr_db: np.ndarray
    cmrr_db: np.ndarray
    low_psrr_db: np.ndarray
    low_cmrr_db: np.ndarray
    supply_current_a: np.ndarray
    output_cm_v: np.ndarray

    @property
    def power_w(self) -> np.ndarray:
        return self.vdd_v * self.supply_current_a


def analyze_ota_ac(measurements: Sequence[MeasOta]) -> AnalysisOtaAc:
    """Measure DC gain, unity-gain bandwidth, phase and gain margin, gain-bandwidth product, PSRR,
    CMRR, supply current and output common mode."""

    identity = measurement_identity(measurements)
    frequency_hz = measurements[0].frequency_hz
    if any(not np.array_equal(item.frequency_hz, frequency_hz) for item in measurements):
        raise ValueError("OTA AC analysis requires one frequency sweep for every point")
    rows = []
    for measurement in measurements:
        # the response with its phase relative to the lowest frequency: an inverting output starts at 180°
        relative_deg = measurement.phase_deg - measurement.phase_deg[0]
        response = measurement.gain_v_per_v * np.exp(1j * np.radians(relative_deg))
        gain_db = calc.db20(measurement.gain_v_per_v)
        if gain_db[0] > 0:
            ugbw_hz = calc.unityGainFreq(response, frequency_hz)
            phase_margin_deg = calc.phaseMargin(response, frequency_hz)
        else:
            ugbw_hz = phase_margin_deg = math.nan
        psrr_db = calc.db20(measurement.outp_gain_v_per_v) - calc.db20(measurement.supply_gain_v_per_v)
        cmrr_db = calc.db20(measurement.outp_gain_v_per_v) - calc.db20(measurement.common_mode_gain_v_per_v)
        readbacks = measurement.info.readbacks
        outputs = [float(readbacks["op_outp_v"])]
        if "op_outn_v" in readbacks:
            outputs.append(float(readbacks["op_outn_v"]))
        # the -3 dB bandwidth once: the gain-bandwidth product (calc.gainBwProd) is the DC gain times it
        bandwidth_hz = calc.bandwidth(response, frequency_hz, 10 * math.log10(2.0), "low")
        figures = (
            gain_db,
            # whole turns off, the start in [-270, 90) as the margins take it
            measurement.phase_deg - 360 * math.floor((measurement.phase_deg[0] + 270) / 360),
            psrr_db,
            cmrr_db,
            float(gain_db[0]),
            ugbw_hz,
            phase_margin_deg,
            bandwidth_hz,
            float(measurement.gain_v_per_v[0]) * bandwidth_hz,
            calc.gainMargin(response, frequency_hz, stable=True),
            float(psrr_db[0]),
            float(cmrr_db[0]),
            float(readbacks["op_supply_current_a"]),
            calc.average(outputs),
        )
        if not 0.0 <= float(readbacks["op_vbp_v"]) <= float(measurement.param.vdd):
            figures = (*(np.full_like(gain_db, math.nan) for _ in range(4)), *[math.nan] * 10)
        rows.append((float(measurement.param.vdd), float(measurement.param.vcm), *figures))
    (
        vdd_v,
        vcm_v,
        gain_db,
        phase_deg,
        psrr_db,
        cmrr_db,
        dc_gain_db,
        ugbw_hz,
        phase_margin_deg,
        bandwidth_hz,
        gbw_hz,
        gain_margin_db,
        low_psrr_db,
        low_cmrr_db,
        current,
        output_cm_v,
    ) = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    return AnalysisOtaAc(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vcm_v=vcm_v,
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        gain_db=gain_db,
        phase_deg=phase_deg,
        dc_gain_db=dc_gain_db,
        ugbw_hz=ugbw_hz,
        phase_margin_deg=phase_margin_deg,
        bandwidth_hz=bandwidth_hz,
        gbw_hz=gbw_hz,
        gain_margin_db=gain_margin_db,
        psrr_db=psrr_db,
        cmrr_db=cmrr_db,
        low_psrr_db=low_psrr_db,
        low_cmrr_db=low_cmrr_db,
        supply_current_a=current,
        output_cm_v=output_cm_v,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisOtaNoise(Analysis):
    """OTA input-referred noise at each measured point.

    ``input_noise_v_rthz`` is the output noise density over the differential gain, one row per
    point and one column per ``frequency_hz``; ``spot_noise_v_rthz`` its value at the sweep
    frequency nearest 1 MHz (``spot_frequency_hz``); ``integrated_noise_v`` its RMS from the
    lowest frequency to the unity-gain bandwidth (NaN where there is none). Points the AC result
    leaves out, their load bias beyond the rails, are NaN.
    """

    vdd_v: np.ndarray
    vcm_v: np.ndarray
    frequency_hz: np.ndarray
    input_noise_v_rthz: np.ndarray
    spot_frequency_hz: float
    spot_noise_v_rthz: np.ndarray
    integrated_noise_v: np.ndarray


def analyze_ota_noise(measurements: Sequence[MeasOta], *, ac: AnalysisOtaAc) -> AnalysisOtaNoise:
    """Refer the output noise to the input, and take its 1 MHz spot value and its RMS to the unity-gain bandwidth."""

    identity = measurement_identity(measurements)
    check_identity(ac, identity, name="ac")
    if len(measurements) != len(ac.vdd_v) or any(
        float(item.param.vdd) != vdd or float(item.param.vcm) != vcm
        for item, vdd, vcm in zip(measurements, ac.vdd_v, ac.vcm_v, strict=True)
    ):
        raise ValueError("OTA noise requires the AC result of the same points in the same order")
    frequency_hz = measurements[0].frequency_hz
    spot = int(np.argmin(np.abs(np.log10(frequency_hz) - 6.0)))
    densities, integrated = [], []
    for measurement, dc_gain_db, ugbw_hz in zip(measurements, ac.dc_gain_db, ac.ugbw_hz, strict=True):
        density = measurement.output_noise_v_rthz / measurement.gain_v_per_v
        if not math.isfinite(dc_gain_db):
            density = np.full_like(density, math.nan)
        densities.append(density)
        if math.isfinite(ugbw_hz):
            band, band_hz = calc.clip(density, frequency_hz, float(frequency_hz[0]), ugbw_hz)
            integrated.append(calc.rmsNoise(band, band_hz))
        else:
            integrated.append(math.nan)
    densities = np.asarray(densities, dtype=np.float64)
    return AnalysisOtaNoise(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=ac.vdd_v,
        vcm_v=ac.vcm_v,
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        input_noise_v_rthz=densities,
        spot_frequency_hz=float(frequency_hz[spot]),
        spot_noise_v_rthz=densities[:, spot],
        integrated_noise_v=np.asarray(integrated, dtype=np.float64),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasOtaTran(Meas):
    """OTA unity-gain transient, a step or a sine: one record, all in ``wave``."""

    dut: OtaParams
    param: OtaTbParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisOtaSlew(Analysis):
    """OTA unity-gain step response at each step point.

    ``low_v`` and ``high_v`` are ``outp``'s levels just before the rising and falling input steps,
    ``rise_slew_v_per_s`` and ``fall_slew_v_per_s`` its 10–90 % slopes between them (``slewrate``;
    the fall's negative), ``rise_settling_s`` and ``fall_settling_s`` the time from each input edge
    until it stays within 1 % of the step (``settlingTime``; NaN where it never does, as when the
    loop rings on), ``rise_overshoot`` and ``fall_overshoot`` how far it passes the final level, a
    fraction of the step (``overshoot``), ``supply_current_a`` the average over the period. The edges are NaN where the
    output moves less than a tenth of the step.
    """

    vcm_v: np.ndarray
    step_v: np.ndarray
    low_v: np.ndarray
    high_v: np.ndarray
    rise_slew_v_per_s: np.ndarray
    fall_slew_v_per_s: np.ndarray
    rise_settling_s: np.ndarray
    fall_settling_s: np.ndarray
    rise_overshoot: np.ndarray
    fall_overshoot: np.ndarray
    supply_current_a: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisOtaDistortion(Analysis):
    """OTA unity-gain sine response at each sine point: ``thd_db`` and ``sndr_db`` of ``outp`` over
    the whole periods after the first two (``spectrumMeas``, harmonics to the fifth), and its
    fundamental's ``gain_v_per_v`` over the input's amplitude; ``frequency_hz`` and
    ``spectrum_dbfs`` its spectrum relative to the input's amplitude, one row per point."""

    vcm_v: np.ndarray
    amplitude_v: np.ndarray
    sine_hz: np.ndarray
    thd_db: np.ndarray
    sndr_db: np.ndarray
    gain_v_per_v: np.ndarray
    frequency_hz: np.ndarray
    spectrum_dbfs: np.ndarray


def analyze_ota_slew(measurements: Sequence[MeasOtaTran]) -> AnalysisOtaSlew:
    """Measure ``outp``'s slew rates, settling and overshoot on the input's rising and falling steps."""

    identity = measurement_identity(measurements)
    if not all(float(item.param.step_v) for item in measurements):
        raise ValueError("OTA slew requires the unity-gain step bench")
    rows = []
    for measurement in measurements:
        wave, tb = measurement.wave, measurement.param
        if wave is None:
            raise ValueError("OTA slew requires a waveform record")
        time_s, output = wave.time_s, wave.v[OtaNets.outp.name][0]
        period, edge = float(tb.period_s), float(tb.transition_time_s)
        rise_s, fall_s = period / 4, 3 * period / 4
        # the levels: the output just before each input edge
        low = calc.average(*calc.clip(output, time_s, rise_s - period / 20, rise_s))
        high = calc.average(*calc.clip(output, time_s, fall_s - period / 20, fall_s))
        up_v, up_s = calc.clip(output, time_s, rise_s, fall_s)
        down_v, down_s = calc.clip(output, time_s, fall_s, float(time_s[-1]))
        # an output that moves less than a tenth of the step (stuck, or not following) has no edges
        if high - low > float(tb.step_v) / 10:
            rise_settled = calc.settlingTime(up_v, up_s, initial=low, final=high, percent_of_step=1.0)
            fall_settled = calc.settlingTime(down_v, down_s, initial=high, final=low, percent_of_step=1.0)
            edges = (
                calc.slewrate(up_v, up_s, low, high),
                calc.slewrate(down_v, down_s, high, low),
                rise_settled - rise_s - edge / 2,
                fall_settled - fall_s - edge / 2,
                max(calc.overshoot(up_v, up_s, low, high), 0.0) / 100,
                max(calc.overshoot(down_v, down_s, high, low), 0.0) / 100,
            )
        else:
            edges = (math.nan,) * 6
        rows.append(
            (float(tb.vcm), float(tb.step_v), low, high, *edges, calc.average(wave.i[OtaNets.vdd.name][0], time_s))
        )
    columns = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    vcm_v, step_v, low_v, high_v, rise_slew, fall_slew, rise_settling, fall_settling, rise_over, fall_over, current = (
        columns
    )
    return AnalysisOtaSlew(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vcm_v=vcm_v,
        step_v=step_v,
        low_v=low_v,
        high_v=high_v,
        rise_slew_v_per_s=rise_slew,
        fall_slew_v_per_s=fall_slew,
        rise_settling_s=rise_settling,
        fall_settling_s=fall_settling,
        rise_overshoot=rise_over,
        fall_overshoot=fall_over,
        supply_current_a=current,
    )


def analyze_ota_distortion(measurements: Sequence[MeasOtaTran]) -> AnalysisOtaDistortion:
    """Measure ``outp``'s harmonic distortion and gain on the unity-gain sine."""

    identity = measurement_identity(measurements)
    if not all(float(item.param.sine_v) for item in measurements):
        raise ValueError("OTA distortion requires the unity-gain sine bench")
    rows, spectra = [], []
    for measurement in measurements:
        wave, tb = measurement.wave, measurement.param
        if wave is None:
            raise ValueError("OTA distortion requires a waveform record")
        interval, amplitude = float(tb.waveform_sample_interval_s), float(tb.sine_v)
        # whole periods after the first two, on the record's uniform grid
        samples = round((tb.sine_periods - 2) / tb.sine_hz / interval)
        output = wave.v[OtaNets.outp.name][0][-samples:]
        sndr, _snr, thd, _sfdr, _enob, frequency_hz, spectrum = calc.spectrumMeas(
            output,
            sample_rate=1 / interval,
            fundamental_frequency=tb.sine_hz,
            offset=calc.average(output),
            full_scale_peak=amplitude,
            maximum_harmonic_order=5,
        )
        fundamental = int(np.argmin(np.abs(frequency_hz - tb.sine_hz)))
        rows.append((float(tb.vcm), amplitude, tb.sine_hz, thd, sndr, 10 ** (spectrum[fundamental] / 20)))
        spectra.append((frequency_hz, spectrum))
    vcm_v, amplitude_v, sine_hz, thd_db, sndr_db, gain = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True)
    )
    length = min(len(frequency_hz) for frequency_hz, _ in spectra)
    return AnalysisOtaDistortion(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vcm_v=vcm_v,
        amplitude_v=amplitude_v,
        sine_hz=sine_hz,
        thd_db=thd_db,
        sndr_db=sndr_db,
        gain_v_per_v=gain,
        frequency_hz=np.asarray(spectra[0][0][:length], dtype=np.float64),
        spectrum_dbfs=np.asarray([spectrum[:length] for _, spectrum in spectra], dtype=np.float64),
    )
