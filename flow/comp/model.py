"""The comparator's behavioral model: the decision a SAR loop sees, from the characterization of
the same ``Params`` in the PDK (``flow.comp.runs``, looked up by ``flow.sweep.lookup``).

    model = comp.model.Model.of("tsmc65", comp.Params(...))
    bits = model.decide(vin_diff_v, rng, vin_cm_v=0.7)

The characterization gives the input-referred noise and the systematic offset over the common
mode (3/8 to 5/8 of the supply; the model interpolates them at the ADC's), the delay from the clock
to the held outputs the converter reads over the input less the offset the same run fitted (its
metastability: the ADC's decision is late where it exceeds the time the SAR sequence allows), and
the supply energy per decision at 0.5 mV, the slowest response, of a decision that leaves the held
outputs and of one that toggles them. A comparator whose nominal S-curve gives no fit has no noise
and no model: more
than 1 % of its decisions unresolved at the characterization's clock (1 ns reset, 4 ns evaluation),
or no monotonic transition within the +-3 mV the S-curve spans.

The decision is the model's own physics, which the behavioral ADC (``flow.adc.sim``) runs:
``Model.Behavioral``, the comparator beyond its ``Params`` (what ``behavioral`` gives at a common
mode: its noise, offset, energy and delay curve), and ``Model.compare``, the decision with that
noise and offset, late where the input is too small to regenerate in time; where no noise is
given, ``Model.strongarm_noise`` estimates a StrongARM's from its sizing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import hdl21 as h
import numpy as np
from hdl21.primitives import MosType
from scipy import constants

from flow.sweep.lookup import characterized, detail

from .params import (
    COX_F_PER_UM2,
    JUNCTION_F_PER_UM,
    L_MIN_UM,
    REGENERATION_SPAN_V,
    SMALL_V,
    W_MIN_UM,
    Bias,
    Latch,
    Params,
)


@dataclass(frozen=True)
class Model:
    """A comparator as its characterization measured it."""

    pdk: str
    params: Params
    noise_v: float  # input-referred RMS noise at the nominal common mode
    offset_v: float  # systematic only: the characterization has no mismatch
    delay_s: float  # clock to the held outputs at an effective 0.5 mV (the delay table's)
    energy_j: float  # supply energy per decision at 0.5 mV, the held outputs unchanged
    # the delay to the held outputs at ascending magnitudes of the effective input, the programmed
    # input less the offset its run fitted (analysis.analyze_metastability)
    delay_table_v: tuple[float, ...]
    delay_table_s: tuple[float, ...]
    cm_table_v: tuple[float, ...]  # common modes of the noise and offset S-curves
    noise_table_v: tuple[float, ...]  # NaN where that S-curve did not resolve
    offset_table_v: tuple[float, ...]
    # supply energy of a 0.5 mV decision that toggles the held outputs; None where not measured
    toggle_energy_j: float | None = None

    @h.paramclass
    class Behavioral:
        """Comparator physics beyond its HDL21 ``Params``; energy is pinned per decision (at the
        characterization's 0.5 mV, its slowest and costliest input: a decision at a large input
        costs less)."""

        noise_v = h.Param(
            dtype=float | None,
            desc="Input-referred RMS noise per decision; None estimates it from the comp.Params sizing",
            default=0.0,
        )
        offset_v = h.Param(dtype=float, desc="Input-referred offset", default=0.0)
        decision_energy_j = h.Param(
            dtype=float, desc="Supply energy per decision that leaves the held outputs as they were", default=0.0
        )
        toggle_energy_j = h.Param(
            dtype=float | None,
            desc="Supply energy per decision that toggles the held outputs; None: decision_energy_j",
            default=None,
        )
        static_power_w = h.Param(
            dtype=float, desc="Static supply power (none for a latch that cuts its current)", default=0.0
        )
        delay_table_v = h.Param(
            dtype=tuple[float, ...] | None,
            desc="Ascending magnitudes of the effective input (less the offset) of a measured clock-to-decision "
            "delay (Model.of's); None never late",
            default=None,
        )
        delay_table_s = h.Param(
            dtype=tuple[float, ...] | None, desc="The clock-to-decision delay at each of delay_table_v", default=None
        )

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        record = characterized("comp", pdk, params, simulate=simulate)
        metrics = record["metrics"]
        noise = metrics.get("noise_v")
        if noise is None or not math.isfinite(noise):
            raise ValueError(f"the comparator in {pdk} has no resolved S-curve, so no noise to model: {params}")
        # not in the reference texts: the model's offset where the record has none (a screen's
        # record, without S-curves), zero; a NaN (an S-curve that located none) passes through.
        # The systematic offset alone: the characterization has no mismatch
        offset_v = metrics.get("offset_v") or 0.0
        toggle_j = metrics.get("energy_toggle_0p5mv_j")
        # the record's delays to the held outputs by the input less the offset (a delay, not NaN,
        # where a decision there toggled them)
        curve = detail(record, "output_delay")
        effective = sorted(
            (float(x), float(delay))
            for x, delay in zip(curve["x"], curve["series"]["delay"], strict=True)
            if delay is not None and math.isfinite(delay) and float(x) > 0
        )
        if len(effective) < 2:
            raise ValueError(f"the comparator in {pdk} has no delay curve to model: {params}")
        table_v, table_s = tuple(x for x, _ in effective), tuple(delay for _, delay in effective)
        curve_at = Model.Behavioral(delay_table_v=table_v, delay_table_s=table_s)
        return cls(
            pdk=pdk,
            params=params,
            noise_v=noise,
            offset_v=offset_v,
            delay_s=float(_delay(curve_at, np.asarray([SMALL_V]))[0]),
            energy_j=metrics["energy_0p5mv_j"],
            delay_table_v=table_v,
            delay_table_s=table_s,
            cm_table_v=tuple(detail(record, "noise_cm")["x"]),
            # an S-curve that did not resolve is null in the record: NaN here
            noise_table_v=tuple(math.nan if v is None else v for v in detail(record, "noise_cm")["series"]["noise"]),
            offset_table_v=tuple(math.nan if v is None else v for v in detail(record, "offset_cm")["series"]["offset"]),
            # a comparator whose 0.5 mV decisions did not toggle the outputs (hysteresis) has none
            toggle_energy_j=toggle_j if toggle_j is not None and math.isfinite(toggle_j) else None,
        )

    @property
    def regeneration_tau_s(self) -> float:
        """The growth of the delay to the held outputs per e-fold fall of the effective input, over
        the table's smallest (``_tau``): the slope the table is extrapolated with. Not the latch's
        own regeneration time constant (the record's ``regeneration_tau_s``, fitted to the latch's
        nodes): the output stage switches partly while the latch still regenerates, so the
        outputs' delay grows less (or, behind a stage that regenerates in turn, more)."""
        return _tau(self.delay_table_v, self.delay_table_s)

    def behavioral(self, *, vin_cm_v: float | None = None) -> Model.Behavioral:
        """The behavioral ADC's comparator parameters at ``vin_cm_v`` (the nominal common mode where
        None): the noise and offset interpolated over the common mode's resolved S-curves, the
        measured delay curve. A dynamic comparator draws no static power."""
        # not in the reference texts: the noise and the offset at a common mode, interpolated
        # linearly between the common modes whose S-curves resolved (held at the ends), the
        # nominal's where fewer than two did; holds inside the characterized span
        # (params.CM_SWEEP of the supply)
        noise_v, offset_v = self.noise_v, self.offset_v
        cm = np.asarray(self.cm_table_v)
        resolved = np.isfinite(self.noise_table_v)
        if vin_cm_v is not None and np.count_nonzero(resolved) >= 2:
            noise_v = float(np.interp(vin_cm_v, cm[resolved], np.asarray(self.noise_table_v)[resolved]))
            offset_v = float(np.interp(vin_cm_v, cm[resolved], np.asarray(self.offset_table_v)[resolved]))
        # not in the reference texts: every decision at the 0.5 mV energy of the record
        # (energy_0p5mv_j, or energy_toggle_0p5mv_j where it toggles the held outputs), whatever
        # its input: an upper estimate, since the small input is the slowest and costliest
        # [Razavi-ADC] Sec. 5.8.4, pp. 96-97: no static power, a device cuts the path in either
        # branch once the comparator has decided
        # holds for every latch here on a switched tail, leakage neglected; not for a design the
        # record shows still drawing late in the evaluation (Metrics.idd_static_a: a signaled
        # latch on a dynamic bias whose drains stop short)
        return Model.Behavioral(
            noise_v=noise_v,
            offset_v=offset_v,
            decision_energy_j=self.energy_j,
            toggle_energy_j=self.toggle_energy_j,
            static_power_w=0.0,
            delay_table_v=self.delay_table_v,
            delay_table_s=self.delay_table_s,
        )

    def decide(self, vin_diff_v: np.ndarray, rng: np.random.Generator, *, vin_cm_v: float) -> np.ndarray:
        """1 where the noisy differential input exceeds the offset (never late: no time limit)."""
        return self.compare(self.params, self.behavioral(vin_cm_v=vin_cm_v), vin_diff_v, rng, vin_cm_v=vin_cm_v)

    @staticmethod
    def strongarm_noise(
        params: Params, vin_cm_v: float, *, vth_v: float = 0.3, gamma: float = 1.0, temperature_k: float = 300.0
    ) -> float:
        """Estimate the StrongARM input-referred RMS noise from its sizing.

        ``sigma^2 = r * (2 k T gamma / C_PQ + r * k T / (2 C_PQ))`` with
        ``r = (V_GS - V_TH) / V_TH``: the input pair's noise integrated until the latch's NMOS
        turn on, and the precharge's kT/C. Only ``diffpair_w``, ``latch_on_w``, ``latch_on_l`` and
        ``rst_w`` enter; the other sizes, the tail, the SR latch, and the Vth flavors are not
        used, so it ranks sizings loosely rather than predicting noise: its terms are upper
        estimates, and the source's integration stops where the latch's own gain begins
        (readme.md: against the characterization).
        """

        if params.latch != Latch.STRONGARM or params.input_pair != MosType.NMOS or params.bias != Bias.SWITCHED:
            raise ValueError(
                "the StrongARM noise estimate needs a single-stage NMOS-input comparator on a switched tail"
            )
        # [Razavi-Analog] Sec. 2.4.2, pp. 29-30: a device's capacitances, each junction's by its
        # width, and the gate-source capacitance of a saturated device, 2/3 W L C_ox
        # C_1 of the noise below, on each of input_p_drain and input_n_drain: the drain of Mdiff,
        # the drain of Mrst and the source of Mcross_on, each its width times
        # params.JUNCTION_F_PER_UM, plus 2/3 W L C_ox of Mcross_on. An upper estimate: the
        # per-width figure lumps junction, gate overlap and wiring, and the 2/3 W L C_ox is a
        # saturated device's, where Mcross_on is off while the noise integrates (its gate, on the
        # latch node, then couples by its overlap alone). No added capacitance: a dynamic bias,
        # with Mcap_p/n on the node, is refused above
        diff_w = params.diffpair_w * W_MIN_UM
        latch_w, latch_l = params.latch_on_w * W_MIN_UM, params.latch_on_l * L_MIN_UM
        c_pq = (
            JUNCTION_F_PER_UM * (diff_w + latch_w + params.rst_w * W_MIN_UM) + 2 / 3 * latch_w * latch_l * COX_F_PER_UM2
        )
        # [Razavi-ADC] Eq. (6.60), p. 116: the StrongArm's input-referred noise with a square-law
        # pair, g_m = I_SS / (V_GS - V_TH)_1,2 put into Eq. (6.59)
        # r = (V_GS - V_TH)_1,2 / V_THN. (V_GS - V_TH)_1,2: Mdiff_p/n's overdrive, taken as
        # vin_cm_v - vth_v, the tail node at the evaluation rail; V_THN: Mcross_on_p/n's threshold,
        # taken as the same vth_v. Both are simplifications: Mtail drops part of the common mode
        # (the source's own design, Sec. 7.2, p. 130, has it in deep triode with a drop under
        # half the pair's V_GS), and Mcross_on's source sits on the drain node, above its bulk.
        # They hold for a wide, short tail and a pair in strong inversion; a long tail leaves the
        # pair near weak inversion, where g_m is no longer I_SS over the overdrive, and r, so the
        # noise, reads high
        ratio = (vin_cm_v - vth_v) / vth_v
        kt = constants.k * temperature_k
        # [Razavi-ADC] Eq. (6.60), p. 116: V_n,in,rms^2 = (2kT / C_1) r (gamma + r / 4), the input
        # pair's noise integrated onto C_1 until the cross-coupled NMOS turn on, and the precharge
        # switches' kT/C
        # C_1: c_pq; M1,2: Mdiff_p/n; the precharge switches: Mrst_p/n; I_SS: Mtail's current;
        # gamma, T: the arguments (gamma 1 and 300 K by default; the benches run at 25 C).
        # Conditions of the source: equal inputs, a constant I_SS, the noise integrated until
        # V_P = V_DD - V_THN; the latch's later gain and its own noise are not in it
        return float(np.sqrt(ratio * (2 * kt * gamma / c_pq + ratio * kt / (2 * c_pq))))

    @staticmethod
    def compare(
        params: Params,
        behavioral: Model.Behavioral,
        vin_diff_v: np.ndarray,
        rng: np.random.Generator,
        *,
        vin_cm_v: float,
        window_s: float | None = None,
        held: np.ndarray | None = None,
    ) -> np.ndarray:
        """Return 1 where the noisy differential input exceeds the offset.

        Unset noise comes from ``strongarm_noise`` of ``params`` at ``vin_cm_v``;
        otherwise ``params`` and ``vin_cm_v`` are not used. With a measured delay curve
        and a ``window_s`` (the time until the held outputs are read), a decision whose
        input is too small to regenerate in time is late: the comparator's SR latch still
        holds its last decision, ``held``. The curve is the delay to the held outputs, so
        a ``window_s`` that is the time until the comparator resets asks more than the
        circuit: its latch may have split by then and the SR latch finishes after the
        reset.
        """

        noise_v = Model.strongarm_noise(params, vin_cm_v) if behavioral.noise_v is None else behavioral.noise_v
        noise = rng.normal(0.0, noise_v, len(vin_diff_v)) if noise_v else 0.0
        # [Razavi-ADC] Eq. (6.61), p. 117: the decision, the sign of the input plus the
        # input-referred noise
        # V_S: vin_diff_v less the offset ([Razavi-ADC] Sec. 5.1, p. 71: the input at which the
        # comparator balances); V_n,in: a Gaussian draw of noise_v a decision. No memory of the
        # decision before: it holds for a latch whose reset leaves nothing of it (the StrongARM);
        # a latch with a dynamic offset decides an input within it by its last decision
        overdrive_v = vin_diff_v + noise - behavioral.offset_v
        decided = (overdrive_v > 0).astype(np.int64)
        if behavioral.delay_table_v is None or window_s is None or held is None:
            return decided
        # [Razavi-ADC] Eq. (7.7), p. 136: an error where the regeneration's delay exceeds the time
        # left
        # [Razavi-ADC] Sec. 5.8.5, p. 98: the RS latch keeps its last state until the comparator
        # decides
        # the delay: to the held outputs at |overdrive_v| (_delay); the time left: window_s, up
        # to the outputs' read
        return np.where(_delay(behavioral, overdrive_v) > window_s, held, decided)


def _tau(table_v: tuple[float, ...], table_s: tuple[float, ...]) -> float:
    """The regeneration time constant of a delay curve over ascending input magnitudes: minus the
    slope of the delay against the log of the input, a least-squares line through those up to
    ``REGENERATION_SPAN_V`` (at least the three smallest)."""
    # [Razavi-ADC] Eq. (7.6), p. 136: an input alpha times smaller delays the regeneration by
    # tau_reg ln(alpha)
    # alpha: the ratio of two entries' effective inputs; the delay: the table's, to the held
    # outputs, so the slope is theirs (Model.regeneration_tau_s), not the latch's own tau_reg.
    # Holds over the entries within REGENERATION_SPAN_V of the offset
    inputs = np.asarray(table_v, dtype=np.float64)
    near = max(3, int(np.count_nonzero(inputs <= REGENERATION_SPAN_V)))
    x = np.log(inputs[:near])
    return -float(np.polyfit(x, np.asarray(table_s[:near], dtype=np.float64), 1)[0])


def _delay(behavioral: Model.Behavioral, overdrive_v: np.ndarray) -> np.ndarray:
    """Return the clock-to-decision delay at each effective input (the input less the offset),
    from the measured curve over its magnitude.

    The delay is interpolated over ln|v|; below the smallest measured input it
    grows by the regeneration time constant of the smallest points (``_tau``),
    ``tau * ln(v_min / |v|)``, the latch's exponential growth; above the largest
    it holds. A zero input never decides.
    """

    # [Razavi-ADC] Eq. (7.7), p. 136: the delay at an input 10^n smaller, n tau_reg ln 10 later
    # here below the table's smallest input, by the table's own slope (_tau); between its entries
    # the delay is interpolated over ln|v|, above the largest held. Holds for the output load and
    # the clock the table was measured with
    table_v = np.asarray(behavioral.delay_table_v, dtype=np.float64)
    table_s = np.asarray(behavioral.delay_table_s, dtype=np.float64)
    tau_s = _tau(tuple(table_v), tuple(table_s))
    magnitude = np.abs(overdrive_v)
    with np.errstate(divide="ignore"):
        log_v = np.log(magnitude)
    inside = np.interp(log_v, np.log(table_v), table_s)
    return np.where(magnitude < table_v[0], table_s[0] + tau_s * (np.log(table_v[0]) - log_v), inside)
