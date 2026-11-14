"""The amplifier's analyses: each from runs' measurements (``flow.pipeline.Meas``) or earlier
results, and the record's metrics.

A small-signal run (``Bench.AC``) holds, on one frequency sweep, the AC response to the balun's
1 V differential stimulus (``sweeps["ac"]``), the transfer to the amplifier's output from every
source (``sweeps["xf"]``; at the nominal point also to the input common mode the inputs ride on,
``sweeps["xf_vcm"]``), the output noise (``sweeps["noise"]``) and the operating point
(``sweeps["opdc"]``, with each transistor's V_DS and V_D,sat): the differential gain and phase and
the figures read from them, the PSRR and CMRR of a single-ended output, the supply and tail
currents, the output level and each device's distance from triode (``analyze_ac``), the input
common-mode range over the common-mode sweep (``analyze_range``), and the noise
(``analyze_noise``). A unity-gain run holds a transient: ``outp``'s response to a large input step
(``analyze_slew``: slew rate, settling, overshoot) or to a sine (``analyze_distortion``). Each
figure is a calculator function of ``flow.analysis.calc``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.analysis import calc
from flow.pipeline import Meas, analysis, check_identity, measurement_identity

from .params import SPECTRUM_HARMONICS, SUPPLY_SWEEP, Bench, Params, Topology
from .subckt import Nets
from .types import AnalysisAc, AnalysisDistortion, AnalysisNoise, AnalysisRange, AnalysisSlew, Metrics


def _single_ended(params: Params) -> bool:
    """Whether the amplifier has one output, ``outp`` (``TbParams.single_ended``)."""
    return params.topology in (Topology.FIVE_T, Topology.SELF_BIASED)


def _response(measurement: Meas) -> np.ndarray:
    """The amplifier's AC output per volt of differential input, its polarity taken off:
    ``outp`` minus ``outn``, or ``outp`` alone of a single-ended amplifier (whose run saves no
    ``outn``), turned over where the topology inverts it. Every first stage follows the input
    with ``outp`` (``subckt``: a five-transistor or self-biased amplifier's ``outp`` on inn's
    drain, a differential one's inp side driving ``outn``), and a common-source second stage
    inverts (``Params.two_stage``); so the phase keeps what the lowest frequency has turned,
    however far that is."""
    ac = measurement.sweeps["ac"]
    outp = ac.v[Nets.outp.name]
    output = outp - ac.v[Nets.outn.name] if Nets.outn.name in ac.v else outp
    # [Razavi-Analog] Fig. 9.23, p. 361: a two-stage op amp, its second stage common-source
    # [Razavi-Analog] Eq. (3.10), p. 48: a common-source stage's gain, -g_m R_D: it inverts
    return -output if measurement.tb.params.two_stage else output


def _margins(op_v: dict[str, np.ndarray], params: Params) -> tuple[float, float]:
    """The least V_DS - V_D,sat (magnitudes) over the amplifier's bench-biased transistors, and
    over its tail and input pair alone, from the operating point's saved ``<device>:vds`` and
    ``<device>:vdsat``; the self-biased amplifier's tails, which its own drains bias, left out."""
    devices = sorted(key.removesuffix(":vds") for key in op_v if key.endswith(":vds"))
    own = params.topology is Topology.SELF_BIASED
    margins = {
        device: abs(float(op_v[f"{device}:vds"][0])) - abs(float(op_v[f"{device}:vdsat"][0]))
        for device in devices
        if not (own and device.startswith("Mtail"))
    }
    pair = [margin for device, margin in margins.items() if device.startswith(("Min_", "Mtail"))]
    return min(margins.values()), min(pair)


@analysis
def analyze_ac(measurements: Sequence[Meas]) -> AnalysisAc:
    """Measure the low-frequency gain, unity-gain bandwidth, phase and gain margin, gain-bandwidth
    product, PSRR, CMRR, supply and tail currents, output level and saturation margins at each
    point."""

    identity = measurement_identity(measurements)
    frequency_hz = measurements[0].sweeps["ac"].x
    if any(not np.array_equal(item.sweeps["ac"].x, frequency_hz) for item in measurements):
        raise ValueError("amplifier AC analysis requires one frequency sweep for every point")
    rows = []
    for measurement in measurements:
        tb = measurement.tb
        single = _single_ended(tb.params)
        xf, op = measurement.sweeps["xf"], measurement.sweeps["opdc"]
        response = _response(measurement)
        # [Razavi-Analog] Fig. 6.43, p. 204: gain over frequency
        gain_db = np.asarray(calc.db20(response))
        # [Razavi-Analog] Sec. 10.1, Fig. 10.2, p. 411: phase of the loop transmission (beta = 1)
        phase_deg = calc.phaseDegUnwrapped(response)
        if gain_db[0] > 0:
            # [Razavi-Analog] Fig. 6.43, p. 204: unity-gain bandwidth
            unity_gain_bandwidth_hz = calc.unityGainFreq(response, frequency_hz)
            # [Razavi-Analog] Sec. 10.3, p. 417: phase margin, 180 deg plus the phase at the crossover
            phase_margin_deg = calc.phaseMargin(response, frequency_hz)
        else:
            unity_gain_bandwidth_hz = phase_margin_deg = math.nan
        if single:
            # the output per volt on each source: the differential gain (the balun's halves), the
            # common mode's (both inputs) and the supply's (the amplifier's and the bias network's)
            to_inp, to_inn = xf.v[Nets.inp.name], xf.v[Nets.inn.name]
            gain_diff, gain_cm = (to_inp - to_inn) / 2, to_inp + to_inn
            gain_supply = xf.v[Nets.vdd.name] + xf.v["vddb"]
            if "xf_vcm" in measurement.sweeps:
                # the inputs held: less the path through the nominal input common mode they ride on
                moved = measurement.sweeps["xf_vcm"]
                gain_supply = gain_supply - (moved.v[Nets.vdd.name] + moved.v["vddb"]) * gain_cm
            # [Razavi-Analog] Sec. 9.11, p. 400: power supply rejection ratio
            psrr_db = np.asarray(calc.db20(gain_diff) - calc.db20(gain_supply))
            # [Razavi-Analog] Eq. (5.42), p. 157: common-mode rejection ratio of a single output
            cmrr_db = np.asarray(calc.db20(gain_diff) - calc.db20(gain_cm))
            vout_v, vout_cm_v = float(op.v[Nets.outp.name][0]), math.nan
        else:
            # [Razavi-Analog] Eq. (4.55), p. 123: a differential output's CMRR, over A_CM-DM, which
            # vanishes without mismatch; its PSRR alike
            psrr_db = cmrr_db = np.full_like(gain_db, math.nan)
            # [Razavi-Analog] Sec. 4.2, p. 103: output common-mode level
            vout_v, vout_cm_v = math.nan, calc.average([float(op.v[net.name][0]) for net in (Nets.outp, Nets.outn)])
        # [Razavi-Analog] Fig. 6.43, p. 204: -3 dB bandwidth
        # the -3 dB bandwidth once: the gain-bandwidth product (calc.gainBwProd) is the low-frequency gain times it
        bandwidth_hz = calc.bandwidth(response, frequency_hz, 10 * math.log10(2.0), "low")
        tail = next(key for key in sorted(op.v) if key.startswith("Mtail") and key.endswith(":ids"))
        figures = (
            gain_db,
            phase_deg,
            psrr_db,
            cmrr_db,
            # [Razavi-Analog] Sec. 6.7.1, p. 204: low-frequency gain
            float(gain_db[0]),
            unity_gain_bandwidth_hz,
            phase_margin_deg,
            bandwidth_hz,
            # [Razavi-Analog] Eq. (6.98), p. 204: gain-bandwidth product
            float(np.abs(response[0])) * bandwidth_hz,
            # [Baker] Sec. 24.1, p. 810: gain margin, how far below unity the gain is where the phase reaches -180 deg
            calc.gainMargin(response, frequency_hz, stable=True),
            float(psrr_db[0]),
            float(cmrr_db[0]),
            # [Baker] Sec. 24.1, p. 805: the amplifier's supply current
            float(op.i[Nets.vdd.name][0]),
            # [Razavi-Analog] Sec. 4.2, Fig. 4.7, p. 103: tail current
            abs(float(op.v[tail][0])),
            vout_v,
            vout_cm_v,
            # [Razavi-Analog] Example 2.2, p. 18: V_D,sat, the least V_DS of saturation
            *_margins(op.v, tb.params),
        )
        # the ideal feedback holds vbp between the rails: on one (within a microvolt) it has lost the output
        if not single and not 1e-6 < float(op.v[Nets.vbp.name][0]) < float(tb.vdd) - 1e-6:
            figures = (*(np.full_like(gain_db, math.nan) for _ in range(4)), *[math.nan] * 14)
        rows.append((float(tb.vdd), float(op.v[Nets.inp.name][0]), *figures))
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
        iss_a,
        vout_v,
        vout_cm_v,
        saturation_margin_v,
        saturation_margin_pair_v,
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
        iss_a=iss_a,
        vout_v=vout_v,
        vout_cm_v=vout_cm_v,
        saturation_margin_v=saturation_margin_v,
        saturation_margin_pair_v=saturation_margin_pair_v,
    )


def _end(vin_cm_v: np.ndarray, margin: np.ndarray, inside: int, outside: int) -> float:
    """Where the saturation margin crosses zero between a point inside the range and its
    neighbour outside, linearly; at the inside point where the neighbour has no margin (NaN)."""
    if not math.isfinite(float(margin[outside])):
        return float(vin_cm_v[inside])
    pair = sorted((inside, outside))
    edge = "rising" if outside < inside else "falling"
    return calc.cross(margin[pair], vin_cm_v[pair], 0.0, edge=edge, occurrence=1)


@analysis
def analyze_range(cm: AnalysisAc, *, nominal: AnalysisAc) -> AnalysisRange:
    """Measure the input common-mode range: about the nominal point (``nominal``, one point), the
    span of the common-mode sweep (``cm``, ascending, at its supply) over which the tail and the
    input pair stay saturated, its ends interpolated, a rail where the sweep ends inside it."""

    check_identity(nominal, cm.identity, name="nominal")
    if len(nominal.vdd_v) != 1 or np.any(cm.vdd_v != nominal.vdd_v[0]) or np.any(np.diff(cm.vin_cm_v) <= 0):
        raise ValueError("amplifier input range requires one nominal point and a rising sweep at its supply")
    vin_cm_v = np.r_[cm.vin_cm_v, nominal.vin_cm_v]
    margin = np.r_[cm.saturation_margin_pair_v, nominal.saturation_margin_pair_v]
    order = np.argsort(vin_cm_v, kind="stable")
    vin_cm_v, margin = vin_cm_v[order], margin[order]
    at = int(np.flatnonzero(order == len(order) - 1)[0])
    low = high = math.nan
    # [Razavi-Analog] Eq. (4.1), p. 105: input common-mode range, the tail and input pair saturated
    if margin[at] >= 0:
        first = last = at
        while first > 0 and margin[first - 1] >= 0:
            first -= 1
        while last < len(margin) - 1 and margin[last + 1] >= 0:
            last += 1
        low = float(vin_cm_v[0]) if first == 0 else _end(vin_cm_v, margin, first, first - 1)
        high = float(vin_cm_v[-1]) if last == len(margin) - 1 else _end(vin_cm_v, margin, last, last + 1)
    return AnalysisRange(
        group=cm.group,
        index=cm.index,
        dut=cm.dut,
        vdd_v=float(nominal.vdd_v[0]),
        vin_cm_v=float(nominal.vin_cm_v[0]),
        vin_cm_min_v=low,
        vin_cm_max_v=high,
        vin_cm_range_v=high - low,
    )


@analysis
def analyze_noise(measurements: Sequence[Meas], *, ac: AnalysisAc) -> AnalysisNoise:
    """Integrate the output noise over the sweep and refer it to the input by the low-frequency
    gain; refer its density to the input by the gain at each frequency, and take its 1 MHz value."""

    identity = measurement_identity(measurements)
    check_identity(ac, identity, name="ac")
    if len(measurements) != len(ac.vdd_v) or any(
        float(item.tb.vdd) != vdd or float(item.sweeps["opdc"].v[Nets.inp.name][0]) != vin_cm
        for item, vdd, vin_cm in zip(measurements, ac.vdd_v, ac.vin_cm_v, strict=True)
    ):
        raise ValueError("amplifier noise requires the AC result of the same points in the same order")
    frequency_hz = measurements[0].sweeps["noise"].x
    if any(not np.array_equal(item.sweeps["noise"].x, frequency_hz) for item in measurements) or not np.array_equal(
        frequency_hz, ac.frequency_hz
    ):
        raise ValueError("amplifier noise requires the AC result's frequency sweep")
    # not in the reference texts: the spot density at the sweep point nearest 1 MHz in log frequency
    spot = int(np.argmin(np.abs(np.log10(frequency_hz) - 6.0)))
    outputs, densities, integrated = [], [], []
    for measurement, gain_db, gain_dc_db in zip(measurements, ac.gain_db, ac.gain_dc_db, strict=True):
        # [Razavi-Analog] Sec. 7.1.1, p. 223: noise spectral density
        output = np.asarray(measurement.sweeps["noise"].v["out"], dtype=np.float64)
        if not math.isfinite(gain_dc_db):
            output = np.full_like(output, math.nan)
        outputs.append(output)
        # [Razavi-Analog] Example 7.11, Eq. (7.45), p. 238: the output noise density over the gain
        densities.append(output / 10 ** (gain_db / 20))
        # [Razavi-Analog] Sec. 7.8, Eq. (7.145), p. 264: total output noise
        integrated.append(calc.rmsNoise(output, frequency_hz) if math.isfinite(gain_dc_db) else math.nan)
    noise_out_v = np.asarray(integrated, dtype=np.float64)
    densities = np.asarray(densities, dtype=np.float64)
    return AnalysisNoise(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=ac.vdd_v,
        vin_cm_v=ac.vin_cm_v,
        frequency_hz=np.asarray(frequency_hz, dtype=np.float64),
        noise_out_v_per_rthz=np.asarray(outputs, dtype=np.float64),
        noise_in_v_per_rthz=densities,
        spot_frequency_hz=float(frequency_hz[spot]),
        noise_in_1mhz_v_per_rthz=densities[:, spot],
        noise_out_v=noise_out_v,
        # [Razavi-Analog] Sec. 7.9, Eq. (7.147), p. 265: total input-referred noise, the integrated
        # output noise over the low-frequency gain
        noise_in_v=noise_out_v / 10 ** (ac.gain_dc_db / 20),
    )


def _settled(values: np.ndarray, band: float) -> bool:
    """Whether a level's window is settled: every sample within ``band`` of the window's average,
    and its last sample less its first within a quarter of the band."""
    return bool(np.all(np.abs(values - calc.average(values)) <= band)) and abs(values[-1] - values[0]) <= band / 4


def _steepest(values: np.ndarray, time_s: np.ndarray, initial: float, final: float) -> float:
    """An edge's steepest slope between its 10 % and 90 % crossings (signed), over the intervals
    of the time axis that overlap them."""
    rising = final > initial
    edge = "rising" if rising else "falling"
    first = calc.cross(values, time_s, initial + 0.1 * (final - initial), edge=edge, occurrence=1)
    last = calc.cross(values, time_s, initial + 0.9 * (final - initial), edge=edge, occurrence=1)
    if not (math.isfinite(first) and math.isfinite(last)):
        return math.nan
    slopes = calc.deriv(values, time_s)[(time_s[1:] > first) & (time_s[:-1] < last)]
    return float(np.max(slopes) if rising else np.min(slopes))


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
        output, stimulus = measurement.v[Nets.outp.name], measurement.v[Nets.inp.name]
        period, edge = float(tb.step_period_s), float(tb.transition_time_s)
        rise_s, fall_s, end_s, window = period / 4, 3 * period / 4, float(time_s[-1]), period / 20
        # the levels: each over the window before an input edge, and the output's last
        windows = [calc.clip(output, time_s, start - window, start) for start in (rise_s, fall_s, end_s)]
        low, high, end = (calc.average(*level) for level in windows)
        vin_low, vin_high = (
            calc.average(*calc.clip(stimulus, time_s, start - window, start)) for start in (rise_s, fall_s)
        )
        up_v, up_s = calc.clip(output, time_s, rise_s, fall_s)
        down_v, down_s = calc.clip(output, time_s, fall_s, end_s)
        band = abs(high - low) / 100
        # an output that moves less than a tenth of the step (stuck, or not following) has no edges
        if high - low > float(tb.vin_step_v) / 10:
            # the rise settles to the high level, the fall to the low level the run starts from, each
            # where its level holds over its window, the fall's also at the run's end
            high_settled = _settled(windows[1][0], band)
            low_settled = _settled(windows[0][0], band) and _settled(windows[2][0], band) and abs(end - low) <= band
            # [Razavi-Analog] Example 9.2, Eq. (9.11), p. 347: settling time to 1 % of the final value
            rise_settled = calc.settlingTime(up_v, up_s, initial=low, final=high, percent_of_step=1.0)
            fall_settled = calc.settlingTime(down_v, down_s, initial=high, final=low, percent_of_step=1.0)
            edges = (
                # [Razavi-Analog] Sec. 9.9, Fig. 9.70, p. 391: slew rate, the slope of the slewing ramp
                _steepest(up_v, up_s, low, high),
                _steepest(down_v, down_s, high, low),
                rise_settled - rise_s - edge / 2 if high_settled else math.nan,
                fall_settled - fall_s - edge / 2 if low_settled else math.nan,
                # not in the reference texts: how far a step response passes its final level, a
                # fraction of the step (the calculator's overshoot)
                max(calc.overshoot(up_v, up_s, low, high), 0.0) / 100,
                max(calc.overshoot(down_v, down_s, high, low), 0.0) / 100,
            )
        else:
            edges = (math.nan,) * 6
        # [Baker] Sec. 24.1, p. 805: the amplifier's supply current, averaged over the period
        idd_a = calc.average(measurement.i[Nets.vdd.name], time_s)
        rows.append((vin_low, vin_high, rise_s + edge / 2, fall_s + edge / 2, low, high, *edges, idd_a))
        outputs.append(output)
    (
        vin_low_v,
        vin_high_v,
        vin_rise_s,
        vin_fall_s,
        low_v,
        high_v,
        rise_slew,
        fall_slew,
        rise_settling,
        fall_settling,
        rise_over,
        fall_over,
        idd,
    ) = (np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True))
    return AnalysisSlew(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vin_low_v=vin_low_v,
        vin_high_v=vin_high_v,
        vin_rise_s=vin_rise_s,
        vin_fall_s=vin_fall_s,
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
        stimulus = calc.value(measurement.v[Nets.inp.name], measurement.time_s, grid_s)
        # [Razavi-Analog] Sec. 14.1.1, Eq. (14.10), p. 579: total harmonic distortion, the harmonics'
        # power over the fundamental's, summed to the seventh harmonic (SPECTRUM_HARMONICS)
        # [Razavi-ADC] Eq. (8.17), p. 152: signal-to-(noise + distortion) ratio
        sndr, _snr, thd, _sfdr, _enob, frequency_hz, spectrum = calc.spectrumMeas(
            output,
            sample_rate=1 / interval,
            fundamental_frequency=tb.vin_frequency_hz,
            offset=calc.average(output),
            full_scale_peak=amplitude,
            maximum_harmonic_order=SPECTRUM_HARMONICS,
        )
        fundamental = int(np.argmin(np.abs(frequency_hz - tb.vin_frequency_hz)))
        # [Razavi-Analog] Example 9.2, Eqs. (9.5)-(9.7), p. 347: closed-loop gain of the buffer
        gain = 10 ** (spectrum[fundamental] / 20)
        rows.append((calc.average(stimulus), amplitude, tb.vin_frequency_hz, thd, sndr, gain))
        spectra.append((frequency_hz, spectrum))
    if len({len(frequency_hz) for frequency_hz, _ in spectra}) != 1:
        raise ValueError("amplifier distortion requires one record length for every point")
    vin_cm_v, vin_amplitude_v, vin_frequency_hz, thd_db, sndr_db, gain = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows, strict=True)
    )
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
        frequency_hz=np.asarray(spectra[0][0], dtype=np.float64),
        spectrum_db=np.asarray([spectrum for _, spectrum in spectra], dtype=np.float64),
    )


def _inside(low: float, high: float, span: AnalysisRange) -> bool:
    """Whether the input levels ``low`` to ``high`` lie within the input common-mode range."""
    return bool(span.vin_cm_min_v <= low and high <= span.vin_cm_max_v)


def metrics(
    *,
    ac: AnalysisAc,
    noise: AnalysisNoise,
    span: AnalysisRange,
    supply: AnalysisAc,
    slew: AnalysisSlew | None = None,
    distortion: AnalysisDistortion | None = None,
) -> Metrics:
    """The record's numbers: from the nominal point (``ac``, ``noise``: one point) the small-signal
    figures, power, currents, output level and noise; the input common-mode range (``span``); from
    the supply's points (``supply``, in ``SUPPLY_SWEEP``'s order) the lowest low-frequency gain and
    saturation margin (NaN where a point lost its output); from a single-ended amplifier's
    unity-gain runs (``slew``, ``distortion``) its slew rates, the slower edge's settling and its
    distortion, NaN where the stimulus leaves the input common-mode range."""

    if len(ac.vdd_v) != 1 or not np.allclose(supply.vdd_v / ac.vdd_v[0], SUPPLY_SWEEP, rtol=1e-3):
        raise ValueError("amplifier metrics require the nominal point and the supply's points about it")
    single = _single_ended(ac.dut)
    gain_margin_db = float(ac.gain_margin_db[0])
    # no phase crossover on the sweep: the margin lies beyond it, unmeasured rather than failed
    unbounded = math.isnan(gain_margin_db) and math.isfinite(float(ac.gain_dc_db[0]))
    step = slew is not None and _inside(float(slew.vin_low_v[0]), float(slew.vin_high_v[0]), span)
    sine = distortion is not None and _inside(
        float(distortion.vin_cm_v[0] - distortion.vin_amplitude_v[0]),
        float(distortion.vin_cm_v[0] + distortion.vin_amplitude_v[0]),
        span,
    )
    return Metrics(
        gain_dc_db=float(ac.gain_dc_db[0]),
        unity_gain_bandwidth_hz=float(ac.unity_gain_bandwidth_hz[0]),
        phase_margin_deg=float(ac.phase_margin_deg[0]),
        gain_margin_db=None if unbounded else gain_margin_db,
        bandwidth_hz=float(ac.bandwidth_hz[0]),
        psrr_dc_db=float(ac.psrr_dc_db[0]) if single else None,
        cmrr_dc_db=float(ac.cmrr_dc_db[0]) if single else None,
        power_w=float(ac.power_w[0]),
        iss_a=float(ac.iss_a[0]),
        vout_v=float(ac.vout_v[0]) if single else None,
        noise_in_1mhz_v_per_rthz=float(noise.noise_in_1mhz_v_per_rthz[0]),
        noise_in_v=float(noise.noise_in_v[0]),
        vin_cm_min_v=span.vin_cm_min_v,
        vin_cm_max_v=span.vin_cm_max_v,
        vin_cm_range_v=span.vin_cm_range_v,
        gain_dc_min_supply_db=float(np.min(supply.gain_dc_db)),
        saturation_margin_min_supply_v=float(np.min(supply.saturation_margin_v)),
        slew_rate_rise_v_per_s=(float(slew.slew_rate_rise_v_per_s[0]) if step else math.nan)
        if slew is not None
        else None,
        slew_rate_fall_v_per_s=(float(-slew.slew_rate_fall_v_per_s[0]) if step else math.nan)
        if slew is not None
        else None,
        settling_s=(float(np.max([slew.settling_rise_s[0], slew.settling_fall_s[0]])) if step else math.nan)
        if slew is not None
        else None,
        thd_db=(float(distortion.thd_db[0]) if sine else math.nan) if distortion is not None else None,
    )
