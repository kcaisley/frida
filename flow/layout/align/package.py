"""A PDK's layout directory (``pdk/<pdk>/layout``) as ALIGN's PDK package: its ``layers.json``,
``models.sp`` and ``stems.json`` (``make_pdk.py`` writes them there, committed with the PDK), a
``gen_param.py`` and an ``__init__.py`` that hand ALIGN frida's generators (``flow/layout/align/pdk``)
by name, loaded from here only when ALIGN asks for one (``pdk.<pdk>.layout.tech`` and the others
stay plain imports). Nothing is copied: ALIGN runs on the PDK's directory itself (``pdk_dir``)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GENERATORS = Path(__file__).resolve().parent / "pdk"
# what ALIGN asks the package for: its generator classes by name and the standard cells' class lookup
EXPORTS = (
    "ArrayWiring",
    "CapGenerator",
    "DifferenceUnit",
    "MOSGenerator",
    "MomUnit",
    "ResGenerator",
    "ResUnit",
    "RingGenerator",
    "ViaArrayGenerator",
    "Wiring",
    "generator_class",
)


def pdk_dir(pdk: str) -> Path:
    """ALIGN's PDK directory of ``pdk``: its layout directory, once ``make_pdk.py`` has written its files."""
    path = ROOT / "pdk" / pdk / "layout"
    if not (path / "layers.json").is_file():
        raise FileNotFoundError(f"{path} holds no layers.json: run flow.layout.align.make_pdk for {pdk}")
    return path


def _load(name: str, path: Path, package: bool = False):
    """The module at ``path``, loaded once as ``name`` (a package: its directory searched for submodules)."""
    if name not in sys.modules:
        locations = [str(path.parent)] if package else None
        spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=locations)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def generators(layout_dir: Path, tech_dir: Path | None = None):
    """frida's generators, drawing for the PDK whose ALIGN files are in ``layout_dir`` and whose
    ``tech`` is in ``tech_dir`` (the same directory but for a test's modified copy of the files)."""
    tech_dir = str(tech_dir or layout_dir)
    if tech_dir not in sys.path:
        sys.path.insert(0, tech_dir)
    os.environ["FRIDA_ALIGN_PDK"] = str(layout_dir)  # where the generators read layers.json, stems.json
    return _load("frida_align_generators", GENERATORS / "__init__.py", package=True)


def exports(layout_dir: Path, tech_dir: Path | None = None):
    """The ``__getattr__`` of a PDK's layout package: a generator name ALIGN asks for, else none."""

    def __getattr__(name: str):
        if name in EXPORTS:
            return getattr(generators(Path(layout_dir), tech_dir), name)
        raise AttributeError(name)

    return __getattr__


def gen_param(layout_dir: Path):
    """frida's ``gen_param`` for the PDK of ``layout_dir``."""
    generators(Path(layout_dir))
    return _load("frida_align_generators.gen_param", GENERATORS / "gen_param.py").gen_param
