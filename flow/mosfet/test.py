"""Smoke tests for the mosfet layout generator."""

from ..layout.serialize import export_layout
from ..layout.tech import load_layer_map, remap_layers
from .primitive import MosfetParams, mosfet


def test_mosfet(tmp_path):
    """Verify mosfet generator produces valid layout."""
    layout = mosfet(MosfetParams(), "ihp130")
    remap_layers(layout, load_layer_map("ihp130"))
    artifacts = export_layout(
        layout, out_dir=tmp_path, stem="smoke", domain="frida.layout.ihp130"
    )
    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()
