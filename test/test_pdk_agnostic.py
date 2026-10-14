"""The superproject holds no PDK's data: numbers, rules, library cells and layouts live in the
PDK submodules (pdk/<pdk>/), which the flows read through each PDK's ``layout/tech.py``.

Scanned: every tracked or untracked (not ignored) file outside pdk/, libs/ and build/. FRIDA's own
netlists and HDL (design/spice, design/hdl) are the design, so they may name the cells they
instantiate; the cells' own netlists are in the PDK.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIP = ("libs/", "build/", "design/spice/", "design/hdl/", "test/test_pdk_agnostic.py")
PDKS = re.compile(r"pdk/[^/]+/")  # the submodules (pdk/README.md and pdk/test_*.py are the superproject's)
LAYOUT = (".gds", ".gds.gz", ".oas", ".oasis")
# a foundry design-rule ID: layer, check, number (PO.S.2, VIA1.R.4, M2.A.2, NW.EN.1, DRM.R.1, M7.DN.1)
RULE = re.compile(
    r"\b(?:PO|OD|CO|CA|GA|M[0-9]|MX|VIA[0-9]|VIAX|V[0-9]|NW|PW|PP|NP|DNW|RPO|DRM|MOM|CB|AP|NT_N|VTL_[NP])"
    r"\.(?:S|W|EN|EX|A|R|L|O|C|E|DN|R)\.[0-9]+[A-Z]?\b"
    r"|\b(?:METAL[0-9]|POLY[0-9]|DIFF|CONT|VIA[0-9]|NWELL|PWELL)\.(?:SPACING|WIDTH|OVERLAP|ENCLOSURE|AREA|EXTENSION)\b"
)
KIT = re.compile(r"/eda/kits/(?!IHP)[A-Za-z]")  # a commercial foundry kit path (IHP's PDK is open)
GENERIC = re.compile(r"[A-Za-z]+[01]?")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode()
    return [
        ROOT / f for f in out.split("\0") if f and not f.startswith(SKIP) and not PDKS.match(f) and (ROOT / f).is_file()
    ]


def _assigned(tech: Path, name: str):
    for node in ast.parse(tech.read_text()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def _library_names() -> dict[str, str]:
    """Each commercial PDK's standard-cell library and cell names -> the PDK (from its tech)."""
    names = {}
    for tech in sorted(ROOT.glob("pdk/*/layout/tech.py")):
        pdk = tech.parts[-3]
        if pdk == "ihp130":  # open PDK
            continue
        for key in ("STD_LIB", "STD_CELLS", "STD_FILL"):
            value = _assigned(tech, key)
            for name in [value] if isinstance(value, str) else value or ():
                if isinstance(name, str) and len(name) > 3:
                    names[name] = pdk
        for lef in tech.parents[1].glob("openroad/lef/*.lef"):  # every library and IO cell
            macros = re.findall(rb"^MACRO\s+(\S+)", lef.read_bytes(), re.MULTILINE)
            names.update({m.decode(errors="replace"): pdk for m in macros})
    # plain words (ANTENNA, LOGIC1) are no evidence: a cell name has a drive or variant suffix
    return {n: p for n, p in names.items() if len(n) > 3 and not GENERIC.fullmatch(n)}


def _text(path: Path) -> str | None:
    try:
        return path.read_text()
    except (UnicodeDecodeError, OSError):
        return None


def test_no_layout_files_outside_the_pdks() -> None:
    assert [str(f.relative_to(ROOT)) for f in _files() if f.name.lower().endswith(LAYOUT)] == []


def test_no_foundry_rules_kits_or_library_cells() -> None:
    if not list(ROOT.glob("pdk/*/layout/tech.py")):
        pytest.skip("no PDK submodules checked out")
    cells = _library_names()
    found = []
    for f in _files():
        text = _text(f)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            hits = RULE.findall(line) + KIT.findall(line) + sorted(set(WORD.findall(line)) & cells.keys())
            if hits:
                found.append(f"{f.relative_to(ROOT)}:{n}: {hits}")
    assert found == [], "PDK data in the superproject (move it to pdk/<pdk>/):\n" + "\n".join(found)
