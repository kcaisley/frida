"""Hardware pytest that queries the Agilent 33250A without changing its state.

Run from the repository root with:

    uv run pytest -q -s -m hw flow/scans/test_awg.py
"""

from pathlib import Path

import pytest

MAP_PATH = Path(__file__).resolve().parent / "map_awg.yaml"
pytestmark = pytest.mark.hw


def test_awg_connectivity() -> None:
    """Query the AWG identity and current output state without changing it."""
    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    dut = Dut(str(MAP_PATH))
    try:
        dut.init()
        awg = dut["awg"]
        identity = str(awg.get_name()).strip()
        print(
            f"GPIB 01: {identity}; "
            f"output={str(awg.get_enable()).strip()}, "
            f"frequency={float(awg.get_frequency()):g} Hz, "
            f"amplitude={float(awg.get_voltage_high()) - float(awg.get_voltage_low()):g} Vpp, "
            f"offset={float(awg.get_voltage_offset()):g} V, "
            f"load={str(awg.get_output_load()).strip()}"
        )
        assert "33250A" in identity, f"unexpected GPIB 01 identity: {identity}"
        print("PASS: Agilent 33250A responded at GPIB address 01")
    finally:
        dut.close()
