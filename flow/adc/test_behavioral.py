"""Behavioral SAR model, redundancy calculation, and plotting contracts."""

from pathlib import Path

import numpy as np
import pytest
from hdl21.prefix import G

from flow import comp
from flow import samp as sampler
from flow.adc.behavioral import (
    AdcBehavioralParams,
    CdacBehavioralParams,
    CompBehavioralParams,
    SalogicBehavioralParams,
    SampBehavioralParams,
    build_continuous_sequence,
    calc_capacitor_mismatch,
    calc_ideal_capacitances,
    calc_redundancy_margins,
    calc_strongarm_noise,
    calc_switch_conductances,
    calc_switch_resistance,
    convert_behavioral,
    samp,
)
from flow.adc.sequences import symbol160_init4_samp20_comp11110000_logic00001111
from flow.adc.sim import AdcTbParams
from flow.adc.subckt import AdcParams
from flow.analysis.plots import plot_adc_redundancy
from flow.caparray.subckt import CapArrayConfig, RedunStrat, get_caparray_weights, unit_capacitance_f


def test_redundancy_calculator(tmp_path: Path) -> None:
    # q_k = sum_{j=k+1}^{M-1} w_j - w_k + w_{M-1} over sum_{j=k}^{M-1} w_j (Ogawa et al., IEICE 2010, Eq. 5)
    margins = calc_redundancy_margins((4, 3, 2, 1))
    assert margins.tolist() == pytest.approx((30.0, 100 / 6, 0.0, 0.0))
    # binary weights tolerate nothing; one more LSB decision tolerates one LSB weight at each stage
    assert calc_redundancy_margins((8, 4, 2, 1)).tolist() == pytest.approx((0.0,) * 4)
    assert calc_redundancy_margins((8, 4, 2, 1, 1)).tolist() == pytest.approx((6.25, 12.5, 25.0, 50.0, 0.0))
    with pytest.raises(ValueError, match="positive SAR weights"):
        calc_redundancy_margins((4, 0, 1))
    (path,) = plot_adc_redundancy(margins, output_path=tmp_path / "single")
    assert path.read_bytes().startswith(b"%PDF")


def test_14_bit_weight_comparison(tmp_path: Path) -> None:
    binary = tuple(2**bit for bit in range(13, -1, -1))
    redistributed_18 = tuple(
        get_caparray_weights(CapArrayConfig(n_dac=14, n_extra=4, redun_strat=RedunStrat.MSB_REDIST))
    )
    redistributed_20 = tuple(
        get_caparray_weights(CapArrayConfig(n_dac=14, n_extra=6, redun_strat=RedunStrat.MSB_REDIST))
    )
    assert tuple(map(len, (binary, redistributed_18, redistributed_20))) == (14, 18, 20)
    assert tuple(map(sum, (binary, redistributed_18, redistributed_20))) == (16383,) * 3
    binary_margin = calc_redundancy_margins(binary)
    redistributed_18_margin = calc_redundancy_margins(redistributed_18)
    redistributed_20_margin = calc_redundancy_margins(redistributed_20)
    assert np.allclose(binary_margin, 0.0)
    assert np.all(redistributed_18_margin[:14] > 0)
    assert np.all(redistributed_20_margin[:16] > 0)

    (path,) = plot_adc_redundancy(
        {
            "14-bit binary": binary_margin,
            "14-bit redistributed (18 stages)": redistributed_18_margin,
            "14-bit redistributed (20 stages)": redistributed_20_margin,
        },
        output_path=tmp_path / "redundancy",
    )
    assert path.name == "redundancy.pdf"
    assert path.read_bytes().startswith(b"%PDF")


def ideal_sar_codes(weights: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Every code's centre converted by an ideal top-plate SAR on ``weights``: the free first
    comparison, each capacitor's step both ways, the comparison after the last; the codes it gives."""
    codes = np.arange(2 * sum(weights) + 2)
    residue = codes + 0.5 - len(codes) / 2
    found = np.zeros_like(codes)
    for weight in weights:
        decision = residue > 0
        found += decision * 2 * weight
        residue = residue - np.where(decision, weight, -weight)
    return codes, found + (residue > 0)


@pytest.mark.parametrize("bits", (10, 11, 12, 13, 14))
def test_every_scheme_reaches_every_code(bits: int) -> None:
    # the decisions' weights of an N-bit converter on its N-1-step DAC: each capacitor's step both
    # ways, then the comparison after the last one switches
    arrays = [CapArrayConfig(n_dac=bits - 1, n_extra=0, redun_strat=RedunStrat.BINARY)] + [
        CapArrayConfig(n_dac=bits - 1, n_extra=extra, redun_strat=scheme)
        for scheme in (RedunStrat.MSB_SPLIT, RedunStrat.LSB_SPLIT, RedunStrat.MSB_REDIST)
        for extra in range(1, 7)
    ]
    for cdac in arrays:
        weights = get_caparray_weights(cdac)
        assert sum(weights) == 2 ** (bits - 1) - 1  # every scheme the binary total
        margins = calc_redundancy_margins((*(2 * weight for weight in weights), 1))
        # no stage's error band is lost (a negative margin would be missing codes); the split MSBs
        # and the redistribution give the free first comparison its tolerance, the split LSBs none
        assert np.all(margins >= 0.0), (bits, cdac)
        assert (margins[0] > 0.0) == (cdac.redun_strat in (RedunStrat.MSB_SPLIT, RedunStrat.MSB_REDIST)), cdac
        # and an ideal SAR on the weights converts every code to itself
        codes, found = ideal_sar_codes(weights)
        assert len(codes) == 2**bits and np.array_equal(codes, found), cdac


TB = AdcTbParams(
    dut=AdcParams(adc_bits=12, cdac=CapArrayConfig()),
    symbol_rate=1.6 * G,
    **symbol160_init4_samp20_comp11110000_logic00001111.as_tb_fields(),
)


def with_tb(**fields) -> AdcBehavioralParams:
    return AdcBehavioralParams(tb=AdcTbParams(**{**TB.__dict__, **fields}))


def test_continuous_sequence_reproduces_the_catalog_recipe() -> None:
    assert build_continuous_sequence(16) == symbol160_init4_samp20_comp11110000_logic00001111


def test_ideal_capacitances_reproduce_the_generated_weights() -> None:
    main_f, diff_f = calc_ideal_capacitances(TB.dut.cdac)
    np.testing.assert_allclose((main_f - diff_f) / unit_capacitance_f(TB.dut.cdac), get_caparray_weights(TB.dut.cdac))


def test_capacitor_mismatch_follows_pelgrom_area_scaling() -> None:
    draws = calc_capacitor_mismatch(
        np.tile([100e-15, 1e-15], (20000, 1)), unit_mismatch=0.01, rng=np.random.default_rng(0)
    )
    # sigma_C = 1 % * sqrt(C * 1 fF): 0.1 fF for 100 fF and 0.01 fF for 1 fF.
    np.testing.assert_allclose(np.std(draws / 1e-15, axis=0), [0.1, 0.01], rtol=0.03)


def ideal_codes(params: AdcBehavioralParams, points: int = 2001) -> tuple[np.ndarray, np.ndarray]:
    tb = params.tb
    main_f, diff_f = calc_ideal_capacitances(tb.dut.cdac)
    full_scale_v = float(tb.vdd_dac.dc) * np.sum(main_f - diff_f) / np.sum(main_f + diff_f)
    vin_v = np.linspace(-full_scale_v, full_scale_v, points)
    code_weights = np.append(2 * np.asarray(get_caparray_weights(tb.dut.cdac)), 1)
    code_max = (1 << tb.dut.adc_bits) - 1
    bout = convert_behavioral(params, vin_v).bout
    code = np.rint((bout @ code_weights) * code_max / code_weights.sum())
    ideal_code = np.clip(np.floor((vin_v / full_scale_v + 1) / 2 * (code_max + 1)), 0, code_max)
    return code, ideal_code


@pytest.mark.parametrize("astate", [(0, 1) * 8, (0,) * 16, (1,) * 16, (1, 1, 0, 0) * 4])
def test_ideal_transfer_is_independent_of_the_initial_state(astate) -> None:
    code, ideal_code = ideal_codes(with_tb(dac_astate_p=astate, dac_astate_n=astate))
    assert np.max(np.abs(code - ideal_code)) <= 1


@pytest.mark.parametrize("n_dac, n_extra", [(9, 3), (13, 6)])
def test_other_resolutions_convert_and_scale_logic_energy(n_dac: int, n_extra: int) -> None:
    cdac = CapArrayConfig(n_dac=n_dac, n_extra=n_extra)
    stages = len(get_caparray_weights(cdac))
    params = AdcBehavioralParams(
        tb=AdcTbParams(
            dut=AdcParams(adc_bits=n_dac + 1, cdac=cdac),
            symbol_rate=1.6 * G,
            dac_astate_p=(0, 1) * (stages // 2) + (0,) * (stages % 2),
            dac_astate_n=(0, 1) * (stages // 2) + (0,) * (stages % 2),
            dac_bstate_p=(0,) * stages,
            dac_bstate_n=(0,) * stages,
            **build_continuous_sequence(stages).as_tb_fields(),
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


def test_sampler_resistance_peaks_at_mid_supply_and_delays_the_track() -> None:
    switch = SampBehavioralParams(n_conductance_s_per_v=10e-3, p_conductance_s_per_v=10e-3)
    resistance = calc_switch_resistance(sampler.Params(), switch, np.asarray([0.1, 0.6, 1.1]), 1.2)
    assert resistance[1] > resistance[0] and resistance[1] > resistance[2]
    held = samp(
        sampler.Params(),
        switch,
        {"p": np.asarray([0.6]), "n": np.asarray([0.6])},
        {"p": np.asarray([1e6]), "n": np.asarray([0.0])},
        load_f={"p": 1e-12, "n": 1e-12},
        gate_v=1.2,
        rng=np.random.default_rng(0),
    )
    # A 1 V/us slope lags by R * C = resistance[1] * 1 pF.
    assert held["p"][0] == pytest.approx(0.6 - 1e6 * resistance[1] * 1e-12)
    assert held["n"][0] == pytest.approx(0.6)


def test_differential_caps_double_their_weight_without_diffcaps() -> None:
    # With dac_diffcaps=0 the diff plates move with the main plates, so each
    # step is (main + diff) instead of (main - diff): a small input resolves
    # to a code nearer mid-scale.
    vin_v = np.asarray([0.2])
    code_weights = np.append(2 * np.asarray(get_caparray_weights(TB.dut.cdac)), 1)
    differential = convert_behavioral(with_tb(dac_diffcaps=1), vin_v).bout @ code_weights
    common = convert_behavioral(with_tb(dac_diffcaps=0), vin_v).bout @ code_weights
    assert abs(common[0] - code_weights.sum() / 2) < abs(differential[0] - code_weights.sum() / 2)


def test_sampler_jitter_shifts_both_sides_by_one_common_time() -> None:
    held = samp(
        sampler.Params(),
        SampBehavioralParams(n_conductance_s_per_v=0.0, p_conductance_s_per_v=0.0, jitter_s=1e-9),
        {"p": np.full(20000, 0.6), "n": np.full(20000, 0.6)},
        {"p": np.full(20000, 1e6), "n": np.full(20000, -1e6)},
        load_f={"p": 1e-12, "n": 1e-12},
        gate_v=1.2,
        rng=np.random.default_rng(0),
    )
    # 1 V/us times 1 ns RMS: 1 mV per side, perfectly anticorrelated across sides.
    assert np.std(held["p"]) == pytest.approx(1e-3, rel=0.03)
    np.testing.assert_allclose(held["p"] - 0.6, -(held["n"] - 0.6))


def test_sampler_conductances_follow_the_hdl21_switch_sizing() -> None:
    switch = SampBehavioralParams()
    # 32 x 0.12 um over 60 nm: W/L of 64.
    assert calc_switch_conductances(sampler.Params(), switch) == pytest.approx((300e-6 * 64, 100e-6 * 64))
    assert calc_switch_conductances(
        sampler.Params(switch_type=sampler.SwitchType.NMOS, mos_l=2), switch
    ) == pytest.approx((300e-6 * 32, 0.0))


def test_strongarm_noise_falls_with_larger_pq_capacitance() -> None:
    small = calc_strongarm_noise(comp.Params(), 0.7)
    large = calc_strongarm_noise(comp.Params(diffpair_w=64, rst_w=16), 0.7)
    assert 1e-3 < small < 5e-3
    assert large < small


def reference_codes(vin_v: float, conversions: int = 400, **reference) -> np.ndarray:
    """The output codes at a DC input with the reference's departure (``CdacBehavioralParams``'s
    ``reference_*``) the only impairment."""
    params = AdcBehavioralParams(
        tb=TB,
        comp=CompBehavioralParams(noise_v=0.0),
        cdac=CdacBehavioralParams(**reference),
        seed=3,
    )
    code_weights = np.append(2 * np.asarray(get_caparray_weights(TB.dut.cdac)), 1)
    bout = convert_behavioral(params, np.full(conversions, vin_v)).bout
    return (bout @ code_weights) * ((1 << TB.dut.adc_bits) - 1) / code_weights.sum()


def full_scale_and_lsb() -> tuple[float, float]:
    main_f, diff_f = calc_ideal_capacitances(TB.dut.cdac)
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


def test_the_reference_noise_leaves_the_other_sources_draws_alike() -> None:
    """The reference's noise draws from a stream of its own: a negligible one changes no decision
    the comparator's noise makes."""
    _, lsb_v = full_scale_and_lsb()

    def bout(**reference) -> np.ndarray:
        params = AdcBehavioralParams(
            tb=TB, comp=CompBehavioralParams(noise_v=lsb_v), cdac=CdacBehavioralParams(**reference), seed=3
        )
        return convert_behavioral(params, np.full(200, 0.33 * lsb_v)).bout

    assert np.array_equal(bout(reference_noise_v=1e-12), bout())


def test_the_model_quiets_each_source_alone_and_scales_the_settling() -> None:
    from types import SimpleNamespace

    from flow.adc.model import AdcModel, Reference

    main_f, diff_f = calc_ideal_capacitances(TB.dut.cdac)
    model = AdcModel(
        pdk="none",
        params=TB.dut,
        comp=SimpleNamespace(
            behavioral=lambda vin_cm_v: CompBehavioralParams(
                noise_v=1e-4, delay_table_v=(1e-6, 1e-3), delay_table_s=(200e-12, 50e-12)
            )
        ),
        samp=SimpleNamespace(
            behavioral=lambda load_f: SampBehavioralParams(
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
    resistance = calc_switch_resistance(TB.dut.samp, sampler, np.asarray([0.2, 0.6, 1.0]), 1.2)
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
