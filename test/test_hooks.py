"""Keep Python hook coverage aligned with the capacitor DAC's package (capdac)."""

import re
import shlex
import tomllib
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def python_hooks():
    config = yaml.safe_load((Path(__file__).resolve().parents[1] / ".pre-commit-config.yaml").read_text())
    return {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}


@pytest.mark.parametrize("hook_id", ["ruff-lint", "ruff-format", "ty-flow"])
def test_python_hooks_cover_the_capacitor_dac(python_hooks, hook_id):
    pattern = python_hooks[hook_id]["files"]
    assert re.search(pattern, "flow/capdac/subckt.py")
    assert re.search(pattern, "flow/capdac/test_subckt.py")
    assert not re.search(pattern, "flow/capdac/readme.md")
    assert not re.search(pattern, "flow/capdac_other/subckt.py")


def test_ty_checks_the_capacitor_dac(python_hooks):
    hook = python_hooks["ty-flow"]
    command = shlex.split(hook["entry"])
    assert "flow/capdac" in command
    assert hook["pass_filenames"] is False


def test_ty_hdl21_boundary_covers_the_capacitor_dac():
    config = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())["tool"]["ty"]
    includes = {
        pattern
        for override in config["overrides"]
        if "hdl21.**" in override.get("analysis", {}).get("replace-imports-with-any", [])
        for pattern in override["include"]
    }
    assert "flow/capdac/**" in includes
