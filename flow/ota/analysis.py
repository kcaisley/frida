"""Typed OTA measurements, results, and analyses.

A ``MeasOta`` is one operating point, AC response and noise analysis of the OTA testbench: the
differential output per volt of differential input, magnitude and unwrapped phase, and the
output noise density, at each frequency. Its
operating point (supply current, output and load bias voltages) is in the run readbacks. The
figures are Usb2Phy's op-amp bench's: DC gain and unity-gain bandwidth, with the phase margin.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, check_identity, measurement_identity
from flow.ota.sim import OtaTbParams
from flow.ota.subckt import OtaParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasOta(Meas):
    """OTA AC response and output noise at one supply and input common mode: one row per frequency."""

    dut: OtaParams
    param: OtaTbParams
    frequency_hz: np.ndarray
    gain_v_per_v: np.ndarray
    phase_deg: np.ndarray
    output_noise_v_rthz: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisOtaAc(Analysis):
    """OTA small-signal figures at each measured point.

    ``gain_db`` and ``phase_deg`` hold the response, one row per point and one column per
    ``frequency_hz``. ``dc_gain_db`` is the gain at the lowest frequency, ``ugbw_hz`` the
    first unity-gain crossing (log-interpolated), ``phase_margin_deg`` 180° plus the phase
    there relative to the lowest frequency; NaN where the gain never reaches unity. Every
    figure is NaN where the ideal common-mode feedback drives vbp beyond the rails: no real
    feedback holds the output common mode there (a folded cascode at the lowest supplies).
    """

    vdd_v: np.ndarray
    vcm_v: np.ndarray
    frequency_hz: np.ndarray
    gain_db: np.ndarray
    phase_deg: np.ndarray
    dc_gain_db: np.ndarray
    ugbw_hz: np.ndarray
    phase_margin_deg: np.ndarray
    supply_current_a: np.ndarray
    output_cm_v: np.ndarray

    @property
    def power_w(self) -> np.ndarray:
        return self.vdd_v * self.supply_current_a


def analyze_ota_ac(measurements: Sequence[MeasOta]) -> AnalysisOtaAc:
    """Measure DC gain, unity-gain bandwidth, phase margin, supply current, and output common mode."""

    identity = measurement_identity(measurements)
    frequency_hz = measurements[0].frequency_hz
    if any(not np.array_equal(item.frequency_hz, frequency_hz) for item in measurements):
        raise ValueError("OTA AC analysis requires one frequency sweep for every point")
    log_frequency = np.log10(frequency_hz)
    rows = []
    for measurement in measurements:
        gain_db = 20 * np.log10(measurement.gain_v_per_v)
        # the phase relative to the lowest frequency: an inverting output starts at 180°
        phase_deg = measurement.phase_deg - 360 * np.round(measurement.phase_deg[0] / 360)
        crossing = calc.cross(gain_db, log_frequency, 0.0, edge="falling", occurrence=1)
        if gain_db[0] > 0 and math.isfinite(crossing):
            ugbw_hz = 10**crossing
            phase_margin_deg = 180 + calc.value(phase_deg - phase_deg[0], log_frequency, crossing)
        else:
            ugbw_hz = phase_margin_deg = math.nan
        readbacks = measurement.info.readbacks
        outputs = [float(readbacks["op_outp_v"])]
        if "op_outn_v" in readbacks:
            outputs.append(float(readbacks["op_outn_v"]))
        figures = (
            gain_db,
            phase_deg,
            float(gain_db[0]),
            ugbw_hz,
            phase_margin_deg,
            float(readbacks["op_supply_current_a"]),
            calc.average(outputs),
        )
        if not 0.0 <= float(readbacks["op_vbp_v"]) <= float(measurement.param.vdd):
            figures = (np.full_like(gain_db, math.nan), np.full_like(phase_deg, math.nan), *[math.nan] * 5)
        rows.append((float(measurement.param.vdd), float(measurement.param.vcm), *figures))
    vdd_v, vcm_v, gain_db, phase_deg, dc_gain_db, ugbw_hz, phase_margin_deg, current, output_cm_v = (
        np.asarray(column, dtype=np.float64) for column in zip(*rows)
    )
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
