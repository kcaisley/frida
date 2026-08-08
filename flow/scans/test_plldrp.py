"""Software and opt-in hardware tests for the PLL DRP controller.

The calculation tests perform no hardware I/O and run by default. The test
marked ``hw`` writes the Si570 and FPGA PLL-control registers, then checks
their readback; run it after programming the variable-clock firmware with:

    uv run pytest -q -s -m hw flow/scans/test_plldrp.py
"""

from pathlib import Path
from time import sleep

import pytest

from flow.scans.plldrp import (
    PLL_DIVIDERS,
    calculate_pll_frequency,
    select_pll_configuration,
    set_pll_divider,
)

TEST_SYMBOL_RATES_BPS = tuple(
    rate_mbd * 1e6
    for rate_mbd in (
        80,
        100,
        125,
        160,
        200,
        250,
        320,
        400,
        500,
        640,
        800,
        900,
        1000,
        1200,
        1400,
        1600,
    )
)
SI570_FACTORY_FREQUENCY_HZ = 156.25e6


def test_calculate_supported_pll_frequencies() -> None:
    """Software-only: calculate all 19 divider settings without hardware I/O."""
    for divider in PLL_DIVIDERS:
        sequencer_hz, serializer_hz = calculate_pll_frequency(divider)
        assert sequencer_hz == pytest.approx(400_000_000 / divider)
        assert serializer_hz == pytest.approx(1_600_000_000 / divider)
        assert 2 * serializer_hz == pytest.approx(3_200_000_000 / divider)


def test_select_pll_configuration() -> None:
    """Software-only: select legal Si570/N pairs without hardware I/O."""
    configurations = tuple((target, *select_pll_configuration(target)) for target in TEST_SYMBOL_RATES_BPS)
    assert configurations[0] == (80_000_000.0, 100_000_000.0, 20)
    assert configurations[-1] == (1_600_000_000.0, 200_000_000.0, 2)

    for target_symbol_rate_bps, si570_frequency_hz, divider_n in configurations:
        _, serializer_frequency_hz = calculate_pll_frequency(
            divider_n,
            input_frequency_hz=si570_frequency_hz,
        )
        assert 100_000_000 <= si570_frequency_hz <= 200_000_000
        assert divider_n in PLL_DIVIDERS
        assert 2 * serializer_frequency_hz == pytest.approx(target_symbol_rate_bps)

    with pytest.raises(ValueError, match="not reachable"):
        select_pll_configuration(79_999_999.0)
    with pytest.raises(ValueError, match="not reachable"):
        select_pll_configuration(1_600_000_001.0)


@pytest.mark.hw
def test_pll_register_write_and_readback() -> None:
    """Hardware: program each Si570/PLL setting and verify register readback."""
    from basil.dut import Dut

    daq = Dut(str(Path(__file__).resolve().parent / "map_fpga.yaml"))
    hardware_ready = False
    try:
        daq.init()
        hardware_ready = True
        si570 = daq["si570"]
        gpio = daq["gpio2"]

        # Recall the factory registers once to recover the crystal frequency
        # used to reconstruct every subsequently programmed output frequency.
        si570.reset()
        factory_hs_div, factory_n1, factory_rfreq = si570.read_registers()
        crystal_frequency_hz = SI570_FACTORY_FREQUENCY_HZ * factory_hs_div * factory_n1 / (factory_rfreq / 2**28)

        for target_symbol_rate_bps in TEST_SYMBOL_RATES_BPS:
            si570_frequency_hz, divider = select_pll_configuration(target_symbol_rate_bps)
            sequencer_hz, serializer_hz = calculate_pll_frequency(
                divider,
                input_frequency_hz=si570_frequency_hz,
            )
            si570.frequency_change(si570_frequency_hz / 1e6)
            sleep(0.02)
            status = set_pll_divider(gpio, divider)

            # Read the GPIO register again independently of set_pll_divider's
            # polling and check the written divider plus all returned status.
            gpio.read()
            assert gpio["REQUEST_N"].tovalue() == divider
            assert gpio["ACTIVE_N"].tovalue() == divider
            assert gpio["APPLIED_TOGGLE"].tovalue() == status.applied_toggle
            assert not gpio["BUSY"].tovalue()
            assert gpio["LOCKED"].tovalue()
            assert not gpio["ERROR"].tovalue()

            hs_div, n1, rfreq = si570.read_registers()
            assert hs_div in (4, 5, 6, 7, 9, 11)
            assert n1 == 1 or (2 <= n1 <= 128 and n1 % 2 == 0)
            assert 0 < rfreq < 2**38
            readback_frequency_hz = crystal_frequency_hz * (rfreq / 2**28) / (hs_div * n1)
            assert readback_frequency_hz == pytest.approx(si570_frequency_hz, rel=1e-6)

            print(
                f"target={target_symbol_rate_bps / 1e6:g} MBd, "
                f"Si570={si570_frequency_hz / 1e6:g} MHz "
                f"(readback={readback_frequency_hz / 1e6:g} MHz), "
                f"(HS_DIV={hs_div}, N1={n1}, RFREQ={rfreq}), N={divider:2d}: "
                f"request={status.request_n:2d}, active={status.active_n:2d}, "
                f"ack={status.applied_toggle}, busy={int(status.busy)}, "
                f"locked={int(status.locked)}, error={int(status.error)}, "
                f"seq={sequencer_hz / 1e6:g} MHz, "
                f"ser={serializer_hz / 1e6:g} MHz, "
                f"symbols={2 * serializer_hz / 1e6:g} MBd"
            )
    finally:
        if hardware_ready:
            try:
                daq["si570"].frequency_change(200.0)
                sleep(0.02)
                set_pll_divider(daq["gpio2"], 2)
            finally:
                daq.close()
        else:
            daq.close()
