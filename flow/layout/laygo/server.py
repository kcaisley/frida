"""The hosted laygo server's layers: it routes in one PDK's layer map (SERVER_PDK), whose
numbers and names come from that PDK's ``tech``; post.py maps them back to the target PDK."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SERVER_PDK = "ihp130"
ROOT = Path(__file__).resolve().parents[3]


def _tech():
    path = ROOT / "pdk" / SERVER_PDK / "layout" / "tech.py"
    spec = importlib.util.spec_from_file_location(f"_server_tech_{SERVER_PDK}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def server_layers() -> dict[str, tuple[int, int]]:
    """Our metal names (M1..M5) -> the server's (layer, datatype)."""
    t = _tech()
    return {m: t.LAYERS[m] for m in t.LAYER_NAMES}


def server_names() -> dict[str, str]:
    """Our metal names (M1..M5) -> the server's layer names."""
    return dict(_tech().LAYER_NAMES)
