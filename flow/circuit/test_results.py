"""Software-only tests for VLSIR-to-FRIDA result conversion."""

from pathlib import Path

import hdl21 as h
import numpy as np
import pytest
from vlsirtools.spice.sim_data import TranResult

from flow.adc.sim import AdcTbParams
from flow.adc.subckt import AdcNets
from flow.analysis.io import read_measurement, write_measurement
from flow.analysis.types import CompIntWave, MeasAdcInt, MeasCompInt
from flow.circuit.ports import waveform_net_names
from flow.circuit.results import convert_raw_adc_to_measurement, convert_raw_comp_to_measurement
from flow.comp import CompParams
from flow.comp.sim import CompTb, CompTbParams
from pdk import tsmc65


def test_adc_waveform_conversion_writes_shared_hdf5(tmp_path: Path) -> None:
    expected_bout = "10110100101100101"
    time_step_s = 0.05e-9
    conversion_offsets_s = np.asarray([0.0, 170.0e-9])
    times_s = np.arange(0.0, 345.0e-9 + time_step_s / 2, time_step_s)
    comp_edge_times_s = np.concatenate(
        [offset_s + 5.0e-9 + np.arange(17) * 8.0e-9 for offset_s in conversion_offsets_s]
    )
    logic_edge_times_s = np.concatenate(
        [offset_s + 5.0e-9 + np.arange(16) * 8.0e-9 + 3.0e-9 for offset_s in conversion_offsets_s]
    )

    # The ADC has 17 comparator decisions but only 16 DAC-update/ LOGIC edges:
    # its final decision does not update the CDAC. Put each decision transition
    # at 97% of the COMP-to-LOGIC interval. The production LOGIC-edge sample
    # must decode the new bit, whereas an earlier 95% sample still sees the
    # preceding decision. B16 is retained until the next INIT LOGIC pulse.
    seq_comp_v = np.zeros_like(times_s)
    seq_logic_v = np.zeros_like(times_s)
    for edge_s in comp_edge_times_s:
        seq_comp_v[(times_s >= edge_s) & (times_s < edge_s + 0.5e-9)] = 1.2
    for edge_s in logic_edge_times_s:
        seq_logic_v[(times_s >= edge_s) & (times_s < edge_s + 0.5e-9)] = 1.2
    for edge_s in (1.5e-9, 171.5e-9, 341.5e-9):
        seq_logic_v[(times_s >= edge_s) & (times_s < edge_s + 0.25e-9)] = 1.2

    comp_out_v = np.zeros_like(times_s)
    repeated_bout = expected_bout * len(conversion_offsets_s)
    for decision_index, bit in enumerate(repeated_bout):
        transition_s = comp_edge_times_s[decision_index] + 0.97 * 3.0e-9
        stop_s = (
            comp_edge_times_s[decision_index + 1] + 0.97 * 3.0e-9
            if decision_index + 1 < len(repeated_bout)
            else times_s[-1] + time_step_s
        )
        comp_out_v[(times_s >= transition_s) & (times_s < stop_s)] = 1.2 * int(bit)

    raw_wave_names = waveform_net_names(AdcNets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
    values = {name: np.zeros_like(times_s) for name in raw_wave_names}
    values.update(
        {
            "vin_p": np.full_like(times_s, 0.650),
            "vin_n": np.full_like(times_s, 0.600),
            "seq_init": np.where(
                ((times_s >= 1.0e-9) & (times_s < 2.0e-9))
                | ((times_s >= 171.0e-9) & (times_s < 172.0e-9))
                | ((times_s >= 341.0e-9) & (times_s < 342.0e-9)),
                1.2,
                0.0,
            ),
            "seq_comp": seq_comp_v,
            "seq_logic": seq_logic_v,
            "comp_out": comp_out_v,
            # Spectre voltage-source current is into the source positive
            # terminal, hence negative while each rail delivers current.
            "i(vdd_a)": np.full_like(times_s, -2.0e-6),
            "i(vdd_d)": np.full_like(times_s, -40.0e-6),
            "i(vdd_dac)": np.full_like(times_s, -20.0e-6),
        }
    )
    values = {
        "time": times_s,
        **values,
    }
    signal_names = {"time": "time", **{name: name for name in raw_wave_names}}
    signal_names["comp.latch_p"] = "latch_internal"
    values["latch_internal"] = np.full_like(times_s, 0.875)
    raw_path = tmp_path / "netlist.raw"
    raw_path.touch()

    params = AdcTbParams(waveform_sample_interval_s=50e-12, conversions=2)
    h5_path = tmp_path / "adc.h5"
    expected = convert_raw_adc_to_measurement(
        TranResult("tran", values, {}),
        params=params,
        raw_path=raw_path,
        signal_names={raw: alias for alias, raw in signal_names.items()},
    )
    write_measurement(h5_path, expected)
    raw_path.unlink()  # Newly written measurements must not need the original raw file.
    measurement = read_measurement(h5_path)

    assert isinstance(measurement, MeasAdcInt)
    assert measurement.info.backend == "spice"
    assert measurement.info.readbacks["raw_format"] == "spectre_nutbin"
    assert measurement.info.readbacks["raw_max_timestep_s"] == pytest.approx(time_step_s)
    assert measurement.info.readbacks["waveform_sample_interval_s"] == pytest.approx(50e-12)
    assert measurement.info.readbacks["waveform_interpolated_from_coarser_raw"] is False
    assert measurement.info.readbacks["decision_sample_fraction"] == pytest.approx(1.0)
    assert measurement.info.readbacks["decision_time_reference"] == "seq_logic_rising_threshold_B0_B15"
    assert measurement.info.readbacks["final_decision_sample_fraction"] == pytest.approx(1.0)
    assert measurement.info.readbacks["final_decision_time_reference"] == "next_init_seq_logic_rising_threshold"
    assert measurement.info.readbacks["supply_power_available"] is True
    assert measurement.info.readbacks["supply_current_convention"] == "positive_current_draw"
    assert measurement.info.readbacks["vdd_d_active_average_power_w"] == pytest.approx(48.0e-6)
    assert len(measurement.daq.conversion_index) == 2
    assert all("".join(str(bit) for bit in row) == expected_bout for row in measurement.daq.bout)
    np.testing.assert_array_equal(measurement.daq.bout[0, -2:], [0, 1])
    assert measurement.daq.dout_raw[0] > 0
    assert measurement.daq.dout[0] > 0
    assert measurement.daq.vin_diff_v[0] == pytest.approx(0.050)
    np.testing.assert_array_equal(measurement.wave.conversion_index, [0, 1])
    assert measurement.wave.voltage["comp_out"].shape == (2, len(measurement.wave.time_s))
    np.testing.assert_allclose(np.diff(measurement.wave.time_s), 50e-12)
    assert measurement.wave.voltage["seq_init"][0, 0] == pytest.approx(0.0)
    np.testing.assert_allclose(measurement.wave.current["vdd_a"], 2.0e-6)
    np.testing.assert_allclose(measurement.wave.current["vdd_d"], 40.0e-6)
    np.testing.assert_allclose(measurement.wave.current["vdd_dac"], 20.0e-6)
    np.testing.assert_allclose(measurement.wave.voltage["comp.latch_p"], 0.875)
    assert measurement.wave.voltage["comp.latch_p"].shape == measurement.wave.voltage["comp_out"].shape


@pytest.mark.parametrize("before_v,after_v,expected_bit", [(0.3, 1.2, 1), (0.0, 0.9, 0)])
def test_adc_capture_uses_logic_threshold_not_early_fraction_or_later_sample(
    tmp_path: Path, before_v: float, after_v: float, expected_bit: int
) -> None:
    ticks = np.arange(4001)
    times_s = ticks * 0.05e-9
    names = waveform_net_names(AdcNets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
    values = {name: np.zeros_like(times_s) for name in names}
    values["time"] = times_s
    values["seq_init"][20:40] = 1.2
    values["seq_init"][3000:3020] = 1.2
    values["seq_logic"][3030:3040] = 1.2
    for bit in range(17):
        start = 100 + 160 * bit
        values["seq_comp"][start : start + 10] = 1.2
        if bit < 16:
            values["seq_logic"][start + 60 : start + 70] = 1.2
    # First LOGIC threshold is halfway between ticks 159 and 160 (7.975 ns).
    # The first case resolves after the former 98% read but before LOGIC.
    # The second resolves after LOGIC but before the first above-threshold
    # clock sample, and must therefore still decode zero at the LOGIC edge.
    values["comp_out"][159] = before_v
    values["comp_out"][160:170] = after_v
    raw_path = tmp_path / "netlist.raw"
    raw_path.touch()
    result = convert_raw_adc_to_measurement(
        TranResult("tran", values, {}),
        params=AdcTbParams(waveform_sample_interval_s=50e-12, conversions=1),
        raw_path=raw_path,
        signal_names={name: "time" if name == "time" else name for name in values},
    )
    assert result.daq.bout[0, 0] == expected_bit
    np.testing.assert_array_equal(result.daq.bout[0, 1:], np.zeros(16, dtype=np.uint8))


def test_adc_logic_capture_includes_last_conversion_tail(tmp_path: Path) -> None:
    (tmp_path / "original.raw").touch()
    times = np.arange(8626) * 25e-12
    names = waveform_net_names(AdcNets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
    values = {name: np.zeros_like(times) for name in names}
    values["time"] = times
    for cycle in range(3):
        start = cycle * 4000
        values["seq_init"][start : start + 100] = 1.2
        values["seq_logic"][start + 75 : start + 100] = 1.2
        for bit in range(17 if cycle < 2 else 1):
            comp = start + 600 + bit * 200
            values["seq_comp"][comp : comp + 175] = 1.2
            if cycle < 2 and bit < 16:
                values["seq_logic"][comp + 175 : comp + 200] = 1.2
    for cycle in range(2):
        # Final output resolves after next INIT LOGIC, then changes at next B0.
        # Production decode must retain the earlier LOGIC value.
        begin = (cycle + 1) * 4000 + 200
        end = (cycle + 1) * 4000 + 600
        values["comp_out"][begin:end] = 1.2
        values["comp_out"][end] = 0.3
    result = convert_raw_adc_to_measurement(
        TranResult("tran", values, {}),
        params=AdcTbParams(waveform_sample_interval_s=50e-12, conversions=2),
        raw_path=tmp_path / "original.raw",
        signal_names={name: "time" if name == "time" else name for name in values},
    )
    assert result.param.conversions == 2
    np.testing.assert_array_equal(result.daq.bout[:, :16], np.zeros((2, 16)))
    np.testing.assert_array_equal(result.daq.bout[:, 16], [0, 0])
    np.testing.assert_array_equal(result.wave.conversion_index, [0, 1])
    assert result.info.readbacks["final_decision_time_reference"] == "next_init_seq_logic_rising_threshold"
    (tmp_path / "truncated.raw").touch()
    # Next COMP is unnecessary for production decode once next INIT LOGIC is saved.
    truncated = convert_raw_adc_to_measurement(
        TranResult("tran", {name: value[:8400] for name, value in values.items()}, {}),
        params=AdcTbParams(waveform_sample_interval_s=50e-12, conversions=2),
        raw_path=tmp_path / "truncated.raw",
        signal_names={name: "time" if name == "time" else name for name in values},
    )
    np.testing.assert_array_equal(truncated.daq.bout, result.daq.bout)


def test_adc_continuous_records_require_next_init_logic(tmp_path: Path) -> None:
    """Sample B16 at next INIT LOGIC and exclude the final unavailable capture."""
    params = AdcTbParams(
        waveform_sample_interval_s=50e-12,
        conversions=2,
        symbol_rate=1.6e9,
        seq_init_pattern="1111" + "0" * 156,
        seq_samp_pattern="0000" + "1" * 24 + "0" * 132,
        seq_comp_pattern="0" * 28 + "11111100" * 16 + "1111",
        seq_logic_pattern="0001" + "0" * 24 + "00000010" * 16 + "0000",
    )
    ticks = np.arange(16_001)
    times_s = ticks * 12.5e-12
    raw_names = waveform_net_names(AdcNets) | {"i(vdd_a)", "i(vdd_d)", "i(vdd_dac)"}
    values = {name: np.zeros_like(times_s) for name in raw_names}
    values["time"] = times_s
    for name in ("init", "samp", "comp", "logic"):
        pattern = np.array([int(bit) for bit in getattr(params, f"seq_{name}_pattern")])
        values[f"seq_{name}"] = 1.2 * pattern[(ticks // 50) % 160]
    # B16 only resolves late in its shortened evaluation. Its output changes
    # after reset, before the old extrapolated 101.175 ns capture point.
    for offset in (0, 8_000):
        values["comp_out"][(ticks >= offset + 7_994) & (ticks < offset + 8_020)] = 1.2
    raw_path = tmp_path / "netlist.raw"
    raw_path.touch()
    measurement = convert_raw_adc_to_measurement(
        TranResult("tran", values, {}),
        params=params,
        raw_path=raw_path,
        signal_names={name: "time" if name == "time" else name for name in values},
    )
    assert measurement.param.conversions == 1
    np.testing.assert_array_equal(measurement.daq.bout[:, :16], np.zeros((1, 16)))
    np.testing.assert_array_equal(measurement.daq.bout[:, 16], [0])
    np.testing.assert_array_equal(measurement.wave.conversion_index, [0])
    assert measurement.info.readbacks["unavailable_logic_conversions_json"] == "[1]"
    assert measurement.wave.voltage["comp_out"].shape == (1, len(measurement.wave.time_s))
    assert measurement.wave.time_s[-1] > 100e-9


def test_comp_waveform_conversion_writes_shared_hdf5(tmp_path: Path) -> None:
    params = CompTbParams(
        waveform_sample_interval_s=500e-12,
        comp=CompParams(diffpair_w=31),
        vin_diff_values_v=(-100e-6, 0.0, 100e-6),
        conversions=2,
    )
    time_step_s = 0.5e-9
    cycle_s = 40e-9
    trial_count = 6
    times_s = np.arange(0.0, trial_count * cycle_s + time_step_s / 2.0, time_step_s)
    decisions = np.asarray([0, 0, 0, 1, 1, 1], dtype=np.uint8)
    clock = np.zeros_like(times_s)
    comp_difference = np.zeros_like(times_s)
    output_difference = np.zeros_like(times_s)
    previous_sign = -1.0
    for trial, decision in enumerate(decisions):
        start_s = trial * cycle_s
        eval_start_s = start_s + 10e-9
        stop_s = start_s + cycle_s
        active = (times_s >= eval_start_s) & (times_s < stop_s)
        clock[active] = 1.2
        sign = 1.0 if decision else -1.0
        resolved = (times_s >= eval_start_s + 2e-9) & (times_s < stop_s)
        comp_difference[resolved] = sign
        output_difference[(times_s >= start_s) & (times_s < eval_start_s + 2e-9)] = previous_sign
        output_difference[resolved] = sign
        previous_sign = sign

    values = {
        "time": times_s,
        "vin_p": np.full_like(times_s, 0.8),
        "vin_n": np.full_like(times_s, 0.8),
        "clock": clock,
        "vout_p": 0.6 + output_difference / 2.0,
        "vout_n": 0.6 - output_difference / 2.0,
        "comp_p": 0.6 + comp_difference / 2.0,
        "comp_n": 0.6 - comp_difference / 2.0,
        "i(vdd)": np.full_like(times_s, -10e-6),
    }
    signal_names = {
        "time": "time",
        "inp": "vin_p",
        "inn": "vin_n",
        "clk": "clock",
        "outp": "vout_p",
        "outn": "vout_n",
        "latch_p": "comp_p",
        "latch_n": "comp_n",
        "i(vdd)": "i(vdd)",
    }
    raw_path = tmp_path / "netlist.raw"
    raw_path.touch()
    h.pdk.set_default(tsmc65.pdk_logic)
    compiled_tb = CompTb(params)
    h.pdk.compile(compiled_tb)

    h5_path = tmp_path / "comp.h5"
    expected = convert_raw_comp_to_measurement(
        TranResult("tran", values, {}),
        params=params,
        raw_path=raw_path,
        signal_names={raw: alias for alias, raw in signal_names.items()},
    )
    write_measurement(h5_path, expected)
    measurement = read_measurement(h5_path)

    assert isinstance(measurement, MeasCompInt)
    assert isinstance(measurement.wave, CompIntWave)
    assert measurement.param == params
    assert measurement.info.readbacks["raw_format"] == "spectre_nutbin"
    assert measurement.info.readbacks["vdd_active_average_power_w"] == pytest.approx(12e-6)
    assert measurement.info.readbacks["energy_per_decision_j"] == pytest.approx(480e-15)
    np.testing.assert_allclose(measurement.daq.vin_diff_v, [-100e-6, -100e-6, 0.0, 0.0, 100e-6, 100e-6])
    np.testing.assert_array_equal(measurement.daq.decision, decisions)
    np.testing.assert_array_equal(measurement.wave.trial_index, np.arange(6))
    assert measurement.wave.voltage["clk"].shape == (6, 80)
    np.testing.assert_allclose(measurement.wave.current["vdd"], 10e-6)


def _adc_names(view):
    from flow.adc.sim import AdcTb, AdcTbParams, adc_signal_names

    path = None if view == "hdl21gen" else Path(__file__).resolve().parents[1] / "adc/fixtures" / f"{view}_ports.scs"
    params = AdcTbParams(
        waveform_sample_interval_s=50e-12, view=view, pex_cell="" if view == "hdl21gen" else "adc_12b_17step"
    )
    return adc_signal_names(AdcTb(params, pex_netlist=path), view)


def test_frida2_rc_waveforms_use_device_terminal_nodes() -> None:
    names = {alias: raw for raw, alias in _adc_names("frida2").items()}
    legacy = {alias: raw for raw, alias in _adc_names("frida1").items()}
    assert names["vdac_p"] == "xtop.xadc.N_VDAC_P_XXsampswitch_p/MM0_d"
    assert names["dac_state_p[0]"].startswith("xtop.xadc.N_DAC_STATE_P_MAIN<0>_")
    assert legacy["dac_state_p[0]"].startswith("xtop.xadc.N_DAC_STATE_P_MAIN<15>_")
    assert names["dac_state_p[0]"].split("/", 1)[1] == legacy["dac_state_p[0]"].split("/", 1)[1]


@pytest.mark.parametrize("view", ("frida1", "frida2"))
def test_extracted_waveforms_cover_every_dac_stage_and_comparator_nodes(view):
    names = {alias: raw for raw, alias in _adc_names(view).items()}
    assert len(names) == len(set(names.values()))
    for side in ("p", "n"):
        for kind in ("", "_diff"):
            for stage in range(16):
                for family in ("state", "botplate"):
                    node = names[f"dac_{family}_{side}{kind}[{stage}]"]
                    assert f"<{stage if view == 'frida2' else 15 - stage}>_" in node
    assert names["comp.latch_p"].endswith("XXLATCH/MMM4_d")
    assert names["comp.latch_n"].endswith("XXLATCH/MMM3_d")
    assert names["comp.input_p_drain"].endswith("XXLATCH/MMM1_d")
    assert names["comp.input_n_drain"].endswith("XXLATCH/MMM2_d")


def test_generated_adc_map_covers_all_sixteen_capacitor_stages():
    names = _adc_names("hdl21gen")
    for side in ("p", "n"):
        for stage in range(16):
            assert names[f"xtop.xadc.dac_state_{side}_{stage}"] == f"dac_state_{side}[{stage}]"
            assert names[f"xtop.xadc.dac_botplate_{side}_{stage}"] == f"dac_botplate_{side}[{stage}]"
    assert not any("c16_" in alias for alias in names.values())


@pytest.mark.parametrize("fault", ("coarse", "nonfinite", "shape", "duplicate_alias", "unmapped", "missing"))
def test_converters_reject_invalid_transients_before_decoding(tmp_path, fault):
    from flow.comp.sim import CompTbParams

    times = np.arange(4) * 10e-12
    data = {"time": times, "raw": np.zeros(4)}
    names = {"time": "time", "raw": "vin_p"}
    if fault == "coarse":
        data["time"] = times * 2
    elif fault == "nonfinite":
        data["raw"][1] = np.nan
    elif fault == "shape":
        data["raw"] = np.zeros(3)
    elif fault == "duplicate_alias":
        names["raw"] = "time"
    elif fault == "unmapped":
        data["extra"] = np.zeros(4)
    else:
        names["missing"] = "vin_n"
    result = TranResult("tran", data, {})
    for convert, params in (
        (convert_raw_adc_to_measurement, AdcTbParams()),
        (convert_raw_comp_to_measurement, CompTbParams()),
    ):
        with pytest.raises(ValueError, match="Invalid transient"):
            convert(result, params=params, raw_path=tmp_path / "unused.raw", signal_names=names)


def test_conversion_bodies_contain_no_inline_raises():
    import ast
    import inspect

    for convert in (convert_raw_adc_to_measurement, convert_raw_comp_to_measurement):
        assert not any(isinstance(node, ast.Raise) for node in ast.walk(ast.parse(inspect.getsource(convert))))


def test_raw_step_validation_accepts_spectre_strobe_jitter_but_rejects_coarser_data():
    from flow.circuit.results import _is_valid_conversion

    # Observed adjacent timestamps from a 10 ps Spectre strobe-only run.
    times = np.array([3.164999925451418e-8, 3.166000000000151e-8])
    names = {"time": "time", "raw": "vin_p"}
    result = TranResult("tran", {"time": times, "raw": np.zeros(2)}, {})
    assert _is_valid_conversion(result, names, 10e-12)
    result = TranResult("tran", {"time": np.array([0.0, 10.1e-12]), "raw": np.zeros(2)}, {})
    assert not _is_valid_conversion(result, names, 10e-12)
