"""The ADC's timing sequencer (the next chip's), for now its analyses of the bench's captures and
their figures alone, each in its own stage module (``types.py``, ``analysis.py``, ``plots.py``; the
pipeline's contract takes the block up once it has a sweep), their names re-exported here: the
serializer's eyes (``analyze_symbol_eye``, ``analyze_word``) and a converter capture's scope decode
against FastRX's (``analyze_scope_bits``). The scans import it directly (``from flow import seqgen``
then ``seqgen.analyze_word``)."""

from . import types, analysis, plots  # noqa: I001 - the pipeline's order
from .analysis import analyze_scope_bits, analyze_symbol_eye, analyze_word
from .plots import plot_scope_bits, plot_scope_samples, plot_symbol_eye, plot_word
from .types import AnalysisCapture, AnalysisScopeBits, AnalysisSymbolEye, AnalysisWord

__all__ = [
    "AnalysisCapture",
    "AnalysisScopeBits",
    "AnalysisSymbolEye",
    "AnalysisWord",
    "analysis",
    "analyze_scope_bits",
    "analyze_symbol_eye",
    "analyze_word",
    "plot_scope_bits",
    "plot_scope_samples",
    "plot_symbol_eye",
    "plot_word",
    "plots",
    "types",
]
