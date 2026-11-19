"""The sampling switch's behavioral model: the held top-plate voltage, from the characterization of
the same ``Params`` in the PDK (``flow.samp.runs``, looked up by ``flow.sweep.lookup``).

    model = samp.model.Model.of("tsmc65", samp.Params())
    params = model.behavioral(load_f=1.2e-12)

The characterization's on-resistance over the input level (the closed switch's, its gate drive
settled, into 1 pF) sets the tracking lag of each side, ``R(v) C dv/dt``, and its pedestal over
the input level what
the opening switch leaves on each side; its sines' held samples the sampling instant's shift with
the input (the aperture); the held kT/C noise follows from each side's load, and the aperture
jitter is assumed (the clock is not characterized). An input level the characterization never
settled at is an open switch (infinite resistance); one outside the levels it measured is refused.

The held voltage is the model's own physics, which the behavioral ADC (``flow.adc.sim``)
runs: ``Model.Behavioral``, the switch beyond its ``Params`` (what ``behavioral`` gives for a load:
its noise, jitter, on-resistance and pedestal curves, its aperture), and ``Model.sample``, each side
held through its input-dependent RC from the previous sample's held value over the track window;
``Model.resistance`` is that on-resistance, the measured curve or, without one, the triode
conductances of the switch's sizing (``Model.conductances``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import hdl21 as h
import numpy as np
from scipy import constants

from flow.sweep.lookup import characterized, detail

from .params import L_MIN_UM, NMOS_K_A_PER_V2, PMOS_K_A_PER_V2, W_MIN_UM, Params, SwitchType


def _finite(value: float | None) -> float:
    """``value`` as a float, zero where it is missing or not finite."""
    return float(value) if value is not None and math.isfinite(float(value)) else 0.0


@dataclass(frozen=True)
class Model:
    """A sampling switch as its characterization measured it."""

    pdk: str
    params: Params
    ron_v: tuple[float, ...]  # input levels of the on-resistance curve
    ron_ohm: tuple[float, ...]  # inf where the switch never settled
    bandwidth_hz: float  # into 1 pF at mid-supply
    pedestal_vin_v: tuple[float, ...] = ()  # input levels of the pedestal curve (settled ones)
    pedestal_v: tuple[float, ...] = ()
    aperture_s: float = 0.0  # the sampling instant's shift, aperture_s + aperture_s_per_v * v later
    aperture_s_per_v: float = 0.0
    evidence: str | None = None  # the record's: prelayout or postlayout
    # not in the reference texts: an ASSUMED RMS aperture jitter of the on-chip clock, 2 ps (as
    # FRIDA-2's behavioral scans take it); the clock is not characterized here
    # Terms: Delta T of [Razavi-ADC] Eq. (3.86), p. 55, one draw for both sides (``sample``).
    # Holds for: an assumption until the clock path is characterized.
    jitter_s: float = 2e-12

    @h.paramclass
    class Behavioral:
        """Top-plate sampler physics beyond its HDL21 ``Params``.

        Its on-resistance follows the triode conductances of the two devices,
        ``n * (V_gate - v - V_tn) + p * (v - V_tp)`` (a bootstrapped NMOS ``n * (V_gate -
        V_tn)``, its V_GS the supply at every input), and peaks near mid-supply. None
        conductances come from the ``Params`` sizing; zero for both makes the switch ideal.
        """

        noise_v = h.Param(dtype=float, desc="RMS differential noise of each held sample", default=0.0)
        noise_load_f = h.Param(
            dtype=float | None,
            desc="The load per side noise_v is for: each side's noise scales to its own load; None takes noise_v as is",
            default=None,
        )
        n_conductance_s_per_v = h.Param(
            dtype=float | None, desc="NMOS triode conductance per volt of overdrive; None derives it", default=None
        )
        p_conductance_s_per_v = h.Param(
            dtype=float | None, desc="PMOS triode conductance per volt of overdrive; None derives it", default=None
        )
        # not in the reference texts: rough thresholds (0.35 V) for the triode conductances where
        # no characterization is given (``resistance``)
        # Terms: V_TH of MN (``n_threshold_v``) and |V_TH| of MP (``p_threshold_v``).
        # Holds for: a rough estimate: constant over the input (no body effect).
        n_threshold_v = h.Param(dtype=float, desc="NMOS threshold voltage", default=0.35)
        p_threshold_v = h.Param(dtype=float, desc="PMOS threshold magnitude", default=0.35)
        jitter_s = h.Param(dtype=float, desc="RMS aperture jitter, common to both sides", default=0.0)
        ron_table_v = h.Param(
            dtype=tuple[float, ...] | None,
            desc="Input levels of a measured on-resistance curve (Model.of's); None uses the conductances",
            default=None,
        )
        ron_table_ohm = h.Param(
            dtype=tuple[float, ...] | None, desc="The on-resistance at each of ron_table_v (inf: open)", default=None
        )
        pedestal_table_vin_v = h.Param(
            dtype=tuple[float, ...] | None,
            desc="Input levels of a measured pedestal curve (Model.of's); None leaves no pedestal",
            default=None,
        )
        pedestal_table_v = h.Param(
            dtype=tuple[float, ...] | None, desc="The pedestal at each of pedestal_table_vin_v", default=None
        )
        aperture_s = h.Param(dtype=float, desc="The sampling instant's delay at 0 V input", default=0.0)
        aperture_s_per_v = h.Param(dtype=float, desc="The sampling instant's delay per volt of input", default=0.0)
        track_s = h.Param(
            dtype=float | None,
            desc="The track window, from the previous held value; None: long enough that nothing is left",
            default=None,
        )

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        record = characterized("samp", pdk, params, simulate=simulate)
        curve = detail(record, "ron_vin")
        # not in the reference texts: a level the characterization shows no time constant at (None,
        # or NaN) is an open switch, R = infinity
        # Terms: R the record's ron_vin curve (flow.samp.analysis.analyze_track).
        # Holds for: a level outside the settled input range (an NMOS above V_DD - V_TH).
        ron = [math.inf if y is None or not math.isfinite(y) else float(y) for y in curve["series"]["on-resistance"]]
        pedestal = detail(record, "pedestal_vin")
        found = [
            (float(x), float(y))
            for x, y, r in zip(pedestal["x"], pedestal["series"]["pedestal"], ron, strict=True)
            if y is not None and math.isfinite(y) and math.isfinite(r)
        ]
        values = record["metrics"]
        return cls(
            pdk=pdk,
            params=params,
            ron_v=tuple(float(x) for x in curve["x"]),
            ron_ohm=tuple(ron),
            bandwidth_hz=values["bandwidth_hz"],
            pedestal_vin_v=tuple(x for x, _ in found),
            pedestal_v=tuple(y for _, y in found),
            # no aperture where the sines' samples inside the settled levels were too few to fit one
            aperture_s=_finite(values.get("aperture_s")),
            aperture_s_per_v=_finite(values.get("aperture_s_per_v")),
            evidence=record.get("evidence"),
        )

    def behavioral(self, *, load_f: float, temperature_k: float = 300.0) -> Model.Behavioral:
        """The behavioral ADC's sampler parameters for a top-plate load of ``load_f`` per side: the
        differential kT/C noise of the two plates, sqrt(2 k T / C), each side's scaled to its own
        load in ``sample``."""
        # [Razavi-ADC] Eq. (3.55), p. 39: V_n,out,rms = sqrt(kT / C) on a sampling capacitor; Sec. 3.6,
        # p. 41: two of them differentially, sqrt(2 k T / C)
        # Terms: C ``load_f``, a side's top-plate load (the array's capacitance on vout); T
        #   ``temperature_k``.
        # Ours against the source: none; each side's own load rescales its share in ``sample``.
        # Holds for: a switch whose bandwidth passes its own thermal noise (R_on drops out).
        return Model.Behavioral(
            noise_v=float(np.sqrt(2 * constants.k * temperature_k / load_f)),
            noise_load_f=load_f,
            jitter_s=self.jitter_s,
            ron_table_v=self.ron_v,
            ron_table_ohm=self.ron_ohm,
            pedestal_table_vin_v=self.pedestal_vin_v or None,
            pedestal_table_v=self.pedestal_v or None,
            aperture_s=self.aperture_s,
            aperture_s_per_v=self.aperture_s_per_v,
        )

    def hold(self, vin, slope, *, load_f: dict[str, float], gate_v: float, rng: np.random.Generator):
        """Each side's held voltage (``Model.sample``), its noise that of its own load."""
        # not in the reference texts: the noise is computed for the two sides' mean load and each
        # side's share rescaled to its own in ``sample`` (sqrt(C_mean / C_side))
        # Terms: C_mean the mean of ``load_f``'s two sides (their top-plate loads).
        # Holds for: two sides of nearly equal load (the rescaling is exact for each side alone).
        mean_load = float(np.mean(list(load_f.values())))
        return self.sample(
            self.params, self.behavioral(load_f=mean_load), vin, slope, load_f=load_f, gate_v=gate_v, rng=rng
        )

    @staticmethod
    def conductances(params: Params, behavioral: Model.Behavioral) -> tuple[float, float]:
        """Return the NMOS and PMOS triode conductances per volt of overdrive.

        Unset values are ``k' * W / L`` of the ``Params`` devices; a switch
        type without a device contributes zero. ``mos_vth`` is not used: the
        thresholds are behavioral parameters.
        """

        # [Razavi-ADC] Eq. (3.23), p. 27: R_on = 1 / (mu_n C_ox (W / L)(V_GS - V_TH)): the conductance
        # a volt of overdrive is k' W / L
        # Terms: W / L MN's (MP's), mos_w W_MIN_UM over mos_l L_MIN_UM; k' = mu C_ox the rough
        #   NMOS_K_A_PER_V2 and PMOS_K_A_PER_V2.
        # Ours against the source: no velocity saturation or mobility degradation: a rough value,
        #   used only where no characterization is given.
        # Holds for: deep triode (the output near the input).
        aspect = params.mos_w * W_MIN_UM / (params.mos_l * L_MIN_UM)
        nmos = (SwitchType.NMOS, SwitchType.TGATE, SwitchType.BOOTSTRAP)
        n_s = NMOS_K_A_PER_V2 * aspect if params.switch_type in nmos else 0.0
        p_s = PMOS_K_A_PER_V2 * aspect if params.switch_type in (SwitchType.PMOS, SwitchType.TGATE) else 0.0
        return (
            n_s if behavioral.n_conductance_s_per_v is None else behavioral.n_conductance_s_per_v,
            p_s if behavioral.p_conductance_s_per_v is None else behavioral.p_conductance_s_per_v,
        )

    @staticmethod
    def resistance(params: Params, behavioral: Model.Behavioral, vin_v: np.ndarray, gate_v: float) -> np.ndarray:
        """Return the sampler on-resistance at each input voltage; zero for an ideal switch, inf for
        an open one. A measured curve (``ron_table_v``, ``ron_table_ohm``) is interpolated, in its
        conductance next to an open level (which conducts nothing); an input outside its levels is
        refused. The characterization's levels reach the supply less half the level runs' step
        (``params.VIN_TOP``, 1.195 V of 1.2 V): an ADC whose swing a side passes it (FRIDA's 12-bit
        sawtooth reaches 1.1935 V; one above about 0.95 V differential full scale at 1.05 times it,
        about the 0.7 V common mode) is refused."""

        if behavioral.ron_table_v is not None:
            levels = np.asarray(behavioral.ron_table_v, dtype=np.float64)
            vin_v = np.asarray(vin_v, dtype=np.float64)
            if np.any(vin_v < levels.min()) or np.any(vin_v > levels.max()):
                raise ValueError(
                    f"the sampler's input reaches {float(vin_v.min()):.4g} to {float(vin_v.max()):.4g} V, outside its "
                    f"characterized levels {float(levels.min()):.4g} to {float(levels.max()):.4g} V"
                )
            measured = np.asarray(behavioral.ron_table_ohm, dtype=np.float64)
            # not in the reference texts: between two measured levels the resistance is linear in
            # the input; next to an open level (infinite R) the conductance is, so that it falls to
            # zero there instead of the resistance jumping
            # Terms: the levels and R the record's ron_vin curve (flow.samp.analysis.analyze_track).
            # Holds for: an input inside the characterized levels (refused outside them).
            with np.errstate(divide="ignore", invalid="ignore"):
                direct = np.interp(vin_v, levels, measured)
                toward_open = 1.0 / np.interp(vin_v, levels, 1.0 / measured)
            return np.where(np.isfinite(direct), direct, toward_open)
        n_s, p_s = Model.conductances(params, behavioral)
        if n_s == 0 and p_s == 0:
            return np.zeros_like(vin_v)
        # [Razavi-ADC] Eq. (3.23), p. 27: R_on = 1 / (mu_n C_ox (W / L)(V_DD - V_in - V_TH)); Eq. (3.36),
        # p. 32: the complementary pair's two in parallel
        # Terms: the NMOS's overdrive ``gate_v`` - V_in - ``n_threshold_v``, the PMOS's V_in -
        #   ``p_threshold_v`` (its gate at 0 V); the conductances ``conductances`` gives.
        # Ours against the source: a bootstrapped gate holds V_GS = ``gate_v`` whatever the input
        #   ([Razavi-ADC] Sec. 3.8.1, p. 43), so its overdrive has no V_in; a device below its
        #   threshold conducts nothing; the total conductance floored at 1 pS.
        # Holds for: no measured curve given (the rough constants); constant thresholds.
        source = 0.0 if params.switch_type is SwitchType.BOOTSTRAP else vin_v
        conductance = n_s * np.maximum(gate_v - source - behavioral.n_threshold_v, 0.0)
        conductance += p_s * np.maximum(vin_v - behavioral.p_threshold_v, 0.0)
        return 1.0 / np.maximum(conductance, 1e-12)

    @staticmethod
    def sample(
        params: Params,
        behavioral: Model.Behavioral,
        vin: dict[str, np.ndarray],
        slope: dict[str, np.ndarray],
        *,
        load_f: dict[str, float],
        gate_v: float,
        rng: np.random.Generator,
    ) -> dict[str, np.ndarray]:
        """Hold each side's input through its input-dependent RC, with each side's kT/C.

        A first-order track lags a moving input by its time constant, so the held
        value is ``v - R(v) * C * dv/dt``; the sampling instant moves later by the aperture
        ``a + b v``; aperture jitter shifts both sides' sampling instant by one common random
        time; the opening switch leaves the pedestal at ``v``. With a track window
        (``track_s``) each sample settles from the previous one's held value, the residue
        exp(-T / RC) of their difference left; without one, nothing is left, but a switch
        that is open (infinite resistance) holds the previous sample (the first: its input).
        The residue starts from the previous held value, not from where the converter left the
        top plate (its conversion's end and the INIT reload's step), which this call is not given:
        the error is exp(-T / RC) times the distance between the two.
        """

        count = len(vin["p"])
        jitter_s = rng.normal(0.0, behavioral.jitter_s, count) if behavioral.jitter_s else 0.0
        held = {}
        for side in ("p", "n"):
            v = np.asarray(vin[side], dtype=np.float64)
            tau_s = Model.resistance(params, behavioral, v, gate_v) * load_f[side]
            tracking = np.isfinite(tau_s)
            # [Razavi-ADC] Eq. (3.26), p. 29: a first-order track's phase shift tan^-1(R_on C_1 omega), for
            # R_on C_1 omega << 1 a delay R_on C_1; Eq. (3.86), p. 55: an instant Delta T later holds
            # Delta T dV_in/dt more: held = v + (Delta T - R(v) C) dv/dt
            # Terms: R(v) ``resistance`` at the side's input v (vin), C its load ``load_f[side]``,
            #   dv/dt ``slope[side]``; Delta T the jitter's draw (one for both sides) and the
            #   aperture ``aperture_s`` + ``aperture_s_per_v`` v.
            # Ours against the source: both to first order in the slope; an open switch (infinite
            #   R) has no lag term and holds the previous sample (below).
            # Holds for: R C omega << 1 and an input that is a straight line over the delay.
            delay_s = jitter_s + behavioral.aperture_s + behavioral.aperture_s_per_v * v
            target = v + (delay_s - np.where(tracking, tau_s, 0.0)) * slope[side]
            if behavioral.pedestal_table_vin_v is not None:
                # [Razavi-Analog] Eq. (13.26), p. 550: the pedestal the opening switch leaves on C_H
                # Terms: the characterized pedestal at the side's input level (the record's
                #   pedestal_vin curve), linear between levels, its end values past them.
                # Ours against the source: the measured curve at the bench's 1 pF, not rescaled to
                #   ``load_f``.
                # Holds for: a load near the bench's.
                target = target + np.interp(
                    v, np.asarray(behavioral.pedestal_table_vin_v), np.asarray(behavioral.pedestal_table_v)
                )
            # [Razavi-ADC] Eq. (3.55), p. 39: sqrt(kT / C) on each side's own plate: a side's share of
            # the differential ``noise_v`` is noise_v / sqrt(2), scaled by sqrt(C_ref / C_side)
            # Terms: C_ref ``noise_load_f`` (the load ``noise_v`` was computed for), C_side
            #   ``load_f[side]``.
            # Holds for: independent noise on the two sides.
            scale = 1.0 if behavioral.noise_load_f is None else math.sqrt(behavioral.noise_load_f / load_f[side])
            if behavioral.noise_v:
                target = target + rng.normal(0.0, behavioral.noise_v / np.sqrt(2.0) * scale, count)
            # [Razavi-ADC] Eq. (3.81), p. 54: V_FS (1 - exp(-t_acq / (R_on1 C_1))): a track window T
            # leaves exp(-T / (R C)) of the step from where the output started
            # Terms: T ``track_s``; R C the side's ``tau_s``; the start the previous sample's held
            #   value: held_n = target_n + (held_n-1 - target_n) exp(-T / tau_n).
            # Ours against the source: the settled switch's R from the clock's rise on (its
            #   turn-on, which the acquisition times hold, is left out); the start is the previous
            #   held value, not where the converter left the top plate.
            # Holds for: T long against the turn-on; without a window nothing is left.
            if behavioral.track_s is None:
                left = np.where(tracking, 0.0, 1.0)
            else:
                with np.errstate(divide="ignore", invalid="ignore"):
                    left = np.where(tracking, np.exp(-behavioral.track_s / tau_s), 1.0)
            if not np.any(left > 0):
                held[side] = target
                continue
            out = np.empty(count)
            previous = float(v[0]) if count else 0.0
            for index in range(count):
                previous = target[index] + (previous - target[index]) * left[index]
                out[index] = previous
            held[side] = out
        return held
