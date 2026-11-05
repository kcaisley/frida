"""The capacitive DAC, a block on the pipeline (docs/pipeline.md): its parameters, circuit,
testbench, analyses, plots, design space and behavioral model, each in its own stage module, their
names re-exported here (``from flow import capdac`` then ``capdac.Params``, ``capdac.analyze_settling``)."""

from . import params, subckt, sim, types, analysis, plots, sweep, model  # noqa: I001 - the pipeline's order
from .analysis import analyze_mismatch, analyze_settling, metrics
from .model import Model
from .params import Params, Redundancy, TbParams, WeightImpl
from .plots import (
    plot_dac_dnl,
    plot_dac_inl,
    plot_mismatch_dac_inl,
    plot_mismatch_gap,
    plot_mismatch_inl,
    plot_model_stage,
    plot_settling_stage,
)
from .sim import simulate, testbench
from .subckt import Nets, netlist
from .sweep import arrays, record, runs
from .types import AnalysisMismatch, AnalysisSettling

__all__ = [
    "AnalysisMismatch",
    "AnalysisSettling",
    "Model",
    "Nets",
    "Params",
    "Redundancy",
    "TbParams",
    "WeightImpl",
    "analysis",
    "analyze_mismatch",
    "analyze_settling",
    "arrays",
    "metrics",
    "model",
    "netlist",
    "params",
    "plot_dac_dnl",
    "plot_dac_inl",
    "plot_mismatch_dac_inl",
    "plot_mismatch_gap",
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
