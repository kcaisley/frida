"""Typed FRIDA measurement I/O, numerical analyses, and plots.

The analyses are loaded when first used (``flow.analysis.analyze_cdac_transition``), so a block's
stages can use the helper modules (``calc``, ``io``) without loading every analysis. The ADC's
analyses are its block's (``adc.analyze_ramp``)."""

from importlib import import_module

__all__ = [
    "analyze_cdac_cap_mismatch",
    "analyze_cdac_decisions",
    "analyze_cdac_transition",
    "read_analysis",
    "read_measurement",
    "write_analysis",
    "write_measurement",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = "io" if name.startswith(("read_", "write_")) else name.split("_")[1]
    return getattr(import_module(f"{__name__}.{module}"), name)
