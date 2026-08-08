"""Run the ADC capacitor-driver polarity check with a stock HDL simulator."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner

REPO_ROOT = Path(__file__).resolve().parents[1]
COCOTB_DIR = Path(__file__).resolve().parent / "cocotb"
HDL_DIR = REPO_ROOT / "design" / "hdl"


def test_adc_capdriver_polarity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Check the behavioral ADC against the fabricated active-high XOR convention."""

    simulator = os.getenv("SIM", "icarus")
    build_dir = tmp_path / "adc_capdriver"
    monkeypatch.syspath_prepend(COCOTB_DIR)
    runner = get_runner(simulator)
    runner.build(
        sources=[
            HDL_DIR / "cells_behavioral.v",
            HDL_DIR / "clkgate.v",
            HDL_DIR / "salogic.v",
            HDL_DIR / "capdriver.v",
            HDL_DIR / "sampdriver.v",
            HDL_DIR / "caparray.v",
            HDL_DIR / "sampswitch.v",
            HDL_DIR / "comp.v",
            HDL_DIR / "adc.v",
        ],
        hdl_toplevel="adc",
        build_dir=build_dir,
        always=True,
    )
    runner.test(
        test_module="adc_capdriver_cocotb",
        hdl_toplevel="adc",
        build_dir=build_dir,
        test_dir=build_dir,
    )
