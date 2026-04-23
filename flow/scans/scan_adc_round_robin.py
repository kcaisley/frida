"""Scan: ADC round-robin with always-on sample clock and continuous comparator clock.

This scan is based on `scan_adc.py`, but changes the sequencer behavior to:
- keep `CLK_SAMP` asserted continuously
- toggle `CLK_COMP` continuously at 200 MHz
  (2.5 ns high, 2.5 ns low on the 400 MHz sequencer grid)
- loop through ADCs 0..15, selecting and enabling one ADC at a time
- write the chip registers after each ADC selection/update

Simulation runs a finite scan and captures data.
Hardware uses the FPGA sequencer in free-running mode and only clocks/switches
ADCs continuously; it does not capture or parse comparator output.

No analog input voltage is driven in this scan. Entry points handle sim
(cocotb + cocotbext-ams) and hardware (basil DAQ) setup/teardown.

Usage (simulation, from repo root):
    uv run python flow/scans/scan_adc_round_robin.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotbext.ams import MixedSignalBridge

from flow.scans import daq
from flow.scans.chip import N_ADCS, N_COMP_BITS, Frida, SimBackend, pack_seq_tracks
from flow.scans.sim import SimAWG, SimPSU, create_adc_block, include_dirs, verilog_sources

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]


def _generate_round_robin_sequence(
    conversion_period_ns: int = 100,
    seq_clk_period_ns: float = 2.5,
    n_comp_bits: int = N_COMP_BITS,
    capture_delay_steps: int = 1,
) -> dict[str, list[int]]:
    """Generate a sequencer pattern with always-on sample clock.

    The sequencer runs at 400 MHz (2.5 ns/step). This pattern:
    - keeps `CLK_SAMP` high for the full sequence
    - toggles `CLK_COMP` every other step, yielding 200 MHz
    - toggles `CLK_LOGIC` on the opposite phase for the first 16 decisions
    - generates `CLK_COMP_CAP` delayed from the comparator clock edges
    - keeps `SEN_COMP` high across the active comparison/capture window
    """
    n_steps = int(conversion_period_ns / seq_clk_period_ns)

    clk_init = [0] * n_steps
    clk_samp = [1] * n_steps
    clk_comp = [0] * n_steps
    clk_logic = [0] * n_steps
    clk_comp_cap = [0] * n_steps
    sen_comp = [0] * n_steps

    # CLK_LOGIC is kept low throughout the pattern
    # CLK_SAMP is kept high throughout the pattern
    comp_start = 0
    # n_logic_bits = max(n_comp_bits - 1, 0) - removed as CLK_LOGIC is not used

    for bit in range(n_comp_bits):
        comp_step = comp_start + bit * 2
        if comp_step < n_steps:
            clk_comp[comp_step] = 1
        # CLK_LOGIC remains low throughout the pattern

        sample_step = comp_start + bit * 2 + 1 + capture_delay_steps
        if sample_step < n_steps:
            clk_comp_cap[sample_step] = 1

    sen_start = comp_start
    last_capture = comp_start + (n_comp_bits - 1) * 2 + 1 + capture_delay_steps
    sen_end = min(last_capture + 2, n_steps)
    for i in range(sen_start, sen_end):
        sen_comp[i] = 1

    return {
        "CLK_INIT": clk_init,
        "CLK_SAMP": clk_samp,
        "CLK_COMP": clk_comp,
        "CLK_LOGIC": clk_logic,
        "CLK_COMP_CAP": clk_comp_cap,
        "SEN_COMP": sen_comp,
    }


async def configure_round_robin_sequencer(
    chip: Frida,
    conversion_period_ns: int = 100,
    seq_clk_period_ns: float = 2.5,
    capture_delay_steps: int = 1,
) -> None:
    """Load the always-on sample / continuous comparator sequence."""
    seq = _generate_round_robin_sequence(
        conversion_period_ns=conversion_period_ns,
        seq_clk_period_ns=seq_clk_period_ns,
        capture_delay_steps=capture_delay_steps,
    )
    n_steps = len(seq["CLK_SAMP"])
    chip._seq_n_steps = n_steps
    mem_data = pack_seq_tracks(seq)
    await daq.seq_load(chip._backend, mem_data, n_steps)


async def scan_adc_round_robin_once(
    chip: Frida,
    n_conversions: int = 1,
    n_rounds: int = 1,
) -> dict[int, np.ndarray]:
    """Run one finite round-robin pass through ADCs 0..15.

    For each ADC:
    - disable all ADCs
    - select the ADC on the output mux
    - enable only that ADC
    - write registers
    - run conversions

    Returns:
        Mapping from ADC index to captured bit arrays of shape
        `(n_rounds, n_conversions, 17)`.
    """
    await configure_round_robin_sequencer(chip)

    chip.set_dac_state(
        astate_p=0x7FFF,
        bstate_p=0x7FFF,
        astate_n=0x7FFF,
        bstate_n=0x7FFF,
    )

    results: dict[int, np.ndarray] = {}

    for adc in range(N_ADCS):
        chip.disable_all_adcs()
        chip.select_adc(adc)
        chip.enable_adc(
            adc,
            en_init=True,
            en_samp_p=True,
            en_samp_n=True,
            en_comp=True,
            en_update=True,
            dac_mode=False,
            dac_diffcaps=False,
        )
        await chip.reg_write()

        bits = await chip.run_conversions(n_conversions=n_conversions, repetitions=n_rounds)
        results[adc] = bits

        logger.info(
            "Round-robin ADC %d complete: %d rounds x %d conversions, first bits=%s",
            adc,
            n_rounds,
            n_conversions,
            "".join(str(b) for b in bits[0, 0]),
        )

    return results


@cocotb.test()
async def scan_adc_round_robin_sim(dut):
    """cocotb entry point — sets up clocks, bridge, then runs scan."""
    import os

    vdd = float(os.environ.get("SCAN_VDD", "1.2"))
    n_conversions = int(os.environ.get("SCAN_N_CONVERSIONS", "1"))
    n_rounds = int(os.environ.get("SCAN_N_ROUNDS", "1"))
    duration_ns = 1000 + N_ADCS * n_rounds * n_conversions * 200

    cocotb.start_soon(Clock(dut.BUS_CLK, 6250, units="ps").start())
    cocotb.start_soon(Clock(dut.SEQ_CLK, 2500, units="ps").start())
    cocotb.start_soon(Clock(dut.SPI_CLK, 100_000, units="ps").start())

    adc_block = create_adc_block(vdd=vdd)
    bridge = MixedSignalBridge(dut, [adc_block], max_sync_interval_ns=1.0)
    await bridge.start(duration_ns=duration_ns, analog_vcd="scan_adc_round_robin.vcd")

    backend = SimBackend(dut)
    peripherals = SimpleNamespace(awg=SimAWG(bridge), psu=SimPSU(vdd))
    chip = Frida(backend, peripherals)
    await chip.init()

    await scan_adc_round_robin_once(
        chip,
        n_conversions=n_conversions,
        n_rounds=n_rounds,
    )

    await bridge.stop()


async def scan_adc_round_robin_hw(
    vdd: float = 1.2,
    n_conversions: int = 1,
) -> None:
    """Hardware entry point — free-run sequencer, continuously clock comparator during ADC switching."""
    from basil.dut import Dut

    from flow.scans.chip import HardwareBackend
    from flow.scans.peripherals import BasilPSU

    yaml_path = Path(__file__).resolve().parent / "map_fpga.yaml"
    daq_dev = Dut(str(yaml_path))
    daq_dev.init()

    backend = HardwareBackend(daq_dev)
    peripherals = SimpleNamespace(psu=BasilPSU(daq_dev))

    chip = Frida(backend, peripherals)
    await chip.init()

    await configure_round_robin_sequencer(chip)
    chip.set_dac_state(
        astate_p=0x7FFF,
        bstate_p=0x7FFF,
        astate_n=0x7FFF,
        bstate_n=0x7FFF,
    )
    await chip.reg_write()

    # Calculate total steps for one full conversion cycle
    total_steps = chip._seq_n_steps * n_conversions

    # Start the sequencer with infinite repeat
    await daq.seq_trigger(chip._backend, total_steps, repeat=0)
    logger.info(
        "Started free-running hardware sequencer: %d steps per cycle, repeat=0 (infinite)",
        total_steps,
    )
    await daq.seq_trigger(chip._backend, total_steps, repeat=0)
    logger.info(
        "Started free-running hardware sequencer: %d steps per cycle, repeat=0 (infinite)",
        total_steps,
    )

    # Calculate total steps for one full conversion cycle
    total_steps = chip._seq_n_steps * n_conversions

    # Configure and start the sequencer
    await daq.seq_trigger(chip._backend, total_steps, repeat=0)
    logger.info(
        "Started free-running hardware sequencer: %d steps per cycle, repeat=0 (infinite)",
        total_steps,
    )

    pass_index = 0
    while True:
        pass_index += 1
        logger.info("Starting hardware ADC switch pass %d", pass_index)

        # The sequencer is already running continuously
        # Just wait for 1 second before switching ADCs
        await asyncio.sleep(1.0)

        for adc in range(N_ADCS):
            chip.disable_all_adcs()
            chip.select_adc(adc)
            chip.enable_adc(
                adc,
                en_init=True,
                en_samp_p=True,
                en_samp_n=True,
                en_comp=True,
                en_update=True,
                dac_mode=False,
                dac_diffcaps=False,
            )
            await chip.reg_write()
            logger.info("Hardware free-run active ADC=%d", adc)

            # The sequencer continues running while we wait
            # Just wait for 1 second after switching ADCs
            await asyncio.sleep(1.0)


def main():
    parser = argparse.ArgumentParser(description="ADC round-robin scan with always-on sample clock")
    parser.add_argument("--vdd", type=float, default=1.2)
    parser.add_argument("--n-conversions", type=int, default=1)
    parser.add_argument("--n-rounds", type=int, default=1, help="Finite rounds for simulation only")
    parser.add_argument("--sim", choices=["icarus"], default="icarus")
    parser.add_argument("--hw", action="store_true", help="Run on hardware instead of sim")
    args = parser.parse_args()

    if args.hw:
        import asyncio

        asyncio.run(
            scan_adc_round_robin_hw(
                vdd=args.vdd,
                n_conversions=args.n_conversions,
            )
        )
    else:
        import os

        from cocotb_tools.runner import get_runner

        os.environ["SCAN_VDD"] = str(args.vdd)
        os.environ["SCAN_N_CONVERSIONS"] = str(args.n_conversions)
        os.environ["SCAN_N_ROUNDS"] = str(args.n_rounds)

        runner = get_runner(args.sim)
        runner.build(
            sources=verilog_sources(),
            includes=include_dirs(),
            hdl_toplevel="tb_integration",
            build_dir=str(REPO / "scratch" / "scan_adc_round_robin"),
            defines={"COCOTBEXT_AMS": 1},
            waves=True,
            timescale=("1ns", "1ps"),
        )
        runner.test(
            hdl_toplevel="tb_integration",
            test_module="flow.scans.scan_adc_round_robin",
            waves=True,
        )


if __name__ == "__main__":
    main()
