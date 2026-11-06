"""Behavioral FRIDA SAR ADC built from four blocks driven by HDL21 parameters.

The sampler and the comparator are their blocks' models (``flow.samp.model.Model.sample`` and
``flow.comp.model.Model.compare``, each with its physics as ``Model.Behavioral``); ``salogic``
and ``cdac`` model the SAR logic and the capacitor array with its drivers. Each takes its own
behavioral parameters and can run alone; ``convert_behavioral`` wires them into the ADC loop of
``TbParams``. Stage and decision counts come from the CDAC configuration, and every time from
the programmed SEQ rows and symbol rate, so resolution and speed are free parameters.

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

import flow.comp.model as comp_model
import flow.samp.model as samp_model
from flow.adc.params import TbParams
from flow.adc.sim import AdcSequence
from flow.cdac.caparray.subckt import CapArrayConfig, CapArrayParams, get_caparray_weights, unit_capacitance_f


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
    # the reference (VDD_DAC) as a driver of output resistance reference_r_ohm onto a decoupling
    # capacitance reference_c_f, with white noise reference_noise_v at the node; the defaults are an
    # ideal reference (the front end's own characterization), the reference study sets them
    reference_r_ohm = h.Param(dtype=float, desc="Reference driver's output resistance; 0 is ideal", default=0.0)
    reference_c_f = h.Param(dtype=float, desc="Reference node's decoupling capacitance; 0 is ideal", default=0.0)
    reference_noise_v = h.Param(
        dtype=float, desc="RMS reference noise at each decision, coupled by the plates held at it", default=0.0
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

    tb = h.Param(dtype=TbParams, desc="ADC stimulus and digital configuration", default=TbParams())
    samp = h.Param(dtype=samp_model.Model.Behavioral, desc="Sampler", default=samp_model.Model.Behavioral())
    comp = h.Param(dtype=comp_model.Model.Behavioral, desc="Comparator", default=comp_model.Model.Behavioral())
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


def calc_sequence_times(tb: TbParams, decisions: int) -> tuple[np.ndarray, np.ndarray]:
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


def calc_decision_windows(tb: TbParams, decisions: int) -> np.ndarray:
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


def salogic(tb: TbParams, state: dict[str, np.ndarray], stage: int, decided: np.ndarray):
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
    params: CdacBehavioralParams, tb: TbParams, side: str, before: np.ndarray, after: np.ndarray
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


def calc_side_capacitances(params: CdacBehavioralParams, tb: TbParams, side: str) -> tuple[np.ndarray, np.ndarray]:
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
    # the reference's noise draws from a stream of its own, so the other sources draw alike with and
    # without it
    reference_rng = rng.spawn(1)[0]
    vin_cm_v = float(tb.vin_cm.dc)
    slope = np.zeros(conversions) if vin_diff_slope_v_per_s is None else np.asarray(vin_diff_slope_v_per_s)
    caps = {side: calc_side_capacitances(params.cdac, tb, side) for side in ("p", "n")}
    load_f = {
        side: float(np.sum(main_f) + np.sum(diff_f)) + params.cdac.parasitic_f
        for side, (main_f, diff_f) in caps.items()
    }
    vref_v, diffcaps = float(tb.vdd_dac.dc), int(tb.dac_diffcaps)
    top = samp_model.Model.sample(
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
    # the reference node's dip below its value, each conversion's, as of dip_s: every switch draws its
    # charge from the decoupling capacitance and the driver restores it with R C; the node has
    # recovered over the sampling phase by the first decision
    reference_tau_s = params.cdac.reference_r_ohm * params.cdac.reference_c_f
    droop = reference_tau_s > 0
    dip = np.zeros(conversions)
    dip_s = 0.0
    for decision in range(stages + 1):
        # Unsettled remainders of earlier updates decay with one time constant.
        seen = top["p"] - top["n"]
        if params.cdac.reference_noise_v or droop:
            # the reference's error (its dip, a noise sample) reaches each top plate through the
            # fraction of its load whose bottom plates sit at the reference
            reference_v = dip * np.exp(-(comp_s[decision] - dip_s) / reference_tau_s) if droop else 0.0
            if params.cdac.reference_noise_v:
                reference_v = reference_v + reference_rng.normal(0.0, params.cdac.reference_noise_v, conversions)
            for side, sign in (("p", 1.0), ("n", -1.0)):
                main_f, diff_f = caps[side]
                at_vref_f = state[side] @ main_f + (state[side] ^ diffcaps) @ diff_f
                seen = seen + sign * reference_v * at_vref_f / load_f[side]
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
        decided = comp_model.Model.compare(
            tb.dut.comp, params.comp, seen, rng, vin_cm_v=vin_cm_v, window_s=float(windows_s[decision]), held=held
        )
        bout[:, decision] = decided
        held = decided
        if decision == stages:
            break
        differential_step = np.zeros(conversions)
        step_charge = np.zeros(conversions)
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
                step_charge += charge
                transitions += toggled
                writes += target != before
                differential_step += top_step if side == "p" else -top_step
        else:
            after = salogic(tb, state, decision, decided)
            for side in ("p", "n"):
                top_step, charge, toggled = cdac(params.cdac, tb, side, state[side], after[side])
                top[side] = top[side] + top_step
                dac_charge += charge
                step_charge += charge
                transitions += toggled
                writes += np.sum(after[side] != state[side], axis=1)
                differential_step += top_step if side == "p" else -top_step
                at_main_f[side] = after[side] @ caps[side][0]
                at_diff_f[side] = (after[side] ^ diffcaps) @ caps[side][1]
            state = after
        switch_s = logic_s[decision] + stage_delay_s[decision]
        steps.append((switch_s, stage_tau_s[decision], differential_step))
        if droop:
            dip = dip * np.exp(-(switch_s - dip_s) / reference_tau_s) - step_charge / params.cdac.reference_c_f
            dip_s = switch_s

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
