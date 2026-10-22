"""The CDAC's targets (``python -m flow cdac.<target>``)."""

from __future__ import annotations

from flow.sweep import runner as sweep_runner


def characterization() -> None:
    """The CDAC of every converter of ``flow.adc.sweep`` in TSMC65 (``flow.cdac.sweep``: every ADC
    variant's array, and the specification study's ideal arrays; 16 Spectre runs at a time),
    tabulated: the settling the ADC models read."""
    sweep_runner.run(["cdac"], ("tsmc65",), 16)
    sweep_runner.table(["cdac"], 16)
