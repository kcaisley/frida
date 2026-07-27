"""Cocotb checks for the dual-channel SAR logic."""

import cocotb
from cocotb.triggers import Timer

DAC_WIDTH = 16
DAC_MASK = (1 << DAC_WIDTH) - 1


async def pulse_update(dut) -> None:
    """Apply one rising edge to the SAR update clock."""

    dut.clk_update.value = 0
    await Timer(1, unit="ns")
    dut.clk_update.value = 1
    await Timer(1, unit="ns")
    dut.clk_update.value = 0
    await Timer(1, unit="ns")


async def initialize(dut, astate_p: int, astate_n: int) -> None:
    """Load known A states and initialize the MSB-first SAR cycle."""

    dut.clk_update.value = 0
    dut.clk_init.value = 1
    dut.dac_mode.value = 0
    dut.dac_astate_p.value = astate_p
    dut.dac_astate_n.value = astate_n
    dut.dac_bstate_p.value = 0
    dut.dac_bstate_n.value = 0
    dut.comp_p.value = 0
    dut.comp_n.value = 0
    await pulse_update(dut)
    dut.clk_init.value = 0


@cocotb.test()
async def test_init_loads_a_states(dut) -> None:
    await initialize(dut, 0xA55A, 0x3CC3)

    assert int(dut.dac_state_p.value) == 0xA55A
    assert int(dut.dac_state_n.value) == 0x3CC3


@cocotb.test()
async def test_static_mode_loads_b_states(dut) -> None:
    await initialize(dut, 0x0000, 0xFFFF)
    dut.dac_bstate_p.value = 0x1234
    dut.dac_bstate_n.value = 0xFEDC
    dut.dac_mode.value = 0

    await pulse_update(dut)

    assert int(dut.dac_state_p.value) == 0x1234
    assert int(dut.dac_state_n.value) == 0xFEDC


@cocotb.test()
async def test_sar_mode_updates_each_side_msb_first(dut) -> None:
    await initialize(dut, 0x0000, DAC_MASK)
    dut.dac_mode.value = 1

    comp_p_bits = [1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1]
    comp_n_bits = [0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 0]
    expected_p = 0x0000
    expected_n = DAC_MASK

    for cycle, (comp_p, comp_n) in enumerate(zip(comp_p_bits, comp_n_bits, strict=True)):
        bit = DAC_WIDTH - 1 - cycle
        dut.comp_p.value = comp_p
        dut.comp_n.value = comp_n

        await pulse_update(dut)

        expected_p = (expected_p & ~(1 << bit)) | (comp_p << bit)
        expected_n = (expected_n & ~(1 << bit)) | (comp_n << bit)
        assert int(dut.dac_state_p.value) == expected_p
        assert int(dut.dac_state_n.value) == expected_n

    dut.comp_p.value = 1 - comp_p_bits[-1]
    dut.comp_n.value = 1 - comp_n_bits[-1]
    await pulse_update(dut)

    assert int(dut.dac_state_p.value) == expected_p
    assert int(dut.dac_state_n.value) == expected_n
