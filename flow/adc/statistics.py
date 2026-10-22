"""Capacitor mismatch as statistics rather than draws: what a Pelgrom coefficient costs a capacitor
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
Rather than assume which, ``MismatchStatistics.of`` walks every decision path of the nominal array
(``calc_paths``: each comparator splits the input interval a path still holds at its threshold)
and takes each code's width as the sum of its paths', linear in every plate's error. A stage's
transition sigma is the largest of the codes whose width starts at its decision.

**Redundancy margin.** Stage k tolerates a wrong decision within q_k (Ogawa et al.,
``calc_redundancy_margins``): a wrong 1 there takes b_k, and the 0s after it give back
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
(``calc_drawn_linearity``; ``test_statistics``): on the extracted 10- to 14-bit arrays the worst
DNL and INL agree within about 5 % to 0.2 %·sqrt(fF) and the INL within about 10 % to 0.85 %. A
redundant array's worst DNL is overstated past about 0.4 %·sqrt(fF): its near-coincident
thresholds (different paths' a fraction of an LSB apart) then reorder, and a code's edge becomes
the nearer of several thresholds, which the one-threshold Gaussian lets move freely.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.special import ndtr

from flow.adc.behavioral import calc_redundancy_margins
from flow.analysis import calc

FEMTO = 1e-15
# thresholds closer than this (LSB) are one
TIE_LSB = 1e-6


@dataclass(frozen=True)
class Paths:
    """Every decision path of one conversion that some input takes, by the input interval it
    holds (LSB), in input order."""

    decisions: np.ndarray  # (paths, decisions) 0 or 1, the first decision first
    lower: np.ndarray  # the input where the path starts (-inf for the lowest)
    upper: np.ndarray
    lower_stage: np.ndarray  # the decision whose threshold is the lower edge (-1: none)
    upper_stage: np.ndarray
    code: np.ndarray  # the output code the design weights decode it to


def calc_paths(a_lsb, b_lsb, weights, code_max: int) -> Paths:
    """Each decision path that some input takes, with the p and n sides' steps ``a_lsb`` and
    ``b_lsb`` (LSB, C0 first) and the decoder's ``weights`` (one a decision): each comparator
    splits the input interval a path still holds at its threshold, and empty halves are dropped."""
    a, b = np.asarray(a_lsb, dtype=np.float64), np.asarray(b_lsb, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    stages = len(a)
    if len(b) != stages or len(weights) != stages + 1:
        raise ValueError("expected one step a side per capacitor and one weight a decision")
    lower, upper = np.array([-np.inf]), np.array([np.inf])
    lower_stage, upper_stage = np.array([-1]), np.array([-1])
    reference = np.zeros(1)
    decisions = np.zeros((1, 0), dtype=np.int8)
    for k in range(stages + 1):
        # decided 0 below the threshold, 1 above it; the threshold is the new edge where it cuts
        # (a threshold within TIE_LSB of an edge already there is that edge: redundant arrays put
        # thresholds of different decisions on one input, and rounding would open slivers there)
        cuts_upper = reference < upper - TIE_LSB
        cuts_lower = reference > lower + TIE_LSB
        below_upper = np.where(cuts_upper, reference, upper)
        below_upper_stage = np.where(cuts_upper, k, upper_stage)
        above_lower = np.where(cuts_lower, reference, lower)
        above_lower_stage = np.where(cuts_lower, k, lower_stage)
        below = cuts_lower
        above = cuts_upper
        lower, upper, lower_stage, upper_stage = (
            np.concatenate((lower[below], above_lower[above])),
            np.concatenate((below_upper[below], upper[above])),
            np.concatenate((lower_stage[below], above_lower_stage[above])),
            np.concatenate((below_upper_stage[below], upper_stage[above])),
        )
        decisions = np.concatenate(
            (
                np.column_stack((decisions[below], np.zeros(np.count_nonzero(below), dtype=np.int8))),
                np.column_stack((decisions[above], np.ones(np.count_nonzero(above), dtype=np.int8))),
            )
        )
        if k < stages:
            reference = np.concatenate((reference[below] - a[k], reference[above] + b[k]))
    order = np.argsort(lower, kind="stable")
    code = np.clip(np.rint(decisions[order] @ weights * code_max / np.sum(weights)), 0, code_max).astype(np.int64)
    return Paths(decisions[order], lower[order], upper[order], lower_stage[order], upper_stage[order], code)


def calc_side_steps(main_f, diff_f, parasitic_f: float, code_max: int, *, diffcaps: bool = True, nominal=None):
    """One side's steps in the nominal array's LSB: each capacitor's share of the side's load,
    (main - diff) / (sum(main) + sum(diff) + parasitic) (main + diff where the difference plate
    moves with the main one), scaled so the nominal steps are c 2^bits / (2 sum(c)). ``nominal``
    (main, diff) sets the LSB; the array itself where not given."""
    main, diff = np.asarray(main_f, dtype=np.float64), np.asarray(diff_f, dtype=np.float64)
    sign = -1.0 if diffcaps else 1.0
    nominal_main, nominal_diff = (main, diff) if nominal is None else map(np.asarray, nominal)
    load = np.sum(nominal_main) + np.sum(nominal_diff) + parasitic_f
    lsb_per_share = (code_max + 1) * load / (2 * np.sum(nominal_main + sign * nominal_diff))
    return (main + sign * diff) / (np.sum(main) + np.sum(diff) + parasitic_f) * lsb_per_share


def calc_drawn_linearity(sides, parasitic_f: float, weights, code_max: int, *, diffcaps: bool = True, nominal=None):
    """The exact DNL and INL (LSB, codes 1 to code_max - 1, as the ramp's code density grades
    them) and the missing codes of one drawn array: ``sides`` the p and n sides' (main, diff)
    capacitances, ``nominal`` the design's (main, diff) for the LSB."""
    (main_p, diff_p), (main_n, diff_n) = sides
    a = calc_side_steps(main_p, diff_p, parasitic_f, code_max, diffcaps=diffcaps, nominal=nominal)
    b = calc_side_steps(main_n, diff_n, parasitic_f, code_max, diffcaps=diffcaps, nominal=nominal)
    paths = calc_paths(a, b, weights, code_max)
    active = (paths.code > 0) & (paths.code < code_max)
    widths = np.bincount(paths.code[active], weights=(paths.upper - paths.lower)[active], minlength=code_max + 1)
    widths = widths[1:code_max]
    dnl = calc.dnl(widths)
    return dnl, calc.inl(dnl), int(np.count_nonzero(widths <= 0))


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

    def log_probability(x: float) -> float:
        below = ndtr((-x - mean) / sigma) if x < -least else 0.0
        return float(np.sum(np.log(np.clip(ndtr((x - mean) / sigma) - below, 1e-300, 1.0))))

    low, high = floor, floor + 10.0 * float(np.max(sigma)) + 10.0 * float(np.max(np.abs(mean)))
    target = math.log(quantile)
    for _ in range(80):
        middle = 0.5 * (low + high)
        low, high = (middle, high) if log_probability(middle) < target else (low, middle)
    return high


@dataclass(frozen=True)
class MismatchStatistics:
    """An array's mismatch statistics at a Pelgrom coefficient of 1 (every sigma scales with A):
    by stage (C0 first) and by code (1 to code_max - 1), and the distinct code widths the worst
    DNL and the missing codes are over. ``of`` derives them; the methods give the predictions at a
    coefficient A (a fraction: 0.001 is 0.1 %·sqrt(fF))."""

    weight_sigma: np.ndarray  # each stage's step on one side (LSB)
    transition_sigma: np.ndarray  # the largest DNL sigma of a code that stage's decision bounds (LSB)
    margin_lsb: np.ndarray  # each stage's redundancy margin (Ogawa et al.), at the design weights
    margin_sigma: np.ndarray  # the margin's own sigma: stage k's step and every later one's (LSB)
    gamma_error: np.ndarray  # each stage's step on both sides less its decoder weight, gain off (LSB)
    gamma_sigma: np.ndarray  # and its sigma
    dnl_mean: np.ndarray  # the nominal array's DNL by code (its own error against the design weights)
    dnl_sigma: np.ndarray
    inl_mean: np.ndarray
    inl_sigma: np.ndarray
    width_mean: np.ndarray  # by distinct width: its nominal width (LSB), sigma and how many codes
    width_sigma: np.ndarray
    width_dnl_sigma: np.ndarray  # the same as DNL: the mean width and the gain taken off
    width_codes: np.ndarray

    @classmethod
    def of(cls, main_f, diff_f, parasitic_f: float, weights, code_max: int, *, diffcaps: bool = True):
        """From one side's nominal main and difference capacitances (C0 first), the top plate's
        other load, the decoder's weights (one a decision) and the output's largest code."""
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

        def edge(stage):
            mask = before[None, :] < stage[:, None]
            return -(1 - decided) * mask, decided * mask

        if np.any((paths.lower_stage[active] < 0) | (paths.upper_stage[active] < 0)):
            raise ValueError("a code between the ends has an unbounded path")
        (a_low, b_low), (a_high, b_high) = edge(paths.lower_stage[active]), edge(paths.upper_stage[active])
        codes = paths.code[active] - 1
        count = code_max - 1
        a_width = np.zeros((count, stages), dtype=np.int64)
        b_width = np.zeros((count, stages), dtype=np.int64)
        np.add.at(a_width, codes, a_high - a_low)
        np.add.at(b_width, codes, b_high - b_low)
        width = (a_width + b_width) @ steps

        # chained to the plates: a side's step error is lsb_per_farad (dc_k - c_k dC / load), the
        # plates (main and difference, p and n) independent with sigma sqrt(C 1 fF) at A = 1
        plate_sigma = np.sqrt(np.concatenate((main, diff)) * FEMTO)

        def plates(rows):
            share = (rows @ switched / load)[:, None]
            return lsb_per_farad * np.hstack((rows - share, sign * rows - share)) * plate_sigma

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

        def by_group(values, reduce=np.maximum):
            out = np.full(groups, -np.inf)
            reduce.at(out, group, values)
            return out

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

        weight_sigma = lsb_per_farad * np.sqrt((main + diff) * FEMTO)
        remaining = np.cumsum(weights[::-1])[::-1]
        # Ogawa's margin is in the decoder's weights, a step's half: in output LSB
        margin_lsb = (calc_redundancy_margins(weights) / 100 * remaining)[:stages] / 2 * code_max / np.sum(weights)
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
        return cls(
            weight_sigma=weight_sigma,
            transition_sigma=transition_sigma,
            margin_lsb=margin_lsb,
            margin_sigma=margin_sigma,
            gamma_error=gamma_error,
            gamma_sigma=np.sqrt(np.sum(gamma_rows**2, axis=1)),
            dnl_mean=dnl_mean,
            dnl_sigma=dnl_sigma,
            inl_mean=inl_mean,
            inl_sigma=inl_sigma,
            width_mean=by_group(width) / mean_width,
            width_sigma=by_group(width_sigma) / mean_width,
            width_dnl_sigma=by_group(dnl_sigma),
            width_codes=sizes,
        )

    def dnl_quantile(self, unit_mismatch: float, quantile: float = 0.95) -> float:
        """The worst |DNL|'s ``quantile`` (LSB): the independent maximum over the distinct widths,
        an upper bound by Sidak's inequality where the nominal array has no error of its own."""
        return _independent_maximum_quantile(
            self.width_mean - 1.0, unit_mismatch * self.width_dnl_sigma, quantile, -1.0
        )

    def inl_quantile(self, unit_mismatch: float, quantile: float = 0.95) -> float:
        """The worst |INL|'s ``quantile`` (LSB): half the sum of the stages' gain-corrected step
        errors' magnitudes, nominal and drawn (folded normals; exact for a binary array, an upper
        bound for the weights' part of any), less what that sum overstates the nominal array's own
        worst INL by (its codes need not take every decision pattern)."""
        weights = _sum_of_folded_normals_quantile(self.gamma_error / 2, unit_mismatch * self.gamma_sigma / 2, quantile)
        return weights + float(np.max(np.abs(self.inl_mean))) - float(np.sum(np.abs(self.gamma_error))) / 2

    def missing_codes(self, unit_mismatch: float) -> np.ndarray:
        """The distribution of the missing-code count: P(count = m) for m = 0, 1, ..., each
        distinct width missing (not positive) with Phi(-w / sigma), the widths independent."""
        sigma = unit_mismatch * self.width_sigma
        with np.errstate(divide="ignore", invalid="ignore"):
            missing = np.where(sigma > 0, ndtr(-self.width_mean / sigma), (self.width_mean <= 0).astype(float))
        distribution = np.ones(1)
        for probability, codes in zip(missing, self.width_codes, strict=True):
            if probability < 1e-12:
                continue
            grown = np.zeros(len(distribution) + codes)
            grown[: len(distribution)] += (1.0 - probability) * distribution
            grown[codes:] += probability * distribution
            distribution = grown
        return distribution

    def missing_codes_quantile(self, unit_mismatch: float, quantile: float = 0.95) -> float:
        """The missing-code count's ``quantile``."""
        return float(np.searchsorted(np.cumsum(self.missing_codes(unit_mismatch)), quantile))

    def missing_codes_expected(self, unit_mismatch: float) -> float:
        """The expected number of missing codes."""
        distribution = self.missing_codes(unit_mismatch)
        return float(np.arange(len(distribution)) @ distribution)

    def margin_over_sigma(self, unit_mismatch: float) -> np.ndarray:
        """Each stage's redundancy margin over its own sigma at ``unit_mismatch``."""
        return self.margin_lsb / (unit_mismatch * self.margin_sigma)
