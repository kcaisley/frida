"""The delay line and ring oscillator, a block on the pipeline (docs/pipeline.md): its parameters,
circuit, testbench, analyses, plots and design space, each in its own stage module, their names
re-exported here (``from flow import delay`` then ``delay.Params``, ``delay.analyze_oscillation``)."""

from . import params, subckt, sim, types, analysis, plots, runs  # noqa: I001 - the pipeline's order
from .analysis import analyze_oscillation, analyze_propagation, metrics
from .params import Control, Params, Stage, TbParams
from .plots import (
    plot_delay_fall_control,
    plot_delay_fall_supply,
    plot_delay_rise_control,
    plot_delay_rise_supply,
    plot_energy_control,
    plot_energy_supply,
    plot_fall_time_control,
    plot_kvco_control,
    plot_oscillation_frequency_control,
    plot_oscillation_frequency_supply,
    plot_rise_time_control,
    plot_stage_delay_supply,
)
from .sim import simulate, testbench
from .subckt import Nets, netlist
from .runs import (
    chain2_coupled,
    chain4,
    chain4_starved,
    results,
    ring4_coupled,
    ring4_tail,
    ring5,
    ring5_starved,
    sizes,
    testbenches,
)
from .types import AnalysisOscillation, AnalysisPropagation, Metrics

__all__ = [
    "AnalysisOscillation",
    "AnalysisPropagation",
    "Control",
    "Metrics",
    "Nets",
    "Params",
    "Stage",
    "TbParams",
    "analysis",
    "analyze_oscillation",
    "analyze_propagation",
    "chain2_coupled",
    "chain4",
    "chain4_starved",
    "metrics",
    "netlist",
    "params",
    "plot_delay_fall_control",
    "plot_delay_fall_supply",
    "plot_delay_rise_control",
    "plot_delay_rise_supply",
    "plot_energy_control",
    "plot_energy_supply",
    "plot_fall_time_control",
    "plot_kvco_control",
    "plot_oscillation_frequency_control",
    "plot_oscillation_frequency_supply",
    "plot_rise_time_control",
    "plot_stage_delay_supply",
    "plots",
    "results",
    "ring4_coupled",
    "ring4_tail",
    "ring5",
    "ring5_starved",
    "runs",
    "sim",
    "simulate",
    "sizes",
    "subckt",
    "testbench",
    "testbenches",
    "types",
]
