"""Scan: Run ADC conversions via cocotb-native cosimulation.

Uses cocotbext-ams to bridge the analog ADC subcircuit with the Icarus
digital simulation. The scan IS the cocotb test — no socket IPC.

Usage (from repo root):
    uv run python flow/scans/scan_adc.py
    uv run python flow/scans/scan_adc.py --vin 0.3 --n-conversions 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import cocotb
from cocotb.clock import Clock
from cocotb.runner import get_runner

from cocotbext.ams import MixedSignalBridge

from flow.scans.chip import Frida
from flow.scans.sim import (
    SimAWG,
    SimPSU,
    create_adc_block,
    include_dirs,
    verilog_sources,
)

REPO = Path(__file__).resolve().parents[2]


# =========================================================================
# cocotb test
# =========================================================================

@cocotb.test()
async def scan_adc_simple(dut):
    """Sweep differential input voltage and record ADC output codes."""

    # Read parameters from environment (set by the runner at bottom)
    import os
    vin_start = float(os.environ.get("SCAN_VIN_START", "-0.6"))
    vin_stop = float(os.environ.get("SCAN_VIN_STOP", "0.6"))
    vin_step = float(os.environ.get("SCAN_VIN_STEP", "0.05"))
    vdd = float(os.environ.get("SCAN_VDD", "1.2"))
    n_conversions = int(os.environ.get("SCAN_N_CONVERSIONS", "1"))
    cm = vdd / 2

    voltages = np.arange(vin_start, vin_stop + vin_step / 2, vin_step)
    duration_ns = 500 + len(voltages) * n_conversions * 200

    # Start clocks
    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, units="ps").start())  # 160 MHz
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, units="ps").start())  # 400 MHz

    # Create the mixed-signal bridge
    adc_block = create_adc_block(vdd=vdd)
    bridge = MixedSignalBridge(dut, [adc_block], max_sync_interval_ns=1.0)
    await bridge.start(duration_ns=duration_ns, analog_vcd="scan_adc.vcd")

    # Initialize chip
    peripherals = SimpleNamespace(awg=SimAWG(bridge), psu=SimPSU(vdd))
    chip = Frida(dut, peripherals)
    await chip.init()

    # Configure ADC 0
    chip.select_adc(0)
    chip.enable_adc(0)
    chip.set_dac_state(astate_p=0xFFFF, astate_n=0xFFFF)
    await chip.write_spi()

    # Sweep
    results = []
    for diff in voltages:
        await chip.set_vin(diff=diff, cm=cm)
        bits = await chip.run_conversion(n_conversions)
        results.append(bits)
        dut._log.info(
            "vin_diff=%.3fV: bits=%s", diff,
            "".join(str(b) for b in bits[0]),
        )

    # Log summary
    all_bits = np.concatenate(results, axis=0)
    dut._log.info("Scan complete: %d voltage steps, %d total conversions",
                  len(voltages), all_bits.shape[0])

    await bridge.stop()


# =========================================================================
# Runner (invoked from CLI)
# =========================================================================

def main():
    parser = argparse.ArgumentParser(description="ADC cosimulation scan")
    parser.add_argument("--vin-start", type=float, default=-0.6)
    parser.add_argument("--vin-stop", type=float, default=0.6)
    parser.add_argument("--vin-step", type=float, default=0.05)
    parser.add_argument("--vdd", type=float, default=1.2)
    parser.add_argument("--n-conversions", type=int, default=1)
    parser.add_argument("--sim", choices=["icarus"], default="icarus")
    args = parser.parse_args()

    import os
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
    )
    runner.test(
        hdl_toplevel="tb_integration",
        test_module="flow.scans.scan_adc",
    )


if __name__ == "__main__":
    main()
