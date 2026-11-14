"""The charge-sensitive amplifier, a block on the pipeline (docs/pipeline.md): its parameters,
circuit, testbench, analyses, plots and design space, each in its own stage module, their names
re-exported here (``from flow import csa`` then ``csa.Params``, ``csa.analyze_pulse``)."""

from . import params, subckt, sim, types, analysis, plots, runs  # noqa: I001 - the pipeline's order
from .analysis import analyze_noise, analyze_pulse, analyze_supply, metrics
from .params import Feedback, Params, Stimulus, TbParams, layout_view
from .plots import (
    plot_amplitude_charge,
    plot_enc_supply,
    plot_gain_charge,
    plot_gain_supply,
    plot_noise_density,
    plot_peaking_supply,
    plot_power_supply,
    plot_pulse_q250,
    plot_pulse_q500,
    plot_pulse_q1000,
    plot_pulse_q2000,
    plot_tot_charge,
)
from .sim import simulate, testbench
from .subckt import Nets, netlist
from .runs import continuous, krum, krum_pmos, reset, results, scaled, testbenches
from .types import AnalysisNoise, AnalysisPulse, AnalysisSupply, Metrics

__all__ = [
    "AnalysisNoise",
    "AnalysisPulse",
    "AnalysisSupply",
    "Feedback",
    "Metrics",
    "Nets",
    "Params",
    "Stimulus",
    "TbParams",
    "analysis",
    "analyze_noise",
    "analyze_pulse",
    "analyze_supply",
    "continuous",
    "krum",
    "krum_pmos",
    "layout_view",
    "metrics",
    "netlist",
    "params",
    "plot_amplitude_charge",
    "plot_enc_supply",
    "plot_gain_charge",
    "plot_gain_supply",
    "plot_noise_density",
    "plot_peaking_supply",
    "plot_power_supply",
    "plot_pulse_q250",
    "plot_pulse_q500",
    "plot_pulse_q1000",
    "plot_pulse_q2000",
    "plot_tot_charge",
    "plots",
    "reset",
    "results",
    "runs",
    "scaled",
    "sim",
    "simulate",
    "subckt",
    "testbench",
    "testbenches",
    "types",
]
