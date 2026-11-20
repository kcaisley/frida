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

from .params import L_MIN_UM, LOAD_F, NMOS_K_A_PER_V2, PMOS_K_A_PER_V2, W_MIN_UM, Params, SwitchType


def _finite(value: float | None) -> float:
    """``value`` as a float, zero where it is missing or not finite."""
    # not in the reference texts: a record without an aperture fit (too few sine samples inside
    # its settled levels) gives the model none: a + b V_in with a = b = 0
    # Terms: a, b the record's aperture_s and aperture_s_per_v (flow.samp.analysis.analyze_sine).
    # Holds for: a missing fit; the held value then has the track's lag and the pedestal alone.
    return float(value) if value is not None and math.isfinite(float(value)) else 0.0


def _between(levels: np.ndarray, measured: np.ndarray, vin_v: np.ndarray) -> np.ndarray:
    """The resistance at each of ``vin_v`` from a curve ``measured`` at increasing ``levels``: its
    conductance linear between two levels, the curve's own value at a level."""
    # not in the reference texts: between two measured levels the conductance 1 / R is linear in
    # the input, as a triode device's is ([Razavi-ADC] Eq. (3.24), p. 27: 1 / R_on linear in
    # V_X): 1 / R(v) = (1 - w) / R_0 + w / R_1, written R(v) = R_0 / (1 + w (R_0 / R_1 - 1)) so
    # that equal neighbours give their value exactly; next to an open level (infinite R) the
    # conductance falls to zero there
    # Terms: R_0, R_1 the curve at the levels v_0 <= v <= v_1 on either side of the input, w =
    #   (v - v_0) / (v_1 - v_0); the levels and R the record's ron_vin curve
    #   (flow.samp.analysis.analyze_track).
    # Ours against the source: a measured curve in place of the law; the law's linear conductance
    #   is only the interpolant.
    # Holds for: an input inside the levels (``resistance`` refuses one outside); a twelfth of the
    #   supply between levels (a steep NMOS curve's midpoints are then within a few per cent).
    index = np.clip(np.searchsorted(levels, vin_v, side="right") - 1, 0, len(levels) - 2)
    weight = (vin_v - levels[index]) / (levels[index + 1] - levels[index])
    first, second = measured[index], measured[index + 1]
    # the finite neighbour is the base, so that an open one enters as a ratio of zero
    swap = ~np.isfinite(first)
    base, other, share = (
        np.where(swap, second, first),
        np.where(swap, first, second),
        np.where(swap, 1 - weight, weight),
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        found = base / (1 + share * (base / other - 1))
    return np.where(share == 0, base, np.where(np.isfinite(base), found, np.inf))


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
    # not in the reference texts: an ASSUMED RMS aperture jitter of the on-chip clock, 2 ps; the
    # clock is not characterized here
    # Terms: the rms value of Delta T of [Razavi-ADC] Eq. (3.86), p. 55, one draw a sample for
    #   both sides (``sample``).
    # Ours against the source: none.
    # Holds for: an assumption until the clock path is characterized; it adds Delta T dV_in/dt
    #   to each held sample, common to the two sides and so cancelled in their difference only
    #   where their slopes are alike (a differential input's are opposite).
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
        # Ours against the source: constant over the input, where a switch's threshold rises with
        #   its source above the bulk (body effect), above this over the input range (the readme's
        #   calibrations).
        # Holds for: a rough estimate only (``resistance``).
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
        pedestal_load_f = h.Param(
            dtype=float | None,
            desc="The load pedestal_table_v was measured into: each side's scales to its own; None takes it as is",
            default=None,
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
        # Ours against the source: [Razavi-ADC] Eq. (3.24), p. 27 has R_on rise without bound at
        #   V_DD - V_TH; a real switch still conducts there (weak inversion), with a time constant
        #   past the level runs' read window.
        # Holds for: a level outside the settled input range (an NMOS above V_DD - V_TH). The
        #   switch there moves part of the way in a track window where the model holds the
        #   previous sample: outside the settled range the model's error is up to the whole step.
        ron = [math.inf if y is None or not math.isfinite(y) else float(y) for y in curve["series"]["on-resistance"]]
        # not in the reference texts: the pedestal curve keeps the levels with a finite R_on only
        # Terms: the record's pedestal_vin curve (flow.samp.analysis.analyze_hold), level by level
        #   with its ron_vin curve.
        # Holds for: the settled levels; ``sample`` holds the curve's end values past them.
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
        # Holds for: a switch whose bandwidth passes its own thermal noise (R_on drops out): the
        #   equipartition value, exact for a resistance. A noise run of a kit whose device model
        #   gives a channel in deep triode less than 4kT g_ds reads lower (the readme's
        #   calibrations); this is the upper, physical value.
        return Model.Behavioral(
            noise_v=float(np.sqrt(2 * constants.k * temperature_k / load_f)),
            noise_load_f=load_f,
            jitter_s=self.jitter_s,
            ron_table_v=self.ron_v,
            ron_table_ohm=self.ron_ohm,
            pedestal_table_vin_v=self.pedestal_vin_v or None,
            pedestal_table_v=self.pedestal_v or None,
            pedestal_load_f=LOAD_F,
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
        # Ours against the source: no mobility degradation and no source or drain resistance: a
        #   rough value, above a simulated 65-nm switch's triode conductance a volt (the readme's
        #   calibrations), used only where no characterization is given.
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
        an open one. A measured curve (``ron_table_v``, ``ron_table_ohm``) is interpolated in its
        conductance (an open level conducts nothing); an input outside its levels is refused. The
        characterization's levels run from a twelfth of the supply to the supply less half the
        level runs' step (``params.VIN_SWEEP``, ``params.VIN_TOP``: 0.1 to 1.195 V of 1.2 V): an
        ADC whose swing a side passes them is refused (flow.adc's sawtooth, 1.05 times its 0.94 V
        differential full scale about a 0.7 V common mode, reaches 0.7 + 1.05 x 0.47 = 1.19 V a
        side; a full scale above 0.943 V differential would pass the top level)."""

        if behavioral.ron_table_v is not None:
            levels = np.asarray(behavioral.ron_table_v, dtype=np.float64)
            vin_v = np.asarray(vin_v, dtype=np.float64)
            # not in the reference texts: an input outside the measured levels is refused, not
            # extrapolated: min_i v_i <= v <= max_i v_i
            # Terms: v_i the curve's levels (the record's: a twelfth of the supply to the supply
            #   less half the level runs' step).
            # Holds for: a converter whose swing a side stays inside the levels (the docstring's
            #   arithmetic for flow.adc's).
            if np.any(vin_v < levels.min()) or np.any(vin_v > levels.max()):
                raise ValueError(
                    f"the sampler's input reaches {float(vin_v.min()):.4g} to {float(vin_v.max()):.4g} V, outside its "
                    f"characterized levels {float(levels.min()):.4g} to {float(levels.max()):.4g} V"
                )
            measured = np.asarray(behavioral.ron_table_ohm, dtype=np.float64)
            return _between(levels, measured, vin_v)
        n_s, p_s = Model.conductances(params, behavioral)
        if n_s == 0 and p_s == 0:
            return np.zeros_like(vin_v)
        # [Razavi-ADC] Eq. (3.24), p. 27: R_on = 1 / (mu_n C_ox (W / L)(V_DD - V_X - V_TH)); Eq. (3.36),
        # p. 32: the complementary pair's two in parallel
        # Terms: V_DD ``gate_v`` (the clock's high level), V_X the input: the NMOS's overdrive
        #   ``gate_v`` - V_in - ``n_threshold_v``, the PMOS's V_in - ``p_threshold_v`` (its gate at
        #   0 V); the conductances ``conductances`` gives.
        # Ours against the source: a bootstrapped gate holds its V_GS whatever the input
        #   ([Razavi-ADC] Sec. 3.8.1, p. 43), taken as the source's ideal V_b = ``gate_v``, so its
        #   overdrive has no V_in: ours holds V_b' of Eq. (3.70), p. 50, BOOST_MIN of the supply
        #   or more, which this leaves out (its overdrive up to (1 - BOOST_MIN) V_DD high); a
        #   device below its threshold conducts nothing; the total conductance floored at 1 pS.
        # Holds for: no measured curve given. A rough estimate: with the rough constants and
        #   constant thresholds it reads low against a simulated 65-nm switch's R_on (the
        #   readme's calibrations).
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
                # Ours against the source: the measured curve (the channel's charge and the
                #   clock's feedthrough), a charge on the load it was measured into
                #   (``pedestal_load_f``, the bench's): a side's step is that charge on its own
                #   load, the curve times C_bench / C_side, as the source's 1 / C_H.
                # Holds for: a load large against the switch's own capacitance on vout (which adds
                #   to both loads); no ``pedestal_load_f``: the curve as it is.
                share = 1.0 if behavioral.pedestal_load_f is None else behavioral.pedestal_load_f / load_f[side]
                target = target + share * np.interp(
                    v, np.asarray(behavioral.pedestal_table_vin_v), np.asarray(behavioral.pedestal_table_v)
                )
            # [Razavi-ADC] Eq. (3.55), p. 39: sqrt(kT / C) on each side's own plate: a side's share of
            # the differential ``noise_v`` is noise_v / sqrt(2), scaled by sqrt(C_ref / C_side)
            # Terms: C_ref ``noise_load_f`` (the load ``noise_v`` was computed for), C_side
            #   ``load_f[side]``.
            # Ours against the source: none; the rescaling to a side's own load is ours.
            # Holds for: independent noise on the two sides.
            scale = 1.0 if behavioral.noise_load_f is None else math.sqrt(behavioral.noise_load_f / load_f[side])
            if behavioral.noise_v:
                target = target + rng.normal(0.0, behavioral.noise_v / np.sqrt(2.0) * scale, count)
            # [Razavi-ADC] Eq. (3.81), p. 54: V_FS (1 - exp(-t_acq / (R_on1 C_1))): a track window T
            # leaves exp(-T / (R C)) of the step from where the output started
            # Terms: T ``track_s``; R C the side's ``tau_s``; the start the previous sample's held
            #   value: held_n = target_n + (held_n-1 - target_n) exp(-T / tau_n).
            # Ours against the source: the settled switch's R, at the level it settles to, from
            #   the clock's rise on (its turn-on, which the acquisition times hold, is left out);
            #   the start is the previous held value, not where the converter left the top plate.
            # Holds for: a step small against the switch's overdrive, or a window of many time
            #   constants (the residue is then nothing either way). A full-scale step starts with
            #   the switch saturated and turning on, which leaves more than this law where T / tau
            #   is small (the readme's calibrations; take the residue from the acquisition run
            #   there).
            # not in the reference texts: without a window (``track_s`` None) nothing is left of
            # the previous sample, exp(-T / tau) = 0, and an open switch (infinite R) leaves all of
            # it, 1; the first sample's previous value is its own input, held_-1 = v_0
            # Terms: held_-1 the recursion's start; v_0 the side's first input.
            # Holds for: a first sample not read for its residue (an open first level then holds
            #   the input itself).
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
