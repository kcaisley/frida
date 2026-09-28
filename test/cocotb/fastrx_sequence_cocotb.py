"""Wrapped RX_SEN with host-controlled receiver stop before sequencer reset."""

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

from flow.adc.sim import AdcTbParams
from flow.scans.fastrx import convert_fastrx_words_to_adc
from flow.scans.seqgen import build_fastrx_capture_pattern


@cocotb.test()
async def capture_frames(dut):
    cocotb.start_soon(Clock(dut.bus_clk, 10, unit="ns").start())
    cocotb.start_soon(Clock(dut.seq_clk, 6, unit="ns").start())

    async def write(address, value, rx=False):
        await FallingEdge(dut.bus_clk)
        dut.addr.value = address
        dut.data.value = value
        dut.rx_wr.value = int(rx)
        dut.seq_wr.value = int(not rx)
        await FallingEdge(dut.bus_clk)
        dut.rx_wr.value = 0
        dut.seq_wr.value = 0

    async def register(address, value):
        for byte in range(4):
            await write(address + byte, (value >> (8 * byte)) & 255)

    for words, start, conversions in (
        (20, 0, 1),
        (20, 0, 4),
        (20, 7, 1),
        (20, 7, 4),
        (20, 3, 3),
        (20, 2, 3),
        (32, 9, 3),
        (20, 7, 2050),
    ):
        dut.rst.value = 1
        dut.addr.value = 0
        dut.data.value = 0
        dut.seq_wr.value = 0
        dut.rx_wr.value = 0
        dut.fifo_read.value = 0
        await Timer(1500, unit="ns")
        dut.rst.value = 0
        await Timer(100, unit="ns")
        row = "".join(f"{word + 1:08b}" for word in range(words))
        params = AdcTbParams(seq_init_pattern=row, seq_samp_pattern=row, seq_comp_pattern=row, seq_logic_pattern=row)
        program = build_fastrx_capture_pattern(params, start, 17)
        bits = [int(x) for x in "10110001011100101"]
        # Use the spare sequencer test-data lane as a deterministic COMP_OUT stream.
        for i in range(len(program) // 8):
            position = i % words
            bit = (position - start) % words
            if bit < 17 and bits[bit]:
                program[8 * i + 4] |= 2
        # The sequencer shows its last physical RAM word while reset.
        for i in range(1024):
            await write(64 + i, 0)
        for i, value in enumerate(program):
            await write(64 + i, value)
        await register(4, len(program) // 8)
        await register(8, 0)
        await register(12, 0)
        await register(16, 0)
        await register(20, 0)
        await register(24, 0)
        await register(28, 0)
        await write(3, 1)
        await write(2, 1, rx=True)
        received = []

        async def drain(received=received):
            while True:
                await FallingEdge(dut.bus_clk)
                valid = not int(dut.fifo_empty.value)
                dut.fifo_read.value = int(valid)
                if valid:
                    received.append(int(dut.fifo_data.value))

        observed_controls = []

        async def monitor(observed=observed_controls):
            while True:
                await FallingEdge(dut.seq_clk)
                observed.append(int(dut.seq_out.value) & 0xFFFFFFFF)

        monitor_task = cocotb.start_soon(monitor())
        drain_task = cocotb.start_soon(drain())
        await write(1, 0)
        # Keep repeating until all requested frames have crossed into the FIFO.
        startup = int(start + 17 > words)
        for _ in range(conversions + 100):
            if len(received) >= conversions + startup:
                break
            await Timer(words * 6, unit="ns")
        else:
            raise AssertionError("receiver did not produce requested frames")
        await write(2, 0, rx=True)
        await write(0, 0)
        await Timer(3000, unit="ns")
        assert int(dut.seq.DONE.value) == 1
        count = len(received)
        await Timer(3000, unit="ns")
        assert len(received) == count, "receiver kept writing after completion"
        drain_task.cancel()
        monitor_task.cancel()
        controls = [int.from_bytes(program[i : i + 4], "little") for i in range(0, len(program), 8)]
        expected_controls = controls * (conversions + startup)
        first = observed_controls.index(expected_controls[0])
        assert observed_controls[first : first + len(expected_controls)] == expected_controls
        dut.fifo_read.value = 0
        startup = int(start + 17 > words)
        assert len(received) >= conversions + startup, (words, start, conversions, len(received), received[:5])
        bout, _, _ = convert_fastrx_words_to_adc(received, 17, [1] * 17, 12)
        np.testing.assert_array_equal(bout[startup : startup + conversions], np.tile(bits, (conversions, 1)))
