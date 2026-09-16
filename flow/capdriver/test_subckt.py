"""Software-only tests of the generic driver and capacitor-array integration."""

import io
from dataclasses import replace

import hdl21 as h
import pytest

from flow.caparray.subckt import CapArray, CapArrayConfig, CapArrayParams

from .subckt import CapDriver, CapDriverParams, ClockXor, ClockXorParams


@pytest.mark.parametrize("band", [1, 2, 4])
def test_clock_xor_interface(band):
    call = ClockXor(ClockXorParams(drive_band=band))
    assert call.module is ClockXor
    assert ClockXor.domain == "generic"
    assert ClockXor.name == "clock_xor"
    assert tuple(ClockXor.ports) == ("A", "B", "Y", "VDD", "VSS")
    assert call.params.drive_band == band


@pytest.mark.parametrize("band", [0, -1, 3, 8, True, 1.5])
def test_clock_xor_rejects_invalid_bands(band):
    with pytest.raises(ValueError):
        ClockXorParams(drive_band=band)


@pytest.mark.parametrize("n_stages", [1, 2, 3, 4, 5, 16, 19])
def test_default_bands_and_stage_wiring(n_stages):
    module = CapDriver(CapDriverParams(n_stages=n_stages))
    assert tuple(module.ports) == ("dac_state", "dac_drive", "dac_drive_invert", "vdd", "vss")
    assert module.dac_state.width == module.dac_drive.width == n_stages
    assert module.dac_drive_invert.width == 1
    expected = (4, 4, 2, 2)[:n_stages] + (1,) * max(0, n_stages - 4)
    assert len(module.instances) == n_stages
    for stage, band in enumerate(expected):
        xor = module.instances[f"xor_{stage}"]
        assert xor.of.module is ClockXor
        assert xor.of.params.drive_band == band
        assert xor.conns["A"] is module.dac_drive_invert
        assert xor.conns["B"].parent is module.dac_state
        assert xor.conns["B"].index == stage
        assert xor.conns["Y"].parent is module.dac_drive
        assert xor.conns["Y"].index == stage
        assert xor.conns["VDD"] is module.vdd
        assert xor.conns["VSS"] is module.vss
    h.elaborate(module)


def test_custom_bands_and_generic_netlist():
    module = CapDriver(CapDriverParams(n_stages=3, strengths=(1, 4, 2)))
    assert tuple(inst.of.params.drive_band for inst in module.instances.values()) == (1, 4, 2)
    dest = io.StringIO()
    h.netlist(module, dest, fmt="spice")
    assert "dac_drive_invert dac_state_0 dac_drive_0 vdd vss" in dest.getvalue()
    assert "clock_xor" in dest.getvalue()


@pytest.mark.parametrize("technology", ["tsmc65", "tsmc28", "tower180"])
def test_compiled_driver_preserves_invert_and_state_pin_paths(technology):
    compiler = pytest.importorskip(f"pdk.{technology}.pdk_logic")
    module = CapDriver(CapDriverParams(n_stages=6))
    compiler.compile(module)
    for stage in range(6):
        xor = module.instances[f"xor_{stage}"]
        assert isinstance(xor.of, h.Module)
        assert xor.conns["A"] is module.dac_drive_invert
        assert xor.conns["B"].parent is module.dac_state
        assert xor.conns["B"].index == stage
        if technology == "tsmc65":
            for cell in xor.of.instances.values():
                assert cell.conns["A1"] is xor.of.A
                assert cell.conns["A2"] is xor.of.B
    dest = io.StringIO()
    h.netlist(module, dest, fmt="spice")
    assert "clock_xor" not in dest.getvalue()


def test_public_driver_api_isolates_pdk_compilation():
    compilers = [
        pytest.importorskip(f"pdk.{technology}.pdk_logic") for technology in ("tsmc65", "tower180", "tsmc28", "tsmc65")
    ]
    params = CapDriverParams(n_stages=3, strengths=(1, 2, 4))
    previous = []
    for compiler in compilers:
        module = CapDriver(params)
        assert all(module is not other for other in previous)
        assert all(inst.of.module is ClockXor for inst in module.instances.values())
        compiler.compile(module)
        domain = compiler.__name__.split(".")[1]
        assert {cell.of.module.domain for xor in module.instances.values() for cell in xor.of.instances.values()} == {
            domain
        }
        previous.append(module)
    # Earlier compilations must remain unchanged by later requests.
    assert previous[0].xor_0.of.cell_0.of.module.domain == "tsmc65"
    assert {cell.of.module.domain for cell in previous[1].xor_0.of.instances.values()} == {"tower180"}


@pytest.mark.parametrize("kind", ["driver", "adc", "adc_tb"])
def test_public_api_returns_unmodified_hierarchy_after_mutation(kind):
    """Exercise production hierarchy isolation even in CI without private PDKs."""
    from flow.adc.sim import AdcTb, AdcTbParams
    from flow.adc.subckt import Adc, AdcParams

    cases = {
        "driver": (CapDriver, CapDriverParams(n_stages=3), ()),
        "adc": (Adc, AdcParams(), ("xcapdriver_p_main",)),
        "adc_tb": (AdcTb, AdcTbParams(view="hdl21gen"), ("xadc", "xcapdriver_p_main")),
    }
    generator, params, path = cases[kind]
    first = generator(params)
    driver = first
    for name in path:
        driver = driver.instances[name].of
    # Model the in-place replacement performed by a PDK walker.
    replacement = h.Module(name="compiled_xor")
    for name in ClockXor.ports:
        replacement.add(h.Inout(name=name))
    driver.xor_0.of = replacement
    second = generator(params)
    second_driver = second
    for name in path:
        second_driver = second_driver.instances[name].of
    assert second is not first
    assert second_driver is not driver
    assert second_driver.xor_0.of.module is ClockXor


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_stages": 0},
        {"n_stages": -1},
        {"n_stages": 2, "strengths": ()},
        {"n_stages": 2, "strengths": (1,)},
        {"n_stages": 2, "strengths": (1, 2, 4)},
        {"n_stages": 2, "strengths": (1, 3)},
        {"n_stages": 2, "strengths": (0, 4)},
    ],
)
def test_invalid_driver_configuration(kwargs):
    with pytest.raises(ValueError):
        CapDriver(CapDriverParams(**kwargs))


def test_adc_passes_custom_bands_to_all_four_drivers():
    from flow.adc.subckt import Adc, AdcParams

    params = AdcParams(cdac=CapArrayConfig(driver_strengths=(1, 2, 4, 1) * 4))
    module = Adc(params)
    for side in ("p", "n"):
        for kind in ("main", "diff"):
            driver = module.instances[f"xcapdriver_{side}_{kind}"].of
            assert (
                tuple(inst.of.params.drive_band for inst in driver.instances.values()) == params.cdac.driver_strengths
            )
    with pytest.raises(ValueError):
        Adc(replace(params, cdac=replace(params.cdac, driver_strengths=(3,) * 16)))


def test_passive_array_has_no_driver_dependency():
    module = CapArray(CapArrayParams(cdac=CapArrayConfig(weights=(1,) * 16)))
    assert all(inst.of is not ClockXor for inst in module.instances.values())
    assert not {"vdd", "dac_state", "dac_drive_invert"} & module.ports.keys()
