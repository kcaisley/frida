"""Software-only tests for the named HDL21 ADC simulation campaigns."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import hdl21 as h
import pytest

from flow.scans.params import AdcTbParams

from . import testbench


def test_named_simulation_targets_are_explicit() -> None:
    """Keep the command-line target set small, stable, and searchable."""

    assert testbench.TARGETS == (
        "frida65a_noise_vs_rate_cm",
        "hdl21gen_noise_vs_rate_cm",
        "frida65a_noise_large_signal",
        "hdl21gen_noise_large_signal",
    )
    assert all(callable(getattr(testbench, name)) for name in testbench.TARGETS)


@pytest.mark.parametrize(
    ("target_name", "view", "large_signal"),
    [
        ("frida65a_noise_vs_rate_cm", "frida65a", False),
        ("hdl21gen_noise_vs_rate_cm", "hdl21gen", False),
        ("frida65a_noise_large_signal", "frida65a", True),
        ("hdl21gen_noise_large_signal", "hdl21gen", True),
    ],
)
def test_named_campaigns_expand_to_the_expected_matrix(
    monkeypatch: pytest.MonkeyPatch,
    target_name: str,
    view: str,
    large_signal: bool,
) -> None:
    """Expand every public campaign into complete parameters without Spectre."""

    calls: list[dict[str, Any]] = []

    def record_case(params: AdcTbParams, **kwargs: Any) -> None:
        calls.append({"params": params, **kwargs})

    monkeypatch.setattr(testbench, "_CHECK_MODE", False)
    monkeypatch.setattr(testbench, "_run_spectre_case", record_case)
    getattr(testbench, target_name)()

    expected_names = (
        tuple(f"{rate}msps_cm600mv_sine1000mvpp" for rate in (10, 5, 1))
        if large_signal
        else tuple(
            f"{rate}msps_cm{common_mode_mv}mv_dc50mv"
            for rate in (10, 5, 1)
            for common_mode_mv in (200, 600, 1000)
        )
    )
    assert tuple(call["case_dir"].name for call in calls) == expected_names
    assert all(call["view"] == view for call in calls)
    assert all(call["check"] is False for call in calls)
    assert all(call["execute"] is True for call in calls)

    alternating = tuple(int(bit) for bit in "0101010101010101")
    for call in calls:
        params = call["params"]
        assert params.dac_astate_p == alternating
        assert params.dac_astate_n == alternating
        assert params.dac_bstate_p == (0,) * 16
        assert params.dac_bstate_n == (0,) * 16
        if large_signal:
            assert params.conversions == 1_000
            assert isinstance(params.vin_diff, h.Vsin.Params)
            assert float(params.vin_diff.voff) == pytest.approx(0.0)
            assert float(params.vin_diff.vamp) == pytest.approx(0.5)
            assert float(params.vin_diff.freq) == pytest.approx(9_998.770151)
            assert float(params.vin_cm.dc) == pytest.approx(0.6)
        else:
            assert params.conversions == 100
            assert isinstance(params.vin_diff, h.Vdc.Params)
            assert float(params.vin_diff.dc) == pytest.approx(0.05)


def test_pex_external_module_preserves_extracted_positional_pin_order() -> None:
    """Pin the irregular Calibre port order rather than sorting logical buses."""

    ports = testbench.FRIDA65A_PEX_PORTS
    assert len(ports) == 84
    assert len(set(ports)) == len(ports)
    assert ports[:20] == (
        "vdd_a",
        "vin_p",
        "vss_a",
        "dac_mode",
        "dac_diffcaps",
        "seq_init",
        "en_init",
        "seq_samp",
        "en_samp_p",
        "en_samp_n",
        "seq_comp",
        "en_comp",
        "seq_update",
        "en_update",
        "comp_out",
        "vin_n",
        "vdd_d",
        "vss_d",
        "vdd_dac",
        "vss_dac",
    )
    # Fingerprint the complete, intentionally irregular Calibre declaration.
    assert hashlib.sha256("\0".join(ports).encode()).hexdigest() == (
        "f6789370c748077856692f87bb0971751777fdd2f913b99c0ba9e09860a5cb25"
    )
    assert [port.name for port in testbench.Frida65aPexAdc.port_list] == list(ports)
    for bus_name in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n"):
        assert {name for name in ports if name.startswith(f"{bus_name}_")} == {
            f"{bus_name}_{bit}" for bit in range(16)
        }


@pytest.mark.parametrize("view", ["frida65a", "hdl21gen"])
def test_check_and_production_decks_have_distinct_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    view: str,
) -> None:
    """Keep checks short and noiseless while production enables transient noise."""

    written: dict[str, Any] = {}

    def record_deck(sim: Any, path: Path, *, compact: bool) -> None:
        assert compact is True
        written[path.name] = sim

    monkeypatch.setattr(testbench, "set_pdk", lambda _: None)
    monkeypatch.setattr(testbench, "AdcTb", lambda params, selected_view: h.Module(name="TestTb"))
    monkeypatch.setattr(testbench.h.pdk, "compile", lambda module: module)
    monkeypatch.setattr(testbench, "write_sim_netlist", record_deck)

    params = AdcTbParams(conversions=3)
    testbench._run_spectre_case(
        params,
        view=view,
        case_dir=tmp_path / "production",
        check=False,
        execute=False,
    )
    assert set(written) == {"input.scs"}
    production_text = "\n".join(
        attr.text for attr in written["input.scs"].attrs if isinstance(attr, h.Literal)
    )
    assert "rawfmt=nutascii" in production_text
    assert "tran tran stop=4.8e-07" in production_text
    assert "strobeperiod=3.90625e-11 strobeoutput=strobeonly" in production_text
    assert "noisefmin=2083333.33333 noisefmax=25G noiseseed=1" in production_text
    assert "dyn_setuphold" not in production_text

    written.clear()
    testbench._run_spectre_case(
        params,
        view=view,
        case_dir=tmp_path / "check",
        check=True,
        execute=False,
    )
    assert set(written) == {"checks.scs", "input.scs"}
    check_text = "\n".join(
        attr.text for attr in written["checks.scs"].attrs if isinstance(attr, h.Literal)
    )
    capture_text = "\n".join(
        attr.text for attr in written["input.scs"].attrs if isinstance(attr, h.Literal)
    )
    assert "tran tran stop=1e-07" in check_text
    assert "dyn_setuphold" in check_text
    assert "dyn_subcktpwr" in check_text
    assert "static_erc" in check_text
    assert "saveOptions options save=selected" in check_text
    assert "save xtop.vin_p" in check_text
    assert "tran tran stop=1e-07" in capture_text
    assert "strobeperiod=3.90625e-11 strobeoutput=strobeonly" in check_text
    assert "strobeperiod=3.90625e-11 strobeoutput=strobeonly" in capture_text
    assert "noisefmin" not in check_text
    assert "noisefmin" not in capture_text

    save_literal = next(
        attr.text
        for attr in written["input.scs"].attrs
        if isinstance(attr, h.Literal) and attr.text.startswith("save ")
    )
    saved_signals = save_literal.replace("\\\n", " ").split()[1:]
    assert len(saved_signals) >= 30
    assert len(saved_signals) == len(set(saved_signals))

    written.clear()
    testbench._run_spectre_case(
        AdcTbParams(symbol_rate=160e6),
        view=view,
        case_dir=tmp_path / "slow",
        check=False,
        execute=False,
    )
    slow_text = "\n".join(
        attr.text for attr in written["input.scs"].attrs if isinstance(attr, h.Literal)
    )
    assert "strobeperiod=5e-11 strobeoutput=strobeonly" in slow_text
