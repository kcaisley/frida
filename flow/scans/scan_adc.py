"""Scan: Sweep ADC input voltage and record conversion output codes.

The scan logic is backend-agnostic — it takes a Frida chip object and
a voltage array. Entry points handle sim (cocotb + cocotbext-ams) and
hardware (basil DAQ) setup/teardown.

Usage (simulation, from repo root):
    uv run python flow/scans/scan_adc.py
    uv run python flow/scans/scan_adc.py --vin-start -0.3 --vin-stop 0.3
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
    voltages: np.ndarray,
    n_conversions: int = 1,
    cm: float = 0.6,
) -> np.ndarray:
    """Sweep differential input voltage and record ADC output codes.

    Args:
        chip: Initialized Frida controller (any backend).
        voltages: Array of differential voltages to sweep.
        n_conversions: Number of conversions per voltage step.
        cm: Common-mode voltage.

    Returns:
        Array of shape (n_voltages, n_conversions, 17) with bits MSB first.
    """
    chip.select_adc(0)
    chip.enable_adc(0)
    chip.set_dac_state(astate_p=0xFFFF, astate_n=0xFFFF)
    await chip.write_spi()

    results = []
    for diff in voltages:
        await chip.set_vin(diff=float(diff), cm=cm)
        bits = await chip.run_conversions(n_conversions)
        results.append(bits[0])  # squeeze repetitions dim
        logger.info(
            "vin_diff=%.3fV: bits=%s",
            diff,
            "".join(str(b) for b in bits[0, 0]),
        )

    all_bits = np.stack(results, axis=0)
    logger.info(
        "Scan complete: %d voltage steps, %d conversions each",
        all_bits.shape[0],
        all_bits.shape[1],
    )
    return all_bits


# =========================================================================
# Simulation entry point (cocotb + cocotbext-ams)
# =========================================================================


@cocotb.test()
async def scan_adc_sim(dut):
    """cocotb entry point — sets up clocks, bridge, then runs scan."""
    import os

    vin_start = float(os.environ.get("SCAN_VIN_START", "-0.6"))
    vin_stop = float(os.environ.get("SCAN_VIN_STOP", "0.6"))
    vin_step = float(os.environ.get("SCAN_VIN_STEP", "0.05"))
    vdd = float(os.environ.get("SCAN_VDD", "1.2"))
    n_conversions = int(os.environ.get("SCAN_N_CONVERSIONS", "1"))

    voltages = np.arange(vin_start, vin_stop + vin_step / 2, vin_step)
    duration_ns = 500 + len(voltages) * n_conversions * 200

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

    await scan_adc(chip, voltages, n_conversions, cm=vdd / 2)

    await bridge.stop()


# =========================================================================
# Hardware entry point (basil DAQ over SiTcp)
# =========================================================================


async def scan_adc_hw(
    vin_start: float = -0.6,
    vin_stop: float = 0.6,
    vin_step: float = 0.05,
    vdd: float = 1.2,
    n_conversions: int = 1,
) -> np.ndarray:
    """Hardware entry point — connects to FPGA, runs scan."""
    from basil.dut import Dut

    from flow.scans.chip import HardwareBackend
    from flow.scans.peripherals import BasilAWG, BasilPSU

    yaml_path = Path(__file__).resolve().parent / "map_fpga.yaml"
    daq = Dut(str(yaml_path))
    daq.init()

    backend = HardwareBackend(daq)
    peripherals = SimpleNamespace(awg=BasilAWG(), psu=BasilPSU(daq))
    chip = Frida(backend, peripherals)
    await chip.init()

    voltages = np.arange(vin_start, vin_stop + vin_step / 2, vin_step)
    return await scan_adc(chip, voltages, n_conversions, cm=vdd / 2)


# =========================================================================
# CLI runner (launches simulation via cocotb runner)
# =========================================================================


def main():
    parser = argparse.ArgumentParser(description="ADC voltage sweep scan")
    parser.add_argument("--vin-start", type=float, default=-0.6)
    parser.add_argument("--vin-stop", type=float, default=0.6)
    parser.add_argument("--vin-step", type=float, default=0.05)
    parser.add_argument("--vdd", type=float, default=1.2)
    parser.add_argument("--n-conversions", type=int, default=1)
    parser.add_argument("--sim", choices=["icarus"], default="icarus")
    parser.add_argument("--hw", action="store_true", help="Run on hardware instead of sim")
    args = parser.parse_args()

    if args.hw:
        import asyncio

        results = asyncio.run(
            scan_adc_hw(
                vin_start=args.vin_start,
                vin_stop=args.vin_stop,
                vin_step=args.vin_step,
                vdd=args.vdd,
                n_conversions=args.n_conversions,
            )
        )
        print(f"Results shape: {results.shape}")
    else:
        import os

        from cocotb.runner import get_runner

        os.environ["SCAN_VIN_START"] = str(args.vin_start)
        os.environ["SCAN_VIN_STOP"] = str(args.vin_stop)
        os.environ["SCAN_VIN_STEP"] = str(args.vin_step)
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
