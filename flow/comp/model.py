"""The comparator's behavioral model: the decision a SAR loop sees, from the characterization of
the same ``Params`` in the PDK (``flow.comp.sweep``, looked up by ``flow.sweep.lookup``).

    model = comp.model.Model.of("tsmc65", comp.Params(...))
    bits = model.decide(vin_diff_v, rng, vin_cm_v=0.7)

The characterization gives the input-referred noise and the systematic offset over the common
mode (3/8 to 5/8 of the supply; the model interpolates them at the ADC's), the clock-to-decision
delay over the input from 0.1 mV to 100 mV (its metastability: the ADC's decision is late where
it exceeds the time the SAR sequence allows), and the supply energy per decision at 0.5 mV, the
slowest response. A comparator whose nominal S-curve gives no fit has no noise and no model: more
than 1 % of its decisions unresolved at the characterization's clock (1 ns reset, 4 ns evaluation),
or no monotonic transition within the +-3 mV the S-curve spans.

The decision is the model's own physics, which the behavioral ADC (``flow.adc.behavioral``) runs:
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

from .params import COX_F_PER_UM2, JUNCTION_F_PER_UM, L_MIN_UM, W_MIN_UM, Latch, Params


@dataclass(frozen=True)
class Model:
    """A comparator as its characterization measured it."""

    pdk: str
    params: Params
    noise_v: float  # input-referred RMS noise at the nominal common mode
    offset_v: float  # systematic only: the characterization has no mismatch
    delay_s: float  # clock to decision at 0.5 mV
    energy_j: float  # supply energy per decision at 0.5 mV
    delay_table_v: tuple[float, ...]  # ascending input magnitudes of the measured delay
    delay_table_s: tuple[float, ...]
    cm_table_v: tuple[float, ...]  # common modes of the noise and offset S-curves
    noise_table_v: tuple[float, ...]  # NaN where that S-curve did not resolve
    offset_table_v: tuple[float, ...]

    @h.paramclass
    class Behavioral:
        """Comparator physics beyond its HDL21 ``Params``; energy is pinned per decision."""

        noise_v = h.Param(
            dtype=float | None,
            desc="Input-referred RMS noise per decision; None estimates it from the comp.Params sizing",
            default=0.0,
        )
        offset_v = h.Param(dtype=float, desc="Input-referred offset", default=0.0)
        decision_energy_j = h.Param(dtype=float, desc="Supply energy per decision", default=0.0)
        static_power_w = h.Param(dtype=float, desc="Static supply power", default=0.0)
        delay_table_v = h.Param(
            dtype=tuple[float, ...] | None,
            desc="Ascending input magnitudes of a measured clock-to-decision delay (Model.of's); None never late",
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
        return cls(
            pdk=pdk,
            params=params,
            noise_v=noise,
            offset_v=metrics.get("offset_v") or 0.0,
            delay_s=metrics["delay_0p5mv_s"],
            energy_j=metrics["energy_0p5mv_j"],
            delay_table_v=tuple(detail(record, "metastability")["x"]),
            delay_table_s=tuple(detail(record, "metastability")["series"]["delay"]),
            cm_table_v=tuple(detail(record, "noise_cm")["x"]),
            # an S-curve that did not resolve is null in the record: NaN here
            noise_table_v=tuple(math.nan if v is None else v for v in detail(record, "noise_cm")["series"]["noise"]),
            offset_table_v=tuple(math.nan if v is None else v for v in detail(record, "offset_cm")["series"]["offset"]),
        )

    @property
    def regeneration_tau_s(self) -> float:
        """The latch's regeneration time constant: the delay's growth per e-fold fall of the input,
        between the two smallest measured inputs."""
        return (self.delay_table_s[0] - self.delay_table_s[1]) / math.log(self.delay_table_v[1] / self.delay_table_v[0])

    def behavioral(self, *, vin_cm_v: float | None = None) -> Model.Behavioral:
        """The behavioral ADC's comparator parameters at ``vin_cm_v`` (the nominal common mode where
        None): the noise and offset interpolated over the common mode's resolved S-curves, the
        measured delay curve. A dynamic comparator draws no static power."""
        noise_v, offset_v = self.noise_v, self.offset_v
        cm = np.asarray(self.cm_table_v)
        resolved = np.isfinite(self.noise_table_v)
        if vin_cm_v is not None and np.count_nonzero(resolved) >= 2:
            noise_v = float(np.interp(vin_cm_v, cm[resolved], np.asarray(self.noise_table_v)[resolved]))
            offset_v = float(np.interp(vin_cm_v, cm[resolved], np.asarray(self.offset_table_v)[resolved]))
        return Model.Behavioral(
            noise_v=noise_v,
            offset_v=offset_v,
            decision_energy_j=self.energy_j,
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
        """Estimate the StrongARM input-referred RMS noise, Razavi (SSC Magazine 2015) eq. (15).

        ``sigma^2 = r * (4 k T gamma / C_PQ + r * k T / (2 C_PQ))`` with
        ``r = (V_GS - V_TH) / V_TH``. ``C_PQ`` is the diffusion of the input-pair
        drain, latch-NMOS source, and reset device at each P/Q node plus the
        latch NMOS gate. Only ``diffpair_w``, ``latch_on_w``, ``latch_on_l`` and
        ``rst_w`` enter; the other sizes, the tail, the SR latch, and the Vth
        flavors are not used. Against the SPICE comparator candidate sweep the
        estimate runs a median 4.4 times high, so it ranks sizings loosely
        rather than predicting noise.
        """

        if params.latch != Latch.STRONGARM or params.input_pair != MosType.NMOS:
            raise ValueError("the StrongARM noise estimate needs a single-stage NMOS-input comparator")
        diff_w = params.diffpair_w * W_MIN_UM
        latch_w, latch_l = params.latch_on_w * W_MIN_UM, params.latch_on_l * L_MIN_UM
        c_pq = (
            JUNCTION_F_PER_UM * (diff_w + latch_w + params.rst_w * W_MIN_UM) + 2 / 3 * latch_w * latch_l * COX_F_PER_UM2
        )
        ratio = (vin_cm_v - vth_v) / vth_v
        kt = constants.k * temperature_k
        return float(np.sqrt(ratio * (4 * kt * gamma / c_pq + ratio * kt / (2 * c_pq))))

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
        and a ``window_s`` (the time until the comparator resets or its output is
        read), a decision whose input is too small to regenerate in time is late:
        the comparator's SR latch still holds its last decision, ``held``.
        """

        noise_v = Model.strongarm_noise(params, vin_cm_v) if behavioral.noise_v is None else behavioral.noise_v
        noise = rng.normal(0.0, noise_v, len(vin_diff_v)) if noise_v else 0.0
        overdrive_v = vin_diff_v + noise - behavioral.offset_v
        decided = (overdrive_v > 0).astype(np.int64)
        if behavioral.delay_table_v is None or window_s is None or held is None:
            return decided
        return np.where(_delay(behavioral, overdrive_v) > window_s, held, decided)


def _delay(behavioral: Model.Behavioral, overdrive_v: np.ndarray) -> np.ndarray:
    """Return the clock-to-decision delay at each input, from the measured curve.

    The delay is interpolated over ln|v|; below the smallest measured input it
    grows by the regeneration time constant of the two smallest points,
    ``tau * ln(v_min / |v|)``, the latch's exponential growth; above the largest
    it holds. A zero input never decides.
    """

    table_v = np.asarray(behavioral.delay_table_v, dtype=np.float64)
    table_s = np.asarray(behavioral.delay_table_s, dtype=np.float64)
    tau_s = (table_s[0] - table_s[1]) / np.log(table_v[1] / table_v[0])
    magnitude = np.abs(overdrive_v)
    with np.errstate(divide="ignore"):
        log_v = np.log(magnitude)
    inside = np.interp(log_v, np.log(table_v), table_s)
    return np.where(magnitude < table_v[0], table_s[0] + tau_s * (np.log(table_v[0]) - log_v), inside)
