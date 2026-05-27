import cocotb
from cocotb.triggers import Timer

REGISTER_WIDTH = 180


async def tick_spi(dut, bit):
    dut.spi_sdi.value = bit
    await Timer(1, unit="ns")
    dut.spi_sclk.value = 1
    await Timer(1, unit="ns")
    dut.spi_sclk.value = 0
    await Timer(1, unit="ns")


async def reset_dut(dut):
    dut.spi_sclk.value = 0
    dut.spi_sdi.value = 0
    dut.spi_cs_b.value = 1
    dut.rst_b.value = 0
    await Timer(2, unit="ns")
    dut.rst_b.value = 1
    await Timer(1, unit="ns")


@cocotb.test()
async def test_reset_clears_register(dut):
    await reset_dut(dut)

    assert int(dut.spi_bits.value) == 0
    assert int(dut.spi_sdo.value) == 0


@cocotb.test()
async def test_shift_mosi_into_parallel_register(dut):
    await reset_dut(dut)
    dut.spi_cs_b.value = 0

    pattern_bits = [(0x2D3 >> bit) & 1 for bit in reversed(range(10))]
    expected = 0

    for bit in pattern_bits:
        expected = ((expected << 1) | bit) & ((1 << REGISTER_WIDTH) - 1)
        await tick_spi(dut, bit)
        assert int(dut.spi_bits.value) == expected


@cocotb.test()
async def test_chip_select_holds_register(dut):
    await reset_dut(dut)
    dut.spi_cs_b.value = 0

    for bit in [1, 0, 1, 1]:
        await tick_spi(dut, bit)

    captured = int(dut.spi_bits.value)
    dut.spi_cs_b.value = 1

    for bit in [0, 0, 0, 0, 1, 1]:
        await tick_spi(dut, bit)

    assert int(dut.spi_bits.value) == captured


@cocotb.test()
async def test_sdo_streams_shift_register_msb_on_falling_edge(dut):
    await reset_dut(dut)
    dut.spi_cs_b.value = 0

    input_bits = [1, 0, 1, 1] + [0] * (REGISTER_WIDTH - 4) + [1, 1, 0, 0]
    expected = 0

    for bit in input_bits:
        expected = ((expected << 1) | bit) & ((1 << REGISTER_WIDTH) - 1)
        await tick_spi(dut, bit)
        assert int(dut.spi_sdo.value) == ((expected >> (REGISTER_WIDTH - 1)) & 1)
