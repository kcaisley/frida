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

    assert set(sim.TARGETS) == {
        "frida65a_noise_vs_rate_netlists",
        "frida65a_noise_smoke",
        "frida65a_noise_vs_rate",
        "frida65a_transfer_curve_netlist",
        "frida65a_transfer_curve",
        "hdl21gen_noise_vs_rate_netlists",
        "hdl21gen_noise_smoke",
        "hdl21gen_noise_vs_rate",
        "hdl21gen_transfer_curve_netlist",
        "hdl21gen_transfer_curve",
    }
    assert all(callable(target) for target in sim.TARGETS.values())


def test_named_campaigns_expand_to_the_expected_matrix() -> None:
    """Expand the shared ADC campaign recipe into complete parameters."""

    cases = sim._noise_vs_rate_cases()
    expected_names = tuple(f"{rate}msps_cm700mv_dc50mv" for rate in (10, 6, 2))
    assert tuple(name for name, _params in cases) == expected_names

    alternating = tuple(int(bit) for bit in "0101010101010101")
    for _name, params in cases:
        assert params.dac_astate_p == alternating
        assert params.dac_astate_n == alternating
        assert params.dac_bstate_p == (0,) * 16
        assert params.dac_bstate_n == (0,) * 16
        assert params.conversions == 100
        assert isinstance(params.vin_diff, h.Vdc.Params)
        assert float(params.vin_diff.dc) == pytest.approx(0.05)
        assert float(params.vin_cm.dc) == pytest.approx(0.7)
        assert float(params.seq_logic_phase_delay_symbols) == pytest.approx(2.0)


def test_transfer_curve_uses_one_settled_conversion_per_10mv_step() -> None:
    """Cover the full reviewed transfer range in one simulation case."""

    ((name, params),) = sim._transfer_curve_cases()
    tokens = params.vin_diff.wave.split()
    times_s = tuple(float(value) for value in tokens[0::2])
    values_v = tuple(float(value) for value in tokens[1::2])

    assert name == "10msps_cm700mv_transfer"
    assert params.campaign == "adc_transfer"
    assert params.conversions == 151
    assert float(params.symbol_rate) == pytest.approx(1.6e9)
    assert float(params.vin_cm.dc) == pytest.approx(0.7)
    assert float(params.seq_logic_phase_delay_symbols) == pytest.approx(2.0)
    assert len(times_s) == 302
    assert times_s[0] == 0.0
    assert times_s[-1] == pytest.approx(24.16e-6)
    assert values_v[0] == pytest.approx(-0.75)
    assert values_v[-1] == pytest.approx(0.75)
    assert tuple(sorted(set(values_v))) == pytest.approx(tuple(step / 100.0 for step in range(-75, 76)))


def test_spectre_cases_reject_more_than_one_hundred_fifty_one_conversions(tmp_path: Path) -> None:
    """Bound every production transient while permitting the full transfer."""

    with pytest.raises(ValueError, match="limited to 151 conversions"):
        sim._prepare_spectre_case(
            AdcTbParams(conversions=152),
            view="hdl21gen",
            case_dir=tmp_path / "too-long",
            circuit_checks=False,
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
        assert {name for name in ports if name.startswith(f"{bus_name}_")} == {f"{bus_name}_{bit}" for bit in range(16)}


@pytest.mark.parametrize("view", ["frida65a", "hdl21gen"])
def test_smoke_and_production_decks_have_distinct_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    view: str,
) -> None:
    """Keep checks short and noiseless while production enables transient noise."""

    written: dict[str, Any] = {}

    def record_deck(sim: Any, path: Path) -> None:
        written[path.name] = sim

    monkeypatch.setattr(sim, "set_pdk", lambda _: None)
    monkeypatch.setattr(sim, "AdcTb", lambda params, _selected_view: h.Module(name="TestTb"))
    monkeypatch.setattr(sim.h.pdk, "compile", lambda module: module)
    monkeypatch.setattr(sim, "write_spectre_input", record_deck)

    params = AdcTbParams(conversions=3)
    sim._prepare_spectre_case(
        params,
        view=view,
        case_dir=tmp_path / "production",
        circuit_checks=False,
    )
    assert set(written) == {"input.scs"}
    production_text = "\n".join(attr.text for attr in written["input.scs"].attrs if isinstance(attr, h.Literal))
    assert "rawfmt=nutascii" in production_text
    assert "tran tran stop=4.8e-07" in production_text
    assert "strobeperiod=3.90625e-11 strobeoutput=strobeonly" in production_text
    assert "noisefmin=2083333.33333 noisefmax=25G noiseseed=1" in production_text
    assert "dyn_setuphold" not in production_text

    written.clear()
    sim._prepare_spectre_case(
        params,
        view=view,
        case_dir=tmp_path / "check",
        circuit_checks=True,
    )
    assert set(written) == {"checks.scs", "input.scs"}
    check_text = "\n".join(attr.text for attr in written["checks.scs"].attrs if isinstance(attr, h.Literal))
    capture_text = "\n".join(attr.text for attr in written["input.scs"].attrs if isinstance(attr, h.Literal))
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
    sim._prepare_spectre_case(
        AdcTbParams(symbol_rate=160e6, conversions=3),
        view=view,
        case_dir=tmp_path / "slow",
        circuit_checks=False,
    )
    slow_text = "\n".join(attr.text for attr in written["input.scs"].attrs if isinstance(attr, h.Literal))
    assert "strobeperiod=5e-11 strobeoutput=strobeonly" in slow_text

    written.clear()
    transfer_params = sim._transfer_curve_cases()[0][1]
    transfer_case = sim._prepare_spectre_case(
        transfer_params,
        view=view,
        case_dir=tmp_path / "transfer",
        circuit_checks=False,
        transient_noise=False,
        maximum_waveform_records=3,
    )
    transfer_text = "\n".join(attr.text for attr in written["input.scs"].attrs if isinstance(attr, h.Literal))
    assert "tran tran stop=2.416e-05" in transfer_text
    assert "noisefmin" not in transfer_text
    assert transfer_case.maximum_waveform_records == 3


def test_spectre_commands_wait_for_a_license(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Queue check and production runs instead of failing on license pressure."""

    commands: list[list[str]] = []
    monkeypatch.setattr(sim, "set_pdk", lambda _: None)
    monkeypatch.setattr(sim, "AdcTb", lambda params, _selected_view: h.Module(name="TestTb"))
    monkeypatch.setattr(sim.h.pdk, "compile", lambda module: module)
    monkeypatch.setattr(sim, "write_spectre_input", lambda sim_input, path: path.write_text(""))
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

    case = sim._prepare_spectre_case(
        AdcTbParams(conversions=1),
        view="hdl21gen",
        case_dir=tmp_path / "case",
        circuit_checks=True,
    )
    sim._execute_spectre_case(case)

    assert len(commands) == 2
    for command in commands:
        timeout_index = command.index("+lqtimeout")
        assert command[timeout_index + 1] == "3600"
        assert f"+mt={sim.SPECTRE_THREADS_PER_SIMULATION}" in command
