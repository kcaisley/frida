"""Typed cascode bias measurements, results, and analyses.

A ``MeasBias`` is one run of the cascode bias testbench: the generator's operating point (its four
gate voltages, the test mirrors' inner nodes and its supply current, in the run readbacks) and both
test mirrors' output currents over their output voltage. The figures are the current source's
(``flow.idac``), for a mirror the generator biases: the current at mid-supply over the reference,
the output resistance there (``deriv``), the compliance (the output voltages around mid-supply
whose current stays within 5 % of it, ``calc.compliance_range``) and the mirror
device's drain-source voltage, the headroom the cascode gate leaves it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis import calc
from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.bias.sim import BiasTbParams
from flow.bias.subckt import BiasParams

# the characteristics' common shape: each resampled at this many points from ground to its supply


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasBias(Meas):
    """Cascode bias generator at one supply and reference current: one row per test mirror output
    voltage."""

    dut: BiasParams
    param: BiasTbParams
    vout_v: np.ndarray
    n_current_a: np.ndarray
    p_current_a: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisBiasMirror(Analysis):
    """The test mirrors the generator biases, at each point.

    ``n_ratio`` and ``p_ratio`` are each mirror's current at mid-supply over the reference,
    ``n_output_resistance_ohm`` and ``p_output_resistance_ohm`` its output resistance there,
    ``n_compliance_v`` the lowest output voltage at which the NMOS mirror's current is within 5 % of
    that (the PMOS mirror's ``p_compliance_v`` the highest), ``n_headroom_v`` and ``p_headroom_v``
    the mirror devices' drain-source voltages; ``vbn_v`` to ``vcasp_v`` the generated gates,
    ``supply_current_a`` the generator's own. ``vout_v`` and ``n_iv_ratio``/``p_iv_ratio`` (one row
    per point, 49 from ground to its supply) hold both characteristics over the reference.
    """

    vdd_v: np.ndarray
    iref_a: np.ndarray
    n_ratio: np.ndarray
    p_ratio: np.ndarray
    n_output_resistance_ohm: np.ndarray
    p_output_resistance_ohm: np.ndarray
    n_compliance_v: np.ndarray
    p_compliance_v: np.ndarray
    n_headroom_v: np.ndarray
    p_headroom_v: np.ndarray
    vbn_v: np.ndarray
    vcasn_v: np.ndarray
    vbp_v: np.ndarray
    vcasp_v: np.ndarray
    supply_current_a: np.ndarray
    vout_v: np.ndarray
    n_iv_ratio: np.ndarray
    p_iv_ratio: np.ndarray


def analyze_bias_mirror(measurements: Sequence[MeasBias]) -> AnalysisBiasMirror:
    """Measure each test mirror's ratio, output resistance, compliance and headroom at each point."""

    identity = measurement_identity(measurements)
    rows = []
    for measurement in measurements:
        tb, readbacks, vout_v = measurement.param, measurement.info.readbacks, measurement.vout_v
        vdd, iref, nominal = float(tb.vdd), float(tb.iref), float(tb.vdd) / 2
        row = [vdd, iref]
        for current in (measurement.n_current_a, measurement.p_current_a):
            row.append(calc.value(current, vout_v, nominal) / iref)
        # deriv's slopes belong to the intervals between samples: read them at the midpoints
        middles = (vout_v[1:] + vout_v[:-1]) / 2
        for current in (measurement.n_current_a, measurement.p_current_a):
            row.append(1 / abs(calc.value(calc.deriv(current, vout_v), middles, nominal)))
        row.append(calc.compliance_range(measurement.n_current_a, vout_v, nominal)[0])
        row.append(calc.compliance_range(measurement.p_current_a, vout_v, nominal)[1])
        row += [float(readbacks["op_tn_v"]), vdd - float(readbacks["op_tp_v"])]
        row += [float(readbacks[f"op_{name}_v"]) for name in ("vbn", "vcasn", "vbp", "vcasp")]
        row.append(float(readbacks["op_supply_current_a"]))
        grid = np.linspace(0.0, vdd, 49)
        characteristics = (
            calc.value(current / iref, vout_v, grid) for current in (measurement.n_current_a, measurement.p_current_a)
        )
        rows.append((*row, grid, *characteristics))
    columns = list(zip(*rows, strict=True))
    scalars = [np.asarray(column, dtype=np.float64) for column in columns[:-3]]
    vdd_v, iref_a, n_ratio, p_ratio, n_res, p_res, n_comp, p_comp, n_head, p_head, vbn, vcasn, vbp, vcasp, current = (
        scalars
    )
    return AnalysisBiasMirror(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        vdd_v=vdd_v,
        iref_a=iref_a,
        n_ratio=n_ratio,
        p_ratio=p_ratio,
        n_output_resistance_ohm=n_res,
        p_output_resistance_ohm=p_res,
        n_compliance_v=n_comp,
        p_compliance_v=p_comp,
        n_headroom_v=n_head,
        p_headroom_v=p_head,
        vbn_v=vbn,
        vcasn_v=vcasn,
        vbp_v=vbp,
        vcasp_v=vcasp,
        supply_current_a=current,
        vout_v=np.asarray(columns[-3], dtype=np.float64),
        n_iv_ratio=np.asarray(columns[-2], dtype=np.float64),
        p_iv_ratio=np.asarray(columns[-1], dtype=np.float64),
    )
