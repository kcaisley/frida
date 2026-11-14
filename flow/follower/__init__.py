"""The follower, a block on the pipeline (docs/pipeline.md): its parameters, circuit, testbench,
analyses, plots and design space, each in its own stage module, their names re-exported here
(``from flow import follower`` then ``follower.Params``, ``follower.analyze_transfer``)."""

from . import params, subckt, sim, types, analysis, plots, runs  # noqa: I001 - the pipeline's order
from .analysis import analyze_impedance, analyze_slew, analyze_transfer, metrics
from .params import Params, Stimulus, TbParams, Topology
from .plots import (
    plot_bandwidth_supply,
    plot_bandwidth_vin,
    plot_gain_frequency,
    plot_gain_supply,
    plot_gain_vin,
    plot_psrr_supply,
    plot_psrr_vin,
    plot_vout_vin,
    plot_zout_frequency,
    plot_rout_vin,
)
from .sim import simulate, testbench
from .subckt import Nets, netlist
from .runs import flipped, flipped_pmos, results, scaled, source, source_pmos, testbenches
from .types import AnalysisImpedance, AnalysisSlew, AnalysisTransfer, Metrics

__all__ = [
    "AnalysisImpedance",
    "AnalysisSlew",
    "AnalysisTransfer",
    "Metrics",
    "Nets",
    "Params",
    "Stimulus",
    "TbParams",
    "Topology",
    "analysis",
    "analyze_impedance",
    "analyze_slew",
    "analyze_transfer",
    "flipped",
    "flipped_pmos",
    "metrics",
    "netlist",
    "params",
    "plot_bandwidth_supply",
    "plot_bandwidth_vin",
    "plot_gain_frequency",
    "plot_gain_supply",
    "plot_gain_vin",
    "plot_psrr_supply",
    "plot_psrr_vin",
    "plot_rout_vin",
    "plot_vout_vin",
    "plot_zout_frequency",
    "plots",
    "results",
    "runs",
    "scaled",
    "sim",
    "simulate",
    "source",
    "source_pmos",
    "subckt",
    "testbench",
    "testbenches",
    "types",
]
