"""Software-only checks for the named CDAC simulation targets."""

import hdl21 as h

from . import sim


def test_cdac_targets_are_named_and_explicit() -> None:
    assert set(sim.TARGETS) == {
        "frida65_baseline_netlist",
        "frida65_baseline_transient",
    }
    assert sim.MAX_PARALLEL_SIMULATIONS > 0


def test_cdac_sim_input_writes_selected_nutascii() -> None:
    simulation = sim.sim_input(sim.CdacTbParams())
    literal_text = "\n".join(attr.text for attr in simulation.attrs if isinstance(attr, h.Literal))

    assert "rawfmt=nutascii" in literal_text
    assert "xtop.top" in literal_text
    assert "xtop.dac_bits_15" in literal_text
    assert "tran tran stop=" in literal_text
