"""Read SPICE .raw files using spicelib."""

import numpy as np
from pathlib import Path
from typing import Dict, Tuple
from spicelib import RawRead


def read_raw(raw_file: Path) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """
    Read a .raw file and extract time axis and all traces.

    Args:
        raw_file: Path to .raw file

    Returns:
        Tuple of (time_array, traces_dict)
    """
    raw = RawRead(str(raw_file), traces_to_read='*', dialect='ngspice')
    time = raw.get_axis()

    traces = {}
    for name in raw.get_trace_names():
        traces[name] = raw.get_wave(name)

    return time, traces
