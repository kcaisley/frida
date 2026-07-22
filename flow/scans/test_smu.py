"""Hardware pytest that queries three Keithley SMUs without changing state.

The instruments are expected at front-panel GPIB addresses 02, 03, and 04.
The check only queries identity and source state; it does not alter or enable
any output.

Run from the repository root with:

    uv run pytest -q -s -m hw flow/scans/test_smu.py
"""

from pathlib import Path

import pytest

MAP_PATH = Path(__file__).resolve().parent / "map_smu.yaml"
SMU_NAMES = ("smu1", "smu2", "smu3")
pytestmark = pytest.mark.hw


def test_smu_connectivity() -> None:
    """Query all three SMU identities and source states without changing them."""
    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    dut = Dut(str(MAP_PATH))
    try:
        dut.init()

        smu_names = []
        for address, name in zip((2, 3, 4), SMU_NAMES, strict=True):
            smu = dut[name]
            identity = str(smu.get_name()).strip()
            smu_names.append(identity)
            print(
                f"GPIB {address:02d} {name}: {identity}; "
                f"output={str(smu.get_on()).strip()}, "
                f"source={str(smu.get_source_mode()).strip()}, "
                f"setpoint={float(smu.get_source_voltage()):g} V, "
                f"current_limit={float(smu.get_current_limit()):g} A"
            )

        assert all("MODEL 2400" in identity for identity in smu_names), f"unexpected Keithley identities: {smu_names}"
        assert len(set(smu_names)) == len(smu_names), (
            "the three Keithley ID strings are not unique; check their GPIB addresses and serial numbers"
        )
        print("PASS: all three Keithley 2400 SourceMeters responded on the shared GPIB bus")
    finally:
        dut.close()
