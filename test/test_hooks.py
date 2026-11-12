"""Keep the checks' Python coverage (tools/check.py, pyproject.toml [tool.check]) aligned with the
capacitor DAC's package (capdac)."""

import re
import tomllib
from pathlib import Path

from flow.test_pipeline import typed

PROJECT = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
CHECK = PROJECT["tool"]["check"]


def test_ruff_covers_the_capacitor_dac():
    pattern = CHECK["python-files"]
    assert re.search(pattern, "flow/capdac/subckt.py")
    assert re.search(pattern, "flow/capdac/test_subckt.py")
    assert not re.search(pattern, "flow/capdac/readme.md")
    assert not re.search(pattern, "flow/capdac_other/subckt.py")


def test_ty_checks_the_capacitor_dac():
    assert "flow/capdac/subckt.py" in typed()


def test_ty_hdl21_boundary_covers_the_capacitor_dac():
    config = PROJECT["tool"]["ty"]
    includes = {
        pattern
        for override in config["overrides"]
        if "hdl21.**" in override.get("analysis", {}).get("replace-imports-with-any", [])
        for pattern in override["include"]
    }
    assert "flow/capdac/**" in includes
