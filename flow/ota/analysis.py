"""The amplifier's analyses: each from runs' measurements (``flow.pipeline.Meas``), and the
record's metrics.

A small-signal run (``Bench.AC``) holds, on one frequency sweep, the AC response to the balun's
1 V differential stimulus (``sweeps["ac"]``), the transfer to ``outp`` from every source
(``sweeps["xf"]``), the output noise (``sweeps["noise"]``) and the operating point
(``sweeps["opdc"]``): the differential gain and phase and the figures read from them, the PSRR and
CMRR at ``outp``, the supply current and the output common mode (``analyze_ac``), and the noise
referred to the input (``analyze_noise``). A unity-gain run holds a transient: ``outp``'s response
to a large input step (``analyze_slew``: slew rate, settling, overshoot) or to a sine
(``analyze_distortion``). Each figure is a calculator function of ``flow.analysis.calc``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.pipeline import Meas, analysis, check_identity, measurement_identity

from .params import CM_SWEEP, GAIN_DROP_DB, NOMINAL_CM, Bench
from .subckt import Nets
from .types import AnalysisAc, AnalysisDistortion, AnalysisNoise, AnalysisSlew, Metrics


def _response(measurement: Meas) -> np.ndarray:
    """The differential AC response to the 1 V differential stimulus: ``outp`` minus ``outn``, or
    ``outp`` alone of a single-ended amplifier, whose run saves no ``outn``."""
    ac = measurement.sweeps["ac"]
    outp = ac.v[Nets.outp.name]
    return outp - ac.v[Nets.outn.name] if Nets.outn.name in ac.v else outp


def _span(within: np.ndarray, center: int) -> tuple[int, int]:
    """The run of true entries about ``center``: its first and last index."""
    low = high = center
    while low > 0 and within[low - 1]:
        low -= 1
    while high < len(within) - 1 and within[high + 1]:
        high += 1
    return low, high


@analysis
def analyze_ac(measurements: Sequence[Meas]) -> AnalysisAc:
    """Measure the low-frequency gain, unity-gain bandwidth, phase and gain margin, gain-bandwidth
    product, PSRR, CMRR, supply current and output common mode at each point."""

    identity = measurement_identity(measurements)
    frequency_hz = measurements[0].sweeps["ac"].x
    if any(not np.array_equal(item.sweeps["ac"].x, frequency_hz) for item in measurements):
        raise ValueError("amplifier AC analysis requires one frequency sweep for every point")
    rows = []
    for measurement in measurements:
        tb = measurement.tb
        xf, op = measurement.sweeps["xf"], measurement.sweeps["opdc"]
        output = _response(measurement)
        gain, phase_deg = np.abs(output), calc.phaseDegUnwrapped(output)
        # the response with its phase relative to the lowest frequency: an inverting output starts at 180 degrees
        response = gain * np.exp(1j * np.radians(phase_deg - phase_deg[0]))
        gain_db = np.asarray(calc.db20(gain))
        if gain_db[0] > 0:
            # [Razavi-Analog] Fig. 6.43, p. 204: unity-gain bandwidth
            unity_gain_bandwidth_hz = calc.unityGainFreq(response, frequency_hz)
            # [Razavi-Analog] Sec. 10.3, p. 417: phase margin
            phase_margin_deg = calc.phaseMargin(response, frequency_hz)
        else:
            unity_gain_bandwidth_hz = phase_margin_deg = math.nan
        # at outp: the differential gain (the balun's halves), the common mode's (both inputs), the supply's
        to_inp, to_inn = xf.v[Nets.inp.name], xf.v[Nets.inn.name]
        gain_outp, gain_cm, gain_supply = (
            np.abs((to_inp - to_inn) / 2),
            np.abs(to_inp + to_inn),
            np.abs(xf.v[Nets.vdd.name]),
        )
        # [Razavi-Analog] Sec. 9.11, p. 400: power supply rejection ratio
        psrr_db = np.asarray(calc.db20(gain_outp) - calc.db20(gain_supply))
        # [Razavi-Analog] Eq. (4.55), p. 123: common-mode rejection ratio
        cmrr_db = np.asarray(calc.db20(gain_outp) - calc.db20(gain_cm))
        # a single-ended amplifier's run saves no outn
        outputs = [float(op.v[net.name][0]) for net in (Nets.outp, Nets.outn) if net.name in op.v]
        # [Razavi-Analog] Fig. 6.43, p. 204: -3-dB bandwidth
        # the -3 dB bandwidth once: the gain-bandwidth product (calc.gainBwProd) is the low-frequency gain times it
        bandwidth_hz = calc.bandwidth(response, frequency_hz, 10 * math.log10(2.0), "low")
        figures = (
            gain_db,
            # whole turns off, the start in [-270, 90) as the margins take it
            phase_deg - 360 * math.floor((phase_deg[0] + 270) / 360),
            psrr_db,
            cmrr_db,
            # [Razavi-Analog] Sec. 6.7.1, p. 204: low-frequency gain
            float(gain_db[0]),
            unity_gain_bandwidth_hz,
            phase_margin_deg,
            bandwidth_hz,
            # [Razavi-Analog] Eq. (6.98), p. 204: gain-bandwidth product
            float(gain[0]) * bandwidth_hz,
            # [Baker] Sec. 24.1, p. 810: gain margin
            calc.gainMargin(response, frequency_hz, stable=True),
            float(psrr_db[0]),
            float(cmrr_db[0]),
            # [Razavi-PLL] Example 3.5, p. 70: supply current
            float(op.i[Nets.vdd.name][0]),
            # [Razavi-Analog] Sec. 4.2, p. 103: output common-mode level
            calc.average(outputs),
        )
        if not 0.0 <= float(op.v[Nets.vbp.name][0]) <= float(tb.vdd):
            figures = (*(np.full_like(gain_db, math.nan) for _ in range(4)), *[math.nan] * 10)
        rows.append((float(tb.vdd), float(tb.vin_cm_v), *figures))
    (
        vdd_v,
        vin_cm_v,
        gain_db,
        phase_deg,
        psrr_db,
        cmrr_db,
        gain_dc_db,
        unity_gain_bandwidth_hz,
        phase_margin_deg,
        bandwidth_hz,
        gbw_hz,
        gain_margin_db,
        psrr_dc_db,
        cmrr_dc_db,
        idd_a,
        vout_cm_v,
    ) = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    return AnalysisAc(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        vin_cm_v=vin_cm_v,
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        gain_db=gain_db,
        phase_deg=phase_deg,
        gain_dc_db=gain_dc_db,
        unity_gain_bandwidth_hz=unity_gain_bandwidth_hz,
        phase_margin_deg=phase_margin_deg,
        bandwidth_hz=bandwidth_hz,
        gbw_hz=gbw_hz,
        gain_margin_db=gain_margin_db,
        psrr_db=psrr_db,
        cmrr_db=cmrr_db,
        psrr_dc_db=psrr_dc_db,
        cmrr_dc_db=cmrr_dc_db,
        idd_a=idd_a,
        vout_cm_v=vout_cm_v,
    )


@analysis
def analyze_noise(measurements: Sequence[Meas], *, ac: AnalysisAc) -> AnalysisNoise:
    """Refer the output noise to the input, and take its 1 MHz spot value and its RMS to the
    unity-gain bandwidth."""

    identity = measurement_identity(measurements)
    check_identity(ac, identity, name="ac")
    if len(measurements) != len(ac.vdd_v) or any(
        float(item.tb.vdd) != vdd or float(item.tb.vin_cm_v) != vin_cm
        for item, vdd, vin_cm in zip(measurements, ac.vdd_v, ac.vin_cm_v, strict=True)
    ):
        raise ValueError("amplifier noise requires the AC result of the same points in the same order")
    frequency_hz = measurements[0].sweeps["ac"].x
    spot = int(np.argmin(np.abs(np.log10(frequency_hz) - 6.0)))
    densities, integrated = [], []
    for measurement, gain_dc_db, unity_gain_bandwidth_hz in zip(
        measurements, ac.gain_dc_db, ac.unity_gain_bandwidth_hz, strict=True
    ):
        # [Razavi-Analog] Sec. 7.1.1, p. 223: noise spectral density
        # the output's, over the differential gain: referred to the input
        density = measurement.sweeps["noise"].v["out"] / np.abs(_response(measurement))
        if not math.isfinite(gain_dc_db):
            density = np.full_like(density, math.nan)
        densities.append(density)
        if math.isfinite(unity_gain_bandwidth_hz):
            band, band_hz = calc.clip(density, frequency_hz, float(frequency_hz[0]), unity_gain_bandwidth_hz)
            # [Razavi-Analog] Eq. (7.45), p. 238: input-referred noise
            integrated.append(calc.rmsNoise(band, band_hz))
        else:
            integrated.append(math.nan)
    densities = np.asarray(densities, dtype=np.float64)
    return AnalysisNoise(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=ac.vdd_v,
        vin_cm_v=ac.vin_cm_v,
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        noise_in_v_per_rthz=densities,
        spot_frequency_hz=float(frequency_hz[spot]),
        noise_in_1mhz_v_per_rthz=densities[:, spot],
        noise_in_v=np.asarray(integrated, dtype=np.float64),
    )


@analysis
def analyze_slew(measurements: Sequence[Meas]) -> AnalysisSlew:
    """Measure ``outp``'s slew rates, settling and overshoot on the input's rising and falling steps."""

    identity = measurement_identity(measurements)
    if not all(item.tb.bench is Bench.STEP for item in measurements):
        raise ValueError("amplifier slew requires the unity-gain step bench")
    time_s = measurements[0].time_s
    if any(not np.array_equal(item.time_s, time_s) for item in measurements):
        raise ValueError("amplifier slew requires one time axis for every point")
    rows, outputs = [], []
    for measurement in measurements:
        tb = measurement.tb
        output = measurement.v[Nets.outp.name]
        period, edge = float(tb.step_period_s), float(tb.transition_time_s)
        rise_s, fall_s = period / 4, 3 * period / 4
        # the levels: the output just before each input edge
        low = calc.average(*calc.clip(output, time_s, rise_s - period / 20, rise_s))
        high = calc.average(*calc.clip(output, time_s, fall_s - period / 20, fall_s))
        up_v, up_s = calc.clip(output, time_s, rise_s, fall_s)
        down_v, down_s = calc.clip(output, time_s, fall_s, float(time_s[-1]))
        # an output that moves less than a tenth of the step (stuck, or not following) has no edges
        if high - low > float(tb.vin_step_v) / 10:
            # [Razavi-Analog] Example 9.2, p. 346: settling time to 1 %
            rise_settled = calc.settlingTime(up_v, up_s, initial=low, final=high, percent_of_step=1.0)
            fall_settled = calc.settlingTime(down_v, down_s, initial=high, final=low, percent_of_step=1.0)
            edges = (
                # [Razavi-Analog] Sec. 9.9, p. 391: slew rate
                calc.slewrate(up_v, up_s, low, high),
                calc.slewrate(down_v, down_s, high, low),
                rise_settled - rise_s - edge / 2,
                fall_settled - fall_s - edge / 2,
                # not in the reference texts: how far a step response passes its final level, a
                # fraction of the step (the calculator's overshoot)
                max(calc.overshoot(up_v, up_s, low, high), 0.0) / 100,
                max(calc.overshoot(down_v, down_s, high, low), 0.0) / 100,
            )
        else:
            edges = (math.nan,) * 6
        # [Razavi-PLL] Example 3.5, p. 70: supply current
        idd_a = calc.average(measurement.i[Nets.vdd.name], time_s)
        rows.append((float(tb.vin_cm_v), float(tb.vin_step_v), low, high, *edges, idd_a))
        outputs.append(output)
    columns = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    (
        vin_cm_v,
        vin_step_v,
        low_v,
        high_v,
        rise_slew,
        fall_slew,
        rise_settling,
        fall_settling,
        rise_over,
        fall_over,
        idd,
    ) = columns
    return AnalysisSlew(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_cm_v=vin_cm_v,
        vin_step_v=vin_step_v,
        vout_low_v=low_v,
        vout_high_v=high_v,
        slew_rate_rise_v_per_s=rise_slew,
        slew_rate_fall_v_per_s=fall_slew,
        settling_rise_s=rise_settling,
        settling_fall_s=fall_settling,
        overshoot_rise=rise_over,
        overshoot_fall=fall_over,
        idd_a=idd,
        time_s=np.asarray(time_s, dtype=np.float64),
        vout_v=np.asarray(outputs, dtype=np.float64),
    )


@analysis
def analyze_distortion(measurements: Sequence[Meas]) -> AnalysisDistortion:
    """Measure ``outp``'s harmonic distortion and gain on the unity-gain sine."""

    identity = measurement_identity(measurements)
    if not all(item.tb.bench is Bench.SINE for item in measurements):
        raise ValueError("amplifier distortion requires the unity-gain sine bench")
    rows, spectra = [], []
    for measurement in measurements:
        tb = measurement.tb
        interval, amplitude = float(tb.waveform_sample_interval_s), float(tb.vin_amplitude_v)
        # whole periods after the first two, on a uniform grid of the run's interval to its end
        samples = round((tb.sine_periods - 2) / tb.vin_frequency_hz / interval)
        grid_s = float(measurement.time_s[-1]) - interval * np.arange(samples - 1, -1, -1)
        output = calc.value(measurement.v[Nets.outp.name], measurement.time_s, grid_s)
        # [Razavi-Analog] Eq. (14.10), p. 579: total harmonic distortion
        # [Razavi-ADC] Sec. 8.2.2, p. 150: signal-to-(noise + distortion) ratio
        sndr, _snr, thd, _sfdr, _enob, frequency_hz, spectrum = calc.spectrumMeas(
            output,
            sample_rate=1 / interval,
            fundamental_frequency=tb.vin_frequency_hz,
            offset=calc.average(output),
            full_scale_peak=amplitude,
            maximum_harmonic_order=5,
        )
        fundamental = int(np.argmin(np.abs(frequency_hz - tb.vin_frequency_hz)))
        rows.append((float(tb.vin_cm_v), amplitude, tb.vin_frequency_hz, thd, sndr, 10 ** (spectrum[fundamental] / 20)))
        spectra.append((frequency_hz, spectrum))
    vin_cm_v, vin_amplitude_v, vin_frequency_hz, thd_db, sndr_db, gain = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True)
    )
    length = min(len(frequency_hz) for frequency_hz, _ in spectra)
    return AnalysisDistortion(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_cm_v=vin_cm_v,
        vin_amplitude_v=vin_amplitude_v,
        vin_frequency_hz=vin_frequency_hz,
        thd_db=thd_db,
        sndr_db=sndr_db,
        gain=gain,
        frequency_hz=np.asarray(spectra[0][0][:length], dtype=np.float64),
        spectrum_db=np.asarray([spectrum[:length] for _, spectrum in spectra], dtype=np.float64),
    )


def metrics(
    *,
    ac: AnalysisAc,
    noise: AnalysisNoise,
    supply: AnalysisAc,
    slew: AnalysisSlew | None = None,
    distortion: AnalysisDistortion | None = None,
) -> Metrics:
    """The record's numbers: from the input common mode's runs (``ac``, ``noise``: in
    ``CM_SWEEP``'s order) the small-signal figures, power, output common mode and noise at
    mid-supply input, and the span of common modes about it keeping the low-frequency gain within
    ``GAIN_DROP_DB`` of its mid-supply value (NaN where that point lost its output); from the
    supply's (``supply``) the lowest low-frequency gain (NaN where a point lost its output); from a
    single-ended amplifier's unity-gain runs (``slew``, ``distortion``) its slew rates, the slower
    edge's settling and its distortion."""

    nominal = CM_SWEEP.index(NOMINAL_CM)
    # [Razavi-Analog] Eq. (4.1), p. 105: input common-mode range
    within = ac.gain_dc_db >= ac.gain_dc_db[nominal] - GAIN_DROP_DB  # NaN: outside
    low, high = _span(within, nominal)
    vin_cm_range_v = (CM_SWEEP[high] - CM_SWEEP[low]) * float(ac.vdd_v[nominal]) if within[nominal] else math.nan
    return Metrics(
        gain_dc_db=float(ac.gain_dc_db[nominal]),
        unity_gain_bandwidth_hz=float(ac.unity_gain_bandwidth_hz[nominal]),
        phase_margin_deg=float(ac.phase_margin_deg[nominal]),
        gain_margin_db=float(ac.gain_margin_db[nominal]),
        bandwidth_hz=float(ac.bandwidth_hz[nominal]),
        psrr_dc_db=float(ac.psrr_dc_db[nominal]),
        cmrr_dc_db=float(ac.cmrr_dc_db[nominal]),
        power_w=float(ac.power_w[nominal]),
        vout_cm_v=float(ac.vout_cm_v[nominal]),
        noise_in_1mhz_v_per_rthz=float(noise.noise_in_1mhz_v_per_rthz[nominal]),
        noise_in_v=float(noise.noise_in_v[nominal]),
        vin_cm_range_v=vin_cm_range_v,
        gain_dc_min_supply_db=float(np.min(supply.gain_dc_db)),
        slew_rate_rise_v_per_s=float(slew.slew_rate_rise_v_per_s[0]) if slew is not None else None,
        slew_rate_fall_v_per_s=float(-slew.slew_rate_fall_v_per_s[0]) if slew is not None else None,
        settling_s=float(np.max([slew.settling_rise_s[0], slew.settling_fall_s[0]])) if slew is not None else None,
        thd_db=float(distortion.thd_db[0]) if distortion is not None else None,
    )
