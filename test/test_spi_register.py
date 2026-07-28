"""Run the SPI register cocotb checks with a stock HDL simulator."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner

REPO_ROOT = Path(__file__).resolve().parents[1]
COCOTB_DIR = Path(__file__).resolve().parent / "cocotb"
SPI_RTL = REPO_ROOT / "design" / "hdl" / "spi.v"
FRIDA_SPI_RTL = REPO_ROOT / "design" / "hdl" / "frida_spi.v"
BEHAVIORAL_CELLS = REPO_ROOT / "design" / "hdl" / "cells_behavioral.v"


@pytest.mark.parametrize(
    ("name", "sources"),
    (
        ("behavioral", (SPI_RTL,)),
        ("explicit_cells", (BEHAVIORAL_CELLS, FRIDA_SPI_RTL)),
    ),
)
def test_spi_register(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    sources: tuple[Path, ...],
) -> None:
    """Build one SPI implementation and run the shared cocotb regression."""

    simulator = os.getenv("SIM", "icarus")
    build_dir = tmp_path / name
    monkeypatch.syspath_prepend(COCOTB_DIR)
    runner = get_runner(simulator)
    runner.build(
        sources=list(sources),
        hdl_toplevel="spi_register",
        build_dir=build_dir,
        always=True,
    )
    runner.test(
        test_module="spi_register_cocotb",
        hdl_toplevel="spi_register",
        build_dir=build_dir,
        test_dir=build_dir,
    )
