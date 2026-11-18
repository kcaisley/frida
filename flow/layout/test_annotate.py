"""The extraction's nets on the schematic's (``flow.layout.annotate``): by the LVS database where it
holds them, by their labels where it keeps no trace of them."""

from __future__ import annotations

from pathlib import Path

from flow.layout import annotate


class _Lvs:
    """An LVS database that holds no net: every probe misses."""

    def read(self, path: str) -> None:
        pass

    def layer_indexes(self) -> list[int]:
        return []


def test_a_net_the_database_drops_is_found_by_its_label(monkeypatch) -> None:
    """A net LVS kept no trace of (no device on it: a MOM capacitor's plate where the deck extracts
    no capacitor) is the schematic net its label names; one KLayout numbered, a disjoint piece of a
    labelled net and a cell's inner net have none, the first floating where a probe found it so."""
    monkeypatch.setattr(annotate.db, "LayoutVsSchematic", _Lvs)
    probed = {"vdac": None, "MAIN_2": None, "$96": annotate.FLOATING, "vss$1": None, "x1/n0": None, "vdd": "vdd"}
    monkeypatch.setattr(annotate, "_probed", lambda lvs, layers, probe: probed[probe[0]])
    probes = {name: [[name, 0, 0, 0]] for name in probed}
    found = annotate.schematic_nets(Path("none.lvsdb"), probes)
    assert found == {
        "vdac": "vdac",
        "MAIN_2": "main_2",
        "$96": annotate.FLOATING,
        "vss$1": None,
        "x1/n0": None,
        "vdd": "vdd",
    }
