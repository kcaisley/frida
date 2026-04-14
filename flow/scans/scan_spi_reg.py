"""Scan: SPI register write/readback verification.

Writes a known configuration to the FRIDA chip's 180-bit SPI shift
register using the Frida class high-level API, reads it back, and
verifies bit-for-bit match.

Tests the full SPI chain: FPGA SPI master → SDI → chip shift register
→ SDO → FPGA SPI master.

Usage (simulation, from repo root):
    uv run python flow/scans/scan_spi_reg.py

Usage (hardware):
    uv run python flow/scans/scan_spi_reg.py --hw
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotbext.ams import MixedSignalBridge

from flow.scans.chip import Frida, SimBackend
from flow.scans.sim import create_adc_block, include_dirs, verilog_sources

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]


# =========================================================================
# Scan logic (backend-agnostic)
# =========================================================================


async def scan_spi_reg(chip: Frida) -> dict:
    """Write a known register state, read back, verify all 180 bits match.

    Args:
        chip: Initialized Frida controller (any backend).

    Returns:
        Dict with 'sent', 'received', 'n_mismatch', and 'pass' keys.
    """
    chip.select_adc(5)
    chip.enable_adc(
        0,
        en_init=True,
        en_samp_p=True,
        en_samp_n=True,
        en_comp=True,
        en_update=True,
        dac_diffcaps=True,
    )
    chip.set_dac_state(
        astate_p=0xAAAA,
        bstate_p=0x5555,
        astate_n=0x1234,
        bstate_n=0xABCD,
    )

    expected = chip.spi_bits.copy()
    await chip.write_spi()
    readback = await chip.read_spi()

    n_mismatch = (expected ^ readback).count(1)
    result = {
        "sent": expected,
        "received": readback,
        "n_mismatch": n_mismatch,
        "pass": n_mismatch == 0,
    }

    if n_mismatch == 0:
        logger.info("SPI register scan PASS: all 180 bits match")
    else:
        logger.error(
            "SPI register scan FAIL: %d/180 bits differ\n  sent: %s\n  recv: %s",
            n_mismatch,
            expected.tobytes().hex(),
            readback.tobytes().hex(),
        )

    return result


# =========================================================================
# Simulation entry point (cocotb + cocotbext-ams)
# =========================================================================


@cocotb.test()
async def scan_spi_reg_sim(dut):
    """cocotb entry point — sets up clocks, bridge, then runs scan."""
    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, unit="ps").start())
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, unit="ps").start())

    adc_block = create_adc_block(vdd=1.2)
    bridge = MixedSignalBridge(dut, [adc_block], max_sync_interval_ns=1.0)
    await bridge.start(duration_ns=50_000, analog_vcd="scan_spi_reg.vcd")

    backend = SimBackend(dut)
    chip = Frida(backend)
    await chip.init()

    result = await scan_spi_reg(chip)
    assert result["pass"], f"SPI register scan failed: {result['n_mismatch']}/180 bits differ"

    await bridge.stop()


# =========================================================================
# Hardware entry point (basil DAQ over SiTcp)
# =========================================================================


async def scan_spi_reg_hw() -> dict:
    """Hardware entry point — connects to FPGA, runs scan."""
    from basil.dut import Dut

    from flow.scans.chip import HardwareBackend

    yaml_path = Path(__file__).resolve().parent / "map_fpga.yaml"
    daq = Dut(str(yaml_path))
    daq.init()

    backend = HardwareBackend(daq)
    chip = Frida(backend)
    await chip.init()

    return await scan_spi_reg(chip)


# =========================================================================
# CLI runner (launches simulation via cocotb runner)
# =========================================================================


def main():
    parser = argparse.ArgumentParser(description="SPI register write/readback scan")
    parser.add_argument("--hw", action="store_true", help="Run on hardware instead of sim")
    args = parser.parse_args()

    if args.hw:
        import asyncio

        result = asyncio.run(scan_spi_reg_hw())
        if result["pass"]:
            print("PASS: all 180 bits match")
        else:
            print(f"FAIL: {result['n_mismatch']}/180 bits differ")
            print(f"  sent: {result['sent'].tobytes().hex()}")
            print(f"  recv: {result['received'].tobytes().hex()}")
    else:
        from cocotb_tools.runner import get_runner

        runner = get_runner("icarus")
        runner.build(
            verilog_sources=verilog_sources(),
            includes=include_dirs(),
            hdl_toplevel="tb_integration",
            build_dir=str(REPO / "scratch" / "scan_spi_reg"),
            defines={"COCOTBEXT_AMS": ""},
        )
        runner.test(
            hdl_toplevel="tb_integration",
            test_module="flow.scans.scan_spi_reg",
        )


if __name__ == "__main__":
    main()
