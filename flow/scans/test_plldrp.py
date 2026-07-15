"""Software calculation and hardware tests for the PLL DRP controller.

The pure helper test is collected by pytest without requiring hardware. Run
the hardware sweep explicitly after programming the variable-clock firmware:

    uv run python -m flow.scans.test_plldrp
"""

import logging
from pathlib import Path
from time import sleep

import pytest

from flow.scans.plldrp import (
    PLL_CLKFBOUT_MULT,
    PLL_DIVCLK_DIVIDE,
    PLL_DIVIDERS,
    PLL_INPUT_FREQUENCY_HZ,
    build_pll_frequency_table,
    calculate_pll_frequency,
    select_pll_configuration,
    set_pll_divider,
)

HARDWARE_TEST_SYMBOL_RATES_BPS = tuple(
    rate_mbd * 1e6 for rate_mbd in (80, 100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 900, 1000, 1200, 1400, 1600)
)


def test_build_pll_frequency_table() -> None:
    """Calculate all 19 legal paired output-divider settings."""
    table = build_pll_frequency_table(
        PLL_INPUT_FREQUENCY_HZ,
        PLL_DIVCLK_DIVIDE,
        PLL_CLKFBOUT_MULT,
        PLL_DIVIDERS,
    )

    assert tuple(table) == PLL_DIVIDERS
    for divider, frequency in table.items():
        sequencer_hz, serializer_hz = calculate_pll_frequency(divider)
        assert frequency.divider_n == divider
        assert frequency.clkout0_divide == 4 * divider
        assert frequency.clkout1_divide == divider
        assert frequency.sequencer_frequency_hz == sequencer_hz
        assert frequency.serializer_frequency_hz == serializer_hz
        assert frequency.sequencer_frequency_hz == pytest.approx(400_000_000 / divider)
        assert frequency.serializer_frequency_hz == pytest.approx(1_600_000_000 / divider)
        assert frequency.ddr_line_rate_bps == pytest.approx(3_200_000_000 / divider)

    assert table[2].vco_frequency_hz == pytest.approx(1_600_000_000)
    assert table[2].clkout0_divide == 8
    assert table[2].clkout1_divide == 2
    assert table[2].sequencer_frequency_hz == pytest.approx(200_000_000)
    assert table[2].serializer_frequency_hz == pytest.approx(800_000_000)
    assert table[2].ddr_line_rate_bps == pytest.approx(1_600_000_000)
    assert table[20].clkout0_divide == 80
    assert table[20].clkout1_divide == 20
    assert table[20].sequencer_frequency_hz == pytest.approx(20_000_000)
    assert table[20].serializer_frequency_hz == pytest.approx(80_000_000)
    assert table[20].ddr_line_rate_bps == pytest.approx(160_000_000)


def test_select_pll_configuration() -> None:
    """Select legal Si570/N pairs over the complete 80--1600 MBd range."""
    configurations = tuple((target, *select_pll_configuration(target)) for target in HARDWARE_TEST_SYMBOL_RATES_BPS)
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


def main() -> None:
    from basil.dut import Dut

    logging.basicConfig(level=logging.INFO)
    daq = Dut(str(Path(__file__).resolve().parent / "map_fpga.yaml"))
    daq.init()
    try:
        for target_symbol_rate_bps in HARDWARE_TEST_SYMBOL_RATES_BPS:
            si570_frequency_hz, divider = select_pll_configuration(target_symbol_rate_bps)
            sequencer_hz, serializer_hz = calculate_pll_frequency(
                divider,
                input_frequency_hz=si570_frequency_hz,
            )
            daq["si570"].frequency_change(si570_frequency_hz / 1e6)
            sleep(0.02)
            status = set_pll_divider(daq["gpio2"], divider)
            hs_div, n1, rfreq = daq["si570"].read_registers()
            print(
                f"target={target_symbol_rate_bps / 1e6:g} MBd, "
                f"Si570={si570_frequency_hz / 1e6:g} MHz "
                f"(HS_DIV={hs_div}, N1={n1}, RFREQ={rfreq}), N={divider:2d}: "
                f"request={status.request_n:2d}, active={status.active_n:2d}, "
                f"ack={status.applied_toggle}, busy={int(status.busy)}, "
                f"locked={int(status.locked)}, error={int(status.error)}, "
                f"seq={sequencer_hz / 1e6:g} MHz, "
                f"ser={serializer_hz / 1e6:g} MHz, "
                f"symbols={2 * serializer_hz / 1e6:g} MBd"
            )
    finally:
        try:
            daq["si570"].frequency_change(200.0)
            sleep(0.02)
            set_pll_divider(daq["gpio2"], 2)
        finally:
            daq.close()


if __name__ == "__main__":
    main()
