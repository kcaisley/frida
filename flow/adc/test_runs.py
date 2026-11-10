"""The ADC's design space (``flow.adc.runs``, the grid ``converters``, in TSMC65 alone): the plain
product of the comparator grid, the samplers, the arrays (both weight builds), the resolutions and
the capacitance scales, every component its block sweep's instance; its runs at each level, every
capture the figures read; the record of any of them; and the circuit simulator's runs, each the
testbench it builds, and each timing's figures."""

import importlib.util
import inspect
import math
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import hdl21 as h
import hdl21.sim as hs
import numpy as np
import pytest

from flow import capdac, comp, samp
from flow.adc import plots, runs, sim
from flow.adc.analysis import analyze_extracted
from flow.adc.params import (
    FIN_CYCLES,
    FIN_RATES_HZ,
    FRIDA1_ARRAY,
    FRIDA1_BITS,
    LADDER,
    LADDER_NAMES,
    MISMATCH_COEFFICIENTS,
    RATES_HZ,
    REFERENCE_NOISE_V,
    REFERENCE_QUIET,
    REFERENCE_R_OUT_OHM,
    RESOLUTIONS,
    VALIDATION_DRAWS,
    Extraction,
    Fabricated,
    Params,
    Probes,
    Quiet,
    Recipe,
    Simulator,
    TbParams,
)
from flow.pipeline import Level, Pdk
from flow.sweep.runner import design_space, digest

from .test_analysis import _campaign

PEX_FIXTURES = {"frida1": Path(__file__).parent / "fixtures" / "frida1_ports.scs"}

# the record's figures by name, in the viewer's order: the plots module's
FIGURES = [
    name.removeprefix("plot_")
    for name, value in vars(plots).items()
    if name.startswith("plot_") and inspect.isfunction(value)
]


def _tsmc65_site() -> bool:
    try:
        return importlib.util.find_spec("pdk.tsmc65.hdl21.site") is not None
    except ModuleNotFoundError:
        return False


# FRIDA-1's extracted runs take their inputs' paths from the TSMC65 kit's site module
SITE = pytest.mark.skipif(not _tsmc65_site(), reason="FRIDA-1's extracted runs read the TSMC65 kit's site")


def _instances(pdk: str) -> list:
    return [params for _label, params in runs.converters.instances(pdk)]


def _swept_arrays() -> list[capdac.Params]:
    """The arrays the converters take: capdac's design space, its grid (both weight builds) and
    FRIDA-1's array."""
    return [cdac for _label, cdac in capdac.arrays.instances("tsmc65")] + [capdac.frida1()]


def _values(pdk: str, parameter: str) -> tuple[Any, ...]:
    """The values the grid gives a converter's ``parameter`` (its comparators, its samplers) in
    ``pdk``, in order: every resolution's space gives the same."""
    widened = [space.widened[parameter] for space in runs.converters.spaces(pdk).values()]
    assert all(other == widened[0] for other in widened)
    return widened[0].values


def _arrays(pdk: Pdk, bits: int) -> dict[str, capdac.Params]:
    """The arrays the grid gives a resolution's converters in ``pdk``, by name, in order."""
    cdac = runs.converters.spaces(pdk)[f"{bits}b"].widened["cdac"]
    return dict(zip(cdac.names, cdac.values, strict=True))


def test_the_design_space_is_the_plain_product() -> None:
    adcs = _instances("tsmc65")
    comparators, samplers = _values("tsmc65", "comp"), _values("tsmc65", "samp")
    assert len(samplers) == 5
    assert len(adcs) == len(comparators) * 5 * (10 * 3 * 2 * 2 + 1) == 12_100
    assert len({digest(adc) for adc in adcs}) == len(adcs)
    arrays = _swept_arrays()
    for adc in adcs:
        # the free first comparison and the one after the last capacitor: an N-1-step DAC
        assert adc.adc_bits == adc.cdac.bits and adc.adc_bits in (10, 12, 14)
        assert adc.cdac in arrays
        assert adc.cdac.weights is None  # a fabricated array's own field: the design space never sets it
        assert adc.samp in samplers and adc.comp in comparators
    # every array of every resolution and scale with every comparator and sampler
    assert {(adc.comp, adc.samp, adc.cdac) for adc in adcs} == {
        (comp, samp, cdac) for comp in comparators for samp in samplers for cdac in arrays
    }


def test_elsewhere_no_converter_until_the_dac_is_characterized_there() -> None:
    """A converter's DAC is capdac's record, which TSMC65 alone has: the grid gives no other PDK an
    instance. Their spaces stay as they will be swept: each array with the PDK's StrongARM ladder at
    its longest tail and the widest bootstrapped switch."""
    arrays = _swept_arrays()
    assert runs.converters.pdks == (Pdk.TSMC65,)
    for pdk in ("tsmc28", "ihp130", "tower180", "lf150", "tpsc65"):
        assert not _instances(pdk)
        ladder = [params for _label, params in comp.base_strongarm.instances(pdk)]
        longest = max(params.tail_l for params in ladder)
        assert list(_values(pdk, "comp")) == [params for params in ladder if params.tail_l == longest]
        assert [samp.mos_w for samp in _values(pdk, "samp")] == [160]
        spaced = [cdac for space in runs.converters.spaces(pdk).values() for cdac in space.widened["cdac"].values]
        assert len(spaced) == len(arrays) and set(spaced) == set(arrays)
        assert len(_values(pdk, "comp")) * len(arrays) in (484, 605)


def test_each_resolution_takes_binary_and_three_schemes_with_two_four_and_six_extra_cycles() -> None:
    assert RESOLUTIONS == (10, 12, 14)
    schemes = [(capdac.Redundancy.BINARY, 0)] + [
        (scheme, extra)
        for scheme in (capdac.Redundancy.MSB_SPLIT, capdac.Redundancy.LSB_SPLIT, capdac.Redundancy.MSB_REDIST)
        for extra in (2, 4, 6)
    ]
    count = 0
    for bits in RESOLUTIONS:
        named = _arrays(Pdk.TSMC65, bits)
        count += len(named)
        arrays = [cdac for cdac in named.values() if cdac != FRIDA1_ARRAY]
        # the difference capacitors' arrays, then the unit capacitors': one minimum's, then two
        # minimums', each binary and then each scheme
        assert [(cdac.weight_impl, cdac.scale, cdac.redundancy, cdac.extra) for cdac in arrays] == [
            (build, scale, scheme, extra)
            for build in (capdac.WeightImpl.DIFFERENCE_CAPS, capdac.WeightImpl.UNIT_CAPS)
            for scale in (1, 2)
            for scheme, extra in schemes
        ]
        assert {sum(capdac.Model.weights(cdac)) for cdac in arrays} == {2 ** (bits - 1) - 1}
        assert all(cdac.bits == bits for cdac in arrays)
        # the difference capacitors named as the legacy extractions name them, the unit capacitors
        # the same with _unit
        names = list(named)
        assert names[:2] == [f"{bits}b_binary_x1", f"{bits}b_msb_split2_x1"]
        assert names[len(schemes)] == f"{bits}b_binary_x2"
        assert names[2 * len(schemes) : 2 * len(schemes) + 2] == [
            f"{bits}b_binary_x1_unit",
            f"{bits}b_msb_split2_x1_unit",
        ]
        unit = [cdac.weight_impl is capdac.WeightImpl.UNIT_CAPS for cdac in named.values()]
        assert [name.endswith("_unit") for name in names] == unit
        assert [name.removesuffix("_unit") for name, is_unit in zip(names, unit, strict=True) if is_unit] == [
            name for name, is_unit in zip(names, unit, strict=True) if not is_unit and named[name] != FRIDA1_ARRAY
        ]
    assert count == 121


def test_frida1s_converter_is_one_of_the_product() -> None:
    # FRIDA-1's array: capdac's frida1 (its defaults), 16 stages, 17 decisions at 12 bits, at two of
    # the 12-bit least capacitance (its drawn size is near it)
    arrays = _arrays(Pdk.TSMC65, FRIDA1_BITS)
    assert FRIDA1_ARRAY == capdac.frida1() == capdac.Params() == arrays["12b_msb_redist5_x2"]
    assert list(arrays)[-1] == "12b_msb_redist5_x2" and "12b_msb_redist5_x1" not in arrays
    assert FRIDA1_ARRAY.bits == FRIDA1_BITS and FRIDA1_ARRAY.extra == 5 and FRIDA1_ARRAY.scale == 2
    frida1 = [adc for adc in _instances("tsmc65") if adc.cdac == FRIDA1_ARRAY]
    assert len(frida1) == len(_values("tsmc65", "comp")) * len(_values("tsmc65", "samp")) == 100
    assert all(adc.adc_bits == FRIDA1_BITS and len(capdac.Model.weights(adc.cdac)) + 1 == 17 for adc in frida1)
    assert (samp.FRIDA1, comp.FRIDA1) in {(adc.samp, adc.comp) for adc in frida1}


def test_each_swept_array_is_an_instance_of_the_dacs_design_space() -> None:
    """The model reads a converter's DAC from capdac's characterization of the same parameters,
    found by their digest: every array the converters take, of either weight build and FRIDA-1's, is
    an instance of capdac's design space in the PDK, and every instance of it is swept."""
    dacs = design_space("capdac", "tsmc65")
    assert all(digest(adc.cdac) in dacs for adc in _instances("tsmc65"))
    assert {digest(cdac) for cdac in _swept_arrays()} == set(dacs) and len(dacs) == 121


def test_every_component_is_its_block_sweeps_instance() -> None:
    # the same parameters, so the same digest: the ADC model reads that instance's characterization
    comparators = set(design_space("comp", "tsmc65"))
    assert all(digest(params) in comparators for params in _values("tsmc65", "comp"))
    samplers = set(design_space("samp", "tsmc65"))
    assert [digest(samp) for samp in _values("tsmc65", "samp")] == [
        "2e79aff2a06f",  # FRIDA-1's transmission gate
        "f4bf3438c025",  # bootstrapped, doubled boost capacitor (32 minimum widths)
        "b2e58e7c8a85",  # bootstrapped, 64, boosted alike
        "9078be2cb02f",  # 112
        "b43e51f5eb7c",  # 160
    ]
    assert all(digest(samp) in samplers and not samp.dummy for samp in _values("tsmc65", "samp"))


def _stand_in(params: Params | None = None, *, decoupling_f: float = 1e-12) -> SimpleNamespace:
    """A converter for its runs alone (``sim.behavioral_testbenches``): its testbench builder on the continuous
    sequence of FRIDA-1's 16 stages, a full scale of 0.7 V, its decoupling."""
    params = Params() if params is None else params

    def tb(*, conversions, rate_hz, vin_diff):
        base = TbParams(pdk="tsmc65", params=params, conversions=conversions, vin_diff=vin_diff).continuous(16)
        return base.sequenced(symbol_rate=rate_hz * len(base.seq_init.data))

    return SimpleNamespace(tb=tb, full_scale_v=0.7, params=params, decoupling_f=decoupling_f)


def test_the_campaign_has_every_run_the_figures_read() -> None:
    captures = _campaign(_stand_in(), Level.FULL)
    names = set(captures)
    assert {"ramp_train", "ramp_check", "trajectory", "noise", "noise_sampling", "noise_comparator"} <= names
    assert sum(name.startswith("rate_") for name in names) == len(RATES_HZ)
    assert sum(name.startswith("fin_") for name in names) == len(FIN_RATES_HZ) * len(FIN_CYCLES)
    assert sum(name.startswith("dc_") for name in names) == 33
    # both ramps on the CDAC's SPICE draw, independent noise: the calibration's training and check;
    # the nominal rate's sine on it too, its testbench and seeds the nominal sine's
    train, check = captures["ramp_train"], captures["ramp_check"]
    assert train.drawn and check.drawn and train.unit_mismatch == check.unit_mismatch == 0.0
    assert train.noise_seed != check.noise_seed
    drawn, nominal = captures["drawn_sine"], captures["rate_10"]
    assert drawn.drawn and not nominal.drawn and replace(drawn, drawn=False) == nominal
    # one noise source alone: the noise run with the other quiet
    assert captures["noise_sampling"] == replace(captures["noise"], quiet=frozenset({Quiet.COMPARATOR}))
    assert captures["noise_comparator"] == replace(captures["noise"], quiet=frozenset({Quiet.SAMPLING}))
    # sines at -0.5 dBFS of the full scale, DC inputs across it
    assert abs(captures["rate_10"].vin_diff.vamp - 0.7 * 10 ** (-0.5 / 20)) < 1e-9
    assert isinstance(captures["dc_00"].vin_diff, h.Vdc.Params)
    assert captures["dc_00"].vin_diff.dc == -0.7 and captures["dc_32"].vin_diff.dc == 0.7
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
        assert reference.sample_rate_hz == pytest.approx(rate) and own.symbol_rate == reference.symbol_rate
        assert reference.tau_scale == 0.0 and Quiet.COMPARATOR in reference.quiet
        assert own.tau_scale == 1.0 and Quiet.COMPARATOR not in own.quiet
    # the ENOB ladder: the 10 MS/s sine, quantization alone first, one impairment more a step, the
    # last rate_10 itself
    ladder = LADDER_NAMES
    assert len(ladder) == len(LADDER) and ladder[-1] == "rate_10" and "enob_ladder" in FIGURES
    steps = [captures[name] for name in ladder]
    assert all(replace(step, quiet=frozenset(), tau_scale=1.0) == captures["rate_10"] for step in steps)
    assert steps[0].tau_scale == 0.0 and {Quiet.SAMPLER, Quiet.SAMPLING, Quiet.COMPARATOR} <= steps[0].quiet
    assert steps[-1].quiet == frozenset() and steps[-1].tau_scale == 1.0
    # each step adds one impairment: the timing of the comparator (COMPARATOR made it ideal,
    # COMPARATOR_NOISE keeps its delay), else one source less quiet or the settling on
    for before, after in pairwise(steps):
        timing = Quiet.COMPARATOR in before.quiet and Quiet.COMPARATOR_NOISE in after.quiet
        quieter = before.quiet - after.quiet - ({Quiet.COMPARATOR} if timing else set())
        settled = after.tau_scale != before.tau_scale
        assert int(timing) + len(quieter) + int(settled) == 1 and after.quiet - {Quiet.COMPARATOR_NOISE} <= before.quiet
    # the reference study: the nominal sine, its own draw, sampler and comparator ideal, on an ideal
    # reference and at each grid point; the driver's resistance onto the converter's decoupling
    ideal = captures["ref_ideal"]
    assert ideal == replace(nominal, quiet=REFERENCE_QUIET)
    noisy = [captures[name] for name in sorted(names) if name.startswith("ref_noise_")]
    resistive = [captures[name] for name in sorted(names) if name.startswith("ref_r_")]
    assert [tb.reference_noise_v for tb in noisy] == list(REFERENCE_NOISE_V)
    assert [tb.reference_r_ohm for tb in resistive] == list(REFERENCE_R_OUT_OHM)
    assert {tb.reference_c_f for tb in resistive} == {1e-12}
    assert all(replace(tb, reference_noise_v=0.0) == ideal for tb in noisy)
    # no decoupling (NaN: the PDK gives no decap density), no resistance runs
    alone = _campaign(_stand_in(decoupling_f=math.nan), Level.FULL)
    assert not any(name.startswith("ref_r_") for name in alone) and "ref_noise_0" in alone
    # the mismatch is predicted, not drawn: the Monte Carlo that checks it only where asked for
    assert not any(name.startswith("mc_") for name in names)
    assert {"mismatch_weight_sigma", "mismatch_transition_sigma", "mismatch_margin"} <= set(FIGURES)
    drawn = _campaign(_stand_in(), Level.FULL, mismatch_draws=VALIDATION_DRAWS)
    studies = [capture for name, capture in drawn.items() if name.startswith("mc_")]
    assert len(studies) == len(MISMATCH_COEFFICIENTS) * VALIDATION_DRAWS and all(
        c.quiet == {Quiet.SAMPLING, Quiet.COMPARATOR} for c in studies
    )
    assert {c.unit_mismatch for c in studies} == set(MISMATCH_COEFFICIENTS)


@pytest.mark.parametrize("params", [Params(), Fabricated.FRIDA1_1LAYER_RADIX17.params], ids=["frida1", "fabricated"])
def test_each_levels_runs_hold_the_level_below(monkeypatch, params) -> None:
    """``runs`` at each level, its converter a stand-in: SCREEN the ramps, the nominal sine and the
    noise run; each level after it every run of the level below, unchanged; CIRCUIT the circuit
    simulator's runs (``spice_*``) beside FULL's, every other run behavioral."""
    monkeypatch.setattr(sim, "_converter", lambda pdk, found: _stand_in(found))
    checked = []
    monkeypatch.setattr(sim, "_checked", checked.append)
    levels = [runs.testbenches("tsmc65", params, level) for level in Level]
    # each extraction the circuit runs simulate checked once, before any run
    fabricated = params.fabricated is not None
    assert {tb.extraction for tb in checked} == ({Extraction.TAPEOUT, Extraction.SIGNOFF} if fabricated else set())
    assert len(checked) == len({tb.extraction for tb in checked})
    assert set(levels[0]) == {"ramp_train", "ramp_check", "rate_10", "noise"}
    for below, above in pairwise(levels):
        assert set(below) < set(above) and all(above[name] == tb for name, tb in below.items())
    circuit = set(levels[-1]) - set(levels[-2])
    assert circuit and all(name.startswith("spice_") for name in circuit)
    assert {levels[-1][name].simulator for name in circuit} == {Simulator.SPECTRE}
    assert {tb.simulator for name, tb in levels[-1].items() if name not in circuit} == {Simulator.BEHAVIORAL}


@pytest.mark.parametrize("pdk", ["ihp130", "tsmc28"])
def test_a_pdk_without_the_adcs_spectre_runs_has_no_circuit_runs(monkeypatch, pdk) -> None:
    """Outside TSMC65 (the ADC's Spectre runs take its kit's includes) CIRCUIT's runs are FULL's: none
    raises after the behavioral runs before it."""
    monkeypatch.setattr(sim, "_converter", lambda pdk, found: _stand_in(found))
    assert sim._spice_runs(pdk, Params()) == {}
    assert runs.testbenches(pdk, Params(), Level.CIRCUIT) == runs.testbenches(pdk, Params(), Level.FULL)


def test_a_circuit_level_without_its_layouts_signoff_is_refused_before_any_run(monkeypatch) -> None:
    """A fabricated converter's CIRCUIT runs, its layout never signed off: ``runs`` raises, before the
    runner simulates the first of them."""
    pytest.importorskip("pdk.tsmc65.hdl21.site")

    def unlaid(*_):
        raise LookupError("no standing layout")

    monkeypatch.setattr(sim, "_converter", lambda pdk, found: _stand_in(found))
    monkeypatch.setattr(sim.lookup, "laid_out", unlaid)
    with pytest.raises(LookupError, match="no standing layout"):
        runs.testbenches("tsmc65", Fabricated.FRIDA1_1LAYER_RADIX17.params, Level.CIRCUIT)


def test_a_screen_record_measures_what_its_runs_ran(tmp_path: Path) -> None:
    """The record of SCREEN's runs, converted by a behavioral converter of ideal blocks: the ENOB,
    linearity, power, calibrations, noise and the converter's own numbers; every metric of a run it
    did not run None (NaN), none raising; the figures of the runs it has."""
    from flow.adc.test_analysis import _stub_model

    params = Params(adc_bits=10, cdac=capdac.Params(bits=10, redundancy=capdac.Redundancy.BINARY, extra=0))
    converter = _stub_model(tmp_path / "table.csv", params)
    numbers = {
        "full_scale_v": converter.full_scale_v,
        "supply_v": 1.2,
        "settling_tau_s": 0.35e-9,
        "decoupling_f": math.nan,
        "dac_driver_energy_j": 0.0,
        "comp_noise_v": 1e-4,
        "comp_delay_s": 6e-10,
        "comp_regeneration_tau_s": 2e-10,
        "decision_window_s": 2.9e-9,
        "metastable_input_lsb": 1e-3,
    }

    def capture(tb: TbParams):
        measurement = converter.capture(tb, None)
        return replace(measurement, info=replace(measurement.info, readbacks={**measurement.info.readbacks, **numbers}))

    plan = _campaign(converter, Level.SCREEN)
    assert set(plan) == {"ramp_train", "ramp_check", "rate_10", "noise"}
    result = runs.results({name: capture(tb) for name, tb in plan.items()})
    values = result.metrics
    measured = {
        "enob_bits",
        "inl_max_lsb",
        "inl_max_calibrated_lsb",
        "power_w",
        "noise_rms_lsb",
        "redundancy_first_pct",
        "calibration_best",
        "mismatch_dnl_p95_lsb",
        "stages",
        "full_scale_v",
        "metastable_input_lsb",
    }
    assert all(math.isfinite(values[name]) for name in measured)
    unmeasured = {
        "enob_nyquist_bits",
        "rate_max_hz",
        "noise_input_mid_lsb",
        "error_free_rate_max_hz",
        "noise_sampling_rms_lsb",
        "enob_quantization_bits",
        "enob_drawn_design_bits",
        "ref_noise_max_v",
        "spice_noise_rms_lsb",
    }
    assert all(math.isnan(values[name]) for name in unmeasured)
    names = [plot.name for plot in result.details]
    assert {"inl", "inl_calibrated", "noise_spectrum", "enob_rate", "power_rate", "mismatch_inl"} <= set(names)
    assert not {"enob_fin", "enob_ladder", "hsu_rate", "trajectory", "reference_noise"} & set(names)
    assert result.waves == {}


def test_a_record_refuses_another_measurement() -> None:
    with pytest.raises(TypeError, match="not the converter's MeasAdc"):
        runs.results({"noise": SimpleNamespace()})


# the circuit simulator's runs (``spice_*``, at Level.CIRCUIT), the named Spectre campaigns' successors

_TIMINGS = {
    "comp11110000_logic00001111": ("11110000", "00001111", "00001111", "00000000"),
    "comp11110000_logic10000111": ("11110000", "00000111", "10000111", "10000000"),
    "comp11111000_logic10000111": ("11111000", "00000111", "10000111", "10000000"),
    "comp11111000_logic11000011": ("11111000", "00000011", "11000011", "11000000"),
    "comp11111100_logic11000011": ("11111100", "00000011", "11000011", "11000000"),
    "comp11111100_logic11100001": ("11111100", "00000001", "11100001", "11100000"),
    "comp11111110_logic11100001": ("11111110", "00000001", "11100001", "11100000"),
}


def test_a_generated_converters_spice_runs_are_its_rates_and_its_ramp() -> None:
    spice = sim._spice_runs("tsmc65", Params())
    assert set(spice) == {"spice_rate_2", "spice_rate_6", "spice_rate_10", "spice_ramp"}
    recipe = Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC11000011
    for name, rate in (("spice_rate_2", 0.32e9), ("spice_rate_6", 0.96e9), ("spice_rate_10", 1.6e9)):
        tb = spice[name]
        assert (tb.simulator, tb.extraction, tb.params) == (Simulator.SPECTRE, None, Params())
        assert (tb.conversions, float(tb.vin_diff.dc), tb.transient_noise) == (100, 0.05, True)
        assert float(tb.symbol_rate) == rate and tb.rows == tuple("".join(row.split()) for row in recipe.rows)
        # the viewer's waves at the nominal rate, the codes alone elsewhere
        assert tb.probes is (Probes.NODES if name == "spice_rate_10" else Probes.CODES)
        assert sim._runnable(tb)
    ramp = spice["spice_ramp"]
    assert ramp.conversions == 151 and ramp.vin_diff == hs.LinearSweep(start=-0.75, stop=0.75, step=0.01)
    assert not ramp.transient_noise and float(ramp.symbol_rate) == 1.6e9
    # a design of other stages than FRIDA-1's 16: its continuous sequence, its DAC states its own
    ten = sim._spice_runs("tsmc65", Params(adc_bits=10, cdac=capdac.Params(bits=10)))
    stages = ten["spice_rate_10"].stages
    assert stages != 16 and len(ten["spice_rate_10"].dac_astate_p) == stages
    assert all(sim._runnable(tb) for tb in ten.values())


@pytest.mark.parametrize("member", list(Fabricated), ids=lambda member: member.name.lower())
def test_a_fabricated_converters_spice_runs_simulate_its_extractions(member, monkeypatch) -> None:
    """The fabricated converters' runs: the rates on the tape-out's extraction; the one-layer
    radix-17 flavor's ramp and its 15 supply-noise runs; every flavor's seven continuous timings on
    its layout's signoff extraction, their rows each clock's as the reviewed recipes give them."""
    spice = sim._spice_runs("tsmc65", member.params)
    rates = {f"spice_rate_{rate}" for rate in ("2", "6", "10")}
    timings = {f"spice_sequence_{name}" for name in _TIMINGS}
    supplies = {
        f"spice_supply_{rate}_{rail}" for rate in ("2", "6", "10") for rail in ("none", "vdda", "vddd", "vddac", "all")
    }
    extra = {"spice_ramp", *supplies} if member is Fabricated.FRIDA1_1LAYER_RADIX17 else set()
    assert set(spice) == rates | timings | extra
    for name, tb in spice.items():
        assert tb.params == member.params and tb.simulator is Simulator.SPECTRE
        assert tb.extraction is (Extraction.SIGNOFF if name in timings else Extraction.TAPEOUT)
        assert tb.expected_disconnect == (member.layers == 2 and name in timings)
        assert sim._runnable(tb)
    for name in supplies & set(spice):
        tb = spice[name]
        assert (tb.supply_series_resistance_ohm, tb.supply_series_inductance_h) == (1.0, 1e-9)
        assert tb.supply_decoupling_capacitance_f == 1e-12 and tb.supply_noise_bandwidth_hz == 25e9
        assert set(tb.supply_noise_rms_v) <= {0.0, 1e-3} and not tb.transient_noise
    for name in timings:
        tb = spice[name]
        comp_word, first_logic, logic_word, last_logic = _TIMINGS[name.removeprefix("spice_sequence_")]
        assert tb.rows == (
            "1111" + "0" * 156,
            "0000" + "1" * 20 + "0" * 136,
            "0" * 24 + comp_word * 17,
            "001111" + "0" * 18 + first_logic + logic_word * 15 + last_logic,
        )
        assert (float(tb.symbol_rate), tb.conversions, float(tb.vin_diff.dc)) == (1.6e9, 100, 0.05)
        assert tb.transient_noise and float(tb.vin_cm.dc) == pytest.approx(0.7)
    # its signoff extraction's top, the run finding it itself (``sim._extraction``)
    monkeypatch.setattr(sim, "_extraction", lambda tb: (PEX_FIXTURES["frida1"], "adc_12b_17step"))
    assert sim.testbench(spice[f"spice_sequence_{next(iter(_TIMINGS))}"]).name == "AdcTb_frida1"


def _extracted(measurement):
    """A capture's extracted weights as its record decodes with them: read as a run's is
    (``sim.read``, its ``cap_table`` readback's capacitance with it), then ``analyze_extracted``."""
    return analyze_extracted(sim._with_extraction(measurement))


def test_extracted_weights_are_a_pex_tables_effective_capacitances(tmp_path: Path) -> None:
    from flow.adc.test_analysis import adc_measurement

    nominal = adc_measurement([0, 1, 2], readbacks={}).nominal_bout_weights.astype(float)
    effective_ff = nominal[:-1] / 2 * 0.4
    effective_ff[3] *= 1.02
    table = tmp_path / "capacitance_table.csv"
    table.write_text(
        "stage,main_ff,diff_ff,effective_ff\n"
        + "".join(f"{stage},{value + 1},1,{value}\n" for stage, value in enumerate(effective_ff))
    )

    measurement = adc_measurement([0, 1, 2], readbacks={"cap_table": str(table)})
    calibration = _extracted(measurement)

    assert calibration.method == "extracted"
    assert calibration.identity == measurement.identity
    assert np.sum(calibration.calibrated_weights) == pytest.approx(measurement.code_max)
    ratio = calibration.calibrated_weights / (nominal * measurement.code_max / np.sum(nominal))
    # Only stage 3 departs from the nominal capacitor ratios, by its 2 % excess;
    # the terminal decision follows the projected scale instead.
    assert ratio[3] / ratio[0] == pytest.approx(1.02)
    np.testing.assert_allclose(np.delete(ratio[:-1], 3), ratio[0])
    assert calibration.measured_weight_mask.tolist() == [True] * 16 + [False]


def test_extracted_weights_are_a_capacitive_dacs_measured_steps(tmp_path: Path, monkeypatch) -> None:
    """The settling measurement a capacitive DAC's characterization keeps (``flow.capdac``): each
    stage's step as measured (``capdac.Model.measured_steps``), its slower direction's (a falling one
    negative), in proportion to its effective capacitance; nothing extracted (no path), the design's
    own weights, none measured."""
    import flow.capdac.model as capdac_model
    from flow.adc.test_analysis import adc_measurement

    measurement = adc_measurement([0, 1, 2], readbacks={})
    nominal = measurement.nominal_bout_weights.astype(float)
    # the steps in volts: the design's at some gain, stage 3 2 % large, every other stage falling
    steps = 0.37e-3 * nominal[:-1] * np.where(np.arange(len(nominal) - 1) % 2, -1.0, 1.0)
    steps[3] *= 1.02
    path = tmp_path / "settling" / "result.h5"
    read = []
    monkeypatch.setattr(capdac_model, "read_measurement", lambda source: read.append(source) or "settling")
    monkeypatch.setattr(capdac_model, "analyze_settling", lambda meas: SimpleNamespace(step_v=steps) if meas else None)

    measurement = adc_measurement([0, 1, 2], readbacks={"cap_table": str(path)})
    calibration = _extracted(measurement)

    assert calibration.method == "extracted" and calibration.label == "Measured-step weights"
    # read and analyzed once a process, however many captures decode with it
    again = _extracted(measurement)
    np.testing.assert_array_equal(again.calibrated_weights, calibration.calibrated_weights)
    assert read == [path]
    assert calibration.identity == measurement.identity
    assert np.sum(calibration.calibrated_weights) == pytest.approx(measurement.code_max)
    ratio = calibration.calibrated_weights / (nominal * measurement.code_max / np.sum(nominal))
    assert ratio[3] / ratio[0] == pytest.approx(1.02)
    np.testing.assert_allclose(np.delete(ratio[:-1], 3), ratio[0])
    assert calibration.measured_weight_mask.tolist() == [True] * 16 + [False]

    design = _extracted(adc_measurement([0, 1, 2], readbacks={"cap_table": ""}))
    np.testing.assert_allclose(design.calibrated_weights, design.nominal_weights)
    assert not design.measured_weight_mask.any()


def test_each_timings_circuit_run_draws_its_decision_paths_and_its_sequence() -> None:
    """The sequence runs' record (``spice_sequence_*``): the map of the timings, and each timing's
    decision paths (whole, their last decisions, the codes they end on) and programmed sequence,
    each figure named by its run."""
    from flow.adc.test_analysis import adc_measurement, timing_sequences

    spice = {}
    for number, rows in enumerate(timing_sequences[:2]):
        capture = adc_measurement([1000, 1001, 1002, 1001] * 25, sample_rate_hz=10e6, observed_adc=0)
        spice[f"spice_sequence_t{number}"] = replace(
            capture, param=replace(capture.param, tb=capture.tb.sequenced(rows))
        )
    figures = runs.results(spice).details
    names = [figure.name for figure in figures]
    assert names[:3] == ["spice_sequence_enob", "spice_sequence_plausible", "spice_sequence_shift"]
    assert names[3:] == [
        f"spice_sequence_t{number}_{figure}"
        for number in range(2)
        for figure in ("trajectory", "trajectory_final", "trajectory_codes", "sequencer")
    ]
