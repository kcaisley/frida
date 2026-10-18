"""Typed FMOM test-structure extractions, the length fit, and its results.

A ``MeasMomcap`` is one extracted test structure: its terminal pairs' capacitances are in its
readbacks (``c_<first>_<second>_f``, terminals in the style's order, then ``shield`` and
``ground``). A unit family's capacitance is affine in its plate length and, per length, in the
inverse of its plates' spacing:

    C = (alpha / s + beta) L + gamma

alpha / s the field across the gap between facing plates (a parallel plate's, the plate's
thickness over the gap), beta the fringe over and under them, gamma the ends'. The extraction's
own spacing dependence (its width bias tables) bends the per-length capacitance away from that
form by up to a tenth, so each extracted spacing's own affine fit is kept too: those are what a
generator interpolates (``tech.MOM_MODEL``). A difference unit's two fingers each face the ring,
so both its pairs (top to main, top to difference) are points of one family.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.analysis.types import Analysis, Meas, measurement_identity
from flow.momcap.layout import MomTestParams, MomUnit
from flow.momcap.subckt import MomStyle


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasMomcap(Meas):
    """One extracted test structure: every terminal pair's capacitance in the readbacks."""

    dut: MomUnit
    param: MomTestParams
    trial_index: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMomcapFit(Analysis):
    """A unit family's plate-to-plate capacitance against its plate length and spacing, and the fit.

    ``length_um``, ``space_nm`` and ``capacitance_f`` are the plate pairs' points (a difference
    unit's two pairs both); ``alpha_f_nm_per_um``, ``beta_f_per_um`` and ``gamma_f`` the model
    C = (alpha / s + beta) L + gamma minimising the squared relative error (short plates weigh as
    much as long ones); ``min_space_nm`` the closest spacing extracted (the PDK's minimum), and
    ``slope_f_per_um`` the model's capacitance per length there; ``fit_error`` each point's model
    over its extraction, minus one; ``shield_f`` the top plate's (a strip unit's: both strips')
    capacitance to the shield per structure, in the measurements' order. ``spacings_nm`` are the
    extracted spacings, ``spacing_slopes_f_per_um`` and ``spacing_intercepts_f`` each one's own
    affine fit in length (the same relative weighting).
    """

    length_um: np.ndarray
    space_nm: np.ndarray
    capacitance_f: np.ndarray
    alpha_f_nm_per_um: float
    beta_f_per_um: float
    gamma_f: float
    min_space_nm: float
    slope_f_per_um: float
    fit_error: np.ndarray
    shield_f: np.ndarray
    spacings_nm: np.ndarray
    spacing_slopes_f_per_um: np.ndarray
    spacing_intercepts_f: np.ndarray


def analyze_momcap_fit(measurements: Sequence[MeasMomcap]) -> AnalysisMomcapFit:
    """Fit one unit family's plate-to-plate capacitance against its plate length and spacing."""

    identity = measurement_identity(measurements)
    style = identity.dut.style
    lengths, spaces, capacitances, shields = [], [], [], []
    for measurement in measurements:
        readbacks = measurement.info.readbacks
        space = float(readbacks["space_nm"])
        if style == MomStyle.STRIP:
            lengths.append(measurement.param.length_nm / 1000)
            spaces.append(space)
            capacitances.append(float(readbacks["c_a_b_f"]))
            shields.append(float(readbacks["c_a_shield_f"]) + float(readbacks["c_b_shield_f"]))
            continue
        inner = "main" if style == MomStyle.DIFFERENCE else "inner"
        lengths.append(measurement.param.length_nm / 1000)
        spaces.append(space)
        capacitances.append(float(readbacks[f"c_top_{inner}_f"]))
        if style == MomStyle.DIFFERENCE:
            lengths.append(measurement.param.diff_length_nm / 1000)
            spaces.append(space)
            capacitances.append(float(readbacks["c_top_diff_f"]))
        shields.append(float(readbacks["c_top_shield_f"]))
    length_um = np.asarray(lengths, dtype=np.float64)
    space_nm = np.asarray(spaces, dtype=np.float64)
    capacitance_f = np.asarray(capacitances, dtype=np.float64)
    # C / C = 1: each point's row of (L / s, L, 1) over its capacitance
    design = np.column_stack((length_um / space_nm, length_um, np.ones_like(length_um))) / capacitance_f[:, None]
    (alpha, beta, gamma), *_ = np.linalg.lstsq(design, np.ones_like(capacitance_f), rcond=None)
    min_space = float(np.min(space_nm))
    spacings = np.unique(space_nm)
    per_spacing = np.array(
        [
            np.polyfit(length_um[space_nm == s], capacitance_f[space_nm == s], 1, w=1 / capacitance_f[space_nm == s])
            for s in spacings
        ]
    )
    return AnalysisMomcapFit(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        length_um=length_um,
        space_nm=space_nm,
        capacitance_f=capacitance_f,
        alpha_f_nm_per_um=float(alpha),
        beta_f_per_um=float(beta),
        gamma_f=float(gamma),
        min_space_nm=min_space,
        slope_f_per_um=float(alpha / min_space + beta),
        fit_error=((alpha / space_nm + beta) * length_um + gamma) / capacitance_f - 1,
        shield_f=np.asarray(shields, dtype=np.float64),
        spacings_nm=spacings,
        spacing_slopes_f_per_um=per_spacing[:, 0],
        spacing_intercepts_f=per_spacing[:, 1],
    )
