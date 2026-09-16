"""Tests for ADC layout-runner netlist preparation."""

import io
from pathlib import Path
from types import SimpleNamespace

import hdl21 as h
import pytest
from hdl21.prefix import f

from flow.caparray.laygen import CapArrayLayoutParams, UnitLengthCapFamilyParams
from flow.caparray.subckt import CapArray, CapArrayConfig, CapArrayParams
from flow.util.netlist import omit_subcircuit, replace_subcircuit
from pdk.tsmc65.signoff import mom_lvs_device


def test_replace_subcircuit_renames_block_calls_and_top() -> None:
    source = ".subckt old_cap a b\n.ends old_cap\n.subckt old_adc a b\nXcap a b old_cap\n.ends old_adc\n"
    result = replace_subcircuit(
        source,
        old_top="old_adc",
        new_top="adc_12b_17step",
        old_block="old_cap",
        new_block=".subckt new_cap a b\nC0 a b 1f\n.ends new_cap\n",
    )
    assert ".subckt adc_12b_17step a b" in result
    assert "Xcap a b new_cap" in result
    assert "old_cap" not in result


def test_omit_subcircuit_removes_multiline_calls() -> None:
    source = ".subckt empty a b\n.ends empty\n.subckt top a b\nXkeep a b real\nXremove a\n+ b empty\n.ends top\n"
    result = omit_subcircuit(source, "empty")
    assert "empty" not in result
    assert "Xremove" not in result
    assert "Xkeep a b real" in result


def test_historical_mom_source_translates_pin15_to_stage_c0() -> None:
    params = CapArrayParams(
        cdac=CapArrayConfig(n_dac=2, n_extra=0, weights=(64, 1), unit_cap=0.8 * f),
        active_layers=(6,),
        unit_models=(mom_lvs_device(6, 5),),
    )
    module = CapArray(params)
    module.name = "caparray"
    netlist = io.StringIO()
    h.netlist(module, netlist, fmt="spice")
    reference = (
        ".subckt old_cap cap_botplate_diff<1> cap_botplate_diff<0>\n"
        "+ cap_botplate_main<1> cap_botplate_main<0> cap_shieldplate cap_topplate\n"
        ".ends old_cap\n.subckt old_adc top vss\n"
        "Xcap diff_first diff_last main_first main_last vss top old_cap\n.ends old_adc\n"
    )
    mapping = {name: name for name in module.ports}
    mapping.update(
        {
            f"cap_botplate_{kind}<{stage}>": f"cap_botplate_{kind}<{1 - stage}>"
            for kind in ("main", "diff")
            for stage in range(2)
        }
    )
    legacy = replace_subcircuit(
        reference,
        old_top="old_adc",
        new_top="adc",
        old_block="old_cap",
        new_block=netlist.getvalue(),
        pin_map=mapping,
    )
    assert "Xcap top vss main_first main_last diff_first diff_last caparray" in legacy
    assert module.main_0_0_m6.conns["MINUS"].name == "cap_botplate_main<0>"


@pytest.mark.parametrize("active,shield", [((6,), 5), ((6, 7), 5), ((5, 6, 7), 4)])
def test_frida2_runner_uses_c0_first_paired_template_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, active: tuple[int, ...], shield: int
) -> None:
    from flow.adc import layout

    reference = (
        ".subckt caparray_2layer_radix17 cap_botplate_diff<1> cap_botplate_diff<0>\n"
        "+ cap_botplate_main<1> cap_botplate_main<0> cap_shieldplate cap_topplate\n"
        ".ends caparray_2layer_radix17\n.subckt adc_12b_17step top vss\n"
        "Xcap diff_first diff_last main_first main_last vss top caparray_2layer_radix17\n"
        ".ends adc_12b_17step\n"
    )
    read_text = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda path, **kwargs: reference if path.name == "frida-2-template-c0.cdl" else read_text(path, **kwargs),
    )
    # Exercise netlist orchestration without reading or modifying a real template.
    monkeypatch.setattr(layout.db, "Layout", lambda: SimpleNamespace(read=lambda _path: None))
    monkeypatch.setattr(layout, "CapArrayLayout", lambda _params: None)
    monkeypatch.setattr(layout, "AdcLayout", lambda _params, **kwargs: None)
    monkeypatch.setattr(layout, "_write_top", lambda *_args: None)
    monkeypatch.setattr(layout, "run_signoff", lambda *_args: None)
    arrays = []

    def generate_array(params):
        module = CapArray(params)
        arrays.append(module)
        return module

    monkeypatch.setattr(layout, "CapArray", generate_array)
    result = layout._run_frida2(
        tmp_path / "run",
        target_name="frida2_test",
        params=CapArrayLayoutParams(
            cdac=CapArrayConfig(n_dac=2, n_extra=0, weights=(64, 1)),
            family=UnitLengthCapFamilyParams(),
            technology="tsmc65",
            route_layer=4,
            shield_layer=shield,
            active_layers=active,
            top_cell="new_caparray",
        ),
    )
    source = (result / "source.lvs.cdl").read_text()
    assert "Xcap top vss main_last main_first diff_last diff_first new_caparray" in source
    assert (result / "source.ideal.cdl").read_text() == source
    assert "ringfmom.cdl" in source
    assert f"ringfmom_{len(active)}layer" in source
    slope, intercept = {1: (0.17, 0.03), 2: (0.34, 0.06), 3: (0.51, 0.12)}[len(active)]
    assert float(arrays[0].main_0_0.of.params.c) == pytest.approx((slope * 51.72 + intercept) * 1e-15, abs=1e-27)
    assert float(arrays[0].diff_0_0.of.params.c) == pytest.approx((slope * 0.52 + intercept) * 1e-15, abs=1e-27)
    assert (result / "ringfmom.cdl").is_file()
    conductive = (result / "source.pex.cdl").read_text()
    assert "Xcap" not in conductive
    assert "ringfmom" not in conductive
