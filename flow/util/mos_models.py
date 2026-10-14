"""MOS model names of every PDK in ``pdk/`` (each ``layout/tech.py``'s ``MODELS`` and
``MODEL_PREFIXES``), by polarity.

The schematic tools draw any PDK's netlists, so they look a device's polarity up here instead of
guessing it from vendor naming. Generic names (``nmos``, ``nfet``, ``pmos``, ``pfet``) count too.
"""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERIC = {"nmos": "n", "nfet": "n", "mos_n": "n", "pmos": "p", "pfet": "p", "mos_p": "p"}


def _assigned(tech: Path, name: str):
    for node in ast.parse(tech.read_text()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


@cache
def mos_models() -> tuple[dict[str, str], dict[str, str]]:
    """(lower-case model name -> "n"/"p", model-name prefix -> "n"/"p") from every PDK's ``tech``
    (read, not imported)."""
    models, prefixes = dict(GENERIC), {}
    for tech in sorted(ROOT.glob("pdk/*/layout/tech.py")):
        models.update({model.lower(): pol for pol, model in _assigned(tech, "MODELS").items()})
        prefixes.update({pre.lower(): pol for pol, pres in _assigned(tech, "MODEL_PREFIXES").items() for pre in pres})
    return models, prefixes


def polarity(model: str) -> str | None:
    """ "n" or "p" for a MOS model (any PDK's, or a generic name), else None."""
    name = model.lower().lstrip("\\")
    models, prefixes = mos_models()
    return models.get(name) or next((pol for pre, pol in prefixes.items() if name.startswith(pre)), None)
