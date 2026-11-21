"""The capacitive DAC's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis
results alone: a characterization's settling and the behavioral model's step by stage (the record's
plots, which ``flow.capdac.model`` reads back), the plates' Monte Carlo: the 95th percentile of the
converter's INL, of what no calibration recovers and of the DAC's INL over Pelgrom's coefficient,
and the DAC's INL and DNL by code at the middle condition; and the bench's capacitance of each stage
from its switching curves (``analyze_cap_mismatch``), one curve a quantity, so compared converters
overlay as instances. The viewer draws them from their JSON, ``flow.plot.render`` with matplotlib."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from flow.pipeline import Plot, plot

from .types import AnalysisCapMismatch, AnalysisMismatch, AnalysisSettling


@plot
def plot_settling_stage(settling: AnalysisSettling) -> Plot:
    """Each stage's settling to half an LSB, its slower direction's."""
    # [Razavi-ADC] Sec. 8.2.2, Fig. 8.16, p. 150: the settling time t_s, from the input's change until the
    #   output stays within +-0.5 LSB of its final value; here each stage's own step, its slower
    #   direction, drawn by stage (the figure's form frida's own)
    return Plot(
        name="settling_stage",
        title="Settling to half an LSB by stage (C0, the MSB, first; the slower direction)",
        x_label="Stage",
        y_label="Settling time (s)",
        x=list(range(len(settling.settling_s))),
        series={"settling": list(map(float, settling.settling_s))},
    )


@plot
def plot_model_stage(settling: AnalysisSettling) -> Plot:
    """Each stage's step as the behavioral model starts and settles it: its driver's delay and its
    time constant. Two quantities on one ``Time (s)`` axis, against docs/references.md's one
    quantity per axis: the record's figures (seven, this one among them) and this figure's two
    series, which ``Model.of`` reads, are fixed by the block's known-answer tests, so a figure each
    (``Delay (s)``, ``Time constant (s)``) waits for the owner."""
    # [Baker] Fig. 10.9, p. 333: the delay, from the input's 50 % point to the output's (the stage's
    #   state to its main bottom plate); [Razavi-ADC] Eq. (8.14), p. 151: one pole settling into half
    #   an LSB, R_L C_L ln 14 for 3 bits (ln of the step over half an LSB); the time constant drawn
    #   is the model's own from it, (t_s - t_d) / ln(|s| / (LSB / 2)) (``AnalysisSettling.tau_s``),
    #   by stage (the figure's form frida's own)
    return Plot(
        name="model_stage",
        title="The behavioral model's step by stage (C0, the MSB, first): its start and time constant",
        x_label="Stage",
        y_label="Time (s)",
        x=list(range(len(settling.settling_s))),
        series={"delay": list(map(float, settling.delay_s)), "time constant": list(map(float, settling.tau_s))},
    )


@plot
def plot_mismatch_inl(mismatch: Sequence[AnalysisMismatch]) -> Plot:
    """The converter's worst INL with its design weights, 95th percentile over the runs, over
    Pelgrom's coefficient."""
    # [Razavi-ADC] Eq. (12.12), p. 244: an ADC's INL_j = V_j - j Delta, against the line through the end
    #   points; Sec. 15.2.3, p. 318: a SAR ADC's characteristic takes on its DAC's DNL and INL;
    #   [Pelgrom] Eq. (4.34), p. 144: sigma_C / C = A_C / sqrt(C), A_C the coefficient on the x axis;
    #   the 95th percentile of each run's worst |INL| (the design weights decoding) over A_C frida's own
    chosen = sorted(mismatch, key=lambda r: r.pelgrom)
    return Plot(
        name="mismatch_inl",
        title="The converter's worst INL with the design weights, 95th percentile, over a capacitor's coefficient",
        x_label="Pelgrom coefficient (%·sqrt(fF))",
        y_label="INL (LSB)",
        x=[r.pelgrom * 100 for r in chosen],
        series={"inl": [r.inl_p95_lsb for r in chosen]},
    )


@plot
def plot_mismatch_gap(mismatch: Sequence[AnalysisMismatch]) -> Plot:
    """What no calibration recovers, 95th percentile over the runs, over Pelgrom's coefficient."""
    # not in the reference texts: the widest input range one decision path holds over a code's width,
    #   less one (a width less 1 LSB, as [Razavi-ADC] Eq. (12.11), p. 242's DNL): what an ideal
    #   calibration of every decision's weight still cannot split, 0 where no path is wider than a
    #   code; its 95th percentile over the runs against A_C ([Pelgrom] Eq. (4.34), p. 144)
    chosen = sorted(mismatch, key=lambda r: r.pelgrom)
    return Plot(
        name="mismatch_gap",
        title="Unrecoverable code width after ideal calibration, 95th percentile, over a capacitor's coefficient",
        x_label="Pelgrom coefficient (%·sqrt(fF))",
        y_label="Widest code less one (LSB)",
        x=[r.pelgrom * 100 for r in chosen],
        series={"widest code less one": [r.gap_p95_lsb for r in chosen]},
    )


@plot
def plot_mismatch_dac_inl(mismatch: Sequence[AnalysisMismatch]) -> Plot:
    """The DAC's worst INL (the worse side), 95th percentile over the runs, over Pelgrom's
    coefficient."""
    # [Razavi-ADC] Sec. 11.4, p. 216; Eq. (11.19), p. 217: a CDAC's INL from random capacitor mismatch,
    #   its SD proportional to Delta C / C_0 (a thermometric array's, at mid-scale); [Pelgrom] Eq.
    #   (4.34), p. 144: sigma_C / C = A_C / sqrt(C), A_C the coefficient on the x axis; the 95th
    #   percentile of each run's worst |INL| (the worse side's, in the DAC's own LSB) over A_C frida's own
    chosen = sorted(mismatch, key=lambda r: r.pelgrom)
    return Plot(
        name="mismatch_dac_inl",
        title="The DAC's worst INL in its own LSB, 95th percentile, over a capacitor's coefficient",
        x_label="Pelgrom coefficient (%·sqrt(fF))",
        y_label="INL (LSB)",
        x=[r.pelgrom * 100 for r in chosen],
        series={"inl": [r.dac_inl_p95_lsb for r in chosen]},
    )


@plot
def plot_dac_inl(mismatch: AnalysisMismatch) -> Plot:
    """The DAC's INL by code (each code's worst control word) of the run at the 95th percentile."""
    # [Razavi-ADC] Sec. 8.2, Fig. 8.11(b), p. 147: a DAC's INL profile, the characteristic less the line
    #   through its end points, by input code; here a redundant array's words decoded to codes by the
    #   design weights, each code's worst (``calc_dac_transfer``), of the run nearest the DAC's INL's
    #   95th percentile
    return Plot(
        name="dac_inl",
        title="DAC INL in its own LSB by code (the control word by its design weights), the 95th-percentile run at the middle condition",
        x_label="Code",
        y_label="INL (LSB)",
        x=list(range(len(mismatch.dac_inl_curve_lsb))),
        series={"inl": [float(v) for v in mismatch.dac_inl_curve_lsb]},
        x_ticks="code",
    )


@plot
def plot_dac_dnl(mismatch: AnalysisMismatch) -> Plot:
    """The DAC's DNL by code (its words' mean output) of the run at the 95th percentile."""
    # [Razavi-ADC] Eq. (8.5), p. 145: DNL_j = Delta A_j - Delta A_LSB, an output step less the nominal
    #   LSB; Fig. 8.8, p. 146: the DNL plotted by input code; here the step between each code's words'
    #   mean outputs, in the end points' LSB (``calc_dac_transfer``), of the run nearest the DAC's
    #   INL's 95th percentile
    return Plot(
        name="dac_dnl",
        title="DAC DNL in its own LSB by code (the control word by its design weights), the 95th-percentile run at the middle condition",
        x_label="Code",
        y_label="DNL (LSB)",
        x=list(range(len(mismatch.dac_dnl_curve_lsb))),
        series={"dnl": [float(v) for v in mismatch.dac_dnl_curve_lsb]},
        x_ticks="code",
    )


@plot
def plot_fraction_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's effective fraction of its side's capacitance, P's and N's mean, from its
    switching curves (``analyze_cap_mismatch``)."""
    # [Razavi-ADC] Eq. (11.3), p. 211: a step's share of V_REF, k C_0 over the top plate's whole load
    #   (4 C_0 + C_L there); here that share measured, (V_OS - V_transition) / V_REF of the converter's
    #   switching (main less difference plate), P's and N's mean, by stage (the figure frida's own)
    return _by_stage(
        "fraction_stage",
        "Effective fraction by stage (P and N mean)",
        "Effective fraction",
        cap_mismatch.fraction,
        "effective fraction",
    )


@plot
def plot_fraction_error_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's effective fraction (P's and N's mean) less the design's expectation (its weights
    over its total and the top plate's parasitic)."""
    # not in the reference texts: each stage's measured fraction less the design's expectation (its
    #   weight over the array's total and the top plate's load, as [Razavi-ADC] Eq. (11.3), p. 211
    #   gives a step over V_REF), P's and N's mean, by stage: a stage drawn other than its weight
    return _by_stage(
        "fraction_error_stage",
        "Effective fraction less the design's by stage",
        "Effective fraction less the design's",
        cap_mismatch.fraction_error,
        "effective fraction error",
    )


@plot
def plot_asymmetry_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's effective fraction, P's less N's."""
    # not in the reference texts: each stage's effective fraction, P's less N's, by stage: the two
    #   sides' mismatch, zero for sides drawn alike
    return _by_stage(
        "asymmetry_stage",
        "Effective fraction, P less N, by stage",
        "P less N effective fraction",
        cap_mismatch.asymmetry,
        "effective fraction asymmetry",
    )


@plot
def plot_separation_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's difference plates, P's and N's together (twice their fraction's mean): how far
    apart its two modes put its weight."""
    # not in the reference texts: each stage's mode 0 (main plus difference plate) less mode 1 (main
    #   less difference) fraction, halved a side and summed over P and N: twice the difference
    #   plate's fraction (the sides' mean), by stage
    return _by_stage(
        "separation_stage",
        "Difference plates by stage (P and N together)",
        "Difference fraction, P plus N",
        cap_mismatch.separation,
        "difference fraction",
    )


@plot
def plot_main_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's main plate's fraction, P's and N's mean."""
    # not in the reference texts: each stage's main plate's fraction, (mode 0 + mode 1) / 2 of its
    #   switching curves, P's and N's mean, by stage (a plate's capacitance over the top plate's
    #   load, as [Razavi-ADC] Eq. (11.3), p. 211 gives a step over V_REF)
    return _by_stage(
        "main_stage",
        "Main plate's fraction by stage (P and N mean)",
        "Main fraction",
        cap_mismatch.main,
        "main fraction",
    )


@plot
def plot_bias_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's switching-direction bias as the converter switches it (main and difference
    plates against each other): half its 1-to-0 less its 0-to-1 fraction, P's and N's mean."""
    # not in the reference texts: each stage's direction bias in mode 1 (main and difference plates
    #   switched opposite, as the converter switches them): half its 1-to-0 less its 0-to-1
    #   fraction, P's and N's mean, by stage; zero where a stage's two directions agree
    return _by_stage(
        "bias_stage",
        "Switching-direction bias by stage (P and N mean), a fraction",
        "Direction bias",
        cap_mismatch.bias,
        "direction bias",
    )


def _by_stage(name: str, title: str, y_label: str, values: np.ndarray, series: str) -> Plot:
    """One fraction of each stage (C0, the MSB, first), NaN where its curves gave none; its
    ``series`` the quantity in lower case."""
    return Plot(
        name=name,
        title=f"{title}, C0 (the MSB) first",
        x_label="Stage",
        y_label=y_label,
        x=[float(stage) for stage in range(len(values))],
        series={series: [float(value) for value in values]},
        x_ticks="step",
    )
