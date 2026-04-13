"""Scan: Comparator threshold measurement.

Sweeps a fine voltage range around 0mV differential to find the
comparator trip point. Uses only sample + compare phases (no full
SAR conversion).

The scan logic is backend-agnostic. Entry points handle sim/hw setup.

Usage (simulation, from repo root):
    uv run python flow/scans/scan_comp.py
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


async def scan_comp(
    chip: Frida,
    voltages: np.ndarray,
    cm: float = 0.6,
) -> dict:
    """Sweep fine voltage steps and find comparator threshold.

    Args:
        chip: Initialized Frida controller (any backend).
        voltages: Array of differential voltages to sweep.
        cm: Common-mode voltage.

    Returns:
        Dict with 'voltages', 'results', and optionally 'threshold'.
    """
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

    results = []
    for diff in voltages:
        await chip.set_vin(diff=float(diff), cm=cm)
        comp_out = await chip.sample_and_compare()
        results.append(comp_out)
        logger.info("vin_diff=%+.4fV: comp_out=%d", diff, comp_out)

    results_arr = np.array(results)
    output: dict = {"voltages": voltages, "results": results_arr}

    transitions = np.where(np.diff(results_arr) != 0)[0]
    if len(transitions) > 0:
        idx = transitions[0]
        threshold = (voltages[idx] + voltages[idx + 1]) / 2
        output["threshold"] = threshold
        logger.info("Comparator threshold: %.4fV", threshold)
    else:
        logger.warning("No transition detected in sweep range")

    return output


# =========================================================================
# Simulation entry point (cocotb + cocotbext-ams)
# =========================================================================


@cocotb.test()
async def scan_comp_sim(dut):
    """cocotb entry point — sets up clocks, bridge, then runs scan."""
    import os

    vin_start = float(os.environ.get("SCAN_VIN_START", "-0.005"))
    vin_stop = float(os.environ.get("SCAN_VIN_STOP", "0.005"))
    vin_step = float(os.environ.get("SCAN_VIN_STEP", "0.0005"))
    vdd = float(os.environ.get("SCAN_VDD", "1.2"))

    voltages = np.arange(vin_start, vin_stop + vin_step / 2, vin_step)
    duration_ns = 500 + len(voltages) * 200

    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, units="ps").start())
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, units="ps").start())

    adc_block = create_adc_block(vdd=vdd)
    bridge = MixedSignalBridge(dut, [adc_block], max_sync_interval_ns=1.0)
    await bridge.start(duration_ns=duration_ns, analog_vcd="scan_comp.vcd")

    backend = SimBackend(dut)
    peripherals = SimpleNamespace(awg=SimAWG(bridge), psu=SimPSU(vdd))
    chip = Frida(backend, peripherals)
    await chip.init()

    await scan_comp(chip, voltages, cm=vdd / 2)

    await bridge.stop()


# =========================================================================
# Hardware entry point (basil DAQ over SiTcp)
# =========================================================================


async def scan_comp_hw(
    vin_start: float = -0.005,
    vin_stop: float = 0.005,
    vin_step: float = 0.0005,
    vdd: float = 1.2,
) -> dict:
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
    return await scan_comp(chip, voltages, cm=vdd / 2)


# =========================================================================
# CLI runner
# =========================================================================


def main():
    parser = argparse.ArgumentParser(description="Comparator threshold scan")
    parser.add_argument("--vin-start", type=float, default=-0.005)
    parser.add_argument("--vin-stop", type=float, default=0.005)
    parser.add_argument("--vin-step", type=float, default=0.0005)
    parser.add_argument("--vdd", type=float, default=1.2)
    parser.add_argument("--hw", action="store_true", help="Run on hardware instead of sim")
    args = parser.parse_args()

    if args.hw:
        import asyncio

        result = asyncio.run(
            scan_comp_hw(
                vin_start=args.vin_start,
                vin_stop=args.vin_stop,
                vin_step=args.vin_step,
                vdd=args.vdd,
            )
        )
        if "threshold" in result:
            print(f"Threshold: {result['threshold']:.4f}V")
        else:
            print("No transition detected")
    else:
        import os
        from cocotb.runner import get_runner

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
