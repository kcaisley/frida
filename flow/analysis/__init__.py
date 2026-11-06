"""Typed FRIDA measurement I/O, numerical analyses, and plots.

The readers and writers are loaded when first used (``flow.analysis.read_analysis``), so a block's
stages can use the helper modules (``calc``, ``io``) without loading the rest. The analyses are the
blocks' own: the ADC's (``adc.analyze_ramp``), the comparator's of a converter's captures
(``comp.analyze_scope_edges``), the CDAC's of its switching curves (``capdac.analyze_cap_mismatch``)
and the sequencer's (``seqgen.analyze_symbol_eye``)."""

from importlib import import_module

__all__ = [
    "read_analysis",
    "read_measurement",
    "write_analysis",
    "write_measurement",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(f"{__name__}.io"), name)
