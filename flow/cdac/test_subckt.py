"""Software-only tests of the CDAC netlist: both sides' drivers and plates."""

import hdl21 as h
import pytest

from flow import cdac
from flow.capdriver.subckt import CapDriverParams

from .params import _Dac

PARAMS = cdac.Params(
    dac=_Dac(
        driver=CapDriverParams(n_stages=3, strengths=(4, 2, 1)),
        main_f=(400e-15, 200e-15, 100e-15),
        diff_f=(0.0, 10e-15, 90e-15),
        parasitic_f=250e-15,
    ),
    adc_bits=10,
)


def test_both_sides_switch_their_plates_through_a_main_and_a_difference_driver():
    module = cdac.netlist(PARAMS)
    dac = PARAMS.dac
    drivers = {name: inst for name, inst in module.instances.items() if name.startswith("xcapdriver_")}
    assert sorted(drivers) == [f"xcapdriver_{side}_{kind}" for side in "np" for kind in ("diff", "main")]
    for side in "pn":
        main, diff = drivers[f"xcapdriver_{side}_main"], drivers[f"xcapdriver_{side}_diff"]
        assert main.conns["dac_state"] is diff.conns["dac_state"] is getattr(module, f"dac_state_{side}")
        assert main.conns["dac_drive_invert"] is module.dac_invert
        assert diff.conns["dac_drive_invert"] is module.dac_diffcaps
        top = getattr(module, f"vdac_{side}")
        for kind, plates in (("main", dac.main_f), ("diff", dac.diff_f)):
            for stage, plate in enumerate(plates):
                name = f"c{kind}_{side}_{stage}"
                # no capacitor where the array has no plate
                if plate == 0:
                    assert name not in module.instances
                    continue
                cap = module.instances[name]
                assert float(cap.of.params.c) == pytest.approx(plate)
                assert cap.conns["p"].index == stage and cap.conns["n"] is top
        assert float(module.instances[f"cparasitic_{side}"].of.params.c) == pytest.approx(dac.parasitic_f)
    h.elaborate(module)


def test_the_buses_have_a_bit_per_stage_and_the_nets_keep_their_order():
    module = cdac.netlist(PARAMS)
    assert list(module.ports) == list(cdac.Nets.signals)
    widths = {name: port.width for name, port in module.ports.items()}
    assert {name for name, width in widths.items() if width == 3} == {
        "dac_state_p",
        "dac_state_n",
        "dac_botplate_p",
        "dac_botplate_n",
        "dac_botplate_p_diff",
        "dac_botplate_n_diff",
    }


def test_mismatched_or_negative_capacitances_are_refused():
    dac = PARAMS.dac
    short = cdac.Params(
        dac=_Dac(driver=dac.driver, main_f=dac.main_f[:2], diff_f=dac.diff_f, parasitic_f=0.0), adc_bits=10
    )
    negative = cdac.Params(
        dac=_Dac(driver=dac.driver, main_f=dac.main_f, diff_f=(0.0, -1e-15, 0.0), parasitic_f=0.0), adc_bits=10
    )
    for params in (short, negative):
        assert not cdac.valid(params)
        with pytest.raises(ValueError):
            cdac.netlist(params)
    assert cdac.valid(PARAMS) and not cdac.valid(cdac.Params(dac=dac, adc_bits=0))
