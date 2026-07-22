"""Hardware pytest that queries the Tektronix MSO54 without changing its state.

Run from the repository root with:

    uv run pytest -q -s -m hw flow/scans/test_scope.py
"""

from pathlib import Path

import pytest

from basil.HL.tektronix_oscilloscope import response_value

MAP_PATH = Path(__file__).resolve().parent / "map_scope.yaml"
pytestmark = pytest.mark.hw


def test_scope_connectivity() -> None:
    """Query the scope identity and acquisition state without changing it."""
    from basil.dut import Dut

    dut = Dut(str(MAP_PATH))
    try:
        dut.init()
        scope = dut["scope"]
        identity = str(scope.get_name()).strip()
        print(
            f"{identity}; "
            f"acquisition={response_value(scope.get_acquire_state())}, "
            f"mode={response_value(scope.get_acquire_mode())}, "
            f"horizontal_scale={response_value(scope.get_horizontal_scale())} s/div, "
            f"record_length={response_value(scope.get_horizontal_record_length())}"
        )
        assert "MSO54" in identity, f"unexpected scope identity: {identity}"
        print("PASS: Tektronix MSO54 responded over its SCPI socket")
    finally:
        dut.close()
