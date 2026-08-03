"""Software-only tests for the named ADC simulation campaigns."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import hdl21 as h
import pytest

from flow.scans.params import AdcTbParams

from . import sim


def test_named_simulation_targets_are_explicit() -> None:
    """Keep the command-line target set small, stable, and searchable."""

    assert sim.TARGETS == (
        "frida65a_noise_vs_rate",
        "hdl21gen_noise_vs_rate",
    )
    assert all(callable(getattr(sim, name)) for name in sim.TARGETS)


@pytest.mark.parametrize(
    ("target_name", "view"),
    [
        ("frida65a_noise_vs_rate", "frida65a"),
        ("hdl21gen_noise_vs_rate", "hdl21gen"),
    ],
)
def test_named_campaigns_expand_to_the_expected_matrix(
    monkeypatch: pytest.MonkeyPatch,
    target_name: str,
    view: str,
) -> None:
    """Expand every public campaign into complete parameters without Spectre."""

    calls: list[dict[str, Any]] = []

    def record_case(params: AdcTbParams, **kwargs: Any) -> None:
        calls.append({"params": params, **kwargs})

    monkeypatch.setattr(sim, "_CHECK_MODE", False)
    monkeypatch.setattr(sim, "_run_spectre_case", record_case)
    getattr(sim, target_name)()

    expected_names = tuple(f"{rate}msps_cm600mv_dc50mv" for rate in (10, 6, 2))
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
        assert params.conversions == 20
        assert isinstance(params.vin_diff, h.Vdc.Params)
        assert float(params.vin_diff.dc) == pytest.approx(0.05)
        assert float(params.vin_cm.dc) == pytest.approx(0.6)
        assert float(params.seq_logic_phase_delay_symbols) == pytest.approx(2.0)


def test_spectre_cases_reject_more_than_one_hundred_conversions(tmp_path: Path) -> None:
    """Keep every production transient bounded to at most 100 conversions."""

    with pytest.raises(ValueError, match="limited to 100 conversions"):
        sim._run_spectre_case(
            AdcTbParams(conversions=101),
            view="hdl21gen",
            case_dir=tmp_path / "too-long",
            check=False,
            execute=False,
        )


def test_pex_external_module_preserves_extracted_positional_pin_order() -> None:
    """Pin the irregular Calibre port order rather than sorting logical buses."""

    ports = sim.FRIDA65A_PEX_PORTS
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
    assert [port.name for port in sim.Frida65aPexAdc.port_list] == list(ports)
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

    monkeypatch.setattr(sim, "set_pdk", lambda _: None)
    monkeypatch.setattr(sim, "AdcTb", lambda params, selected_view: h.Module(name="TestTb"))
    monkeypatch.setattr(sim.h.pdk, "compile", lambda module: module)
    monkeypatch.setattr(sim, "write_sim_netlist", record_deck)

    params = AdcTbParams(conversions=3)
    sim._run_spectre_case(
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
    sim._run_spectre_case(
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
    sim._run_spectre_case(
        AdcTbParams(symbol_rate=160e6, conversions=3),
        view=view,
        case_dir=tmp_path / "slow",
        check=False,
        execute=False,
    )
    slow_text = "\n".join(
        attr.text for attr in written["input.scs"].attrs if isinstance(attr, h.Literal)
    )
    assert "strobeperiod=5e-11 strobeoutput=strobeonly" in slow_text


def test_spectre_commands_wait_for_a_license(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Queue check and production runs instead of failing on license pressure."""

    commands: list[list[str]] = []
    monkeypatch.setattr(sim, "set_pdk", lambda _: None)
    monkeypatch.setattr(sim, "AdcTb", lambda params, selected_view: h.Module(name="TestTb"))
    monkeypatch.setattr(sim.h.pdk, "compile", lambda module: module)
    monkeypatch.setattr(sim, "write_sim_netlist", lambda sim_input, path, compact: path.write_text(""))
    monkeypatch.setattr(sim.shutil, "which", lambda command: "/usr/bin/spectre")
    monkeypatch.setattr(
        sim.subprocess,
        "run",
        lambda command, **kwargs: commands.append(command),
    )
    monkeypatch.setattr(
        sim,
        "convert_spectre_adc_raw_to_h5",
        lambda raw_path, h5_path, **kwargs: h5_path,
    )

    sim._run_spectre_case(
        AdcTbParams(conversions=1),
        view="hdl21gen",
        case_dir=tmp_path / "case",
        check=True,
        execute=True,
    )

    assert len(commands) == 2
    for command in commands:
        timeout_index = command.index("+lqtimeout")
        assert command[timeout_index + 1] == "3600"
