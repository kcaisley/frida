"""The ADC's analyses: pure functions of its captures and of earlier results (no file I/O).
``analyze_mismatch`` takes a behavioral capture to its array's capacitor mismatch as statistics
rather than draws (``AnalysisMismatch``), from which ``_dnl_quantile``, ``_inl_quantile``,
``_missing_codes_quantile`` and ``_margin_over_sigma`` predict at a Pelgrom coefficient; the
redundancy of a SAR's weights (``_redundancy_margins``, after Ogawa et al.) grades each stage's
error tolerance.

Capacitor mismatch as statistics rather than draws: what a Pelgrom coefficient costs a capacitor
array's DNL, INL and codes, from its capacitances alone, to first order in the mismatch.

The converter samples on its top plates and switches monotonically. Decision k (k = 0 to n, the
first free) compares the input with the reference R_k; above it the n side's capacitor k rises and
the reference moves up by b_k, below it the p side's does and the reference moves down by a_k::

    R_0 = 0,  R_{k+1} = R_k + d_k b_k - (1 - d_k) a_k

A side's step is its capacitor's share of that side's load, a_k = V c_k / C_p, with c_k = main_k -
diff_k (the difference plate moves the other way; main_k + diff_k where it moves with the main
plate) and C_p every plate of the side and the top plate's other load. The LSB is
2 V sum(c) / C / 2^bits, so in LSB the step is s_k = c_k 2^bits / (2 sum(c)): the load cancels
from the nominal steps and only scales a side's gain.

Pelgrom's mismatch draws every plate independently, sigma_C = A sqrt(C 1 fF)
(``calc_capacitor_mismatch``), so a side's step k varies by

    sigma_k = A sqrt((main_k + diff_k) 1 fF) 2^bits / (2 sum(c))   [LSB]

(both plates add their variance, whichever way they move) and the side's load C_p by the sum of
all of them, a gain common to the side's steps: a capacitor drawn large also loads its side more,
which takes back the share c_k / C_p of its own error from every step of that side. The code-level
statistics below keep that term; it lowers a binary array's MSB transition sigma by about a
fifth where the switched capacitance is a third of the load.

**Transitions and widths.** Every code edge is one comparator's threshold, R_k with the decisions
before it, T = sum_{j<k} (d_j b_j - (1 - d_j) a_j). A code's width (the input that converts to it,
what the ramp's code density measures) is, on each decision path ending on it, its upper threshold
less its lower. Two thresholds on one path at decisions k < m differ by the steps between them,

    w = sum_{k <= j < m} (d_j b_j - (1 - d_j) a_j),   sigma_w^2 = sum_{k <= j < m} sigma_j^2,

each step from the side its decision switched. In a binary array the code just above stage k's
transition ends at the last comparison, so sigma^2 = sigma_k^2 + sum_{j>k} sigma_j^2 over the
capacitors (b_k against the a_j after it; the code just below, a_k against the b_j); in a redundant
one the path after a transition need not run to the last comparison, so the next edge can come at
any later decision and the sum stops there, and a code can hold several paths whose widths add.
Rather than assume which, ``analyze_mismatch`` walks every decision path of the nominal array
(``calc_paths``: each comparator splits the input interval a path still holds at its threshold)
and takes each code's width as the sum of its paths', linear in every plate's error. A stage's
transition sigma is the largest of the codes whose width starts at its decision.

**Redundancy margin.** Stage k tolerates a wrong decision within q_k (Ogawa et al.,
``_redundancy_margins``): a wrong 1 there takes b_k, and the 0s after it give back
sum_{j>k} a_j, so q_k moves with exactly those steps' errors. Its sigma is theirs, and q_k / sigma
says how many sigma of mismatch would close the margin (a negative margin is a gap: missing codes).

**DNL and INL.** The code density's DNL is w_c / mean(w) - 1 over the codes between the clipped
ends, and its INL the endpoint-corrected sum (``calc.dnl``, ``calc.inl``); both are linear in the
widths, so to first order each code's DNL and INL are Gaussian, the nominal array's value (an
extraction's own error against the design weights) plus a sum of the plates' errors, with a
variance from the plates' Pelgrom variances. All of them scale with A.

**The worst DNL.** Codes whose widths sum the same steps from the same sides are one random
variable (every last-stage code of a binary array, say), so the worst |DNL| is a maximum over the
distinct widths, not over the codes. Its percentile is the independent maximum over them,
P(max <= x) = prod_g P(|DNL_g| <= x): by Sidak's inequality the true probability is at least that
for centred Gaussians, so the predicted percentile is an upper bound there. A DNL is never under
-1 (a code narrower than none is missing, not negative), so past 1 LSB only the wide side counts.

**The worst INL.** The per-code sigma says little about the worst code: the INL is a sum of
the stages' errors, and some code takes each with the sign that adds. A threshold is
T_c = sum_j d_j(c) gamma_j + (the steps after its own stage), gamma_j = a_j + b_j the stage's step
on both sides, which every code whose path decided 1 at j carries; the decoder expects W_j there.
The endpoint fit takes off the gain: e_j = gamma_j - W_j - W_j sum(gamma - W) / sum(W). As d_j is
0 or 1, max_c sum_j d_j e_j <= sum_j max(e_j, 0) and the minimum >= sum_j min(e_j, 0), with
equality where the codes take every decision pattern (a binary array); the full-scale code
decides 1 everywhere, so sum_j e_j = 0 and the worst |INL| is half of sum_j |e_j|. Each e_j is the
nominal array's own error (an extraction's) plus a Gaussian draw, so with the e_j taken
independent that is a sum of folded normals, whose percentile is a numerical convolution. A
redundant array's codes do not take every pattern, and its decoder rounds between output codes,
so half the nominal errors' sum differs from its nominal worst INL; the prediction is shifted by
that difference, to the nominal INL at A = 0.

**Missing codes.** A code is missing when its width is not positive, P = Phi(-w / sigma_w); the
codes of one distinct width go together, so the count is a sum of independent Bernoulli groups,
whose distribution is again a convolution.

Everything is first order in the mismatch, and checked against exact draws of the same paths
(``calc_drawn_linearity``; ``test_analysis``): on the extracted 10- to 14-bit arrays the worst
DNL and INL agree within about 5 % to 0.2 %·sqrt(fF) and the INL within about 10 % to 0.85 %. A
redundant array's worst DNL is overstated past about 0.4 %·sqrt(fF): its near-coincident
thresholds (different paths' a fraction of an LSB apart) then reorder, and a code's edge becomes
the nearer of several thresholds, which the one-threshold Gaussian lets move freely.
"""

from __future__ import annotations

import math
from functools import partial

import numpy as np
from scipy.special import ndtr

from flow.analysis import calc
from flow.analysis.calc import calc_paths
from flow.analysis.types import MeasAdc
from flow.pipeline import analysis

from .subckt import calc_side_capacitances
from .types import AnalysisCalibration, AnalysisMismatch


def _decode(bout: np.ndarray, calibration: AnalysisCalibration, *, rounded: bool = True) -> np.ndarray:
    """Stored BOUT decisions decoded with ``calibration``'s weights, clipped to its code range.

    The stored DAQ codes are never replaced; calibrated codes exist only in the analysis that
    requests them. ``rounded`` gives whole codes, what an N-bit output word would carry and what
    the histogram analyses count. ``rounded=False`` keeps the fractional codes the dynamic and
    code-spectrum analyses take: rounding them would quantize the converter's output a second
    time, about 0.5 bit of ENOB.
    """

    decisions = np.asarray(bout)
    if decisions.ndim != 2 or decisions.shape[1] != len(calibration.calibrated_weights):
        raise ValueError("calibrated ADC decoding requires one BOUT column per calibrated weight")
    if np.any((decisions != 0) & (decisions != 1)):
        raise ValueError("calibrated ADC decoding requires binary BOUT values")
    fractional = np.clip(
        decisions.astype(np.float64) @ calibration.calibrated_weights, 0.0, float(calibration.code_max)
    )
    return fractional if not rounded else np.rint(fractional).astype(np.int64)


@analysis
def analyze_mismatch(meas: MeasAdc) -> AnalysisMismatch:
    """The predicted mismatch statistics of a behavioral capture's array: its nominal capacitances
    (a capture without a draw), top-plate load, design weights and code range."""
    cdac = meas.param.cdac
    main_f, diff_f = calc_side_capacitances(cdac, meas.tb, "p")
    statistics = _mismatch_statistics(
        main_f,
        diff_f,
        cdac.parasitic_f,
        meas.nominal_bout_weights,
        meas.code_max,
        diffcaps=bool(meas.tb.dac_diffcaps),
    )
    return AnalysisMismatch(group=meas.group, index=meas.index, dut=meas.dut, **statistics)


def _mismatch_statistics(
    main_f, diff_f, parasitic_f: float, weights, code_max: int, *, diffcaps: bool = True
) -> dict[str, np.ndarray]:
    """One side's mismatch statistics at a Pelgrom coefficient of 1 (``AnalysisMismatch``'s
    fields), from its nominal main and difference capacitances (C0 first), the top plate's other
    load, the decoder's weights (one a decision) and the output's largest code."""
    main, diff = np.asarray(main_f, dtype=np.float64), np.asarray(diff_f, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    stages = len(main)
    sign = -1.0 if diffcaps else 1.0
    switched = main + sign * diff
    load = float(np.sum(main) + np.sum(diff) + parasitic_f)
    lsb_per_farad = (code_max + 1) / (2 * float(np.sum(switched)))
    steps = switched * lsb_per_farad
    paths = calc_paths(steps, steps, weights, code_max)

    # each path's edges as sums of the p (a) and n (b) steps before their decision
    active = (paths.code > 0) & (paths.code < code_max)
    decided = paths.decisions[active, :stages].astype(np.int64)
    before = np.arange(stages)

    if np.any((paths.lower_stage[active] < 0) | (paths.upper_stage[active] < 0)):
        raise ValueError("a code between the ends has an unbounded path")
    a_low, b_low = _edge(decided, before, paths.lower_stage[active])
    a_high, b_high = _edge(decided, before, paths.upper_stage[active])
    codes = paths.code[active] - 1
    count = code_max - 1
    a_width = np.zeros((count, stages), dtype=np.int64)
    b_width = np.zeros((count, stages), dtype=np.int64)
    np.add.at(a_width, codes, a_high - a_low)
    np.add.at(b_width, codes, b_high - b_low)
    width = (a_width + b_width) @ steps

    # chained to the plates: a side's step error is lsb_per_farad (dc_k - c_k dC / load), the
    # plates (main and difference, p and n) independent with sigma sqrt(C 1 fF) at A = 1
    plate_sigma = np.sqrt(np.concatenate((main, diff)) * 1e-15)
    plates = partial(
        _plate_rows, switched=switched, load=load, lsb_per_farad=lsb_per_farad, sign=sign, plate_sigma=plate_sigma
    )
    width_rows = np.hstack((plates(a_width), plates(b_width)))
    mean_width = float(np.mean(width))
    dnl_rows = (width_rows - np.outer(width / mean_width, np.mean(width_rows, axis=0))) / mean_width
    dnl_mean = width / mean_width - 1.0
    inl_rows = np.vstack((np.zeros(dnl_rows.shape[1]), np.cumsum(dnl_rows[:-1], axis=0)))
    inl_rows -= np.outer(np.linspace(0.0, 1.0, count), inl_rows[-1])
    dnl_sigma = np.sqrt(np.sum(dnl_rows**2, axis=1))
    inl_sigma = np.sqrt(np.sum(inl_rows**2, axis=1))

    # the distinct widths: codes summing the same steps from the same sides
    _, group, sizes = np.unique(np.hstack((a_width, b_width)), axis=0, return_inverse=True, return_counts=True)
    group = group.ravel()
    groups = len(sizes)
    width_sigma = np.sqrt(np.sum(width_rows**2, axis=1))

    # each stage's transitions: the codes whose outer edges its decision sets
    first = np.r_[True, codes[1:] != codes[:-1]]
    last = np.r_[codes[1:] != codes[:-1], True]
    lower_edge = np.full(count, -1)
    upper_edge = np.full(count, -1)
    lower_edge[codes[first]] = paths.lower_stage[active][first]
    upper_edge[codes[last]] = paths.upper_stage[active][last]
    # a code's width spans the steps from its earlier edge's decision to its later one's: it is
    # that earlier stage's transition
    span_from = np.minimum(lower_edge, upper_edge)
    transition_sigma = np.array(
        [float(np.max(dnl_sigma[span_from == k])) if np.any(span_from == k) else math.nan for k in range(stages)]
    )

    weight_sigma = lsb_per_farad * np.sqrt((main + diff) * 1e-15)
    remaining = np.cumsum(weights[::-1])[::-1]
    # Ogawa's margin is in the decoder's weights, a step's half: in output LSB
    margin_lsb = (_redundancy_margins(weights) / 100 * remaining)[:stages] / 2 * code_max / np.sum(weights)
    # a wrong 1 at stage k (its n step taken) is undone by 0s after it (p steps): the margin is
    # sum_{j>k} a_j - b_k (and the mirror), its error that of those steps
    later = np.triu(np.ones((stages, stages), dtype=np.int64), 1)
    margin_rows = np.hstack((plates(later), plates(-np.eye(stages, dtype=np.int64))))
    margin_sigma = np.sqrt(np.sum(margin_rows**2, axis=1))

    # each stage's step on both sides, less its share of the endpoint gain: its error against the
    # decoder's weight (the nominal array's own) and its sigma
    identity = np.eye(stages, dtype=np.int64)
    gamma_rows = np.hstack((plates(identity), plates(identity)))
    decoder = weights[:stages] * code_max / np.sum(weights)
    share = decoder / np.sum(decoder)
    gamma_rows = gamma_rows - np.outer(share, np.sum(gamma_rows, axis=0))
    gamma_error = 2 * steps / mean_width - decoder
    gamma_error = gamma_error - share * np.sum(gamma_error)
    inl_mean = calc.inl(dnl_mean)
    return {
        "weight_sigma": weight_sigma,
        "transition_sigma": transition_sigma,
        "margin_lsb": margin_lsb,
        "margin_sigma": margin_sigma,
        "gamma_error": gamma_error,
        "gamma_sigma": np.sqrt(np.sum(gamma_rows**2, axis=1)),
        "dnl_mean": dnl_mean,
        "dnl_sigma": dnl_sigma,
        "inl_mean": inl_mean,
        "inl_sigma": inl_sigma,
        "width_mean": _by_group(width, group, groups) / mean_width,
        "width_sigma": _by_group(width_sigma, group, groups) / mean_width,
        "width_dnl_sigma": _by_group(dnl_sigma, group, groups),
        "width_codes": sizes,
    }


def _edge(decided: np.ndarray, before: np.ndarray, stage: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each path's edge at its decision ``stage`` as the p (a) and n (b) steps before it, a step's
    count each (``decided``: each path's decisions, ``before``: the stages)."""
    mask = before[None, :] < stage[:, None]
    return -(1 - decided) * mask, decided * mask


def _plate_rows(
    rows: np.ndarray, *, switched: np.ndarray, load: float, lsb_per_farad: float, sign: float, plate_sigma: np.ndarray
) -> np.ndarray:
    """Sums of a side's steps (``rows``, a count a step) as their errors in every plate's draw at a
    Pelgrom coefficient of 1 (LSB): a step's own plates, less its share of the side's load (a plate
    drawn large loads its side more)."""
    share = (rows @ switched / load)[:, None]
    return lsb_per_farad * np.hstack((rows - share, sign * rows - share)) * plate_sigma


def _by_group(values: np.ndarray, group: np.ndarray, groups: int) -> np.ndarray:
    """The largest of ``values`` in each of the ``groups`` groups (``group``: each value's)."""
    out = np.full(groups, -np.inf)
    np.maximum.at(out, group, values)
    return out


def _dnl_quantile(mismatch: AnalysisMismatch, unit_mismatch: float, quantile: float = 0.95) -> float:
    """The worst |DNL|'s ``quantile`` (LSB) at ``unit_mismatch``: the independent maximum over the
    distinct widths, an upper bound by Sidak's inequality where the nominal array has no error of its
    own."""
    return _independent_maximum_quantile(
        mismatch.width_mean - 1.0, unit_mismatch * mismatch.width_dnl_sigma, quantile, -1.0
    )


def _inl_quantile(mismatch: AnalysisMismatch, unit_mismatch: float, quantile: float = 0.95) -> float:
    """The worst |INL|'s ``quantile`` (LSB) at ``unit_mismatch``: half the sum of the stages'
    gain-corrected step errors' magnitudes, nominal and drawn (folded normals; exact for a binary
    array, an upper bound for the weights' part of any), less what that sum overstates the nominal
    array's own worst INL by (its codes need not take every decision pattern)."""
    weights = _sum_of_folded_normals_quantile(
        mismatch.gamma_error / 2, unit_mismatch * mismatch.gamma_sigma / 2, quantile
    )
    return weights + float(np.max(np.abs(mismatch.inl_mean))) - float(np.sum(np.abs(mismatch.gamma_error))) / 2


def _missing_codes(mismatch: AnalysisMismatch, unit_mismatch: float) -> np.ndarray:
    """The distribution of the missing-code count: P(count = m) for m = 0, 1, ..., each
    distinct width missing (not positive) with Phi(-w / sigma), the widths independent."""
    sigma = unit_mismatch * mismatch.width_sigma
    with np.errstate(divide="ignore", invalid="ignore"):
        missing = np.where(sigma > 0, ndtr(-mismatch.width_mean / sigma), (mismatch.width_mean <= 0).astype(float))
    distribution = np.ones(1)
    for probability, codes in zip(missing, mismatch.width_codes, strict=True):
        if probability < 1e-12:
            continue
        grown = np.zeros(len(distribution) + codes)
        grown[: len(distribution)] += (1.0 - probability) * distribution
        grown[codes:] += probability * distribution
        distribution = grown
    return distribution


def _missing_codes_quantile(mismatch: AnalysisMismatch, unit_mismatch: float, quantile: float = 0.95) -> float:
    """The missing-code count's ``quantile``."""
    return float(np.searchsorted(np.cumsum(_missing_codes(mismatch, unit_mismatch)), quantile))


def _missing_codes_expected(mismatch: AnalysisMismatch, unit_mismatch: float) -> float:
    """The expected number of missing codes."""
    distribution = _missing_codes(mismatch, unit_mismatch)
    return float(np.arange(len(distribution)) @ distribution)


def _margin_over_sigma(mismatch: AnalysisMismatch, unit_mismatch: float) -> np.ndarray:
    """Each stage's redundancy margin over its own sigma at ``unit_mismatch``."""
    return mismatch.margin_lsb / (unit_mismatch * mismatch.margin_sigma)


def _sum_of_folded_normals_quantile(means, scales, quantile: float, points: int = 1 << 14) -> float:
    """The ``quantile`` of sum_j |x_j| with independent x_j ~ N(means_j, scales_j^2): each folded
    normal as its probability over a common grid, convolved (FFT), each cut 8 scales past its mean."""
    means = np.abs(np.asarray(means, dtype=np.float64))
    scales = np.asarray(scales, dtype=np.float64)
    fixed = float(np.sum(means[scales <= 0]))
    means, scales = means[scales > 0], scales[scales > 0]
    if not len(scales):
        return fixed
    edges = np.linspace(0.0, float(np.sum(means + 8.0 * scales)), points + 1)
    spectrum = np.ones(points // 2 + 1, dtype=np.complex128)
    for mean, scale in zip(means, scales, strict=True):
        # P(|x| < e) = Phi((e - m) / s) - Phi((-e - m) / s), each bin's mass at its left edge
        spectrum *= np.fft.rfft(np.diff(ndtr((edges - mean) / scale) - ndtr((-edges - mean) / scale)), n=points)
    cumulative = np.cumsum(np.clip(np.fft.irfft(spectrum, n=points), 0.0, None))
    index = int(np.searchsorted(cumulative, quantile * cumulative[-1]))
    # half a bin a term above the left edges
    return fixed + float(edges[min(index, points - 1)] + 0.5 * (edges[1] - edges[0]) * len(scales))


def _independent_maximum_quantile(mean: np.ndarray, sigma: np.ndarray, quantile: float, least: float) -> float:
    """The ``quantile`` of max_g |x_g| with independent x_g ~ N(mean_g, sigma_g^2) (zero sigma: the
    mean alone), each x_g held at ``least`` from below (a DNL is never under -1: a code narrower than
    none is missing), by bisection of prod_g P(|x_g| <= x)."""
    mean, sigma = np.asarray(mean, dtype=np.float64), np.asarray(sigma, dtype=np.float64)
    floor = float(np.max(np.abs(mean)))
    random = sigma > 0
    if not np.any(random):
        return floor
    mean, sigma = mean[random], sigma[random]
    low, high = floor, floor + 10.0 * float(np.max(sigma)) + 10.0 * float(np.max(np.abs(mean)))
    target = math.log(quantile)
    for _ in range(80):
        middle = 0.5 * (low + high)
        low, high = (middle, high) if _log_probability(middle, mean, sigma, least) < target else (low, middle)
    return high


def _log_probability(x: float, mean: np.ndarray, sigma: np.ndarray, least: float) -> float:
    """log prod_g P(|x_g| <= x) of independent x_g ~ N(mean_g, sigma_g^2), each held at ``least``
    from below."""
    below = ndtr((-x - mean) / sigma) if x < -least else 0.0
    return float(np.sum(np.log(np.clip(ndtr((x - mean) / sigma) - below, 1e-300, 1.0))))


def _redundancy_margins(weights) -> np.ndarray:
    """Return each SAR stage's error tolerance as a percentage of the residue range left at it.

    T. Ogawa, H. Kobayashi, Y. Takahashi, N. Takai, M. Hotta, H. San, T. Matsuura, A. Abe,
    K. Yagi and T. Mori, "SAR ADC Algorithm with Redundancy and Digital Error Correction," IEICE
    Trans. Fundamentals, vol. E93-A, no. 2, pp. 415-423, Feb. 2010, doi:10.1587/transfun.E93.A.415.

    Their Eq. (5) defines the redundancy of step k as q(k) = -p(k+1) + 1 + sum_{i=k+2}^{M} p(i),
    and Proposition 1 shows that a wrong decision at step k still gives the right output code
    when |Vin - Vref(k)| < q(k). They count from 1: p(1) is the initial mid-scale reference, p(k+1)
    the step that decision k sets, and the +1 the last comparison's LSB. Here everything counts
    from 0: the M weights w_0 (C0, the first decision's) to w_{M-1} (the last decision's), w_k the
    step that decision k sets (+-w_k, as the CDAC switches). Their q(k+1) is then::

        q_k = sum_{j=k+1}^{M-1} w_j - w_k + w_{M-1}

    returned as 100 * q_k / sum_{j=k}^{M-1} w_j. Binary weights give 0 at every stage; a positive
    value is the dynamic error (comparator noise or metastability, incomplete DAC settling,
    reference ripple) that stage tolerates; a negative one an error band the later stages cannot
    recover. The last stage's is 0: nothing after it corrects it. The tolerance is a worst-case
    bound per stage, and every stage may err within its own at once. Static weight errors
    (capacitor mismatch) are not tolerated: they need the decoder's weights calibrated.
    """
    values = np.asarray(weights, dtype=float)
    if values.ndim != 1 or len(values) < 2 or not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("expected at least two finite, positive SAR weights in conversion order")
    remaining = np.cumsum(values[::-1])[::-1]
    # q_k = sum_{j=k+1}^{M-1} w_j - w_k + w_{M-1} (Ogawa et al. Eq. 5, counted from 0). Until
    # 2026-10-21 this was (sum_{j=k+1}^{M-1} w_j - w_k) / sum_{j=k}^{M-1} w_j for k < M-1: without
    # the w_{M-1} term every stage read w_{M-1} low, so binary weights went negative toward the LSB
    return (remaining - 2 * values + values[-1]) / remaining * 100
