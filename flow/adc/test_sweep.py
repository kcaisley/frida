"""The ADC's design space (``flow.adc.sweep``, the grid ``converters``): the plain product of the
comparator grid, the samplers, the arrays, the resolutions and the capacitance scales, every
component its block sweep's instance; its campaign (``campaign``), every capture the figures read,
for any testbench builder; and its named Spectre runs, each the testbenches it builds and runs side
by side (the simulator replaced), with the CLI's targets of them (``flow.adc.targets``)."""

import importlib.util
import inspect
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from threading import Barrier
from typing import Any

import hdl21 as h
import hdl21.sim as hs
import numpy as np
import pytest

from flow import comp, samp
from flow.adc import plots, sim, sweep, targets
from flow.adc.params import (
    FIN_CYCLES,
    FIN_RATES_HZ,
    FRIDA1_ARRAY,
    FRIDA1_BITS,
    LADDER,
    LADDER_NAMES,
    MISMATCH_COEFFICIENTS,
    RATES_HZ,
    RESOLUTIONS,
    VALIDATION_DRAWS,
)
from flow.cdac.caparray.layout import ADC_ARRAYS, RADIX17
from flow.cdac.caparray.sim import CASES
from flow.cdac.caparray.subckt import RedunStrat, get_caparray_weights
from flow.sweep.runner import design_space, digest

PEX_FIXTURES = {view: Path(__file__).parent / "fixtures" / f"{view}_ports.scs" for view in ("frida1", "frida2")}

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
    return [params for _label, params in sweep.converters.instances(pdk)]


def _values(pdk: str, parameter: str) -> tuple[Any, ...]:
    """The values the grid gives a converter's ``parameter`` (its comparators, its samplers) in
    ``pdk``, in order: every resolution's space gives the same."""
    widened = [space.widened[parameter] for space in sweep.converters.spaces(pdk).values()]
    assert all(other == widened[0] for other in widened)
    return widened[0].values


def test_the_design_space_is_the_plain_product() -> None:
    adcs = _instances("tsmc65")
    comparators, samplers = _values("tsmc65", "comp"), _values("tsmc65", "samp")
    assert len(samplers) == 5
    assert len(adcs) == len(comparators) * 5 * (10 * 3 * 2 + 1) == 6_100
    assert len({digest(adc) for adc in adcs}) == len(adcs)
    arrays = list(ADC_ARRAYS.values())
    for adc in adcs:
        # the free first comparison and the one after the last capacitor: an N-1-step DAC
        assert adc.adc_bits == adc.cdac.n_dac + 1 and adc.adc_bits in (10, 12, 14)
        assert adc.cdac in arrays  # sized through its extraction
        assert adc.cdac.weights is None and adc.cdac.driver_strengths is None  # FRIDA-1's fabricated fields
        assert adc.samp in samplers and adc.comp in comparators
    # every array of every resolution and scale with every comparator and sampler
    assert {(adc.comp, adc.samp, adc.cdac) for adc in adcs} == {
        (comp, samp, cdac) for comp in comparators for samp in samplers for cdac in arrays
    }


def test_elsewhere_each_array_takes_the_pdks_strongarm_ladder_and_the_widest_switch() -> None:
    arrays = list(ADC_ARRAYS.values())
    for pdk in ("tsmc28", "ihp130", "tower180", "lf150", "tpsc65"):
        adcs = _instances(pdk)
        ladder = [params for _label, params in comp.base_strongarm.instances(pdk)]
        longest = max(params.tail_l for params in ladder)
        assert list(_values(pdk, "comp")) == [params for params in ladder if params.tail_l == longest]
        assert [samp.mos_w for samp in _values(pdk, "samp")] == [160]
        assert len(adcs) == len(_values(pdk, "comp")) * len(arrays) in (244, 305)
        assert {adc.cdac for adc in adcs} == set(arrays)


def test_each_resolution_takes_binary_and_three_schemes_with_two_four_and_six_extra_cycles() -> None:
    assert RESOLUTIONS == (10, 12, 14)
    for bits in RESOLUTIONS:
        for scale in (1, 2):
            arrays = sweep._arrays(bits, scale)
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
    assert FRIDA1_ARRAY == ADC_ARRAYS["12b_msb_redist5_x2"]
    assert FRIDA1_ARRAY.n_dac == RADIX17.n_dac == CASES["radix17"].n_dac
    assert get_caparray_weights(FRIDA1_ARRAY) == get_caparray_weights(RADIX17)
    assert FRIDA1_ARRAY.cap_scale == 2 and "12b_msb_redist5_x1" not in ADC_ARRAYS
    frida1 = [adc for adc in _instances("tsmc65") if adc.cdac == FRIDA1_ARRAY]
    assert len(frida1) == len(_values("tsmc65", "comp")) * len(_values("tsmc65", "samp")) == 100
    assert all(adc.adc_bits == FRIDA1_BITS and len(get_caparray_weights(adc.cdac)) + 1 == 17 for adc in frida1)
    assert (samp.FRIDA1, comp.FRIDA1) in {(adc.samp, adc.comp) for adc in frida1}


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


# the named Spectre runs and their CLI targets


@pytest.mark.parametrize("family,count", (("frida1", 4), ("frida2", 3)))
@pytest.mark.parametrize("check", (False, True))
def test_fixed_input_campaigns(family, count, check, tmp_path, monkeypatch):
    calls = []
    started = Barrier(count)

    def pool(*, max_workers, mp_context):
        assert max_workers == count
        assert mp_context.get_start_method() == "spawn"
        return ThreadPoolExecutor(max_workers=max_workers)

    def capture(params, directory, **options):
        calls.append((directory, params, options))
        started.wait(timeout=10)
        return directory / "netlist.raw", {}

    monkeypatch.setattr(sweep, "ProcessPoolExecutor", pool)
    from flow.analysis import io
    from flow.circuit import results

    monkeypatch.setattr(results, "read_raw_transient", lambda path: object())
    monkeypatch.setattr(results, "convert_raw_adc_to_measurement", lambda *args, **kwargs: object())
    monkeypatch.setattr(io, "write_measurement", lambda *args: None)
    monkeypatch.setattr(sweep, "simulate", capture)
    root = tmp_path / "campaign"
    assert getattr(sweep, f"{family}_sequence")(root, check=check) == root
    timing_count = 7
    assert len(calls) == timing_count * count
    assert len({directory for directory, *_ in calls}) == timing_count * count
    assert len({directory.parent.name for directory, *_ in calls}) == count
    assert len({directory.name for directory, *_ in calls}) == timing_count
    for directory, params, options in calls:
        flavor = directory.parent.name
        assert directory.parent.parent == root
        assert params.conversions == (1 if check else 100)
        assert params.pex_cell == "adc_12b_17step"
        assert params.view == ("frida2" if family == "frida2" else "frida1")
        assert float(params.symbol_rate) == 1.6e9
        assert float(params.vin_diff.dc) == 0.05
        assert float(params.vin_cm.dc) == pytest.approx(0.7)
        assert options["check"] == check
        assert options["noise"] is True
        assert options["pex_netlist"].name == f"{flavor}.pex.netlist"
        assert options["pex_netlist"].parent.name.startswith("20260905_")
        assert options.get("expected_disconnect", False) == (family == "frida1" and "2layer" in flavor)
        assert sum(get_caparray_weights(params.dut.cdac)) == (2303 if "radix20" in flavor else 2047)
        comp = np.fromiter(map(int, params.seq_comp_pattern), dtype=int)
        logic = np.fromiter(map(int, params.seq_logic_pattern), dtype=int)
        assert len(comp) == len(logic) == len(params.seq_init_pattern) == len(params.seq_samp_pattern) == 160
        assert len(comp) / float(params.symbol_rate) == pytest.approx(100e-9)
        comp_rises = np.flatnonzero(np.diff(comp) == 1) + 1
        comp_falls = np.flatnonzero(np.diff(np.r_[comp, 0]) == -1) + 1
        np.testing.assert_array_equal(comp_rises, 24 + 8 * np.arange(17))
        comp_word = directory.name.split("_comp", 1)[1].split("_logic", 1)[0]
        np.testing.assert_array_equal(comp_falls, comp_rises + comp_word.count("1"))
        np.testing.assert_array_equal(
            np.flatnonzero(np.fromiter(map(int, params.seq_init_pattern), dtype=int)), np.arange(4)
        )
        np.testing.assert_array_equal(
            np.flatnonzero(np.fromiter(map(int, params.seq_samp_pattern), dtype=int)), np.arange(4, 24)
        )
        assert sim.testbench(params, pex_netlist=PEX_FIXTURES[family]).name == f"AdcTb_{family}"


@pytest.mark.parametrize("family,count", (("frida1", 4), ("frida2", 3)))
def test_concurrent_campaign_propagates_case_failure(family, count, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        sweep, "ProcessPoolExecutor", lambda **kwargs: ThreadPoolExecutor(max_workers=kwargs["max_workers"])
    )

    def fail_one(_params, directory, *_args, **_kwargs):
        calls.append(directory)
        if "1layer_radix17" in directory.parent.name:
            raise RuntimeError("simulator failed")
        return directory / "netlist.raw", {}

    monkeypatch.setattr(sweep, "simulate", fail_one)
    with pytest.raises(RuntimeError, match="simulator failed"):
        getattr(sweep, f"{family}_sequence")(tmp_path)
    assert len(calls) == 7 * count


@pytest.mark.parametrize(
    "target,count,workers",
    (
        ("hdl21_sample_rate", 3, 3),
        pytest.param("frida1_sample_rate", 12, 4, marks=SITE),
        pytest.param("frida1_supply_noise", 15, 4, marks=SITE),
        ("hdl21_transfer_curve", 1, None),
        pytest.param("frida1_transfer_curve", 1, None, marks=SITE),
    ),
)
@pytest.mark.parametrize("check", (False, True))
def test_other_campaign_recipes(target, count, workers, check, tmp_path, monkeypatch):
    calls = []

    def pool(*, max_workers, mp_context):
        assert max_workers == workers
        assert mp_context.get_start_method() == "spawn"
        return ThreadPoolExecutor(max_workers=max_workers)

    def capture(params, directory, **options):
        calls.append((directory, params, options))
        return directory / "netlist.raw", {}

    monkeypatch.setattr(sweep, "ProcessPoolExecutor", pool)
    from flow.analysis import io
    from flow.circuit import results

    monkeypatch.setattr(results, "read_raw_transient", lambda path: object())
    monkeypatch.setattr(results, "convert_raw_adc_to_measurement", lambda *args, **kwargs: object())
    monkeypatch.setattr(io, "write_measurement", lambda *args: None)
    monkeypatch.setattr(sweep, "simulate", capture)
    assert getattr(sweep, target)(tmp_path, check=check) == tmp_path
    assert len(calls) == count
    assert len({directory for directory, *_ in calls}) == count
    for directory, params, options in calls:
        assert options["check"] == check
        assert params.view == ("hdl21gen" if target.startswith("hdl21") else "frida1")
        if "transfer_curve" in target:
            assert params.conversions == 151
            assert params.vin_diff == hs.LinearSweep(start=-0.75, stop=0.75, step=0.01)
            assert not options.get("noise", False)
        else:
            assert params.conversions == (1 if check else 100)
            assert float(params.vin_diff.dc) == 0.05
        if "supply_noise" in target:
            assert params.supply_series_resistance_ohm == 1.0
            assert params.supply_series_inductance_h == 1e-9
            assert params.supply_decoupling_capacitance_f == 1e-12
            assert params.supply_noise_bandwidth_hz == 25e9
            assert set(params.supply_noise_rms_v) <= {0.0, 1e-3}
            # Preserve the original supply recipe; do not enable device noise
            # as an incidental effect of consolidating the executors.
            assert not options.get("noise", False)
        elif "fixed_input_noise" in target:
            assert options["noise"] is True
    if "vs_rate" in target:
        assert {float(params.symbol_rate) for _, params, _ in calls} == {320e6, 960e6, 1.6e9}


def test_adc_targets_list_only_experiment_targets_in_family_order():
    names = [
        name
        for name, value in vars(targets).items()
        if inspect.isfunction(value) and value.__module__ == targets.__name__ and hasattr(sweep, name)
    ]
    assert names == [
        "hdl21_sample_rate",
        "hdl21_transfer_curve",
        "frida1_sequence",
        "frida1_sample_rate",
        "frida1_transfer_curve",
        "frida1_supply_noise",
        "frida2_sequence",
    ]
    assert all(not inspect.signature(getattr(targets, name)).parameters for name in names)
    assert not hasattr(sweep, "main")


def test_target_runs_full_experiment(tmp_path, monkeypatch):
    calls = []

    def frida2_sequence(directory, **options):
        calls.append((directory, options))

    def new_run(*parts):
        run_dir = (tmp_path / "build").joinpath(*parts, "20260101_000000")
        run_dir.mkdir(parents=True)
        return run_dir

    monkeypatch.setattr(sweep, "frida2_sequence", frida2_sequence)
    monkeypatch.setattr(targets, "new_run", new_run)
    targets.frida2_sequence()
    directory, options = calls[0]
    assert directory == tmp_path / "build/sim/adc/20260101_000000_frida2_sequence"
    assert directory.is_dir()
    assert not (tmp_path / "build/sim/adc/20260101_000000").exists()
    assert options == {}


def test_all_campaign_patterns_are_preserved(monkeypatch, tmp_path):
    """Independent literal expectations cover every clock of all 49 configurations."""
    from concurrent.futures import Future

    expected = {
        "symbol160_init4_samp20_comp11110000_logic00001111": ("11110000", "00001111", "00001111", "00000000"),
        "symbol160_init4_samp20_comp11110000_logic10000111": ("11110000", "00000111", "10000111", "10000000"),
        "symbol160_init4_samp20_comp11111000_logic10000111": ("11111000", "00000111", "10000111", "10000000"),
        "symbol160_init4_samp20_comp11111000_logic11000011": ("11111000", "00000011", "11000011", "11000000"),
        "symbol160_init4_samp20_comp11111100_logic11000011": ("11111100", "00000011", "11000011", "11000000"),
        "symbol160_init4_samp20_comp11111100_logic11100001": ("11111100", "00000001", "11100001", "11100000"),
        "symbol160_init4_samp20_comp11111110_logic11100001": ("11111110", "00000001", "11100001", "11100000"),
    }
    cases = []

    class CaptureExecutor:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def submit(self, function, params, directory, **kwargs):
            cases.append((directory, params))
            future = Future()
            future.set_result((directory / "netlist.raw", {}))
            return future

    from flow.analysis import io
    from flow.circuit import results

    monkeypatch.setattr(results, "read_raw_transient", lambda path: object())
    monkeypatch.setattr(results, "convert_raw_adc_to_measurement", lambda *args, **kwargs: object())
    monkeypatch.setattr(io, "write_measurement", lambda *args: None)
    monkeypatch.setattr(sweep, "ProcessPoolExecutor", CaptureExecutor)
    sweep.frida1_sequence(tmp_path)
    sweep.frida2_sequence(tmp_path)
    assert len(cases) == len({path for path, _ in cases}) == 49
    for path, params in cases:
        comp_word, first_logic, logic_word, last_logic = expected[path.name]
        expected_rows = (
            "1111" + "0" * 156,
            "0000" + "1" * 20 + "0" * 136,
            "0" * 24 + comp_word * 17,
            "001111" + "0" * 18 + first_logic + logic_word * 15 + last_logic,
        )
        assert (
            params.seq_init_pattern,
            params.seq_samp_pattern,
            params.seq_comp_pattern,
            params.seq_logic_pattern,
        ) == expected_rows
        assert float(params.symbol_rate) == 1.6e9
