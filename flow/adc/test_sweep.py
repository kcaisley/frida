"""The ADC's design space (``flow.adc.sweep``, the grid ``converters``): the plain product of the
comparator grid, the samplers, the arrays, the resolutions and the capacitance scales, every
component its block sweep's instance; and its campaign (``campaign``), every capture the figures
read, for any testbench builder."""

import inspect
from dataclasses import replace
from itertools import pairwise

import hdl21 as h

from flow import comp
from flow.adc import plots, sweep
from flow.adc.params import (
    FIN_CYCLES,
    FIN_RATES_HZ,
    LADDER,
    LADDER_NAMES,
    MISMATCH_COEFFICIENTS,
    RATES_HZ,
    VALIDATION_DRAWS,
)
from flow.cdac.caparray.layout import ADC_ARRAYS, RADIX17
from flow.cdac.caparray.sim import CASES
from flow.cdac.caparray.subckt import RedunStrat, get_caparray_weights
from flow.sweep.runner import design_space, digest

# the record's figures by name, in the viewer's order: the plots module's
FIGURES = [
    name.removeprefix("plot_")
    for name, value in vars(plots).items()
    if name.startswith("plot_") and inspect.isfunction(value)
]


def _instances(pdk: str) -> list:
    return [params for _label, params in sweep.converters.instances(pdk)]


def test_the_design_space_is_the_plain_product() -> None:
    adcs = _instances("tsmc65")
    assert sweep.COMPARATORS == sweep.COMP_GRID and len(sweep.SAMPLER_STEPS) == 5
    assert len(adcs) == len(sweep.COMPARATORS) * 5 * (10 * 3 * 2 + 1) == 6_100
    assert len({digest(adc) for adc in adcs}) == len(adcs)
    arrays = list(ADC_ARRAYS.values())
    for adc in adcs:
        # the free first comparison and the one after the last capacitor: an N-1-step DAC
        assert adc.adc_bits == adc.cdac.n_dac + 1 and adc.adc_bits in (10, 12, 14)
        assert adc.cdac in arrays  # sized through its extraction
        assert adc.cdac.weights is None and adc.cdac.driver_strengths is None  # FRIDA-1's fabricated fields
        assert adc.samp in sweep.SAMPLER_STEPS and adc.comp in sweep.COMPARATORS
    # every array of every resolution and scale with every comparator and sampler
    assert {(adc.comp, adc.samp, adc.cdac) for adc in adcs} == {
        (comp, samp, cdac) for comp in sweep.COMPARATORS for samp in sweep.SAMPLER_STEPS for cdac in arrays
    }


def test_elsewhere_each_array_takes_the_pdks_strongarm_ladder_and_the_widest_switch() -> None:
    arrays = list(ADC_ARRAYS.values())
    for pdk in ("tsmc28", "ihp130", "tower180", "lf150", "tpsc65"):
        adcs = _instances(pdk)
        ladder = [params for _label, params in comp.base_strongarm.instances(pdk)]
        longest = max(params.tail_l for params in ladder)
        assert list(sweep.comparators(pdk).values()) == [params for params in ladder if params.tail_l == longest]
        assert [samp.mos_w for samp in sweep.samplers(pdk).values()] == [160]
        assert len(adcs) == len(sweep.comparators(pdk)) * len(arrays) in (244, 305)
        assert {adc.cdac for adc in adcs} == set(arrays)


def test_each_resolution_takes_binary_and_three_schemes_with_two_four_and_six_extra_cycles() -> None:
    assert sweep.RESOLUTIONS == (10, 12, 14)
    for bits in sweep.RESOLUTIONS:
        for scale in (1, 2):
            arrays = sweep.arrays(bits, scale)
            assert [(cdac.redun_strat, cdac.n_extra) for cdac in arrays] == [(RedunStrat.BINARY, 0)] + [
                (scheme, extra)
                for scheme in (RedunStrat.MSB_SPLIT, RedunStrat.LSB_SPLIT, RedunStrat.MSB_REDIST)
                for extra in (2, 4, 6)
            ]
            assert {sum(get_caparray_weights(cdac)) for cdac in arrays} == {2 ** (bits - 1) - 1}
            assert all(cdac.cap_scale == scale for cdac in arrays)
    assert len(ADC_ARRAYS) == 61


def test_frida1s_converter_is_one_of_the_product() -> None:
    # FRIDA-1's array: the characterization's radix-1.7 case, 16 stages, 17 decisions at 12 bits, at
    # two of the 12-bit least capacitance (its drawn size is near it)
    assert sweep.FRIDA1_ARRAY == ADC_ARRAYS["12b_msb_redist5_x2"]
    assert sweep.FRIDA1_ARRAY.n_dac == RADIX17.n_dac == CASES["radix17"].n_dac
    assert get_caparray_weights(sweep.FRIDA1_ARRAY) == get_caparray_weights(RADIX17)
    assert sweep.FRIDA1_ARRAY.cap_scale == 2 and "12b_msb_redist5_x1" not in ADC_ARRAYS
    frida1 = [adc for adc in _instances("tsmc65") if adc.cdac == sweep.FRIDA1_ARRAY]
    assert len(frida1) == len(sweep.COMPARATORS) * len(sweep.SAMPLER_STEPS) == 100
    assert all(adc.adc_bits == sweep.FRIDA1_BITS and len(get_caparray_weights(adc.cdac)) + 1 == 17 for adc in frida1)
    assert (sweep.TGATE, comp.FRIDA1) in {(adc.samp, adc.comp) for adc in frida1}


def test_every_component_is_its_block_sweeps_instance() -> None:
    # the same parameters, so the same digest: the ADC model reads that instance's characterization
    comparators = set(design_space("comp", "tsmc65"))
    assert all(digest(params) in comparators for params in sweep.COMPARATORS)
    samplers = set(design_space("samp", "tsmc65"))
    assert [digest(samp) for samp in sweep.SAMPLER_STEPS] == [
        "2e79aff2a06f",  # FRIDA-1's transmission gate
        "f4bf3438c025",  # bootstrapped, doubled boost capacitor (32 minimum widths)
        "b2e58e7c8a85",  # bootstrapped, 64, boosted alike
        "9078be2cb02f",  # 112
        "b43e51f5eb7c",  # 160
    ]
    assert all(digest(samp) in samplers and not samp.dummy for samp in sweep.SAMPLER_STEPS)


def test_the_campaign_has_every_capture_the_figures_read() -> None:
    def tb(*, conversions, rate_hz, vin_diff):
        return {"conversions": conversions, "rate_hz": rate_hz, "vin_diff": vin_diff}

    captures = sweep.campaign(tb, 0.7)
    names = set(captures)
    assert {"ramp_train", "ramp_check", "trajectory", "noise"} <= names
    assert sum(name.startswith("rate_") for name in names) == len(RATES_HZ)
    assert sum(name.startswith("fin_") for name in names) == len(FIN_RATES_HZ) * len(FIN_CYCLES)
    assert sum(name.startswith("dc_") for name in names) == 33
    # both ramps on the CDAC's SPICE draw, independent noise: the calibration's training and check;
    # the nominal rate's sine on it too, its testbench and seeds the nominal sine's
    train, check = captures["ramp_train"], captures["ramp_check"]
    assert train.drawn and check.drawn and train.unit_mismatch == check.unit_mismatch == 0.0
    assert train.noise_seed != check.noise_seed
    drawn, nominal = captures["drawn_sine"], captures["rate_10"]
    assert drawn.drawn and not nominal.drawn and drawn.tb == nominal.tb and drawn.noise_seed == nominal.noise_seed
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
    names = LADDER_NAMES
    assert len(names) == len(LADDER) and names[-1] == "rate_10" and "enob_ladder" in FIGURES
    steps = [captures[name] for name in names]
    assert all(replace(step, quiet=(), tau_scale=1.0) == captures["rate_10"] for step in steps)
    assert steps[0].tau_scale == 0.0 and {"sampler", "sampling", "comparator"} <= set(steps[0].quiet)
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
    drawn = sweep.campaign(tb, 0.7, mismatch_draws=VALIDATION_DRAWS)
    studies = [capture for name, capture in drawn.items() if name.startswith("mc_")]
    assert len(studies) == len(MISMATCH_COEFFICIENTS) * VALIDATION_DRAWS and all(c.noise_free for c in studies)
    assert {c.unit_mismatch for c in studies} == set(MISMATCH_COEFFICIENTS)
