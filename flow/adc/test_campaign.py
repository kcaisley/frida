"""The ADC campaign declares every capture its figures need, for any testbench builder."""

from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import hdl21 as h
import numpy as np
import pytest

from flow.adc.behavioral import BOLTZMANN_J_PER_K, CompBehavioralParams, SampBehavioralParams, calc_ideal_capacitances
from flow.adc.campaign import (
    FIN_CYCLES,
    FIN_RATES_HZ,
    LADDER,
    MISMATCH_COEFFICIENTS,
    RATES_HZ,
    UNIT_MISMATCH,
    VALIDATION_DRAWS,
    campaign,
    ladder_names,
)
from flow.adc.figures import FIGURES, _extracted, enob_ladder
from flow.adc.subckt import AdcParams
from flow.analysis.adc import analyze_adc_dynamic
from flow.caparray.subckt import CapArrayConfig, RedunStrat


def test_the_campaign_has_every_capture_the_figures_read() -> None:
    def tb(*, conversions, rate_hz, vin_diff):
        return {"conversions": conversions, "rate_hz": rate_hz, "vin_diff": vin_diff}

    captures = campaign(tb, 0.7)
    names = set(captures)
    assert {"ramp_train", "ramp_check", "trajectory", "noise"} <= names
    assert sum(name.startswith("rate_") for name in names) == len(RATES_HZ)
    assert sum(name.startswith("fin_") for name in names) == len(FIN_RATES_HZ) * len(FIN_CYCLES)
    assert sum(name.startswith("dc_") for name in names) == 33
    # one capacitor draw for both ramps, independent noise: the calibration's training and check
    train, check = captures["ramp_train"], captures["ramp_check"]
    assert train.seed == check.seed and train.unit_mismatch == check.unit_mismatch == UNIT_MISMATCH
    assert train.noise_seed != check.noise_seed
    # sines at -0.5 dBFS of the full scale, DC inputs across it
    assert abs(captures["rate_10"].tb["vin_diff"].vamp - 0.7 * 10 ** (-0.5 / 20)) < 1e-9
    assert isinstance(captures["dc_00"].tb["vin_diff"], h.Vdc.Params)
    assert captures["dc_00"].tb["vin_diff"].dc == -0.7 and captures["dc_32"].tb["vin_diff"].dc == 0.7
    assert next(iter(FIGURES)) == "redundancy" and {"noise_input", "hsu_rate"} <= set(FIGURES)
    # what a fabricated instance can show: its settling is its own, only its rate varies
    assert not {"hsu_map", "hsu_fastest"} & set(FIGURES)
    # the noise over the input, and Hsu's study: every rate at the array's own settling, and at each
    # rate a reference with ideal timing at the same rate
    assert "noise_input" in names
    hsu = [name for name in names if name.startswith("hsu_r") and not name.startswith("hsu_reference")]
    references = [name for name in names if name.startswith("hsu_reference_r")]
    assert len(hsu) == len(references) == len(RATES_HZ)
    for index, rate in enumerate(RATES_HZ):
        reference, own = captures[f"hsu_reference_r{index}"], captures[f"hsu_r{index}"]
        assert reference.tb["rate_hz"] == rate == own.tb["rate_hz"]
        assert reference.tau_scale == 0.0 and "comparator" in reference.quiet
        assert own.tau_scale == 1.0 and "comparator" not in own.quiet
    # the ENOB ladder: the 10 MS/s sine, quantization alone first, one impairment more a step, the
    # last rate_10 itself
    names = ladder_names()
    assert len(names) == len(LADDER) and names[-1] == "rate_10" and "enob_ladder" in FIGURES
    steps = [captures[name] for name in names]
    assert all(replace(step, quiet=(), tau_scale=1.0) == captures["rate_10"] for step in steps)
    assert steps[0].tau_scale == 0.0 and {"sampler", "sampling", "comparator", "rail"} <= set(steps[0].quiet)
    assert steps[-1].quiet == () and steps[-1].tau_scale == 1.0
    # each step adds one impairment: the timing of the comparator ("comparator" made it ideal,
    # "comparator_noise" keeps its delay), else one source less quiet or the settling on
    for before, after in pairwise(steps):
        timing = "comparator" in before.quiet and "comparator_noise" in after.quiet
        quieter = set(before.quiet) - set(after.quiet) - ({"comparator"} if timing else set())
        settled = after.tau_scale != before.tau_scale
        assert int(timing) + len(quieter) + int(settled) == 1 and set(after.quiet) - {"comparator_noise"} <= set(
            before.quiet
        )
    # the mismatch is predicted, not drawn: the Monte Carlo that checks it only where asked for
    assert not any(name.startswith("mc_") for name in names)
    assert {"mismatch_weight_sigma", "mismatch_transition_sigma", "mismatch_margin"} <= set(FIGURES)
    drawn = campaign(tb, 0.7, mismatch_draws=VALIDATION_DRAWS)
    studies = [capture for name, capture in drawn.items() if name.startswith("mc_")]
    assert len(studies) == len(MISMATCH_COEFFICIENTS) * VALIDATION_DRAWS and all(c.noise_free for c in studies)
    assert {c.unit_mismatch for c in studies} == set(MISMATCH_COEFFICIENTS)


def _stub_model(table: Path, params: AdcParams):
    """An ADC model of ideal blocks of known impairments, the array's ideal capacitances in an
    extraction's table, at a 1.2 V supply (no PDK)."""
    from flow.adc.model import AdcModel

    class Model(AdcModel):
        supply_v = 1.2

    main_f, diff_f = calc_ideal_capacitances(params.cdac)
    rows = (f"{i},{m * 1e15:.6f},{d * 1e15:.6f},{(m - d) * 1e15:.6f}\n" for i, (m, d) in enumerate(zip(main_f, diff_f)))
    table.write_text("stage,main_ff,diff_ff,effective_ff\n" + "".join(rows))
    load_f = float(np.sum(main_f) + np.sum(diff_f))
    return Model(
        pdk="none",
        params=params,
        comp=SimpleNamespace(
            behavioral=lambda vin_cm_v: CompBehavioralParams(
                noise_v=100e-6, delay_table_v=(1e-6, 1e-3), delay_table_s=(2e-9, 0.6e-9)
            )
        ),
        # an on-resistance twice as high at mid-supply as at the rails: a tracking error that distorts
        samp=SimpleNamespace(
            behavioral=lambda load_f: SampBehavioralParams(
                noise_v=float(np.sqrt(2 * BOLTZMANN_J_PER_K * 300 / load_f)),
                jitter_s=2e-12,
                ron_table_v=(0.2, 0.7, 1.2),
                # on the 12-bit array's 0.54 pF at its 204 aF unit, a time constant of 0.4-0.8 ns
                ron_table_ohm=(750.0, 1500.0, 750.0),
            )
        ),
        cdac=SimpleNamespace(
            draw=lambda unit_mismatch, rng: (main_f, diff_f),
            parasitic_f=0.0,
            main_f=main_f,
            diff_f=diff_f,
            load_f=load_f,
            table=table,
        ),
        drivers=tuple(SimpleNamespace(resistance_ohm=1.0, intrinsic_delay_s=20e-12, energy_j=0.0) for _ in main_f),
        settling=SimpleNamespace(tau_s=(0.35e-9,) * len(main_f), delay_s=(50e-12,) * len(main_f)),
    )


def _capture(model, declared):
    """The model's capture of one declared capture, its sources and settling as declared."""
    return model.capture(
        declared.tb,
        None,
        seed=declared.seed,
        noise_seed=declared.noise_seed,
        unit_mismatch=declared.unit_mismatch,
        quiet=declared.quiet,
        tau_scale=declared.tau_scale,
    )


@pytest.mark.parametrize(
    "cdac",
    [CapArrayConfig(n_dac=11, n_extra=0, redun_strat=RedunStrat.BINARY), CapArrayConfig()],
    ids=["binary", "msb_redist"],
)
def test_the_ladder_starts_at_quantization_and_ends_on_enob_bits(tmp_path: Path, cdac: CapArrayConfig) -> None:
    params = AdcParams(adc_bits=12, cdac=cdac)
    model = _stub_model(tmp_path / "table.csv", params)
    plan = campaign(model.tb, model.full_scale_v, params.adc_bits)
    captures = {name: _capture(model, plan[name]) for name in ladder_names()}
    ladder = enob_ladder(captures)
    assert ladder is not None and len(ladder) == len(LADDER)
    # quantization alone reads the design resolution: the extracted weights' codes unrounded (whole
    # codes would quantize a second time) and the -0.5 dBFS sine's SNDR referred to full scale
    assert ladder[0] == pytest.approx(params.adc_bits, abs=0.02)
    # the sampler's input-dependent on-resistance distorts the held sine
    assert ladder[1] < ladder[0] - 0.5
    # every impairment on is the 10 MS/s sine as enob_bits decodes it (the extracted weights), and
    # the last step's sources and settling capture it again, decision for decision
    rate = captures["rate_10"]
    assert ladder[-1] == analyze_adc_dynamic(rate, calibration=_extracted(rate)).spectral_enob_fs_bits
    _, _, quiet, tau_scale = LADDER[-1]
    again = _capture(model, replace(plan["rate_10"], quiet=quiet, tau_scale=tau_scale))
    np.testing.assert_array_equal(again.bout, rate.bout)
    assert enob_ladder({**captures, "rate_10": again})[-1] == ladder[-1]
    # without the ladder's captures (a SPICE campaign), no ladder
    assert enob_ladder({"rate_10": rate}) is None


@pytest.mark.parametrize("adc_bits", [10, 12])
def test_the_ladders_quantization_reads_the_design_resolution(tmp_path: Path, adc_bits: int) -> None:
    """Quantization alone (a binary array, as the sweep's binary instances) reads the design
    resolution: the ladder refers the -0.5 dBFS sine's SNDR to full scale, where at the sine's own
    amplitude it reads half a dB less."""
    params = AdcParams(
        adc_bits=adc_bits, cdac=CapArrayConfig(n_dac=adc_bits - 1, n_extra=0, redun_strat=RedunStrat.BINARY)
    )
    model = _stub_model(tmp_path / "table.csv", params)
    plan = campaign(model.tb, model.full_scale_v, params.adc_bits)
    captures = {name: _capture(model, plan[name]) for name in ladder_names()}
    ladder = enob_ladder(captures)
    assert ladder is not None
    assert ladder[0] == pytest.approx(adc_bits, abs=0.02)
    quantization = captures[ladder_names()[0]]
    at_amplitude = analyze_adc_dynamic(quantization, calibration=_extracted(quantization)).spectral_enob_bits
    assert at_amplitude == pytest.approx(adc_bits - 0.5 / 6.02, abs=0.02)
