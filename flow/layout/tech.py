"""Typed layout rule deck and generic->tech layer mapping utilities."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

import klayout.db as kdb

# ---------------------------------------------------------------------------
# New hierarchical RuleDeck API
# ---------------------------------------------------------------------------


class RelativeRules:
    """Per-relative-layer rule storage.  Supports ``R.M1.spacing.M2`` syntax.

    Values are plain integers in the layout's units (nanometers by convention).
    """

    def __setattr__(self, name: str, value: object) -> None:
        object.__setattr__(self, name, value)

    def __getattr__(self, name: str) -> int:
        raise AttributeError(f"No rule defined for target layer '{name}'")


class NewLayerRules:
    """Rules for a single layer.  Supports both read and write.

    Write (PDK authoring)::

        R.M1.width = 160
        R.M1.spacing.M1 = 180
        R.M1.enclosure.CO = 60

    Read (generator)::

        rail_w = R.M1.width
        gap = R.M1.spacing.M1

    All values are plain integers in layout units (nanometers).
    """

    def __init__(self) -> None:
        self.width: int | None = None
        self.area: int | None = None
        self.spacing: RelativeRules = RelativeRules()
        self.enclosure: RelativeRules = RelativeRules()
        self.overlap: RelativeRules = RelativeRules()


class NewRuleDeck:
    """Hierarchical layout rule deck.

    Supports dot-path access for both authoring and reading::

        deck = NewRuleDeck()
        deck.M1.width = 160
        deck.M1.spacing.M1 = 180
        deck.CO.enclosure.OD = 70

    All values are plain integers in layout units.  By convention,
    generators set units = NANO (matching ``vlsir.raw.Units``), so values
    are nanometers and can be passed directly to ``Box()`` calls.
    """

    def __init__(self) -> None:
        self._layers: dict[str, NewLayerRules] = {}

    def __getattr__(self, name: str) -> NewLayerRules:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._layers:
            self._layers[name] = NewLayerRules()
        return self._layers[name]


# ---------------------------------------------------------------------------
# LayerInfoData — still needed by serialize.py for vlsir.tech layer export
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerInfoData:
    """Tech layer-purpose descriptor used for remap and tech serialization."""

    name: str
    index: int
    sub_index: int = 0
    purpose_type: str = "DRAWING"
    purpose_description: str = "drawing"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

LayerInfoMap = dict[kdb.LayerInfo, kdb.LayerInfo]


def load_rules_deck(tech_name: str) -> NewRuleDeck:
    """Load a PDK's rule deck by name.

    Imports ``pdk.<tech_name>.layout.pdk_layout.rule_deck()`` and returns
    the :class:`NewRuleDeck` directly.  All values are already plain
    integers in layout units (nanometers), so no conversion is needed.

    After loading::

        R = load_rules_deck("ihp130")
        R.M1.width       # → 160  (int, nanometers)
        R.M1.spacing.M1  # → 180
    """
    module = import_module(f"pdk.{tech_name}.layout.pdk_layout")
    return module.rule_deck()


def load_dbu(tech_name: str) -> float:
    """Load a PDK's database-unit size (microns per dbu).

    Imports ``pdk.<tech_name>.layout.pdk_layout.DBU`` and returns the
    float directly.

    After loading::

        layout.dbu = load_dbu("ihp130")   # 0.001 → 1 nm per dbu
    """
    module = import_module(f"pdk.{tech_name}.layout.pdk_layout")
    return module.DBU


def load_layer_map(tech_name: str) -> LayerInfoMap:
    """Load a PDK's generic-to-tech layer mapping.

    Imports ``pdk.<tech_name>.layout.pdk_layout.layer_map()`` and returns
    the ``dict[kdb.LayerInfo, kdb.LayerInfo]`` directly.
    """
    module = import_module(f"pdk.{tech_name}.layout.pdk_layout")
    return module.layer_map()


# ---------------------------------------------------------------------------
# Layer remapping
# ---------------------------------------------------------------------------


def remap_layers(
    layout: kdb.Layout,
    mapping: LayerInfoMap,
    *,
    delete_source: bool = True,
) -> None:
    """Move shapes from generic layers to PDK-specific layers.

    For each ``(generic_info -> pdk_info)`` pair in *mapping*:

    - find or create the source and destination layers,
    - copy all shapes from source to destination,
    - optionally delete the source layer.
    """
    for generic_info, pdk_info in mapping.items():
        src_idx = layout.find_layer(generic_info)
        if src_idx is None or src_idx < 0:
            continue
        dst_idx = layout.layer(pdk_info)
        for cell in layout.each_cell():
            src_shapes = cell.shapes(src_idx)
            if src_shapes.is_empty():
                continue
            for shape in src_shapes.each():
                cell.shapes(dst_idx).insert(shape)
            if delete_source:
                src_shapes.clear()


# ---------------------------------------------------------------------------
# Inline tests
# ---------------------------------------------------------------------------


def test_rule_deck() -> None:
    """Verify hierarchical RuleDeck read/write."""
    R = NewRuleDeck()

    # Write
    R.M1.width = 160
    R.M1.spacing.M1 = 180
    R.M1.spacing.M2 = 200
    R.M1.area = 50_000
    R.CO.enclosure.OD = 70

    # Read
    assert R.M1.width == 160
    assert R.M1.spacing.M1 == 180
    assert R.M1.spacing.M2 == 200
    assert R.M1.area == 50_000
    assert R.CO.enclosure.OD == 70

    # Missing rule raises
    import pytest

    with pytest.raises(AttributeError, match="target layer"):
        _ = R.M1.spacing.M9


def test_remap_layers() -> None:
    """Verify remap_layers moves shapes correctly."""
    layout = kdb.Layout()
    layout.dbu = 0.001

    generic = kdb.LayerInfo(10, 0, "M1")
    pdk = kdb.LayerInfo(7, 0, "METAL1")

    src_idx = layout.layer(generic)
    cell = layout.create_cell("T")
    cell.shapes(src_idx).insert(kdb.Box(0, 0, 100, 100))

    remap_layers(layout, {generic: pdk})

    # Source should be cleared
    assert cell.shapes(src_idx).is_empty()
    # Destination should have the shape
    dst_idx = layout.find_layer(pdk)
    assert dst_idx is not None and dst_idx >= 0
    assert not cell.shapes(dst_idx).is_empty()
