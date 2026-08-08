"""Cocotb checks for the ADC main/difference capacitor-driver polarity."""

import cocotb
from cocotb.triggers import Timer

DAC_MASK = (1 << 16) - 1


async def pulse_update(dut) -> None:
    """Apply one rising edge to the ADC update sequencer input."""

    dut.seq_update.value = 0
    await Timer(1, unit="ns")
    dut.seq_update.value = 1
    await Timer(1, unit="ns")
    dut.seq_update.value = 0
    await Timer(1, unit="ns")


async def load_a_states(dut, state_p: int, state_n: int) -> None:
    """Load known SAR states through the normal ADC initialization path."""

    dut.seq_init.value = 1
    dut.dac_astate_p.value = state_p
    dut.dac_astate_n.value = state_n
    await pulse_update(dut)
    dut.seq_init.value = 0
    await Timer(1, unit="ns")


@cocotb.test()
async def test_adc_diffcap_mode_matches_fabricated_active_high_xor(dut) -> None:
    state_p = 0xA55A
    state_n = 0x3CC3

    dut.seq_init.value = 0
    dut.seq_samp.value = 0
    dut.seq_comp.value = 0
    dut.seq_update.value = 0
    dut.en_init.value = 1
    dut.en_samp_p.value = 0
    dut.en_samp_n.value = 0
    dut.en_comp.value = 0
    dut.en_update.value = 1
    dut.dac_mode.value = 0
    dut.dac_astate_p.value = 0
    dut.dac_bstate_p.value = 0
    dut.dac_astate_n.value = 0
    dut.dac_bstate_n.value = 0
    dut.dac_diffcaps.value = 0

    await load_a_states(dut, state_p, state_n)

    assert int(dut.dac_drive_botplate_main_p.value) == state_p
    assert int(dut.dac_drive_botplate_diff_p.value) == state_p
    assert int(dut.dac_drive_botplate_main_n.value) == state_n
    assert int(dut.dac_drive_botplate_diff_n.value) == state_n

    dut.dac_diffcaps.value = 1
    await Timer(1, unit="ns")

    assert int(dut.dac_drive_botplate_main_p.value) == state_p
    assert int(dut.dac_drive_botplate_diff_p.value) == (state_p ^ DAC_MASK)
    assert int(dut.dac_drive_botplate_main_n.value) == state_n
    assert int(dut.dac_drive_botplate_diff_n.value) == (state_n ^ DAC_MASK)
