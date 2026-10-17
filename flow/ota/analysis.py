"""Typed OTA measurements, results, and analyses.

A ``MeasOta`` is one operating point and AC response of the OTA testbench: the differential
output per volt of differential input, magnitude and unwrapped phase, at each frequency. Its
operating point (supply current, output and load bias voltages) is in the run readbacks. The
figures are Usb2Phy's op-amp bench's: DC gain and unity-gain bandwidth, with the phase margin.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.ota.sim import OtaTbParams
from flow.ota.subckt import OtaParams


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasOta(Meas):
    """OTA AC response at one supply and input common mode: one row per frequency."""

    dut: OtaParams
    param: OtaTbParams
    frequency_hz: np.ndarray
    gain_v_per_v: np.ndarray
    phase_deg: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisOtaAc(Analysis):
    """OTA small-signal figures at each measured point.

    ``gain_db`` and ``phase_deg`` hold the response, one row per point and one column per
    ``frequency_hz``. ``dc_gain_db`` is the gain at the lowest frequency, ``ugbw_hz`` the
    first unity-gain crossing (log-interpolated), ``phase_margin_deg`` 180° plus the phase
    there relative to the lowest frequency; NaN where the gain never reaches unity.
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
        rows.append(
            (
                float(measurement.param.vdd),
                float(measurement.param.vcm),
                gain_db,
                phase_deg,
                float(gain_db[0]),
                ugbw_hz,
                phase_margin_deg,
                float(readbacks["op_supply_current_a"]),
                calc.average(outputs),
            )
        )
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
