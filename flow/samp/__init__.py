"""The sampling switch, a block on the pipeline (docs/pipeline.md): its parameters, circuit,
testbench, analyses, plots and design space, each in its own stage module, their names re-exported
here (``from flow import samp`` then ``samp.Params``, ``samp.analyze_track``)."""

from . import params, subckt, sim, types, analysis, plots, sweep  # noqa: I001 - the pipeline's order
from .analysis import analyze_hold, analyze_track, metrics
from .params import FRIDA1, STRUCTURE, Params, SwitchType, TbParams
from .plots import (
    plot_feedthrough_vin,
    plot_pedestal_supply,
    plot_pedestal_vin,
    plot_ron_supply,
    plot_ron_vin,
    plot_track_error_vin,
)
from .sim import simulate, testbench
from .subckt import Nets, netlist
from .sweep import boost_ladder, bootstrap, frida1, long_channel, nmos, record, runs, scaled, tgate_dummy
from .types import AnalysisHold, AnalysisTrack

__all__ = [
    "FRIDA1",
    "STRUCTURE",
    "AnalysisHold",
    "AnalysisTrack",
    "Nets",
    "Params",
    "SwitchType",
    "TbParams",
    "analysis",
    "analyze_hold",
    "analyze_track",
    "boost_ladder",
    "bootstrap",
    "frida1",
    "long_channel",
    "metrics",
    "netlist",
    "nmos",
    "params",
    "plot_feedthrough_vin",
    "plot_pedestal_supply",
    "plot_pedestal_vin",
    "plot_ron_supply",
    "plot_ron_vin",
    "plot_track_error_vin",
    "plots",
    "record",
    "runs",
    "scaled",
    "sim",
    "simulate",
    "subckt",
    "sweep",
    "testbench",
    "tgate_dummy",
    "types",
]
