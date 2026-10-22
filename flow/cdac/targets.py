"""The CDAC's targets (``python -m flow cdac.<target>``)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from flow.sweep import runner as sweep_runner

from .model import CdacModel


def characterization() -> None:
    """Every ADC variant's CDAC in TSMC65 (``flow.cdac.sweep``, 16 Spectre runs at a time), tabulated:
    the settling the ADC models of ``flow.adc.sweep`` read."""
    sweep_runner.run(["cdac"], ("tsmc65",), 16)
    sweep_runner.table(["cdac"], 16)


def characterization_adc14() -> None:
    """``flow.adc14``'s 16 ideal arrays at its resolution, into the models' cache (``build/models/cdac``),
    16 at a time."""
    from flow.adc14 import sweep as adc14

    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(name, "1")
    # each characterization runs in a process of its own (flow.sweep.lookup)
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda sizing: CdacModel.of("tsmc65", adc14.array(sizing), adc14.BITS + 1), adc14.SIZINGS))
