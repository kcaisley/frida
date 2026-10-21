"""The 14-bit specification study's targets (``python -m flow adc14.<target>``)."""

from __future__ import annotations

from flow.sweep import runner


def sweep() -> None:
    """Every array with every comparator in a fresh run, characterized and tabulated."""
    runner.run(["adc14"], ["tsmc65"], 48)
    runner.table(["adc14"], 16)
