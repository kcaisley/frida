"""The ADC's design space (``flow.adc.sweep``): the plain product of the comparator grid, the
samplers, the arrays, the resolutions and the capacitance scales, every component its block
sweep's instance."""

from flow import comp
from flow.adc import sweep
from flow.caparray.layout import ADC_ARRAYS, RADIX17
from flow.caparray.sim import CASES
from flow.caparray.subckt import RedunStrat, get_caparray_weights
from flow.samp import sweep as samp_sweep
from flow.sweep.runner import design_space, digest


def test_the_design_space_is_the_plain_product() -> None:
    adcs = sweep.instances("tsmc65")
    assert all(not sweep.instances(pdk) for pdk in ("tsmc28", "ihp130", "tower180", "lf150", "tpsc65"))
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
    frida1 = [adc for adc in sweep.instances("tsmc65") if adc.cdac == sweep.FRIDA1_ARRAY]
    assert len(frida1) == len(sweep.COMPARATORS) * len(sweep.SAMPLER_STEPS) == 100
    assert all(adc.adc_bits == sweep.FRIDA1_BITS and len(get_caparray_weights(adc.cdac)) + 1 == 17 for adc in frida1)
    assert (sweep.TGATE, comp.frida1()) in {(adc.samp, adc.comp) for adc in frida1}


def test_every_component_is_its_block_sweeps_instance() -> None:
    # the same parameters, so the same digest: the ADC model reads that instance's characterization
    comparators = set(design_space("comp", "tsmc65"))
    assert all(digest(params) in comparators for params in sweep.COMPARATORS)
    samplers = {digest(samp) for samp in samp_sweep.instances("tsmc65")}
    assert [digest(samp) for samp in sweep.SAMPLER_STEPS] == [
        "0208193e4ead",  # FRIDA-1's transmission gate
        "b2cc08f9747c",  # bootstrapped, doubled boost capacitor (32 minimum widths)
        "9c9f7a31d4a4",  # bootstrapped, 64, boosted alike
        "4cdbd50b7bca",  # 112
        "a24997a98572",  # 160
    ]
    assert all(digest(samp) in samplers and not samp.dummy for samp in sweep.SAMPLER_STEPS)
