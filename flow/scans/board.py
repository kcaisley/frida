"""The physical boards' inventory and calibration map (``map_board.yaml``): each channel's CDAC
flavor and metal layers, the flavors' weights and top-plate parasitics, and each board's supplies,
input calibration and FastRX capture settings. It imports nothing of the ADC, so the measurement
types (``flow.analysis.types``) read it without reaching the ADC's modules."""

from functools import cache
from pathlib import Path
from typing import Any

from yaml import safe_load


@cache
def load_board_map() -> dict[str, Any]:
    """Load the physical-board inventory and calibration map."""

    return safe_load((Path(__file__).resolve().parent / "map_board.yaml").read_text())
