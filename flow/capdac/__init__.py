"""The capacitive DAC, a block on the pipeline (docs/pipeline.md): its parameters, circuit,
testbench, analyses, plots, design space and behavioral model, each in its own stage module, their
names re-exported here (``from flow import capdac`` then ``capdac.Params``, ``capdac.analyze_settling``)."""

from . import params, subckt, sim, types, analysis, plots, search, model  # noqa: I001 - the pipeline's order
from .analysis import (
    analyze_cap_mismatch,
    analyze_decisions,
    analyze_mismatch,
    analyze_settling,
    analyze_transition,
    metrics,
)
from .model import Model
from .params import Params, Redundancy, TbParams, WeightImpl
from .plots import (
    plot_asymmetry_stage,
    plot_bias_stage,
    plot_dac_dnl,
    plot_dac_inl,
    plot_fraction_error_stage,
    plot_fraction_stage,
    plot_main_stage,
    plot_mismatch_dac_inl,
    plot_mismatch_gap,
    plot_mismatch_inl,
    plot_model_stage,
    plot_separation_stage,
    plot_settling_stage,
)
from .sim import simulate, testbench
from .subckt import Nets, netlist
from .search import arrays, frida1, record, runs
from .types import (
    AnalysisCapMismatch,
    AnalysisMismatch,
    AnalysisSettling,
    AnalysisSwitching,
    AnalysisTransition,
)

__all__ = [
    "AnalysisCapMismatch",
    "AnalysisMismatch",
    "AnalysisSettling",
    "AnalysisSwitching",
    "AnalysisTransition",
    "Model",
    "Nets",
    "Params",
    "Redundancy",
    "TbParams",
    "WeightImpl",
    "analysis",
    "analyze_cap_mismatch",
    "analyze_decisions",
    "analyze_mismatch",
    "analyze_settling",
    "analyze_transition",
    "arrays",
    "frida1",
    "metrics",
    "model",
    "netlist",
    "params",
    "plot_asymmetry_stage",
    "plot_bias_stage",
    "plot_dac_dnl",
    "plot_dac_inl",
    "plot_fraction_error_stage",
    "plot_fraction_stage",
    "plot_main_stage",
    "plot_mismatch_dac_inl",
    "plot_mismatch_gap",
    "plot_mismatch_inl",
    "plot_model_stage",
    "plot_separation_stage",
    "plot_settling_stage",
    "plots",
    "record",
    "runs",
    "search",
    "sim",
    "simulate",
    "subckt",
    "testbench",
    "types",
]
