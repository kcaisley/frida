"""Scan: Digital-interface ADC check.

Configures the FRIDA chip for a normal ADC conversion sequence using the
digital interfaces only:
- reset via GPIO
- SPI register programming
- sequencer-driven LVDS outputs
- fast receiver capture of COMP_OUT

No analog input voltage is driven in this scan. Entry points handle sim
(cocotb + cocotbext-ams) and hardware (basil DAQ) setup/teardown.

Usage (simulation, from repo root):
    uv run python flow/scans/scan_adc.py
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from types import SimpleNamespace

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotbext.ams import MixedSignalBridge

from flow.scans.chip import Frida, SimBackend
from flow.scans.sim import SimAWG, SimPSU, create_adc_block, include_dirs, verilog_sources

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]


# =========================================================================
# Scan logic (backend-agnostic)
# =========================================================================


async def scan_adc(
    chip: Frida,
    n_conversions: int = 1,
) -> np.ndarray:
    """Run a digital-interface ADC check and record conversion output bits.

    Args:
        chip: Initialized Frida controller (any backend).
        n_conversions: Number of conversions to run.

    Returns:
        Array of shape (1, n_conversions, 17) with bits MSB first.
    """
    chip.select_adc(0)
    chip.enable_adc(
        0,
        en_init=True,
        en_samp_p=True,
        en_samp_n=True,
        en_comp=True,
        en_update=True,
        dac_mode=False,
        dac_diffcaps=False,
    )
    chip.set_dac_state(
        astate_p=0x7FFF,
        bstate_p=0x7FFF,
        astate_n=0x7FFF,
        bstate_n=0x7FFF,
    )
    await chip.reg_write()

    # Intentionally do not drive an analog input here.
    # await chip.set_vin(diff=..., cm=...)

    bits = await chip.run_conversions(n_conversions)
    logger.info(
        "Digital ADC check complete: %d conversions, first bits=%s",
        n_conversions,
        "".join(str(b) for b in bits[0, 0]),
    )
    return bits


# =========================================================================
# Simulation entry point (cocotb + cocotbext-ams)
# =========================================================================


@cocotb.test()
async def scan_adc_sim(dut):
    """cocotb entry point — sets up clocks, bridge, then runs scan."""
    import os

    vdd = float(os.environ.get("SCAN_VDD", "1.2"))
    n_conversions = int(os.environ.get("SCAN_N_CONVERSIONS", "1"))
    duration_ns = 500 + n_conversions * 200

    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, units="ps").start())
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, units="ps").start())
    cocotb.start_soon(Clock(dut.SPI_CLK, 100_000, units="ps").start())

    adc_block = create_adc_block(vdd=vdd)
    bridge = MixedSignalBridge(dut, [adc_block], max_sync_interval_ns=1.0)
    await bridge.start(duration_ns=duration_ns, analog_vcd="scan_adc.vcd")

    backend = SimBackend(dut)
    peripherals = SimpleNamespace(awg=SimAWG(bridge), psu=SimPSU(vdd))
    chip = Frida(backend, peripherals)
    await chip.init()

    await scan_adc(chip, n_conversions=n_conversions)

    await bridge.stop()


# =========================================================================
# Hardware entry point (basil DAQ over SiTcp)
# =========================================================================


async def scan_adc_hw(
    vdd: float = 1.2,
    n_conversions: int = 1,
) -> np.ndarray:
    """Hardware entry point — connects to FPGA, runs scan."""
    from basil.dut import Dut

    from flow.scans.chip import HardwareBackend
    from flow.scans.peripherals import BasilPSU

    yaml_path = Path(__file__).resolve().parent / "map_fpga.yaml"
    daq = Dut(str(yaml_path))
    daq.init()

    backend = HardwareBackend(daq)

    # Future analog path:
    # from flow.scans.peripherals import BasilAWG
    # peripherals = SimpleNamespace(awg=BasilAWG(), psu=BasilPSU(daq))
    #
    # For the current digital-only ADC scan, do not instantiate the AWG.
    # This avoids pulling in the Serial-based AWG transport on hosts where
    # the analog instrument stack is not installed.
    peripherals = SimpleNamespace(psu=BasilPSU(daq))

    chip = Frida(backend, peripherals)
    await chip.init()

    return await scan_adc(chip, n_conversions=n_conversions)


# =========================================================================
# CLI runner (launches simulation via cocotb runner)
# =========================================================================


def main():
    parser = argparse.ArgumentParser(description="ADC digital-interface scan")
    parser.add_argument("--vdd", type=float, default=1.2)
    parser.add_argument("--n-conversions", type=int, default=1)
    parser.add_argument("--sim", choices=["icarus"], default="icarus")
    parser.add_argument("--hw", action="store_true", help="Run on hardware instead of sim")
    args = parser.parse_args()

    if args.hw:
        import asyncio

        results = asyncio.run(
            scan_adc_hw(
                vdd=args.vdd,
                n_conversions=args.n_conversions,
            )
        )
        print(f"Results shape: {results.shape}")
    else:
        import os

        from cocotb_tools.runner import get_runner

        os.environ["SCAN_VDD"] = str(args.vdd)
        os.environ["SCAN_N_CONVERSIONS"] = str(args.n_conversions)

        runner = get_runner(args.sim)
        runner.build(
            verilog_sources=verilog_sources(),
            includes=include_dirs(),
            hdl_toplevel="tb_integration",
            build_dir=str(REPO / "scratch" / "scan_adc"),
            defines=["COCOTBEXT_AMS"],
            waves=True,
            timescale=("1ns", "1ps"),
        )
        runner.test(
            hdl_toplevel="tb_integration",
            test_module="flow.scans.scan_adc",
            waves=True,
        )


if __name__ == "__main__":
    main()
