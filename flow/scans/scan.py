"""Unified FRIDA chip scan.

CLI entry point: ``run_scan(args)``, called from ``flow/cli.py``.
Core loop: ``main_loop(chip, params)`` — backend-agnostic, operates
only through the ``Frida`` class.

Sequence values dispatched through ``chip.configure_sequencer()``:
  - "none"      → no sequencer loaded; SPI register write/readback only
  - "adc"       → full SAR conversion
  - "comp"      → continuous comp clock
  - "samp_comp" → single sample+compare
  - "calib"     → init→sample→comp→DAC→comp
  - "fastrx"    → fast_spi_rx loopback test pattern
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotbext.ams import MixedSignalBridge

from flow.scans.chip import Frida, SimBackend
from flow.scans.sim import (
    SimAWG,
    SimPSU,
    create_adc_block,
    include_dirs,
    verilog_sources,
)

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]


# Backend-agnostic scan loop


async def main_loop(
    chip: Frida,
    *,
    sequence: str = "none",
    channels: list[int],
    dacmode: str = "normal",
    dacstate: list[int],
    diffcaps: bool = False,
    input_mode: str = "manual",
    vdd: float = 1.2,
    rate: int = 1,
    cycles: int = 1,
    loopback: str = "none",
    save: bool = False,
) -> dict:
    """Run the unified scan loop across channels and input voltages.

    Steps:
      0. Release chip reset
      1. Load sequencer pattern (unless ``sequence == "none"``)
      2. For each channel:
         a. Configure ADC, set DAC state, write SPI, read back, verify
         b. For each input voltage step (or once in manual mode):
            - Set vin via AWG (unless manual)
            - Trigger sequencer + capture results
         c. Accumulate results
      3. Print results to stdout; optionally save NPZ to scratch/scan/

    Args:
        chip: Initialized ``Frida`` instance (any backend).
        sequence: One of ``"none"``, ``"adc"``, ``"comp"``,
            ``"samp_comp"``, ``"calib"``.
        channels: List of ADC channel indices [0..15].
        dacmode: ``"normal"`` (A-state only) or ``"calib"`` (A→B transition).
        dacstate: List of integer DAC state values. Length 2 for ``normal``
            (astate_p, astate_n), length 4 for ``calib`` (A_P, A_N, B_P, B_N).
        diffcaps: Whether DAC differential caps mode is enabled.
        input_mode: ``"manual"``, ``"dc"``, ``"ramp"``, ``"sine"``.
        vdd: Supply voltage in volts (used as common-mode reference).
        rate: Sequencer clock divider; 1 = full speed.
        cycles: Number of sequence repetitions per voltage step.
            0 = run continuously until Ctrl+C (KeyboardInterrupt).
        save: If True, also write results as NPZ to scratch/scan/.
        loopback: One of ``"none"``, ``"spi"``, ``"fastrx"``, ``"both"``.
            Enables SPI loopback, fast-RX loopback, or both.

    Returns:
        Nested dict: ``{channel_index: list[np.ndarray]}``.
    """
    # Step 0: ensure chip is out of reset
    await chip.reset()

    # Step 0b: configure loopback modes
    await chip.set_spi_loopback(loopback in ("spi", "both"))
    await chip.set_fastrx_loopback(loopback in ("fastrx", "both"))

    # Step 1: load sequencer
    if sequence != "none":
        await chip.configure_sequencer(
            sequence,
            seq_clk_div=rate,
        )

    # Fast RX test mode: no chip configuration needed
    if sequence == "fastrx":
        bits = await chip.run_conversions(
            n_conversions=1,
            repetitions=cycles,
        )
        return {"fastrx": [bits]}

    # Build voltage table from input_mode
    cm = vdd / 2
    if input_mode == "manual":
        voltage_entries: list[dict[str, float] | None] = [None]
    elif input_mode == "dc":
        voltage_entries = [{"diff": 0.0, "cm": cm}]
    elif input_mode == "ramp":
        voltages = np.arange(-0.005, 0.0055, 0.0005)
        voltage_entries = [{"diff": float(v), "cm": cm} for v in voltages]
    elif input_mode == "sine":
        t = np.linspace(0, 2 * np.pi, 64, endpoint=False)
        voltage_entries = [{"diff": 0.005 * np.sin(ti), "cm": cm} for ti in t]
    else:
        raise ValueError(f"Unknown input mode {input_mode!r}")

    # Parse DAC state
    if dacmode == "normal":
        if len(dacstate) < 2:
            raise ValueError(f"normal mode expects 2 DAC values, got {len(dacstate)}")
        astate_p, astate_n = dacstate[0], dacstate[1]
        bstate_p, bstate_n = 0x7FFF, 0x7FFF
    elif dacmode == "calib":
        if len(dacstate) < 4:
            raise ValueError(f"calib mode expects 4 DAC values, got {len(dacstate)}")
        astate_p, astate_n, bstate_p, bstate_n = dacstate[:4]
    else:
        raise ValueError(f"Unknown dacmode {dacmode!r}")

    # Channel loop + voltage loop

    results: dict[int, list[np.ndarray]] = {ch: [] for ch in channels}

    for channel in channels:
        chip.disable_all_adcs()
        chip.select_adc(channel)

        if sequence in ("samp_comp", "comp"):
            chip.enable_adc(
                channel,
                en_init=False,
                en_samp_p=True,
                en_samp_n=True,
                en_comp=True,
                en_update=False,
                dac_mode=(dacmode == "calib"),
                dac_diffcaps=diffcaps,
            )
        else:
            chip.enable_adc(
                channel,
                en_init=True,
                en_samp_p=True,
                en_samp_n=True,
                en_comp=True,
                en_update=True,
                dac_mode=(dacmode == "calib"),
                dac_diffcaps=diffcaps,
            )

        chip.set_dac_state(
            astate_p=astate_p,
            bstate_p=bstate_p,
            astate_n=astate_n,
            bstate_n=bstate_n,
        )

        await chip.reg_write()
        logger.info(
            "SPI register programmed: ch=%d, dacstate=%s, dacmode=%s, diffcaps=%s",
            channel,
            dacstate,
            dacmode,
            diffcaps,
        )

        # Voltage sweep
        for vi, ventry in enumerate(voltage_entries):
            if input_mode != "manual" and ventry is not None:
                await chip.set_vin(diff=ventry["diff"], cm=ventry["cm"])

            if sequence == "none":
                continue

            if cycles == 0:
                # Continuous mode — stream each conversion as it arrives
                try:
                    while True:
                        bits = await chip.run_conversions(
                            n_conversions=1,
                            repetitions=1,
                        )
                        results[channel].append(bits)
                except (asyncio.CancelledError, KeyboardInterrupt):
                    logger.info("Continuous capture interrupted, stopping...")
            else:
                bits = await chip.run_conversions(
                    n_conversions=1,
                    repetitions=cycles,
                )
                results[channel].append(bits)

            if input_mode == "manual":
                break

    # Optionally save NPZ to scratch/scan/
    if save:
        outdir = REPO / "scratch" / "scan"
        outdir.mkdir(parents=True, exist_ok=True)
        np.savez(
            outdir / f"scan_{sequence}.npz",
            channels=channels,
            results={ch: [r.tolist() for r in res] for ch, res in results.items()},
            dacstate=dacstate,
            dacmode=dacmode,
            input_mode=input_mode,
            vdd=vdd,
        )
        logger.info("Results saved to %s", outdir)

    return {ch: res for ch, res in results.items()}


# CLI dispatcher — called from flow/cli.py


def run_scan(args):
    """Entry point from the CLI. ``args`` is the argparse namespace.

    Branches into simulation (cocotb runner) or hardware (basil Dut + Frida).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - [%(levelname)s] (%(threadName)s) %(message)s",
    )
    if args.emulate:
        _run_scan_sim(args)
    else:
        asyncio.run(_run_scan_hw(args))


# Simulation path


def _build_scan_env(args) -> dict[str, str]:
    env = {
        "SCAN_SEQUENCE": args.sequence,
        "SCAN_RATE": str(args.rate),
        "SCAN_CYCLES": str(args.cycles),
        "SCAN_LOOPBACK": args.loopback,
        "SCAN_SAVE": str(args.save).lower(),
    }
    if args.channel is not None:
        env["SCAN_CHANNELS"] = ",".join(str(c) for c in args.channel)
    if args.dacmode is not None:
        env["SCAN_DACMODE"] = args.dacmode
    if args.dacstate is not None:
        env["SCAN_DACSTATE"] = ",".join(str(v) for v in args.dacstate)
    if args.diffcaps is not None:
        env["SCAN_DIFFCAPS"] = str(args.diffcaps).lower()
    if args.input_mode is not None:
        env["SCAN_INPUT"] = args.input_mode
    if args.vdd is not None:
        env["SCAN_VDD"] = str(args.vdd)
    return env


def _run_scan_sim(args):
    import os

    from cocotb_tools.runner import get_runner

    env = _build_scan_env(args)
    for key, val in env.items():
        os.environ[key] = val

    build_dir = REPO / "scratch" / "scan"

    runner = get_runner("icarus")
    runner.build(
        sources=verilog_sources(),
        includes=include_dirs(),
        hdl_toplevel="tb_integration",
        build_dir=str(build_dir),
        defines={"COCOTBEXT_AMS": 1},
        waves=True,
        timescale=("1ns", "1ps"),
    )
    runner.test(
        hdl_toplevel="tb_integration",
        test_module="flow.scans.scan",
        waves=True,
    )


# Hardware path


async def _run_scan_hw(args):
    from types import SimpleNamespace

    from basil.dut import Dut

    from flow.scans.chip import HardwareBackend
    from flow.scans.peripherals import BasilPSU

    yaml_path = REPO / "flow" / "scans" / "map_fpga.yaml"
    daq = Dut(str(yaml_path))
    daq.init()

    backend = HardwareBackend(daq)

    try:
        from flow.scans.peripherals import BasilAWG

        peripherals = SimpleNamespace(
            awg=BasilAWG(),
            psu=BasilPSU(daq),
        )
    except Exception:
        peripherals = SimpleNamespace(psu=BasilPSU(daq))

    chip = Frida(backend, peripherals)
    await chip.init(write_initial_spi=False)

    await main_loop(
        chip,
        sequence=args.sequence,
        channels=args.channel,
        dacmode=args.dacmode,
        dacstate=args.dacstate,
        diffcaps=args.diffcaps,
        input_mode=args.input_mode,
        vdd=args.vdd,
        rate=args.rate,
        cycles=args.cycles,
        loopback=args.loopback,
        save=args.save,
    )


# cocotb test entry point


@cocotb.test(skip=False)
async def sim_scan(dut):
    import os
    from types import SimpleNamespace

    sequence = os.environ.get("SCAN_SEQUENCE", "none")
    channels = [int(c) for c in os.environ.get("SCAN_CHANNELS", "0").split(",")]
    dacmode = os.environ.get("SCAN_DACMODE", "normal")
    dacstate = [int(v) for v in os.environ.get("SCAN_DACSTATE", "32767,32767").split(",")]
    diffcaps = os.environ.get("SCAN_DIFFCAPS", "false").lower() == "true"
    input_mode = os.environ.get("SCAN_INPUT", "manual")
    vdd = float(os.environ.get("SCAN_VDD", "1.2"))
    rate = int(os.environ.get("SCAN_RATE", "1"))
    cycles = int(os.environ.get("SCAN_CYCLES", "1"))
    loopback = os.environ.get("SCAN_LOOPBACK", "none")
    save = os.environ.get("SCAN_SAVE", "false").lower() == "true"

    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, units="ps").start())
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, units="ps").start())
    cocotb.start_soon(Clock(dut.SPI_CLK, 100_000, units="ps").start())

    adc_block = create_adc_block(vdd=vdd)
    bridge = MixedSignalBridge(dut, [adc_block], max_sync_interval_ns=1.0)

    duration_ns = 1000 + len(channels) * cycles * 200
    await bridge.start(duration_ns=duration_ns, analog_vcd=f"scan_{sequence}.vcd")

    backend = SimBackend(dut)
    peripherals = SimpleNamespace(awg=SimAWG(bridge), psu=SimPSU(vdd))
    chip = Frida(backend, peripherals)
    await chip.init(write_initial_spi=False)

    await main_loop(
        chip,
        sequence=sequence,
        channels=channels,
        dacmode=dacmode,
        dacstate=dacstate,
        diffcaps=diffcaps,
        input_mode=input_mode,
        vdd=vdd,
        rate=rate,
        cycles=cycles,
        loopback=loopback,
        save=save,
    )

    await bridge.stop()
