"""Typed MOSFET measurements, results, and analyses.

Every current and voltage is a magnitude: a PMOS's sweeps run to negative voltages, and its
measurements hold the same positive numbers an NMOS's would. The device's drawn width and length
(``w_m``, ``l_m``) are in its run readbacks.

- ``MeasMosfetTransfer``: Id-Vgs at |Vds| ``vds_lin`` (linear) and the supply (saturation).
- ``MeasMosfetOutput``: Id-Vds, one column per gate voltage of the testbench's ``family``.
- ``MeasMosfetNoise``: the drain current's noise and its gate-referred voltage noise at the bias.
- ``MeasMosfetTranNoise``: the drain current at the bias over a transient-noise record.
- ``MeasMosfetMismatch``: the drain current at the bias, one row per Monte Carlo run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas
from flow.mosfet.sim import MosfetTbParams
from flow.mosfet.subckt import MosfetParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasMosfetTransfer(Meas):
    """Id-Vgs: one row per gate voltage."""

    dut: MosfetParams
    param: MosfetTbParams
    vgs_v: np.ndarray
    id_lin_a: np.ndarray
    id_sat_a: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasMosfetOutput(Meas):
    """Id-Vds: one row per drain voltage, one column of ``id_family_a`` per family gate voltage."""

    dut: MosfetParams
    param: MosfetTbParams
    vds_v: np.ndarray
    id_family_a: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasMosfetNoise(Meas):
    """Small-signal noise at the bias: one row per frequency."""

    dut: MosfetParams
    param: MosfetTbParams
    frequency_hz: np.ndarray
    drain_noise_a_rthz: np.ndarray
    gate_noise_v_rthz: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasMosfetTranNoise(Meas):
    """Transient noise at the bias: one row per strobed sample."""

    dut: MosfetParams
    param: MosfetTbParams
    time_s: np.ndarray
    id_a: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasMosfetMismatch(Meas):
    """Monte Carlo of mismatch at the bias: one row per run."""

    dut: MosfetParams
    param: MosfetTbParams
    id_a: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMosfetTransfer(Analysis):
    """The transfer characteristic's figures of merit.

    ``vth_v``: the linear-region curve's tangent at its steepest point, extrapolated to zero
    current, less half of |Vds|. ``subthreshold_swing_mv_dec``: the saturated curve's least gate
    voltage per decade of current, above 1 pA. ``ion_a`` and ``ioff_a``: the saturated current at
    |Vgs| of the supply and of zero. ``gm_s``, ``gm_over_id`` and ``current_density_a_m`` (Id/W)
    hold the saturated curve between each pair of gate-voltage steps (at their midpoints,
    ``gm_vgs_v``), the material of gm/Id design.
    """

    w_m: float
    l_m: float
    vth_v: float
    subthreshold_swing_mv_dec: float
    ion_a: float
    ioff_a: float
    gm_over_id_max: float
    vgs_v: np.ndarray
    id_lin_a: np.ndarray
    id_sat_a: np.ndarray
    gm_vgs_v: np.ndarray
    gm_s: np.ndarray
    gm_over_id: np.ndarray
    current_density_a_m: np.ndarray


def analyze_mosfet_transfer(measurement: MeasMosfetTransfer) -> AnalysisMosfetTransfer:
    """Threshold, subthreshold swing, on and off current, and the gm/Id curve of one device."""

    readbacks = measurement.info.readbacks
    w_m, l_m = float(readbacks["w_m"]), float(readbacks["l_m"])
    vgs, lin, sat = measurement.vgs_v, measurement.id_lin_a, measurement.id_sat_a
    gm_lin = calc.deriv(lin, vgs)
    steepest = int(np.argmax(gm_lin))
    midpoint = (vgs[steepest] + vgs[steepest + 1]) / 2
    current = (lin[steepest] + lin[steepest + 1]) / 2
    vth = midpoint - current / gm_lin[steepest] - measurement.param.vds_lin / 2
    above = sat > 1e-12
    decades = np.log10(np.where(above, sat, 1e-12))
    slope = calc.deriv(decades, vgs)  # decades per volt
    rising = slope[above[:-1] & above[1:] & (slope > 0)]
    swing = 1e3 / float(np.max(rising)) if rising.size else math.nan
    gm_vgs = (vgs[:-1] + vgs[1:]) / 2
    gm = calc.deriv(sat, vgs)
    id_mid = (sat[:-1] + sat[1:]) / 2
    gm_over_id = np.divide(gm, id_mid, out=np.zeros_like(gm), where=id_mid > 1e-15)
    return AnalysisMosfetTransfer(
        group=measurement.group,
        index=measurement.index,
        dut=measurement.dut,
        w_m=w_m,
        l_m=l_m,
        vth_v=float(vth),
        subthreshold_swing_mv_dec=swing,
        ion_a=float(sat[-1]),
        ioff_a=float(sat[0]),
        gm_over_id_max=float(np.max(gm_over_id)),
        vgs_v=np.asarray(vgs, dtype=np.float64),
        id_lin_a=np.asarray(lin, dtype=np.float64),
        id_sat_a=np.asarray(sat, dtype=np.float64),
        gm_vgs_v=gm_vgs,
        gm_s=gm,
        gm_over_id=gm_over_id,
        current_density_a_m=id_mid / w_m,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMosfetOutput(Analysis):
    """The output characteristic at each family gate voltage (``family_vgs_v``).

    At the bias's |Vds| (``bias_vds_v``): ``id_a``, the output conductance ``gds_s``, the Early
    voltage ``early_voltage_v`` (Id over gds), the transconductance ``gm_s`` across the family's
    gate voltages and the intrinsic gain ``intrinsic_gain`` (gm over gds). ``on_resistance_ohm``:
    the first drain-voltage step's resistance. ``vds_v`` and ``id_family_a`` hold the curves.
    """

    bias_vds_v: float
    family_vgs_v: np.ndarray
    id_a: np.ndarray
    gds_s: np.ndarray
    early_voltage_v: np.ndarray
    gm_s: np.ndarray
    intrinsic_gain: np.ndarray
    on_resistance_ohm: np.ndarray
    vds_v: np.ndarray
    id_family_a: np.ndarray


def analyze_mosfet_output(measurement: MeasMosfetOutput) -> AnalysisMosfetOutput:
    """Output conductance, Early voltage, intrinsic gain and on resistance over the family."""

    tb = measurement.param
    vds, curves = measurement.vds_v, measurement.id_family_a
    family = np.asarray(tb.family, dtype=np.float64) * tb.vdd
    bias_vds = tb.bias * tb.vdd
    at = int(np.clip(np.searchsorted(vds, bias_vds), 1, len(vds) - 1))
    gds = (curves[at] - curves[at - 1]) / (vds[at] - vds[at - 1])
    id_bias = (curves[at] + curves[at - 1]) / 2
    gm = np.gradient(id_bias, family) if len(family) > 1 else np.full_like(id_bias, math.nan)
    return AnalysisMosfetOutput(
        group=measurement.group,
        index=measurement.index,
        dut=measurement.dut,
        bias_vds_v=float(bias_vds),
        family_vgs_v=family,
        id_a=id_bias,
        gds_s=gds,
        early_voltage_v=np.divide(id_bias, gds, out=np.full_like(gds, math.inf), where=gds > 0),
        gm_s=gm,
        intrinsic_gain=np.divide(gm, gds, out=np.full_like(gds, math.inf), where=gds > 0),
        on_resistance_ohm=np.divide(
            vds[1] - vds[0], curves[1] - curves[0], out=np.full(curves.shape[1], math.inf), where=curves[1] > curves[0]
        ),
        vds_v=np.asarray(vds, dtype=np.float64),
        id_family_a=np.asarray(curves, dtype=np.float64),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMosfetNoise(Analysis):
    """Small-signal noise at the bias.

    ``white_v_rthz``: the gate-referred floor, the spectrum's least value up to 1 GHz.
    ``flicker_corner_hz``: where the gate-referred power density first falls to twice the
    floor's (the 1/f part equal to the white), NaN where the spectrum starts below it.
    ``gate_1khz_v_rthz`` and ``gate_1mhz_v_rthz``: the gate-referred density at 1 kHz and 1 MHz.
    """

    white_v_rthz: float
    flicker_corner_hz: float
    gate_1khz_v_rthz: float
    gate_1mhz_v_rthz: float
    frequency_hz: np.ndarray
    drain_noise_a_rthz: np.ndarray
    gate_noise_v_rthz: np.ndarray


def analyze_mosfet_noise(measurement: MeasMosfetNoise) -> AnalysisMosfetNoise:
    """The gate-referred white floor, flicker corner and spot noise of one device."""

    frequency, gate = measurement.frequency_hz, measurement.gate_noise_v_rthz
    white = float(np.min(gate[frequency <= 1e9]))
    excess = np.log10(np.square(gate) / (2 * white**2))
    corner = calc.cross(excess, np.log10(frequency), 0.0, edge="falling", occurrence=1) if excess[0] > 0 else math.nan
    return AnalysisMosfetNoise(
        group=measurement.group,
        index=measurement.index,
        dut=measurement.dut,
        white_v_rthz=white,
        flicker_corner_hz=10**corner if math.isfinite(corner) else math.nan,
        gate_1khz_v_rthz=float(10 ** np.interp(3.0, np.log10(frequency), np.log10(gate))),
        gate_1mhz_v_rthz=float(10 ** np.interp(6.0, np.log10(frequency), np.log10(gate))),
        frequency_hz=np.asarray(frequency, dtype=np.float64),
        drain_noise_a_rthz=np.asarray(measurement.drain_noise_a_rthz, dtype=np.float64),
        gate_noise_v_rthz=np.asarray(gate, dtype=np.float64),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMosfetTrannoise(Analysis):
    """The drain current's noise density from its transient-noise record (Welch, eight segments):
    ``drain_noise_a_rthz`` over ``frequency_hz``, and the record's RMS ``rms_a``."""

    rms_a: float
    frequency_hz: np.ndarray
    drain_noise_a_rthz: np.ndarray


def analyze_mosfet_trannoise(measurement: MeasMosfetTranNoise) -> AnalysisMosfetTrannoise:
    """The drain current noise density and RMS of one transient-noise record."""

    time, current = measurement.time_s, measurement.id_a
    deviation = current - np.mean(current)
    frequency, density = calc.psd(
        deviation, sample_rate=1 / float(np.median(np.diff(time))), segment_length=max(64, len(current) // 8)
    )
    return AnalysisMosfetTrannoise(
        group=measurement.group,
        index=measurement.index,
        dut=measurement.dut,
        rms_a=calc.rms(deviation),
        frequency_hz=frequency[1:],
        drain_noise_a_rthz=np.sqrt(density[1:]),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMosfetMismatch(Analysis):
    """Mismatch at the bias over the Monte Carlo runs.

    ``sigma_id_relative``: the drain current's standard deviation over its mean.
    ``sigma_vgs_v``: that deviation referred to the gate through the saturated transconductance at
    the bias's gate voltage (``transfer``). ``avt_v_m``: the Pelgrom coefficient, sigma_vgs times
    the square root of the gate area (V m; 1e-9 V m is 1 mV um).
    """

    runs: int
    id_mean_a: float
    sigma_id_relative: float
    sigma_vgs_v: float
    avt_v_m: float
    id_a: np.ndarray


def analyze_mosfet_mismatch(
    measurement: MeasMosfetMismatch, *, transfer: AnalysisMosfetTransfer
) -> AnalysisMosfetMismatch:
    """Current and gate-referred mismatch, and the Pelgrom coefficient, of one device."""

    current = measurement.id_a
    sigma = float(np.std(current, ddof=1))
    gm = float(np.interp(measurement.param.bias * measurement.param.vdd, transfer.gm_vgs_v, transfer.gm_s))
    sigma_vgs = sigma / gm
    return AnalysisMosfetMismatch(
        group=measurement.group,
        index=measurement.index,
        dut=measurement.dut,
        runs=len(current),
        id_mean_a=float(np.mean(current)),
        sigma_id_relative=sigma / float(np.mean(current)),
        sigma_vgs_v=sigma_vgs,
        avt_v_m=sigma_vgs * math.sqrt(transfer.w_m * transfer.l_m),
        id_a=np.asarray(current, dtype=np.float64),
    )
