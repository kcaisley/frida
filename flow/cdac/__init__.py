"""The CDAC, a block of the pipeline (docs/pipeline.md): an ADC array with the drivers that switch
it, both sides, and its per-stage settling; its parameters, circuit, testbench, analyses, plots and
design space, each in its own stage module, their names re-exported here (``from flow import cdac``
then ``cdac.Params``, ``cdac.analyze_settling``), and its plates' Monte Carlo (``cdac.analyze_mismatch``).
Its behavioral model is ``flow.cdac.model``."""

from . import params, subckt, sim, types, analysis, plots, sweep  # noqa: I001 - the pipeline's order
from .analysis import analyze_mismatch, analyze_settling, metrics
from .params import Params, TbParams
from .plots import (
    plot_dac_dnl,
    plot_dac_inl,
    plot_mismatch_dac_inl,
    plot_mismatch_gap,
    plot_mismatch_gradient,
    plot_mismatch_inl,
    plot_model_stage,
    plot_settling_stage,
)
from .sim import simulate, testbench
from .subckt import Nets, netlist
from .sweep import adc_array, adc_units, record, runs
from .types import AnalysisMismatch, AnalysisSettling

__all__ = [
    "AnalysisMismatch",
    "AnalysisSettling",
    "Nets",
    "Params",
    "TbParams",
    "adc_array",
    "adc_units",
    "analysis",
    "analyze_mismatch",
    "analyze_settling",
    "metrics",
    "netlist",
    "params",
    "plot_dac_dnl",
    "plot_dac_inl",
    "plot_mismatch_dac_inl",
    "plot_mismatch_gap",
    "plot_mismatch_gradient",
    "plot_mismatch_inl",
    "plot_model_stage",
    "plot_settling_stage",
    "plots",
    "record",
    "runs",
    "sim",
    "simulate",
    "subckt",
    "sweep",
    "testbench",
    "types",
]
