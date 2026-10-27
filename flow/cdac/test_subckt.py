"""Software-only tests of the CDAC netlist: both sides' drivers and plates."""

import hdl21 as h
import pytest
from pydantic import ValidationError

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


def _chain(module, bottom) -> list[str]:
    """The inverters from a bottom plate back to the state that drives it: their cells, last first."""

    def key(net):
        # a bus bit is a new slice each time it is taken: by its bus and index
        return (net.parent.name, net.index) if hasattr(net, "parent") else net.name

    cells, net = [], bottom
    while True:
        driver = next((i for i in module.instances.values() if "Y" in i.conns and key(i.conns["Y"]) == key(net)), None)
        if driver is None:
            return cells
        cells.append(driver.of.name)
        net = driver.conns["A"]


def test_each_stage_drives_its_main_plate_with_its_state_and_its_difference_plate_inverted():
    """A buffer of the stage's state onto its main plate, an inverter onto its difference plate,
    the last inverter of each at the stage's drive."""
    module = cdac.netlist(PARAMS)
    dac = PARAMS.dac
    for side in "pn":
        state = getattr(module, f"dac_state_{side}")
        for stage, strength in enumerate(dac.driver.strengths):
            main = _chain(module, getattr(module, f"dac_botplate_{side}")[stage])
            diff = _chain(module, getattr(module, f"dac_botplate_{side}_diff")[stage])
            assert len(main) % 2 == 0 and len(diff) % 2 == 1
            assert main[0] == diff[0] == f"inv_x{strength}()"  # an external cell call
        assert not any(name.startswith("xcapdriver") for name in module.instances) and state.width == 3
    for side in "pn":
        top = getattr(module, f"vdac_{side}")
        for kind, plates in (("main", dac.main_f), ("diff", dac.diff_f)):
            for stage, plate in enumerate(plates):
                name = f"c{kind}_{side}_{stage}"
                # no capacitor where the array has no plate
                if plate == 0:
                    assert name not in module.instances
                    continue
                cap = module.instances[name]
                # a varying FMOM leaf at the plate's extracted value, its shield on the DAC's ground
                assert cap.of.cap.of.params.c.text.startswith(f"{plate:.9g}*(1 + mom_pelgrom")
                assert cap.conns["PLUS"].index == stage and cap.conns["MINUS"] is top
                assert cap.conns["BULK"] is module.vss_dac
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
    for fields in ({"main_f": dac.main_f[:2]}, {"diff_f": (0.0, -1e-15, 0.0)}, {"weights": (1, 2)}):
        with pytest.raises(ValidationError):
            _Dac(**{**dac.__dict__, **fields})
    with pytest.raises(ValidationError):
        cdac.Params(dac=dac, adc_bits=0)
    assert cdac.Params() == PARAMS


def test_each_plate_varies_at_its_centroid_and_a_wrong_placement_is_refused():
    dac = PARAMS.dac
    placed = tuple((10.0 * stage, -5.0) for stage in range(3))
    params = cdac.Params(
        dac=_Dac(
            driver=dac.driver,
            main_f=dac.main_f,
            diff_f=dac.diff_f,
            parasitic_f=dac.parasitic_f,
            main_p_um=placed,
            diff_p_um=placed,
            main_n_um=tuple((-x, y) for x, y in placed),
            diff_n_um=tuple((-x, y) for x, y in placed),
        ),
        adc_bits=10,
    )
    module = cdac.netlist(params)
    assert "mom_gradient*(20*mom_gx + -5*mom_gy)" in module.instances["cmain_p_2"].of.cap.of.params.c.text
    assert "mom_gradient*(-20*mom_gx + -5*mom_gy)" in module.instances["cmain_n_2"].of.cap.of.params.c.text
    with pytest.raises(ValidationError):
        _Dac(driver=dac.driver, main_f=dac.main_f, diff_f=dac.diff_f, parasitic_f=0.0, main_p_um=placed[:2])
