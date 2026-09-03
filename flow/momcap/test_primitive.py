"""Software-only tests for the MOM capacitor layout primitive."""

from ..layout.serialize import export_layout
from ..layout.tech import load_layer_map, remap_layers
from .primitive import MomcapParams, momcap


def test_momcap(tmp_path):
    """Verify the standalone generator emits every requested weighted unit."""
    layout = momcap(MomcapParams(max_weight=4), "tsmc65")
    assert {cell.name for cell in layout.each_cell()} >= {
        "frida_mom_w1_m6",
        "frida_mom_w2_m6",
        "frida_mom_w3_m6",
        "frida_mom_w4_m6",
    }
    assert len(list(layout.cell("MOMCAP_FAMILY").each_inst())) == 4
    remap_layers(layout, load_layer_map("tsmc65"))
    artifacts = export_layout(layout, out_dir=tmp_path, stem="smoke", domain="frida.layout.tsmc65")
    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()
