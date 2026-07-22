"""Hardware pytest that queries the E3634A supply without changing its state.

Run from the repository root with:

    uv run pytest -q -s -m hw flow/scans/test_supply.py
"""

from pathlib import Path

import pytest

MAP_PATH = Path(__file__).resolve().parent / "map_supply.yaml"
pytestmark = pytest.mark.hw


def test_supply_connectivity() -> None:
    """Query the supply identity and current output state without changing it."""
    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    dut = Dut(str(MAP_PATH))
    try:
        dut.init()
        supply = dut["vocm_supply"]
        identity = str(supply.get_name()).strip()
        print(
            f"GPIB 05: {identity}; "
            f"output={str(supply.get_enable()).strip()}, "
            f"setpoint={float(supply.get_set_voltage()):g} V, "
            f"measured={float(supply.get_voltage()):g} V, "
            f"current_limit={float(supply.get_current_limit()):g} A, "
            f"range={str(supply.get_voltage_range()).strip()}"
        )
        assert "E3634A" in identity, f"unexpected GPIB 05 identity: {identity}"
        print("PASS: HP/Agilent E3634A responded at GPIB address 05")
    finally:
        dut.close()
