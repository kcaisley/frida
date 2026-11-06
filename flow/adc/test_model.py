"""The ADC's behavioral model: the SAR loop of its blocks (``convert_behavioral``), the model on
stand-in blocks (``Model.behavioral``) and the reference buffer's requirements it sets
(``Model.reference_requirements``)."""

import importlib
import math
from types import SimpleNamespace

import numpy as np
import pytest
from hdl21.prefix import G

import flow.comp.model as comp_model
import flow.samp.model as samp_model
from flow import capdac
from flow.adc.model import (
    AdcBehavioralParams,
    CdacBehavioralParams,
    Model,
    SalogicBehavioralParams,
    _enob_floor,
    convert_behavioral,
)
from flow.adc.params import DECAP_COVERAGE, REFERENCE_QUIET, REFERENCE_SHARE, Params, Reference, TbParams
from flow.adc.plots import plot_reference_noise, plot_reference_r_out
from flow.adc.sim import AdcSequence, symbol160_init4_samp20_comp11110000_logic00001111
from flow.adc.subckt import calc_ideal_capacitances
from flow.cdac.caparray.model import calc_capacitor_mismatch

TB = TbParams(
    dut=Params(adc_bits=12, cdac=capdac.Params()),
    symbol_rate=1.6 * G,
    **symbol160_init4_samp20_comp11110000_logic00001111.as_tb_fields(),
)


def with_tb(**fields) -> AdcBehavioralParams:
    return AdcBehavioralParams(tb=TbParams(**{**TB.__dict__, **fields}))


def test_capacitor_mismatch_follows_pelgrom_area_scaling() -> None:
    draws = calc_capacitor_mismatch(
        np.tile([100e-15, 1e-15], (20000, 1)), unit_mismatch=0.01, rng=np.random.default_rng(0)
    )
    # sigma_C = 1 % * sqrt(C * 1 fF): 0.1 fF for 100 fF and 0.01 fF for 1 fF.
    np.testing.assert_allclose(np.std(draws / 1e-15, axis=0), [0.1, 0.01], rtol=0.03)


def ideal_codes(params: AdcBehavioralParams, points: int = 2001) -> tuple[np.ndarray, np.ndarray]:
    tb = params.tb
    main_f, diff_f = calc_ideal_capacitances(tb.dut.cdac, float(tb.vdd_dac.dc))
    full_scale_v = float(tb.vdd_dac.dc) * np.sum(main_f - diff_f) / np.sum(main_f + diff_f)
    vin_v = np.linspace(-full_scale_v, full_scale_v, points)
    code_weights = np.append(2 * np.asarray(capdac.Model.weights(tb.dut.cdac)), 1)
    code_max = (1 << tb.dut.adc_bits) - 1
    bout = convert_behavioral(params, vin_v).bout
    code = np.rint((bout @ code_weights) * code_max / code_weights.sum())
    ideal_code = np.clip(np.floor((vin_v / full_scale_v + 1) / 2 * (code_max + 1)), 0, code_max)
    return code, ideal_code


@pytest.mark.parametrize("astate", [(0, 1) * 8, (0,) * 16, (1,) * 16, (1, 1, 0, 0) * 4])
def test_ideal_transfer_is_independent_of_the_initial_state(astate) -> None:
    code, ideal_code = ideal_codes(with_tb(dac_astate_p=astate, dac_astate_n=astate))
    assert np.max(np.abs(code - ideal_code)) <= 1


@pytest.mark.parametrize("bits, extra", [(10, 3), (14, 6)])
def test_other_resolutions_convert_and_scale_logic_energy(bits: int, extra: int) -> None:
    cdac = capdac.Params(bits=bits, extra=extra)
    stages = len(capdac.Model.weights(cdac))
    params = AdcBehavioralParams(
        tb=TbParams(
            dut=Params(adc_bits=bits, cdac=cdac),
            symbol_rate=1.6 * G,
            dac_astate_p=(0, 1) * (stages // 2) + (0,) * (stages % 2),
            dac_astate_n=(0, 1) * (stages // 2) + (0,) * (stages % 2),
            dac_bstate_p=(0,) * stages,
            dac_bstate_n=(0,) * stages,
            **AdcSequence.continuous(stages).as_tb_fields(),
        ),
        salogic=SalogicBehavioralParams(clock_energy_j=1e-15),
    )
    code, ideal_code = ideal_codes(params, points=501)
    assert np.max(np.abs(code - ideal_code)) <= 1
    # Every one of the 3 * stages registers is clocked on all stages + 1 LOGIC edges.
    result = convert_behavioral(params, np.zeros(4))
    np.testing.assert_allclose(result.energy_j["vdd_d"], 3 * stages * (stages + 1) * 1e-15)


def test_static_bottom_plates_draw_no_reference_charge() -> None:
    params = with_tb(dac_mode=0, dac_bstate_p=TB.dac_astate_p, dac_bstate_n=TB.dac_astate_n)
    np.testing.assert_allclose(convert_behavioral(params, np.full(8, 0.1)).energy_j["vdd_dac"], 0.0, atol=1e-30)


def test_differential_caps_double_their_weight_without_diffcaps() -> None:
    # With dac_diffcaps=0 the diff plates move with the main plates, so each
    # step is (main + diff) instead of (main - diff): a small input resolves
    # to a code nearer mid-scale.
    vin_v = np.asarray([0.2])
    code_weights = np.append(2 * np.asarray(capdac.Model.weights(TB.dut.cdac)), 1)
    differential = convert_behavioral(with_tb(dac_diffcaps=1), vin_v).bout @ code_weights
    common = convert_behavioral(with_tb(dac_diffcaps=0), vin_v).bout @ code_weights
    assert abs(common[0] - code_weights.sum() / 2) < abs(differential[0] - code_weights.sum() / 2)


def reference_codes(vin_v: float, conversions: int = 400, **reference) -> np.ndarray:
    """The output codes at a DC input with the reference's departure (``CdacBehavioralParams``'s
    ``reference_*``) the only impairment."""
    params = AdcBehavioralParams(
        tb=TB,
        comp=comp_model.Model.Behavioral(noise_v=0.0),
        cdac=CdacBehavioralParams(**reference),
        seed=3,
    )
    code_weights = np.append(2 * np.asarray(capdac.Model.weights(TB.dut.cdac)), 1)
    bout = convert_behavioral(params, np.full(conversions, vin_v)).bout
    return (bout @ code_weights) * ((1 << TB.dut.adc_bits) - 1) / code_weights.sum()


def full_scale_and_lsb() -> tuple[float, float]:
    main_f, diff_f = calc_ideal_capacitances(TB.dut.cdac, float(TB.vdd_dac.dc))
    full_scale_v = float(TB.vdd_dac.dc) * np.sum(main_f - diff_f) / np.sum(main_f + diff_f)
    return full_scale_v, 2 * full_scale_v / (1 << TB.dut.adc_bits)


def test_reference_noise_cancels_at_mid_scale_and_grows_toward_the_ends() -> None:
    full_scale_v, lsb_v = full_scale_and_lsb()
    # off the first threshold by a third of an LSB: noiseless, every conversion gives one code
    middle, near_top, near_bottom = 0.33 * lsb_v, 0.9 * full_scale_v, -0.9 * full_scale_v
    assert np.std(reference_codes(near_top)) == 0.0
    # 2 mV at the reference: the sides' plates at it differ by about vin / VDD_DAC near the ends
    sigma = {
        vin: float(np.std(reference_codes(vin, reference_noise_v=2e-3))) for vin in (middle, near_top, near_bottom)
    }
    assert sigma[middle] < 0.3
    assert sigma[near_top] > 1.0 and sigma[near_bottom] > 1.0


def test_the_reference_kickback_needs_both_a_slow_driver_and_a_small_decap() -> None:
    full_scale_v, _ = full_scale_and_lsb()
    vin_v = 0.6 * full_scale_v
    ideal = reference_codes(vin_v, 50)
    # 10 pF of decoupling behind 1 kohm: the dip (a switch's charge over 10 pF) has not recovered
    # by the next comparison, so the code moves; a strong driver (1 ohm) restores it in time
    slow = reference_codes(vin_v, 50, reference_r_ohm=1e3, reference_c_f=10e-12)
    fast = reference_codes(vin_v, 50, reference_r_ohm=1.0, reference_c_f=10e-12)
    assert abs(float(np.mean(slow)) - float(np.mean(ideal))) >= 1.0
    assert np.array_equal(fast, ideal)
    # either part alone is an ideal reference
    assert np.array_equal(reference_codes(vin_v, 50, reference_r_ohm=1e3), ideal)
    assert np.array_equal(reference_codes(vin_v, 50, reference_c_f=10e-12), ideal)


def test_a_drawn_arrays_exact_transfer_is_the_noise_free_converters() -> None:
    """The decision paths of a drawn array (``calc_paths``, with each stage's A state) give the
    decisions the behavioral converter makes, ideal sampler and comparator, at every input: a stage
    held at 1 moves the other side's capacitor."""
    from flow.analysis.calc import calc_decision_steps, calc_paths

    stages = len(capdac.Model.weights(TB.dut.cdac))
    astate = (0, 1) * (stages // 2) + (0,) * (stages % 2)
    tb = TbParams(**{**TB.__dict__, "dac_astate_p": astate, "dac_astate_n": astate})
    rng = np.random.default_rng(5)
    main_f, diff_f = calc_ideal_capacitances(tb.dut.cdac, float(tb.vdd_dac.dc))
    drawn = {
        side: (
            calc_capacitor_mismatch(main_f, unit_mismatch=0.01, rng=rng),
            calc_capacitor_mismatch(diff_f, unit_mismatch=0.01, rng=rng),
        )
        for side in ("p", "n")
    }
    cdac = CdacBehavioralParams(
        **{
            f"{kind}_{side}_f": tuple(drawn[side][index])
            for side in drawn
            for index, kind in enumerate(("main", "diff"))
        }
    )
    params = AdcBehavioralParams(tb=tb, comp=comp_model.Model.Behavioral(noise_v=0.0), cdac=cdac)
    code_max = (1 << tb.dut.adc_bits) - 1
    full_scale_v, lsb_v = full_scale_and_lsb()
    # an even count: no input on the first threshold, 0 V, a tie the comparator (overdrive > 0) and
    # the paths (an input on a threshold above it) break apart
    vin_v = np.linspace(-full_scale_v, full_scale_v, 20_010)
    bout = convert_behavioral(params, vin_v).bout
    weights = np.append(2 * np.asarray(capdac.Model.weights(tb.dut.cdac), dtype=np.float64), 1.0)
    a, b = calc_decision_steps(
        (drawn["p"], drawn["n"]), 0.0, code_max, diffcaps=bool(tb.dac_diffcaps), nominal=(main_f, diff_f), astate=astate
    )
    paths = calc_paths(a, b, weights, code_max)
    exact = paths.decisions[np.searchsorted(paths.lower, vin_v / lsb_v, side="right") - 1]
    assert np.array_equal(exact, bout)


def test_the_reference_noise_leaves_the_other_sources_draws_alike() -> None:
    """The reference's noise draws from a stream of its own: a negligible one changes no decision
    the comparator's noise makes."""
    _, lsb_v = full_scale_and_lsb()

    def bout(**reference) -> np.ndarray:
        params = AdcBehavioralParams(
            tb=TB, comp=comp_model.Model.Behavioral(noise_v=lsb_v), cdac=CdacBehavioralParams(**reference), seed=3
        )
        return convert_behavioral(params, np.full(200, 0.33 * lsb_v)).bout

    assert np.array_equal(bout(reference_noise_v=1e-12), bout())


def test_the_model_quiets_each_source_alone_and_scales_the_settling() -> None:
    main_f, diff_f = calc_ideal_capacitances(TB.dut.cdac, float(TB.vdd_dac.dc))
    model = Model(
        pdk="none",
        params=TB.dut,
        comp=SimpleNamespace(
            behavioral=lambda vin_cm_v: comp_model.Model.Behavioral(
                noise_v=1e-4, delay_table_v=(1e-6, 1e-3), delay_table_s=(200e-12, 50e-12)
            )
        ),
        samp=SimpleNamespace(
            behavioral=lambda load_f: samp_model.Model.Behavioral(
                noise_v=1e-4, jitter_s=2e-12, ron_table_v=(0.2, 1.0), ron_table_ohm=(100.0, 300.0)
            )
        ),
        cdac=SimpleNamespace(
            draw=lambda unit_mismatch, rng: (main_f, diff_f),
            parasitic_f=0.0,
            main_f=main_f,
            diff_f=diff_f,
            load_f=float(np.sum(main_f) + np.sum(diff_f)),
        ),
        drivers=tuple(SimpleNamespace(resistance_ohm=1.0, intrinsic_delay_s=20e-12, energy_j=0.0) for _ in main_f),
    )
    # the CDAC's SPICE draw where a capture asks for it, the nominal plates where none is characterized
    from dataclasses import replace

    heavy = (main_f * 1.01, diff_f)
    drawn = replace(model, drawn=(heavy, (main_f, diff_f))).behavioral(TB, drawn=True).cdac
    assert drawn.main_p_f == tuple(heavy[0]) and drawn.main_n_f == tuple(main_f)
    assert model.behavioral(TB, drawn=True).cdac.main_p_f == tuple(main_f)
    # the reference is ideal unless one is given (the reference study's)
    ideal = model.behavioral(TB).cdac
    assert ideal.reference_r_ohm == ideal.reference_c_f == ideal.reference_noise_v == 0.0
    given = model.behavioral(TB, reference=Reference(r_ohm=3.0, c_f=200e-12, noise_v=1e-4)).cdac
    assert (given.reference_r_ohm, given.reference_c_f, given.reference_noise_v) == (3.0, 200e-12, 1e-4)
    # the comparator's noise alone: its delay stays, so a late decision still holds
    noiseless = model.behavioral(TB, quiet=("comparator_noise",)).comp
    assert noiseless.noise_v == 0.0 and noiseless.delay_table_v == (1e-6, 1e-3)
    ideal = model.behavioral(TB, quiet=("comparator",)).comp
    assert ideal.noise_v == 0.0 and ideal.delay_table_v is None
    # a perfect track-and-hold: no on-resistance (so no tracking lag), its noise and jitter kept
    sampler = model.behavioral(TB, quiet=("sampler",)).samp
    assert sampler.ron_table_v is None and sampler.n_conductance_s_per_v == sampler.p_conductance_s_per_v == 0.0
    assert sampler.noise_v == 1e-4 and sampler.jitter_s == 2e-12
    resistance = samp_model.Model.resistance(TB.dut.samp, sampler, np.asarray([0.2, 0.6, 1.0]), 1.2)
    assert not np.any(resistance)
    quiet = model.behavioral(TB, quiet=("sampling",)).samp
    assert quiet.noise_v == quiet.jitter_s == 0.0 and quiet.ron_table_v == (0.2, 1.0)
    with pytest.raises(ValueError, match="nothing to quiet"):
        model.behavioral(TB, quiet=("samplers",))
    # the settling time constants scale; at 0 settling is ideal, the drivers' delay gone too
    nominal, slower = model.behavioral(TB).cdac, model.behavioral(TB, tau_scale=4.0).cdac
    np.testing.assert_allclose(slower.stage_tau_s, 4 * np.asarray(nominal.stage_tau_s))
    assert slower.stage_delay_s == nominal.stage_delay_s
    settled = model.behavioral(TB, tau_scale=0.0).cdac
    assert not any(settled.stage_tau_s) and not any(settled.stage_delay_s) and settled.settling_tau_s == 0.0


def test_an_error_of_the_quantization_noise_costs_an_ideal_quantizer_half_a_bit() -> None:
    assert _enob_floor(12, 12.0) == pytest.approx(11.5)
    assert _enob_floor(12, 12.0, REFERENCE_SHARE) == pytest.approx(12 - 0.5 * math.log2(1 + REFERENCE_SHARE))
    # a converter already far from its resolution loses less of it to the same error
    assert 0 < 11.0 - _enob_floor(12, 11.0) < 0.5 - 1e-3


def test_the_decoupling_is_the_decap_share_of_both_arrays_to_one_figure(monkeypatch) -> None:
    pdk = SimpleNamespace(pdk_logic=SimpleNamespace(DECAP_FF_PER_UM2=4.0))
    monkeypatch.setattr(importlib, "import_module", lambda name: pdk)
    # both arrays' 2000 um^2 at 4 fF/um^2, 30 % of it: 2.4 pF, to one figure
    assert DECAP_COVERAGE == 0.30
    # the property of a stand-in model: its PDK and its arrays' area
    decoupling_f = Model.decoupling_f.fget
    assert decoupling_f(SimpleNamespace(pdk="any", cdac=SimpleNamespace(area_um2=1000.0))) == 2e-12
    assert math.isnan(decoupling_f(SimpleNamespace(pdk="any", cdac=SimpleNamespace(area_um2=0.0))))


def test_each_requirement_is_where_its_loss_reaches_its_share_of_the_quantization_noise(monkeypatch) -> None:
    """A stand-in converter whose added error power grows as the square of the reference's noise
    and of its driver's time constant over 1 ns: each requirement lands within the search's
    resolution of the analytic one, and each figure is the loss over its grid."""
    bits, enob_bits = 12, 11.0
    lsb2 = 1.0 / 12  # the quantization noise power, in LSB^2

    def measured(ref: Reference) -> float:
        # an ideal reference gives the converter's own ENOB
        error = (ref.noise_v / 100e-6) ** 2 + (ref.r_ohm * ref.c_f / 1e-9) ** 2
        return bits - 0.5 * math.log2(2.0 ** (2 * (bits - enob_bits)) + error / lsb2)

    monkeypatch.setattr("flow.adc.model._enob", measured)
    capture = SimpleNamespace(tb=None, seed=0, noise_seed=0, unit_mismatch=0.0, quiet=(), tau_scale=1.0)
    quiets = set()

    def converted(tb, path, reference, quiet, **_) -> Reference:
        quiets.add(quiet)
        return reference

    # a stand-in model: its resolution, its capture and its decoupling
    model = SimpleNamespace(params=SimpleNamespace(adc_bits=bits), capture=converted, decoupling_f=1e-12)
    reference = Model.reference_requirements(model, capture)
    # every point on the DAC alone: the sampler and the comparator ideal
    assert quiets == {REFERENCE_QUIET}
    # the error may reach REFERENCE_SHARE of the quantization noise power: (x / x0)^2 = REFERENCE_SHARE / 12
    within = math.sqrt(REFERENCE_SHARE * lsb2)
    assert reference.noise_max_v == pytest.approx(100e-6 * within, rel=0.05)
    assert reference.noise_max_v <= 100e-6 * within
    assert reference.r_max_ohm == pytest.approx(1e3 * within, rel=0.05)
    assert reference.decap_f == 1e-12
    assert reference.enob_loss_max_bits == pytest.approx(enob_bits - _enob_floor(bits, enob_bits, REFERENCE_SHARE))
    details = [plot_reference_noise(reference), plot_reference_r_out(reference)]
    assert [plot.name for plot in details] == ["reference_noise", "reference_r_out"]
    losses = details[0].series["ENOB loss"]
    assert losses == sorted(losses) and losses[0] == pytest.approx(0.0, abs=1e-3)
