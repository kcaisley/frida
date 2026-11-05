"""The sampling switch's behavioral model: the held top-plate voltage, from the characterization of
the same ``Params`` in the PDK (``flow.samp.sweep``, looked up by ``flow.sweep.lookup``).

    model = samp.model.Model.of("tsmc65", samp.Params())
    params = model.behavioral(load_f=1.2e-12)

The characterization's on-resistance over the input level (into 1 pF, the gate at the supply)
sets the tracking lag of each side, ``R(v) C dv/dt``; the held kT/C noise follows from the load
the ADC puts on it, and the aperture jitter is assumed (the clock is not characterized).

The held voltage is the model's own physics, which the behavioral ADC (``flow.adc.behavioral``)
runs: ``Model.Behavioral``, the switch beyond its ``Params`` (what ``behavioral`` gives for a load:
its noise, jitter and on-resistance curve), and ``Model.sample``, each side held through its
input-dependent RC; ``Model.resistance`` is that on-resistance, the measured curve or, without
one, the triode conductances of the switch's sizing (``Model.conductances``).
"""

from __future__ import annotations

from dataclasses import dataclass

import hdl21 as h
import numpy as np
from scipy import constants

from flow.sweep.lookup import characterized, detail

from .params import L_MIN_UM, NMOS_K_A_PER_V2, PMOS_K_A_PER_V2, W_MIN_UM, Params, SwitchType


@dataclass(frozen=True)
class Model:
    """A sampling switch as its characterization measured it."""

    pdk: str
    params: Params
    ron_v: tuple[float, ...]  # input levels of the on-resistance curve
    ron_ohm: tuple[float, ...]
    bandwidth_hz: float  # into 1 pF at mid-supply
    jitter_s: float = 2e-12  # ASSUMED RMS aperture jitter of the on-chip clock (as FRIDA-2's behavioral scans)

    @h.paramclass
    class Behavioral:
        """Top-plate sampler physics beyond its HDL21 ``Params``.

        Its on-resistance follows the triode conductances of the two devices,
        ``n * (V_gate - v - V_tn) + p * (v - V_tp)``, and peaks near mid-supply.
        None conductances come from the ``Params`` sizing; zero for both makes
        the switch ideal.
        """

        noise_v = h.Param(dtype=float, desc="RMS differential noise of each held sample", default=0.0)
        n_conductance_s_per_v = h.Param(
            dtype=float | None, desc="NMOS triode conductance per volt of overdrive; None derives it", default=None
        )
        p_conductance_s_per_v = h.Param(
            dtype=float | None, desc="PMOS triode conductance per volt of overdrive; None derives it", default=None
        )
        n_threshold_v = h.Param(dtype=float, desc="NMOS threshold voltage", default=0.35)
        p_threshold_v = h.Param(dtype=float, desc="PMOS threshold magnitude", default=0.35)
        jitter_s = h.Param(dtype=float, desc="RMS aperture jitter, common to both sides", default=0.0)
        ron_table_v = h.Param(
            dtype=tuple[float, ...] | None,
            desc="Input levels of a measured on-resistance curve (Model.of's); None uses the conductances",
            default=None,
        )
        ron_table_ohm = h.Param(
            dtype=tuple[float, ...] | None, desc="The on-resistance at each of ron_table_v", default=None
        )

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        record = characterized("samp", pdk, params, simulate=simulate)
        curve = detail(record, "ron_vin")
        pairs = [(x, y) for x, y in zip(curve["x"], curve["series"]["on-resistance"], strict=True) if y is not None]
        return cls(
            pdk=pdk,
            params=params,
            ron_v=tuple(x for x, _ in pairs),
            ron_ohm=tuple(y for _, y in pairs),
            bandwidth_hz=record["metrics"]["bandwidth_hz"],
        )

    def behavioral(self, *, load_f: float, temperature_k: float = 300.0) -> Model.Behavioral:
        """The behavioral ADC's sampler parameters for a top-plate load of ``load_f`` per side: the
        differential kT/C noise of the two plates, sqrt(2 k T / C)."""
        return Model.Behavioral(
            noise_v=float(np.sqrt(2 * constants.k * temperature_k / load_f)),
            jitter_s=self.jitter_s,
            ron_table_v=self.ron_v,
            ron_table_ohm=self.ron_ohm,
        )

    def hold(self, vin, slope, *, load_f: dict[str, float], gate_v: float, rng: np.random.Generator):
        """Each side's held voltage (``Model.sample``)."""
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
        """Return the sampler on-resistance at each input voltage; zero for an ideal switch. A measured
        curve (``ron_table_v``, ``ron_table_ohm``) is interpolated, held flat past its ends."""

        if behavioral.ron_table_v is not None:
            return np.interp(vin_v, np.asarray(behavioral.ron_table_v), np.asarray(behavioral.ron_table_ohm))
        n_s, p_s = Model.conductances(params, behavioral)
        if n_s == 0 and p_s == 0:
            return np.zeros_like(vin_v)
        conductance = n_s * np.maximum(gate_v - vin_v - behavioral.n_threshold_v, 0.0)
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
        """Hold each side's input through its input-dependent RC, with half the noise power per side.

        A first-order track lags a moving input by its time constant, so the held
        value is ``v - R(v) * C * dv/dt``; aperture jitter shifts both sides'
        sampling instant by one common random time. The hold window is long
        against the time constant, so the previous sample's residue is not modeled.
        """

        count = len(vin["p"])
        jitter_s = rng.normal(0.0, behavioral.jitter_s, count) if behavioral.jitter_s else 0.0
        held = {}
        for side in ("p", "n"):
            tau_s = Model.resistance(params, behavioral, vin[side], gate_v) * load_f[side]
            noise = rng.normal(0.0, behavioral.noise_v / np.sqrt(2.0), count) if behavioral.noise_v else 0.0
            held[side] = vin[side] + (jitter_s - tau_s) * slope[side] + noise
        return held
