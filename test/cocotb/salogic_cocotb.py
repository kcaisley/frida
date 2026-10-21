"""Cocotb checks for the dual-channel SAR logic."""

import os

import cocotb
from cocotb.triggers import Timer

# The runner builds salogic with this N_STAGES; FRIDA's 16 is the default.
DAC_WIDTH = int(os.getenv("SALOGIC_N_STAGES", "16"))
DAC_MASK = (1 << DAC_WIDTH) - 1

# Comparator decisions of the 16-stage check, repeated or cut to DAC_WIDTH.
COMP_P_BITS = [1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 1, 0, 1]
COMP_N_BITS = [0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 1, 0]


def stages(word16: int) -> int:
    """Repeat a 16-bit test word over DAC_WIDTH bits, so 16 stages see it unchanged."""

    repeats = -(-DAC_WIDTH // 16)
    return sum(word16 << (16 * k) for k in range(repeats)) & DAC_MASK


def decisions(bits16: list[int]) -> list[int]:
    """Repeat a 16-entry decision list over DAC_WIDTH stages."""

    return (bits16 * -(-DAC_WIDTH // 16))[:DAC_WIDTH]


async def pulse_update(dut) -> None:
    """Apply one rising edge to the SAR update clock."""

    dut.clk_update.value = 0
    await Timer(1, unit="ns")
    dut.clk_update.value = 1
    await Timer(1, unit="ns")
    dut.clk_update.value = 0
    await Timer(1, unit="ns")


async def initialize(dut, astate_p: int, astate_n: int) -> None:
    """Load known A states and initialize the C0-first SAR cycle."""

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
async def test_ports_follow_n_stages(dut) -> None:
    assert len(dut.dac_state_p) == DAC_WIDTH
    assert len(dut.dac_astate_n) == DAC_WIDTH


@cocotb.test()
async def test_init_loads_a_states(dut) -> None:
    await initialize(dut, stages(0xA55A), stages(0x3CC3))

    assert int(dut.dac_state_p.value) == stages(0xA55A)
    assert int(dut.dac_state_n.value) == stages(0x3CC3)


@cocotb.test()
async def test_static_mode_loads_b_states(dut) -> None:
    await initialize(dut, 0x0000, DAC_MASK)
    dut.dac_bstate_p.value = stages(0x1234)
    dut.dac_bstate_n.value = stages(0xFEDC)
    dut.dac_mode.value = 0

    await pulse_update(dut)

    assert int(dut.dac_state_p.value) == stages(0x1234)
    assert int(dut.dac_state_n.value) == stages(0xFEDC)


@cocotb.test()
async def test_sar_mode_updates_each_side_c0_first(dut) -> None:
    await initialize(dut, 0x0000, DAC_MASK)
    dut.dac_mode.value = 1

    comp_p_bits = decisions(COMP_P_BITS)
    comp_n_bits = decisions(COMP_N_BITS)
    expected_p = 0x0000
    expected_n = DAC_MASK

    for cycle, (comp_p, comp_n) in enumerate(zip(comp_p_bits, comp_n_bits, strict=True)):
        stage = cycle
        dut.comp_p.value = comp_p
        dut.comp_n.value = comp_n

        await pulse_update(dut)

        expected_p = (expected_p & ~(1 << stage)) | (comp_p << stage)
        expected_n = (expected_n & ~(1 << stage)) | (comp_n << stage)
        assert int(dut.dac_state_p.value) == expected_p
        assert int(dut.dac_state_n.value) == expected_n

    # The one-hot cycle counter has run out: further updates change nothing.
    dut.comp_p.value = 1 - comp_p_bits[-1]
    dut.comp_n.value = 1 - comp_n_bits[-1]
    await pulse_update(dut)

    assert int(dut.dac_state_p.value) == expected_p
    assert int(dut.dac_state_n.value) == expected_n
