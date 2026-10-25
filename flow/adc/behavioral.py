"""Behavioral FRIDA SAR ADC built from four blocks driven by HDL21 parameters.

``samp``, ``comp``, ``salogic`` and ``cdac`` model the sampler, the
comparator, the SAR logic, and the capacitor array with its drivers. Each
takes its own behavioral parameters and can run alone; ``convert_behavioral``
wires them into the ADC loop of ``AdcTbParams``. Stage and decision counts
come from the CDAC configuration, and every time from the programmed SEQ rows
and symbol rate, so resolution and speed are free parameters.

The SAR logic is a stage counter and a branch select: INIT loads the A state,
then each LOGIC edge writes the counted stage, ``1 - B`` on the P side and
``B`` on the N side (``dac_mode=1``), or reloads the B state (``dac_mode=0``).
Diff bottom plates follow ``state XOR dac_diffcaps``. Logic, comparator, and
driver energies are fixed amounts pinned to these actions. The CDAC charge is
computed: every top plate is one floating node loaded by its main and diff
capacitors and a parasitic capacitance, and the plates at VDD_DAC after an
edge draw ``C * (dV_bottom - dV_top)`` from it.
"""

from __future__ import annotations

from dataclasses import dataclass

import hdl21 as h
import numpy as np
from hdl21.primitives import MosType

from flow import comp as comparator
from flow.adc.sequences import AdcSequence
from flow.adc.sim import AdcTbParams
from flow.caparray.subckt import CapArrayConfig, CapArrayParams, get_caparray_weights, unit_capacitance_f
from flow.samp.subckt import SampParams, SwitchType

# Rough 65-nm LVT device constants for the estimates drawn from HDL21 sizing.
W_MIN_UM = 0.12
L_MIN_UM = 0.06
NMOS_K_A_PER_V2 = 300e-6
PMOS_K_A_PER_V2 = 100e-6
JUNCTION_F_PER_UM = 0.8e-15
COX_F_PER_UM2 = 14e-15
BOLTZMANN_J_PER_K = 1.380649e-23


@h.paramclass
class SampBehavioralParams:
    """Top-plate sampler physics beyond its HDL21 ``SampParams``.

    Its on-resistance follows the triode conductances of the two devices,
    ``n * (V_gate - v - V_tn) + p * (v - V_tp)``, and peaks near mid-supply.
    None conductances come from the ``SampParams`` sizing; zero for both makes
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
        desc="Input levels of a measured on-resistance curve (flow.samp.model); None uses the conductances",
        default=None,
    )
    ron_table_ohm = h.Param(
        dtype=tuple[float, ...] | None, desc="The on-resistance at each of ron_table_v", default=None
    )


@h.paramclass
class CompBehavioralParams:
    """Comparator physics beyond its HDL21 ``comp.Params``; energy is pinned per decision."""

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
        desc="Ascending input magnitudes of a measured clock-to-decision delay (flow.comp.model); None never late",
        default=None,
    )
    delay_table_s = h.Param(
        dtype=tuple[float, ...] | None, desc="The clock-to-decision delay at each of delay_table_v", default=None
    )


@h.paramclass
class CdacBehavioralParams:
    """Capacitor array per side and its drivers; None capacitances are ideal."""

    main_p_f = h.Param(dtype=tuple[float, ...] | None, desc="C0-first P main capacitances", default=None)
    diff_p_f = h.Param(dtype=tuple[float, ...] | None, desc="C0-first P diff capacitances", default=None)
    main_n_f = h.Param(dtype=tuple[float, ...] | None, desc="C0-first N main capacitances", default=None)
    diff_n_f = h.Param(dtype=tuple[float, ...] | None, desc="C0-first N diff capacitances", default=None)
    parasitic_f = h.Param(dtype=float, desc="Top-plate capacitance to ground per side", default=0.0)
    settling_tau_s = h.Param(dtype=float, desc="Single-pole top-plate settling time constant; 0 is ideal", default=0.0)
    stage_tau_s = h.Param(
        dtype=tuple[float, ...] | None,
        desc="C0-first settling time constant after each stage switches; None uses settling_tau_s",
        default=None,
    )
    stage_delay_s = h.Param(
        dtype=tuple[float, ...] | None,
        desc="C0-first delay from the LOGIC edge to each stage's plates starting to move; None is 0",
        default=None,
    )
    driver_energy_j = h.Param(dtype=float, desc="Driver energy per bottom-plate transition", default=0.0)
    driver_static_w = h.Param(dtype=float, desc="Static power per bottom-plate driver", default=0.0)
    reference_noise_v = h.Param(
        dtype=float, desc="RMS VDD_DAC noise at each decision, coupled by the plates held at it", default=0.0
    )


@h.paramclass
class SalogicBehavioralParams:
    """SAR stage counter and branch select; energy is pinned per action and register."""

    clock_energy_j = h.Param(dtype=float, desc="Energy per register per LOGIC edge", default=0.0)
    write_energy_j = h.Param(dtype=float, desc="Energy per state-register value change", default=0.0)
    register_static_w = h.Param(dtype=float, desc="Static power per register with its logic", default=0.0)


@h.paramclass
class AdcBehavioralParams:
    """One HDL21 testbench configuration plus the block physics it does not describe."""

    tb = h.Param(dtype=AdcTbParams, desc="ADC stimulus and digital configuration", default=AdcTbParams())
    samp = h.Param(dtype=SampBehavioralParams, desc="Sampler", default=SampBehavioralParams())
    comp = h.Param(dtype=CompBehavioralParams, desc="Comparator", default=CompBehavioralParams())
    cdac = h.Param(dtype=CdacBehavioralParams, desc="Capacitor array and drivers", default=CdacBehavioralParams())
    salogic = h.Param(dtype=SalogicBehavioralParams, desc="SAR logic", default=SalogicBehavioralParams())
    seed = h.Param(dtype=int, desc="Noise random seed", default=0)


@dataclass(frozen=True, slots=True)
class BehavioralConversions:
    """Decisions, per-conversion energy by rail, and static power by rail."""

    bout: np.ndarray
    energy_j: dict[str, np.ndarray]
    static_power_w: dict[str, float]


def calc_redundancy_margins(weights) -> np.ndarray:
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


def calc_ideal_capacitances(cdac: CapArrayConfig) -> tuple[np.ndarray, np.ndarray]:
    """Return the ideal C0-first main and diff capacitances that ``CapArray`` generates at the
    config's unit capacitance (``unit_capacitance_f``).

    Each weight is split into coarse chunks; a chunk adds
    ``unit * (coarse +/- chunk) / 2 + tail`` to the main and diff plates.
    """
    array = CapArrayParams(cdac=cdac)
    unit_f = unit_capacitance_f(cdac)
    tail_f = unit_f / 2 if array.tail_cap is None else float(array.tail_cap)
    main_f, diff_f = [], []
    for weight in get_caparray_weights(cdac):
        chunks = [array.coarse_weight] * (weight // array.coarse_weight)
        if weight % array.coarse_weight:
            chunks.append(weight % array.coarse_weight)
        main_f.append(sum(unit_f * (array.coarse_weight + chunk) / 2 + tail_f for chunk in chunks))
        diff_f.append(sum(unit_f * (array.coarse_weight - chunk) / 2 + tail_f for chunk in chunks))
    return np.asarray(main_f), np.asarray(diff_f)


def calc_capacitor_mismatch(capacitance_f: np.ndarray, *, unit_mismatch: float, rng: np.random.Generator) -> np.ndarray:
    """Draw Pelgrom mismatch: sigma_C = unit_mismatch * sqrt(C * 1 fF) for every capacitor."""

    capacitance_f = np.asarray(capacitance_f, dtype=np.float64)
    return capacitance_f + rng.normal(0.0, unit_mismatch * np.sqrt(capacitance_f * 1e-15))


def calc_sequence_times(tb: AdcTbParams, decisions: int) -> tuple[np.ndarray, np.ndarray]:
    """Return COMP and post-INIT LOGIC rising times relative to the INIT rise."""

    sequence = AdcSequence.from_tb_params(tb).relative_to_init()
    symbol_s = 1.0 / float(tb.symbol_rate)

    def rising(row: str) -> np.ndarray:
        bits = np.asarray([int(bit) for bit in row])
        return np.flatnonzero((bits == 1) & (np.roll(bits, 1) == 0)) * symbol_s

    comp_s = rising(sequence.comp)
    logic_s = rising(sequence.logic)
    logic_s = logic_s[logic_s > symbol_s * sequence.init.count("1")]
    if len(comp_s) != decisions or len(logic_s) < decisions - 1:
        raise ValueError(f"sequence must contain {decisions} COMP and {decisions - 1} LOGIC rises after INIT")
    return comp_s, logic_s[: decisions - 1]


def calc_decision_windows(tb: AdcTbParams, decisions: int) -> np.ndarray:
    """Return, for each COMP rise, the time until the comparator resets (COMP falls) or the SAR
    logic reads it (LOGIC rises), whichever comes first, wrapping into the next conversion."""

    sequence = AdcSequence.from_tb_params(tb).relative_to_init()
    symbol_s = 1.0 / float(tb.symbol_rate)
    comp = np.asarray([int(bit) for bit in sequence.comp])
    logic = np.asarray([int(bit) for bit in sequence.logic])
    rises = np.flatnonzero((comp == 1) & (np.roll(comp, 1) == 0))
    ends = np.flatnonzero(((comp == 0) & (np.roll(comp, 1) == 1)) | ((logic == 1) & (np.roll(logic, 1) == 0)))
    if len(rises) != decisions or not len(ends):
        raise ValueError(f"sequence must contain {decisions} COMP rises and a COMP fall or LOGIC rise")
    # symbols from each rise to every end, the next conversion's ends a whole conversion later
    after = (ends[None, :] - rises[:, None] - 1) % len(comp) + 1
    return np.min(after, axis=1) * symbol_s


def calc_switch_conductances(hw: SampParams, params: SampBehavioralParams) -> tuple[float, float]:
    """Return the NMOS and PMOS triode conductances per volt of overdrive.

    Unset values are ``k' * W / L`` of the ``SampParams`` devices; a switch
    type without a device contributes zero. ``mos_vth`` is not used: the
    thresholds are behavioral parameters.
    """

    aspect = hw.mos_w * W_MIN_UM / (hw.mos_l * L_MIN_UM)
    n_s = NMOS_K_A_PER_V2 * aspect if hw.switch_type in (SwitchType.NMOS, SwitchType.TGATE) else 0.0
    p_s = PMOS_K_A_PER_V2 * aspect if hw.switch_type in (SwitchType.PMOS, SwitchType.TGATE) else 0.0
    return (
        n_s if params.n_conductance_s_per_v is None else params.n_conductance_s_per_v,
        p_s if params.p_conductance_s_per_v is None else params.p_conductance_s_per_v,
    )


def calc_switch_resistance(
    hw: SampParams, params: SampBehavioralParams, vin_v: np.ndarray, gate_v: float
) -> np.ndarray:
    """Return the sampler on-resistance at each input voltage; zero for an ideal switch. A measured
    curve (``ron_table_v``, ``ron_table_ohm``) is interpolated, held flat past its ends."""

    if params.ron_table_v is not None:
        return np.interp(vin_v, np.asarray(params.ron_table_v), np.asarray(params.ron_table_ohm))
    n_s, p_s = calc_switch_conductances(hw, params)
    if n_s == 0 and p_s == 0:
        return np.zeros_like(vin_v)
    conductance = n_s * np.maximum(gate_v - vin_v - params.n_threshold_v, 0.0)
    conductance += p_s * np.maximum(vin_v - params.p_threshold_v, 0.0)
    return 1.0 / np.maximum(conductance, 1e-12)


def calc_strongarm_noise(
    hw: comparator.Params, vin_cm_v: float, *, vth_v: float = 0.3, gamma: float = 1.0, temperature_k: float = 300.0
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

    if hw.comp_stages != comparator.Stages.SINGLE or hw.preamp_diff_xtors != MosType.NMOS:
        raise ValueError("the StrongARM noise estimate needs a single-stage NMOS-input comparator")
    diff_w = hw.diffpair_w * W_MIN_UM
    latch_w, latch_l = hw.latch_on_w * W_MIN_UM, hw.latch_on_l * L_MIN_UM
    c_pq = JUNCTION_F_PER_UM * (diff_w + latch_w + hw.rst_w * W_MIN_UM) + 2 / 3 * latch_w * latch_l * COX_F_PER_UM2
    ratio = (vin_cm_v - vth_v) / vth_v
    kt = BOLTZMANN_J_PER_K * temperature_k
    return float(np.sqrt(ratio * (4 * kt * gamma / c_pq + ratio * kt / (2 * c_pq))))


def samp(
    hw: SampParams,
    params: SampBehavioralParams,
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
    jitter_s = rng.normal(0.0, params.jitter_s, count) if params.jitter_s else 0.0
    held = {}
    for side in ("p", "n"):
        tau_s = calc_switch_resistance(hw, params, vin[side], gate_v) * load_f[side]
        noise = rng.normal(0.0, params.noise_v / np.sqrt(2.0), count) if params.noise_v else 0.0
        held[side] = vin[side] + (jitter_s - tau_s) * slope[side] + noise
    return held


def comp(
    hw: comparator.Params,
    params: CompBehavioralParams,
    vin_diff_v: np.ndarray,
    rng: np.random.Generator,
    *,
    vin_cm_v: float,
    window_s: float | None = None,
    held: np.ndarray | None = None,
) -> np.ndarray:
    """Return 1 where the noisy differential input exceeds the offset.

    Unset noise comes from ``calc_strongarm_noise`` of ``hw`` at ``vin_cm_v``;
    otherwise ``hw`` and ``vin_cm_v`` are not used. With a measured delay curve
    and a ``window_s`` (the time until the comparator resets or its output is
    read), a decision whose input is too small to regenerate in time is late:
    the comparator's SR latch still holds its last decision, ``held``.
    """

    noise_v = calc_strongarm_noise(hw, vin_cm_v) if params.noise_v is None else params.noise_v
    noise = rng.normal(0.0, noise_v, len(vin_diff_v)) if noise_v else 0.0
    overdrive_v = vin_diff_v + noise - params.offset_v
    decided = (overdrive_v > 0).astype(np.int64)
    if params.delay_table_v is None or window_s is None or held is None:
        return decided
    return np.where(calc_comp_delay(params, overdrive_v) > window_s, held, decided)


def calc_comp_delay(params: CompBehavioralParams, overdrive_v: np.ndarray) -> np.ndarray:
    """Return the clock-to-decision delay at each input, from the measured curve.

    The delay is interpolated over ln|v|; below the smallest measured input it
    grows by the regeneration time constant of the two smallest points,
    ``tau * ln(v_min / |v|)``, the latch's exponential growth; above the largest
    it holds. A zero input never decides.
    """

    table_v = np.asarray(params.delay_table_v, dtype=np.float64)
    table_s = np.asarray(params.delay_table_s, dtype=np.float64)
    tau_s = (table_s[0] - table_s[1]) / np.log(table_v[1] / table_v[0])
    magnitude = np.abs(overdrive_v)
    with np.errstate(divide="ignore"):
        log_v = np.log(magnitude)
    inside = np.interp(log_v, np.log(table_v), table_s)
    return np.where(magnitude < table_v[0], table_s[0] + tau_s * (np.log(table_v[0]) - log_v), inside)


def salogic(tb: AdcTbParams, state: dict[str, np.ndarray], stage: int, decided: np.ndarray):
    """Write the counted stage from the decision, or reload the B state; return the new state."""

    after = {}
    for side, target in (("p", 1 - decided), ("n", decided)):
        after[side] = state[side].copy()
        if tb.dac_mode:
            after[side][:, stage] = target
        else:
            after[side][:] = np.asarray(getattr(tb, f"dac_bstate_{side}"), dtype=np.int64)
    return after


def cdac(
    params: CdacBehavioralParams, tb: AdcTbParams, side: str, before: np.ndarray, after: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return one side's floating top-plate step, VDD_DAC charge, and bottom-plate transitions."""

    main_f, diff_f = calc_side_capacitances(params, tb, side)
    vref_v = float(tb.vdd_dac.dc)
    diffcaps = int(tb.dac_diffcaps)
    total_f = np.sum(main_f) + np.sum(diff_f) + params.parasitic_f
    main_step = vref_v * (after - before)
    diff_after = after ^ diffcaps
    diff_step = vref_v * (diff_after - (before ^ diffcaps))
    top_step = (main_step @ main_f + diff_step @ diff_f) / total_f
    charge = (after * (main_step - top_step[:, None])) @ main_f + (
        diff_after * (diff_step - top_step[:, None])
    ) @ diff_f
    transitions = 2 * np.sum(after != before, axis=1)
    return top_step, charge, transitions


def cdac_stage(
    main_f: np.ndarray,
    diff_f: np.ndarray,
    total_f: float,
    vref_v: float,
    diffcaps: int,
    stage: int,
    before: np.ndarray,
    after: np.ndarray,
    at_vref_f: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``cdac`` where one stage alone switches, from ``before`` to ``after`` (its column): the same
    top-plate step, VDD_DAC charge and transitions in one column's work, ``at_vref_f`` the
    capacitance whose bottom plates sit at the reference after the switch (main and difference)."""

    main_step = vref_v * (after - before)
    diff_after = after ^ diffcaps
    diff_step = vref_v * (diff_after - (before ^ diffcaps))
    top_step = (main_step * main_f[stage] + diff_step * diff_f[stage]) / total_f
    # cdac's charge: the switching stage's own term, less the top-plate step across every plate at
    # the reference
    charge = after * main_step * main_f[stage] + diff_after * diff_step * diff_f[stage] - top_step * at_vref_f
    return top_step, charge, 2 * (after != before)


def calc_side_capacitances(params: CdacBehavioralParams, tb: AdcTbParams, side: str) -> tuple[np.ndarray, np.ndarray]:
    """Return one side's main and diff capacitances, ideal where not given."""

    ideal_main_f, ideal_diff_f = calc_ideal_capacitances(tb.dut.cdac)
    main = getattr(params, f"main_{side}_f")
    diff = getattr(params, f"diff_{side}_f")
    return (
        ideal_main_f if main is None else np.asarray(main),
        ideal_diff_f if diff is None else np.asarray(diff),
    )


def convert_behavioral(
    params: AdcBehavioralParams, vin_diff_v: np.ndarray, vin_diff_slope_v_per_s: np.ndarray | None = None
) -> BehavioralConversions:
    """Convert one differential input per conversion, in order, through the four blocks.

    ``vin_diff_slope_v_per_s`` is the input slope at each sampling instant;
    the sampler's tracking lag needs it, and it defaults to a static input.
    """

    tb = params.tb
    vin_diff_v = np.asarray(vin_diff_v, dtype=np.float64)
    conversions = len(vin_diff_v)
    stages = len(get_caparray_weights(tb.dut.cdac))
    comp_s, logic_s = calc_sequence_times(tb, stages + 1)
    windows_s = calc_decision_windows(tb, stages + 1)
    stage_tau_s = params.cdac.stage_tau_s or (params.cdac.settling_tau_s,) * stages
    stage_delay_s = params.cdac.stage_delay_s or (0.0,) * stages
    initial = {side: np.asarray(getattr(tb, f"dac_astate_{side}"), dtype=np.int64) for side in ("p", "n")}
    if any(len(value) != stages for value in initial.values()):
        raise ValueError(f"A states must hold one value per capacitor ({stages})")
    rng = np.random.default_rng(params.seed)
    vin_cm_v = float(tb.vin_cm.dc)
    slope = np.zeros(conversions) if vin_diff_slope_v_per_s is None else np.asarray(vin_diff_slope_v_per_s)
    caps = {side: calc_side_capacitances(params.cdac, tb, side) for side in ("p", "n")}
    load_f = {
        side: float(np.sum(main_f) + np.sum(diff_f)) + params.cdac.parasitic_f
        for side, (main_f, diff_f) in caps.items()
    }
    vref_v, diffcaps = float(tb.vdd_dac.dc), int(tb.dac_diffcaps)
    top = samp(
        tb.dut.samp,
        params.samp,
        {"p": vin_cm_v + vin_diff_v / 2, "n": vin_cm_v - vin_diff_v / 2},
        {"p": slope / 2, "n": -slope / 2},
        load_f=load_f,
        gate_v=float(tb.vdd_d.dc),
        rng=rng,
    )
    sampled = {side: top[side].copy() for side in ("p", "n")}
    state = {side: np.broadcast_to(initial[side], (conversions, stages)).copy() for side in ("p", "n")}
    dac_charge = np.zeros(conversions)
    transitions = np.zeros(conversions)
    writes = np.zeros(conversions)
    steps: list[tuple[float, float, np.ndarray]] = []
    bout = np.empty((conversions, stages + 1), dtype=np.uint8)
    # the comparator's SR latch holds its last decision: the previous conversion's last, a coin
    # toss here, before the first
    held = rng.integers(0, 2, conversions)
    # each side's capacitance whose bottom plates sit at the reference (main and difference plates),
    # kept up to date stage by stage
    at_main_f = {side: state[side] @ caps[side][0] for side in ("p", "n")}
    at_diff_f = {side: (state[side] ^ diffcaps) @ caps[side][1] for side in ("p", "n")}
    for decision in range(stages + 1):
        # Unsettled remainders of earlier updates decay with one time constant.
        seen = top["p"] - top["n"]
        if params.cdac.reference_noise_v:
            # One VDD_DAC noise sample reaches each top plate through the
            # fraction of its load whose bottom plates sit at the reference.
            vref_noise = rng.normal(0.0, params.cdac.reference_noise_v, conversions)
            for side, sign in (("p", 1.0), ("n", -1.0)):
                main_f, diff_f = caps[side]
                at_vref_f = state[side] @ main_f + (state[side] ^ diffcaps) @ diff_f
                seen = seen + sign * vref_noise * at_vref_f / load_f[side]
        # each stage's step starts after its driver's delay and settles with its own time constant;
        # one not yet started is missing whole. A step 36 time constants on (2e-16 of itself, below a
        # double's resolution of it) or without settling is done and leaves the list
        unsettled = []
        for start_s, tau_s, step in steps:
            elapsed_s = comp_s[decision] - start_s
            if elapsed_s < 0:
                seen = seen - step
                unsettled.append((start_s, tau_s, step))
            elif tau_s > 0 and elapsed_s < 36 * tau_s:
                seen = seen - step * np.exp(-elapsed_s / tau_s)
                unsettled.append((start_s, tau_s, step))
        steps = unsettled
        decided = comp(
            tb.dut.comp, params.comp, seen, rng, vin_cm_v=vin_cm_v, window_s=float(windows_s[decision]), held=held
        )
        bout[:, decision] = decided
        held = decided
        if decision == stages:
            break
        differential_step = np.zeros(conversions)
        if tb.dac_mode:
            # the counted stage alone switches: its column, in place
            for side, target in (("p", 1 - decided), ("n", decided)):
                main_f, diff_f = caps[side]
                before = state[side][:, decision].copy()
                state[side][:, decision] = target
                at_main_f[side] += (target - before) * main_f[decision]
                at_diff_f[side] += ((target ^ diffcaps) - (before ^ diffcaps)) * diff_f[decision]
                at_vref_f = at_main_f[side] + at_diff_f[side]
                top_step, charge, toggled = cdac_stage(
                    main_f, diff_f, load_f[side], vref_v, diffcaps, decision, before, target, at_vref_f
                )
                top[side] = top[side] + top_step
                dac_charge += charge
                transitions += toggled
                writes += target != before
                differential_step += top_step if side == "p" else -top_step
        else:
            after = salogic(tb, state, decision, decided)
            for side in ("p", "n"):
                top_step, charge, toggled = cdac(params.cdac, tb, side, state[side], after[side])
                top[side] = top[side] + top_step
                dac_charge += charge
                transitions += toggled
                writes += np.sum(after[side] != state[side], axis=1)
                differential_step += top_step if side == "p" else -top_step
                at_main_f[side] = after[side] @ caps[side][0]
                at_diff_f[side] = (after[side] ^ diffcaps) @ caps[side][1]
            state = after
        steps.append((logic_s[decision] + stage_delay_s[decision], stage_tau_s[decision], differential_step))

    # INIT reloads the A state with floating top plates, then SAMP forces them
    # to the new input; both edges start from the previous conversion's end.
    for side in ("p", "n"):
        previous_state = np.roll(state[side], 1, axis=0)
        init_state = np.broadcast_to(initial[side], (conversions, stages))
        top_step, charge, toggled = cdac(params.cdac, tb, side, previous_state, init_state)
        main_f, diff_f = caps[side]
        at_vref_f = init_state @ main_f + (init_state ^ diffcaps) @ diff_f
        dac_charge += charge - at_vref_f * (sampled[side] - (np.roll(top[side], 1) + top_step))
        transitions += toggled
        writes += np.sum(init_state != previous_state, axis=1)

    # Two registers per stage hold the P and N states and one the one-hot
    # stage counter, whose bits each rise and fall once per conversion. Every
    # LOGIC edge, including the INIT load, clocks all registers.
    registers = 3 * stages
    logic_edges = stages + 1
    writes += 2 * stages
    return BehavioralConversions(
        bout=bout,
        energy_j={
            "vdd_a": np.full(conversions, params.comp.decision_energy_j * (stages + 1)),
            "vdd_d": registers * logic_edges * params.salogic.clock_energy_j + writes * params.salogic.write_energy_j,
            "vdd_dac": float(tb.vdd_dac.dc) * dac_charge + transitions * params.cdac.driver_energy_j,
        },
        static_power_w={
            "vdd_a": params.comp.static_power_w,
            "vdd_d": registers * params.salogic.register_static_w,
            "vdd_dac": 4 * stages * params.cdac.driver_static_w,
        },
    )


def build_continuous_sequence(stages: int) -> AdcSequence:
    """Return the continuous recipe for ``stages`` capacitors: INIT 4, SAMP 20, one 8-symbol word per decision.

    COMP is high for the first four symbols of each word, LOGIC for the last
    four, and one LOGIC pulse inside INIT loads the A state. For 16 stages it
    equals ``symbol160_init4_samp20_comp11110000_logic00001111``.
    """

    symbols = 24 + 8 * (stages + 1)
    init = "1" * 4 + "0" * (symbols - 4)
    samp = "0" * 4 + "1" * 20 + "0" * (symbols - 24)
    comp = "0" * 24 + "11110000" * (stages + 1)
    logic = "0011110000000000000000000000" + "11110000" * stages + "0000"
    return AdcSequence(init=init, samp=samp, comp=comp, logic=logic[:symbols])
