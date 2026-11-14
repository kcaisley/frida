"""The operational transconductance amplifier, a block on the pipeline (docs/pipeline.md): its
parameters, circuit, testbench, analyses, plots and design space, each in its own stage module,
their names re-exported here (``from flow import ota`` then ``ota.Params``, ``ota.analyze_ac``)."""

from . import params, subckt, sim, types, analysis, plots, runs, model  # noqa: I001 - the pipeline's order
from .analysis import analyze_ac, analyze_distortion, analyze_noise, analyze_slew, metrics
from .model import Model
from .params import Bench, Params, TbParams, Topology
from .plots import (
    plot_cmrr,
    plot_gain,
    plot_gain_cm,
    plot_gain_supply,
    plot_noise_density,
    plot_noise_in_1mhz_cm,
    plot_noise_in_cm,
    plot_phase,
    plot_power_supply,
    plot_psrr,
    plot_spectrum,
    plot_step_response,
    plot_unity_gain_bandwidth_cm,
    plot_unity_gain_bandwidth_supply,
)
from .runs import five_t, five_t_pmos, folded, results, self_biased, sizes, telescopic, testbenches, two_stage
from .sim import simulate, testbench
from .subckt import Nets, netlist
from .types import AnalysisAc, AnalysisDistortion, AnalysisNoise, AnalysisSlew, Metrics

__all__ = [
    "AnalysisAc",
    "AnalysisDistortion",
    "AnalysisNoise",
    "AnalysisSlew",
    "Bench",
    "Metrics",
    "Model",
    "Nets",
    "Params",
    "TbParams",
    "Topology",
    "analysis",
    "analyze_ac",
    "analyze_distortion",
    "analyze_noise",
    "analyze_slew",
    "five_t",
    "five_t_pmos",
    "folded",
    "metrics",
    "model",
    "netlist",
    "params",
    "plot_cmrr",
    "plot_gain",
    "plot_gain_cm",
    "plot_gain_supply",
    "plot_noise_density",
    "plot_noise_in_1mhz_cm",
    "plot_noise_in_cm",
    "plot_phase",
    "plot_power_supply",
    "plot_psrr",
    "plot_spectrum",
    "plot_step_response",
    "plot_unity_gain_bandwidth_cm",
    "plot_unity_gain_bandwidth_supply",
    "plots",
    "results",
    "runs",
    "self_biased",
    "sim",
    "simulate",
    "sizes",
    "subckt",
    "telescopic",
    "testbench",
    "testbenches",
    "two_stage",
    "types",
]
