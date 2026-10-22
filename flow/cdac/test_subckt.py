"""Software-only tests of the CDAC netlist and its testbench."""

import io

import hdl21 as h
import pytest

from flow.capdriver.subckt import CapDriverParams

from .sim import CdacTb, CdacTbParams, cdac_signal_names, window_start_s
from .subckt import Cdac, CdacParams

DAC = CdacParams(
    driver=CapDriverParams(n_stages=3, strengths=(4, 2, 1)),
    main_f=(400e-15, 200e-15, 100e-15),
    diff_f=(0.0, 10e-15, 90e-15),
    parasitic_f=250e-15,
)


def test_both_sides_switch_their_plates_through_a_main_and_a_difference_driver():
    module = Cdac(DAC)
    drivers = {name: inst for name, inst in module.instances.items() if name.startswith("xcapdriver_")}
    assert sorted(drivers) == [f"xcapdriver_{side}_{kind}" for side in "np" for kind in ("diff", "main")]
    for side in "pn":
        main, diff = drivers[f"xcapdriver_{side}_main"], drivers[f"xcapdriver_{side}_diff"]
        assert main.conns["dac_state"] is diff.conns["dac_state"] is getattr(module, f"dac_state_{side}")
        assert main.conns["dac_drive_invert"] is module.dac_invert
        assert diff.conns["dac_drive_invert"] is module.dac_diffcaps
        top = getattr(module, f"vdac_{side}")
        for kind, plates in (("main", DAC.main_f), ("diff", DAC.diff_f)):
            for stage, plate in enumerate(plates):
                name = f"c{kind}_{side}_{stage}"
                # no capacitor where the array has no plate
                if plate == 0:
                    assert name not in module.instances
                    continue
                cap = module.instances[name]
                assert float(cap.of.params.c) == pytest.approx(plate)
                assert cap.conns["p"].index == stage and cap.conns["n"] is top
        assert float(module.instances[f"cparasitic_{side}"].of.params.c) == pytest.approx(DAC.parasitic_f)
    h.elaborate(module)


def test_mismatched_or_negative_capacitances_are_refused():
    with pytest.raises(ValueError):
        Cdac(CdacParams(driver=DAC.driver, main_f=DAC.main_f[:2], diff_f=DAC.diff_f, parasitic_f=0.0))
    with pytest.raises(ValueError):
        Cdac(CdacParams(driver=DAC.driver, main_f=DAC.main_f, diff_f=(0.0, -1e-15, 0.0), parasitic_f=0.0))


def test_the_testbench_switches_each_stage_up_and_back_in_its_turn():
    params = CdacTbParams(dac=DAC, adc_bits=10, window_s=2e-9, waveform_sample_interval_s=1e-12)
    tb = CdacTb(params)
    for stage in range(3):
        up, down = window_start_s(params, stage, True), window_start_s(params, stage, False)
        assert down - up == pytest.approx(params.window_s)
        p, n = tb.instances[f"vstate_p_{stage}"].of.params, tb.instances[f"vstate_n_{stage}"].of.params
        assert float(p.delay) == float(n.delay) == pytest.approx(up)
        assert (float(p.v1), float(p.v2), float(n.v1), float(n.v2)) == (0.0, 1.2, 1.2, 0.0)
        # high for one window, rise and width together
        assert float(p.width) + float(p.rise) == pytest.approx(params.window_s)
    dest = io.StringIO()
    h.netlist(tb, dest, fmt="spice")
    netlist = dest.getvalue()
    for raw in cdac_signal_names(3):
        if raw != "time":
            assert raw.removeprefix("xtop.") in netlist
