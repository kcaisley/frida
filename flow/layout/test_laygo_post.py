"""Tests for laygo's post step (flow/layout/laygo/post.py)."""

import pytest

from .pdkproc import ROOT, in_pdk

needs_server_pdk = pytest.mark.skipif(
    not (ROOT / "pdk/ihp130/layout/tech.py").is_file(), reason="needs the laygo server's PDK submodule (ihp130)"
)


def label_layers(tmp: str) -> tuple[list[tuple[int, int]], tuple[int, int]]:
    """Run bound to a PDK: post a design whose port label sits where another net's M2 bar is centred
    too; (the layers holding the label, the PDK's M3 pin-text layer)."""

    from pathlib import Path

    import klayout.db as kdb
    from tech import PIN_TEXT

    from flow.layout.laygo import post
    from flow.layout.laygo.server import server_layers

    srv = server_layers()
    raw = kdb.Layout()
    raw.dbu = 0.001
    top = raw.create_cell("blk")
    top.shapes(raw.layer(*srv["M2"])).insert(kdb.Box(0, 450, 2000, 550))  # another net's bar
    top.shapes(raw.layer(*srv["M3"])).insert(kdb.Box(950, 0, 1050, 1000))  # the port's escape stub
    top.shapes(raw.layer(0, 0)).insert(kdb.Text("clkb", kdb.Trans(1000, 500)))
    raw.write(str(Path(tmp) / "blk_raw.gds"))
    kdb.Layout().write(str(Path(tmp) / "templates.gds"))
    post.post(str(Path(tmp) / "blk_raw.gds"), str(Path(tmp) / "templates.gds"), str(Path(tmp) / "blk.gds"))
    out = kdb.Layout()
    out.read(str(Path(tmp) / "blk.gds"))
    found = [
        (out.get_info(li).layer, out.get_info(li).datatype)
        for li in out.layer_indexes()
        if any(s.is_text() for s in out.top_cell().shapes(li).each())
    ]
    return found, tuple(PIN_TEXT["M3"])


@needs_server_pdk
def test_a_port_label_goes_on_m3_where_an_m2_bar_is_centred_too(tmp_path) -> None:
    found, m3_text = in_pdk("ihp130", "flow.layout.test_laygo_post", "label_layers", str(tmp_path))
    assert found == [m3_text]
