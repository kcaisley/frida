"""Canonical observations and hardened-interface boundary checks."""

from pathlib import Path

import hdl21 as h
import pytest

from . import sim
from .ip import digital_net_aliases
from .subckt import AdcNets


def test_all_adc_views_expose_the_same_analysis_waveforms():
    observations = []
    for view in ("hdl21gen", "frida1", "frida2"):
        pex = None if view == "hdl21gen" else Path(__file__).parent / "fixtures" / f"{view}_ports.scs"
        tb = sim.AdcTb(sim.AdcTbParams(view=view, pex_cell="adc_12b_17step" if pex else ""), pex_netlist=pex)
        observations.append(set(sim.adc_signal_names(tb, view).values()))
    assert observations[0] == observations[1] == observations[2]
    for side in ("p", "n"):
        for kind in ("", "_diff"):
            for stage in range(16):
                assert f"dac_botplate_{side}{kind}[{stage}]" in observations[0]


@pytest.mark.parametrize("pin", ("seq_typo", "dac_state_p_main[16]", "dac_state_p_main"))
def test_digital_binding_rejects_unknown_pins_and_incompatible_widths(pin):
    module = h.ExternalModule(name="bad_digital", port_list=[h.Inout(name=pin)])
    with pytest.raises((KeyError, ValueError)):
        digital_net_aliases(module)


@pytest.mark.parametrize("fault", ("missing", "duplicate"))
def test_pex_observations_reject_incomplete_or_ambiguous_bindings(monkeypatch, fault):
    tb = sim.AdcTb(
        sim.AdcTbParams(view="frida2", pex_cell="adc_12b_17step"),
        pex_netlist=Path(__file__).parent / "fixtures/frida2_ports.scs",
    )
    aliases = sim.frida2_net_aliases()
    if fault == "missing":
        del aliases[AdcNets.vdac_p]
    else:
        aliases[AdcNets.vdac_p] = aliases[AdcNets.vdac_n]
    monkeypatch.setattr(sim, "frida2_net_aliases", lambda: aliases)
    with pytest.raises((KeyError, ValueError)):
        sim.adc_signal_names(tb, "frida2")
