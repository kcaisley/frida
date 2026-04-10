"""Scan: Comparator threshold measurement via cosimulation.

Sweeps a fine voltage range around 0mV differential to find the
comparator trip point. Uses only sample + compare phases (no full
SAR conversion).

Usage (from repo root):
    uv run python flow/scans/scan_comp.py
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


@cocotb.test()
async def scan_comp_threshold(dut):
    """Sweep fine voltage steps and record comparator output."""

    import os
    vin_start = float(os.environ.get("SCAN_VIN_START", "-0.005"))
    vin_stop = float(os.environ.get("SCAN_VIN_STOP", "0.005"))
    vin_step = float(os.environ.get("SCAN_VIN_STEP", "0.0005"))
    vdd = float(os.environ.get("SCAN_VDD", "1.2"))
    cm = vdd / 2

    voltages = np.arange(vin_start, vin_stop + vin_step / 2, vin_step)
    duration_ns = 500 + len(voltages) * 200

    # Start clocks
    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, units="ps").start())
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, units="ps").start())

    # Create bridge
    adc_block = create_adc_block(vdd=vdd)
    bridge = MixedSignalBridge(dut, [adc_block], max_sync_interval_ns=1.0)
    await bridge.start(duration_ns=duration_ns, analog_vcd="scan_comp.vcd")

    # Initialize chip
    peripherals = SimpleNamespace(awg=SimAWG(bridge), psu=SimPSU(vdd))
    chip = Frida(dut, peripherals)
    await chip.init()

    # Configure ADC 0 with only samp + comp (no init, no update)
    chip.select_adc(0)
    chip.enable_adc(
        0,
        en_init=False,
        en_samp_p=True,
        en_samp_n=True,
        en_comp=True,
        en_update=False,
    )
    chip.set_dac_state(astate_p=0x8000, astate_n=0x8000)  # mid-scale
    await chip.write_spi()

    # Sweep
    results = []
    for diff in voltages:
        await chip.set_vin(diff=diff, cm=cm)
        comp_out = await chip.sample_and_compare()
        results.append(comp_out)
        dut._log.info("vin_diff=%+.4fV: comp_out=%d", diff, comp_out)

    # Find transition
    results_arr = np.array(results)
    transitions = np.where(np.diff(results_arr) != 0)[0]
    if len(transitions) > 0:
        idx = transitions[0]
        threshold = (voltages[idx] + voltages[idx + 1]) / 2
        dut._log.info("Comparator threshold: %.4fV", threshold)
    else:
        dut._log.warning("No transition detected in sweep range")

    await bridge.stop()


def main():
    parser = argparse.ArgumentParser(description="Comparator threshold scan")
    parser.add_argument("--vin-start", type=float, default=-0.005)
    parser.add_argument("--vin-stop", type=float, default=0.005)
    parser.add_argument("--vin-step", type=float, default=0.0005)
    parser.add_argument("--vdd", type=float, default=1.2)
    args = parser.parse_args()

    import os
    os.environ["SCAN_VIN_START"] = str(args.vin_start)
    os.environ["SCAN_VIN_STOP"] = str(args.vin_stop)
    os.environ["SCAN_VIN_STEP"] = str(args.vin_step)
    os.environ["SCAN_VDD"] = str(args.vdd)

    runner = get_runner("icarus")
    runner.build(
        verilog_sources=verilog_sources(),
        includes=include_dirs(),
        hdl_toplevel="tb_integration",
        build_dir=str(REPO / "scratch" / "scan_comp"),
        defines=["COCOTBEXT_AMS"],
    )
    runner.test(
        hdl_toplevel="tb_integration",
        test_module="flow.scans.scan_comp",
    )


if __name__ == "__main__":
    main()
