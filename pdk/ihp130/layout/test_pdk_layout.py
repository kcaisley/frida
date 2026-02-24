"""Layout metadata serialization tests for IHP130."""

from __future__ import annotations

import shutil
from pathlib import Path

from .pdk_layout import layer_infos, write_ihp130_tech_proto


def test_layout_proto_and_layer_payload() -> None:
    """Serialize IHP130 layout proto and validate payload."""
    out_dir = Path("pdk") / "ihp130" / "scratch"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    artifacts = write_ihp130_tech_proto(out_dir)
    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()

    pbtxt = artifacts.pbtxt.read_text(encoding="utf-8")
    assert 'name: "ihp130"' in pbtxt
    assert "layers" in pbtxt
    assert len(layer_infos()) > 0
