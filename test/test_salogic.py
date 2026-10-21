"""Run the SAR logic cocotb checks with a stock HDL simulator."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner

REPO_ROOT = Path(__file__).resolve().parents[1]
COCOTB_DIR = Path(__file__).resolve().parent / "cocotb"
SALOGIC_RTL = REPO_ROOT / "design" / "hdl" / "salogic.v"
BEHAVIORAL_CELLS = REPO_ROOT / "design" / "hdl" / "cells_behavioral.v"


@pytest.mark.parametrize("n_stages", [16, 12, 17])
def test_salogic(n_stages: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Build the SAR logic with N_STAGES capacitor stages and run its cocotb regression."""

    simulator = os.getenv("SIM", "icarus")
    build_dir = tmp_path / f"salogic_{n_stages}"
    monkeypatch.syspath_prepend(COCOTB_DIR)
    runner = get_runner(simulator)
    runner.build(
        sources=[BEHAVIORAL_CELLS, SALOGIC_RTL],
        hdl_toplevel="salogic",
        build_dir=build_dir,
        parameters={"N_STAGES": n_stages},
        always=True,
    )
    runner.test(
        test_module="salogic_cocotb",
        hdl_toplevel="salogic",
        build_dir=build_dir,
        test_dir=build_dir,
        extra_env={"SALOGIC_N_STAGES": str(n_stages)},
    )
