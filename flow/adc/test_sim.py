"""Software-only checks for the native HDL21 ADC simulation interface."""

import inspect
from io import StringIO

import hdl21 as h
import hdl21.sim as hs
import pytest

from flow.adc.subckt import Frida65aPexAdc

from . import sim


def test_adc_testbench_parameters_are_simulation_only() -> None:
    params = sim.AdcTbParams()

    assert params.view == "hdl21gen"
    assert float(params.vin_cm.dc) == pytest.approx(0.7)
    assert not hasattr(params, "temperature_c")
    assert not hasattr(params, "board_id")
    assert not hasattr(params, "campaign")
    assert not hasattr(params, "vdd_io")


@pytest.mark.parametrize("view", ("frida65a", "hdl21gen"))
def test_adc_testbench_generates_each_view(view: str) -> None:
    tb = sim.AdcTb(sim.AdcTbParams(view=view, conversions=1))

    assert isinstance(tb, h.Module)
    assert tb.xadc is not None
    assert tb.dac_astate_p.width == 16
    assert tb.vin.p is not None


def test_adc_transfer_staircase_has_151_codes() -> None:
    params = sim.AdcTbParams(
        symbol_rate=1.6e9,
        conversions=151,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
    )
    tb = sim.AdcTb(params)
    wave = tb.vvin_diff.of.params.wave

    assert isinstance(wave, h.Pwl)
    assert len(wave.points) == 302
    assert float(wave.points[0][1]) == pytest.approx(-0.75)
    assert float(wave.points[1][0]) == pytest.approx(len(params.seq_init_pattern) / float(params.symbol_rate) - 100e-12)
    assert float(wave.points[-1][1]) == pytest.approx(0.75)
    assert float(wave.points[-1][0]) == pytest.approx(
        params.conversions * len(params.seq_init_pattern) / float(params.symbol_rate)
    )


def test_adc_transfer_sweep_must_match_conversion_count() -> None:
    params = sim.AdcTbParams(
        conversions=2,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
    )

    with pytest.raises(ValueError, match="151 values, but conversions=2"):
        sim.AdcTb(params)


def test_extracted_adc_keeps_calibre_port_order() -> None:
    names = tuple(port.name for port in Frida65aPexAdc.port_list)

    assert len(names) == 84
    assert len(set(names)) == 84
    assert names[:5] == ("vdd_a", "vin_p", "vss_a", "dac_mode", "dac_diffcaps")


def test_supply_noise_testbench_repeats_independent_rail_networks() -> None:
    params = sim.AdcTbParams(
        view="frida65a",
        conversions=1,
        supply_series_resistance_ohm=1.0,
        supply_series_inductance_h=1e-9,
        supply_decoupling_capacitance_f=1e-12,
        supply_noise_rms_v=(1e-3, 0.0, 0.0),
        supply_noise_bandwidth_hz=25e9,
    )
    tb = sim.AdcTb(params)
    netlist = StringIO()

    h.netlist(tb, netlist, fmt="spectre")
    text = netlist.getvalue()

    for rail in ("vdd_a", "vdd_d", "vdd_dac"):
        assert float(getattr(tb, f"r{rail}").of.params.r) == pytest.approx(1.0)
        assert float(getattr(tb, f"l{rail}").of.params.l) == pytest.approx(1e-9)
        assert float(getattr(tb, f"c{rail}").of.params.c) == pytest.approx(1e-12)
    assert "vvdd_a (vdd_a_source vss) vsource dc=1.2 noisevec=[0 4e-17 25000000000 4e-17]" in text
    assert tb.vvdd_d.conns["p"] is tb.vdd_d_source
    assert tb.vvdd_dac.conns["p"] is tb.vdd_dac_source
    assert text.count("noisevec=") == 1


def test_adc_main_owns_the_nine_named_targets() -> None:
    source = inspect.getsource(sim.main)
    for name in (
        "frida65a_noise_vs_rate_check",
        "frida65a_noise_vs_rate",
        "frida65a_supply_noise_vs_rate",
        "frida65a_transfer_curve_check",
        "frida65a_transfer_curve",
        "hdl21gen_noise_vs_rate_check",
        "hdl21gen_noise_vs_rate",
        "hdl21gen_transfer_curve_check",
        "hdl21gen_transfer_curve",
    ):
        assert name in source
    assert "build/sim" not in source
