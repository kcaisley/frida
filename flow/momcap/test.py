"""Smoke tests for the momcap layout generator."""

from ..layout.serialize import export_layout
from ..layout.tech import load_layer_map, remap_layers
from .primitive import MomcapParams, momcap


def test_momcap(tmp_path):
    """Verify momcap generator produces valid layout."""
    layout = momcap(MomcapParams(), "ihp130")
    remap_layers(layout, load_layer_map("ihp130"))
    artifacts = export_layout(
        layout, out_dir=tmp_path, stem="smoke", domain="frida.layout.ihp130"
    )
    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()
