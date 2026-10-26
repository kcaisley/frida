"""The CDAC, a block of the pipeline (docs/pipeline.md): an ADC array with the drivers that switch
it, both sides, and its per-stage settling; its parameters, circuit, testbench, analyses, plots and
design space, each in its own stage module, their names re-exported here (``from flow import cdac``
then ``cdac.Params``, ``cdac.analyze_settling``). Its behavioral model is ``flow.cdac.model``."""

from . import params, subckt, sim, types, analysis, plots, sweep  # noqa: I001 - the pipeline's order
from .analysis import analyze_settling, metrics
from .params import Params, TbParams, valid
from .plots import plot_model_stage, plot_settling_stage
from .sim import simulate, testbench
from .subckt import Nets, netlist
from .sweep import adc_array, record, runs
from .types import AnalysisSettling

__all__ = [
    "AnalysisSettling",
    "Nets",
    "Params",
    "TbParams",
    "adc_array",
    "analysis",
    "analyze_settling",
    "metrics",
    "netlist",
    "params",
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
    "valid",
]
