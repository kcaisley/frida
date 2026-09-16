"""Keep Python hook coverage aligned with the capacitor block packages."""

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
@pytest.mark.parametrize("block", ["caparray", "capdriver"])
def test_python_hooks_cover_capacitor_blocks(python_hooks, hook_id, block):
    pattern = python_hooks[hook_id]["files"]
    assert re.search(pattern, f"flow/{block}/subckt.py")
    assert re.search(pattern, f"flow/{block}/test_subckt.py")
    assert not re.search(pattern, "flow/cdac/subckt.py")
    assert not re.search(pattern, f"flow/{block}/readme.md")
    assert not re.search(pattern, f"flow/{block}_other/subckt.py")


def test_ty_checks_both_capacitor_blocks(python_hooks):
    hook = python_hooks["ty-flow"]
    command = shlex.split(hook["entry"])
    assert "flow/caparray" in command
    assert "flow/capdriver" in command
    assert "flow/cdac" not in command
    assert hook["pass_filenames"] is False


def test_ty_hdl21_boundary_covers_renamed_blocks():
    config = tomllib.loads((Path(__file__).resolve().parents[1] / "ty.toml").read_text())
    includes = {
        pattern
        for override in config["overrides"]
        if "hdl21.**" in override.get("analysis", {}).get("replace-imports-with-any", [])
        for pattern in override["include"]
    }
    assert {"flow/caparray/**", "flow/capdriver/**"} <= includes
    assert "flow/cdac/**" not in includes
