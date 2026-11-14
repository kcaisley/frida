"""The delay line and ring oscillator's figures as ``Plot`` specs (``flow.pipeline.Plot``), each
from analysis results alone: a characterization's condition sweeps, over the supply (at the nominal
control, which a supply plot's title states with the nominal supply in volts) and over the control
voltage (at the supply its title states). Each point whose drawn value is missing (NaN) is a gap in
its curve, marked at its x: a ring's by its state (``Oscillation``) where it was not timed. A
differential chain's values are its p chain's, single-ended. The viewer draws a record's from its
JSON, ``flow.plot.render`` any with matplotlib (the CLI's figures step)."""

from __future__ import annotations

import math

from flow.pipeline import Marker, Plot, plot

from .params import SUPPLY_SWEEP, Control, Oscillation
from .types import AnalysisOscillation, AnalysisPropagation


def _condition(chain: AnalysisOscillation | AnalysisPropagation) -> str:
    """A supply plot's condition: the nominal supply in volts, and the control voltage it was
    measured at where the chain has one."""
    nominal = f"nominal {float(chain.vdd_v[SUPPLY_SWEEP.index(1.0)]):g} V"
    if chain.dut.control is Control.NONE:
        return f" ({nominal})"
    return f" ({nominal}, control {float(chain.vcont_v[0]):g} V)"


def _supply(chain: AnalysisOscillation | AnalysisPropagation) -> str:
    """A control plot's condition: the supply voltage it was measured at."""
    return f" (supply {float(chain.vdd_v[0]):g} V)"


def _gaps(
    chain: AnalysisOscillation | AnalysisPropagation, x: list[float], values: list[float], missing: str = "not timed"
) -> list[Marker]:
    """A marker at each point of ``x`` whose drawn value (``values``) is NaN: a ring's named by its
    state where it was not timed (stopped, slow), otherwise ``missing``."""
    states = chain.oscillation if isinstance(chain, AnalysisOscillation) else (Oscillation.TIMED,) * len(x)
    return [
        Marker(at, missing if state is Oscillation.TIMED else state.name.lower())
        for at, value, state in zip(x, values, states, strict=True)
        if not math.isfinite(value)
    ]


# [Razavi-PLL] Sec. 3.2, p. 72: the supply sensitivity K_VDD, the frequency's change with V_DD (the
# text after Eq. (3.24)); [Razavi-PLL] Sec. 1.4.1, p. 12: an inverter's delay falls as V_DD rises
@plot
def plot_oscillation_frequency_supply(oscillation: AnalysisOscillation) -> Plot:
    """A ring's frequency over the supply (``SUPPLY_SWEEP``)."""
    values = [float(value) for value in oscillation.oscillation_frequency_hz]
    return Plot(
        name="oscillation_frequency_supply",
        title=f"Ring frequency over the supply{_condition(oscillation)}",
        x_label="Supply over nominal",
        y_label="Oscillation frequency (Hz)",
        x=list(SUPPLY_SWEEP),
        x_markers=_gaps(oscillation, list(SUPPLY_SWEEP), values),
        series={"oscillation frequency": values},
    )


# [Baker] Sec. 10.1.3, Fig. 10.9, p. 333: t_PLH, the delay to the rising output
@plot
def plot_delay_rise_supply(propagation: AnalysisPropagation) -> Plot:
    """A delay line's delay to its rising output over the supply (``SUPPLY_SWEEP``)."""
    values = [float(value) for value in propagation.delay_rise_s]
    return Plot(
        name="delay_rise_supply",
        title=f"Line delay to the rising output over the supply{_condition(propagation)}",
        x_label="Supply over nominal",
        y_label="Delay (s)",
        x=list(SUPPLY_SWEEP),
        x_markers=_gaps(propagation, list(SUPPLY_SWEEP), values),
        series={"delay": values},
    )


# [Baker] Sec. 10.1.3, Fig. 10.9, p. 333: t_PHL, the delay to the falling output
@plot
def plot_delay_fall_supply(propagation: AnalysisPropagation) -> Plot:
    """A delay line's delay to its falling output over the supply (``SUPPLY_SWEEP``)."""
    values = [float(value) for value in propagation.delay_fall_s]
    return Plot(
        name="delay_fall_supply",
        title=f"Line delay to the falling output over the supply{_condition(propagation)}",
        x_label="Supply over nominal",
        y_label="Delay (s)",
        x=list(SUPPLY_SWEEP),
        x_markers=_gaps(propagation, list(SUPPLY_SWEEP), values),
        series={"delay": values},
    )


# [Razavi-PLL] Sec. 3.3.2, p. 74: a ring's f0 = 1 / (2 N T_D), the mean derived with [Baker]
# Eq. (11.11), p. 354; [Razavi-Analog] Sec. 15.4.1, p. 633: a differential ring's; [Baker] Eq. (11.22),
# p. 360: a string's t_PHL + t_PLH, the sum of its stages'; the mean stage delay (t_PLH + t_PHL) / (2 N)
# not in the reference texts: the mean stage delay drawn over the supply (the model's curve)
@plot
def plot_stage_delay_supply(chain: AnalysisOscillation | AnalysisPropagation) -> Plot:
    """The mean delay per stage over the supply (``SUPPLY_SWEEP``): a ring's 1 / (2 N f0), a delay
    line's (t_PLH + t_PHL) / (2 N); the mean over unequal stages, the gated first stage of a ring
    and the output stage, which drives the load stages, among them."""
    values = [float(value) for value in chain.stage_delay_s]
    return Plot(
        name="stage_delay_supply",
        title=f"Mean stage delay over the supply{_condition(chain)}",
        x_label="Supply over nominal",
        y_label="Stage delay (s)",
        x=list(SUPPLY_SWEEP),
        x_markers=_gaps(chain, list(SUPPLY_SWEEP), values),
        series={"stage delay": values},
    )


# [Baker] Eq. (11.15), p. 355: P_avg = C_tot V_DD^2 f_clk, a cycle's energy C_tot V_DD^2
# [Baker] Eq. (19.27), p. 572: the VCO's power without its bias mirror (the text after it: the mirror
# would double it), which this also leaves out
@plot
def plot_energy_supply(chain: AnalysisOscillation | AnalysisPropagation) -> Plot:
    """The energy per cycle from the chain's own supply over the supply (``SUPPLY_SWEEP``), the bias
    generation excluded: a ring's own cycle, a delay line's input clock's."""
    cycle = "cycle" if isinstance(chain, AnalysisOscillation) else "input cycle"
    values = [float(value) for value in chain.energy_per_cycle_j]
    return Plot(
        name="energy_supply",
        title=f"Energy per {cycle} over the supply, bias excluded{_condition(chain)}",
        x_label="Supply over nominal",
        y_label="Energy per cycle (J)",
        x=list(SUPPLY_SWEEP),
        x_markers=_gaps(chain, list(SUPPLY_SWEEP), values),
        series={"energy per cycle": values},
    )


# [Razavi-PLL] Sec. 11.10, Fig. 11.29(a), p. 365: duty cycle, the high time over the period
# not in the reference texts: the duty cycle drawn over the supply
@plot
def plot_duty_cycle_supply(oscillation: AnalysisOscillation) -> Plot:
    """A ring's duty cycle over the supply (``SUPPLY_SWEEP``)."""
    values = [float(value) for value in oscillation.duty_cycle]
    return Plot(
        name="duty_cycle_supply",
        title=f"Ring duty cycle over the supply{_condition(oscillation)}",
        x_label="Supply over nominal",
        y_label="Duty cycle",
        x=list(SUPPLY_SWEEP),
        x_markers=_gaps(oscillation, list(SUPPLY_SWEEP), values),
        series={"duty cycle": values},
    )


# [Razavi-PLL] Fig. 1.33, p. 28: the VCO's tuning characteristic, f over V_cont; Fig. 3.34, p. 89: a
# ring's, simulated
@plot
def plot_oscillation_frequency_control(oscillation: AnalysisOscillation) -> Plot:
    """A ring's frequency over the control voltage."""
    values = [float(value) for value in oscillation.oscillation_frequency_hz]
    return Plot(
        name="oscillation_frequency_control",
        title=f"Ring frequency over the control{_supply(oscillation)}",
        x_label="Control voltage (V)",
        y_label="Oscillation frequency (Hz)",
        x=[float(value) for value in oscillation.vcont_v],
        x_markers=_gaps(oscillation, [float(value) for value in oscillation.vcont_v], values),
        series={"oscillation frequency": values},
    )


# [Razavi-PLL] Fig. 3.27, p. 84: K_VCO the local slope of the tuning curve, changing along it;
# [Razavi-PLL] Sec. 1.6, pp. 27-28: K_VCO (here in Hz/V)
@plot
def plot_kvco_control(oscillation: AnalysisOscillation) -> Plot:
    """A ring's VCO gain, its frequency's slope, over the control voltage."""
    values = [float(value) for value in oscillation.kvco_hz_per_v]
    return Plot(
        name="kvco_control",
        title=f"VCO gain over the control{_supply(oscillation)}",
        x_label="Control voltage (V)",
        y_label="VCO gain (Hz/V)",
        x=[float(value) for value in oscillation.vcont_v],
        x_markers=_gaps(oscillation, [float(value) for value in oscillation.vcont_v], values, "no timed neighbour"),
        series={"VCO gain": values},
    )


# [Razavi-PLL] Sec. 11.10, Fig. 11.29(a), (c), p. 365: duty cycle, the high time over the period, set
# by an inverter's rise and fall times, which starving devices change
# not in the reference texts: the duty cycle drawn over the control
@plot
def plot_duty_cycle_control(oscillation: AnalysisOscillation) -> Plot:
    """A ring's duty cycle over the control voltage."""
    values = [float(value) for value in oscillation.duty_cycle]
    return Plot(
        name="duty_cycle_control",
        title=f"Ring duty cycle over the control{_supply(oscillation)}",
        x_label="Control voltage (V)",
        y_label="Duty cycle",
        x=[float(value) for value in oscillation.vcont_v],
        x_markers=_gaps(oscillation, [float(value) for value in oscillation.vcont_v], values),
        series={"duty cycle": values},
    )


# [Razavi-PLL] Sec. 11.2, Eq. (11.1), p. 347: a VCDL's delay as a function of V_cont
@plot
def plot_delay_rise_control(propagation: AnalysisPropagation) -> Plot:
    """A delay line's delay to its rising output over the control voltage."""
    values = [float(value) for value in propagation.delay_rise_s]
    return Plot(
        name="delay_rise_control",
        title=f"Line delay to the rising output over the control{_supply(propagation)}",
        x_label="Control voltage (V)",
        y_label="Delay (s)",
        x=[float(value) for value in propagation.vcont_v],
        x_markers=_gaps(propagation, [float(value) for value in propagation.vcont_v], values),
        series={"delay": values},
        y_log=True,
    )


# [Razavi-PLL] Sec. 11.2, Eq. (11.1), p. 347: a VCDL's delay as a function of V_cont
@plot
def plot_delay_fall_control(propagation: AnalysisPropagation) -> Plot:
    """A delay line's delay to its falling output over the control voltage."""
    values = [float(value) for value in propagation.delay_fall_s]
    return Plot(
        name="delay_fall_control",
        title=f"Line delay to the falling output over the control{_supply(propagation)}",
        x_label="Control voltage (V)",
        y_label="Delay (s)",
        x=[float(value) for value in propagation.vcont_v],
        x_markers=_gaps(propagation, [float(value) for value in propagation.vcont_v], values),
        series={"delay": values},
        y_log=True,
    )


# [Baker] Sec. 10.1.3, Fig. 10.9, p. 333; Eq. (2.26), p. 49: t_LH, 10 to 90 %
# not in the reference texts: the output transitions drawn over a starving control, on the delays'
# log scale (both span several times over it)
@plot
def plot_rise_time_control(propagation: AnalysisPropagation) -> Plot:
    """A delay line's output rise time (10 to 90 %) over the control voltage."""
    values = [float(value) for value in propagation.rise_time_s]
    return Plot(
        name="rise_time_control",
        title=f"Line output rise time over the control{_supply(propagation)}",
        x_label="Control voltage (V)",
        y_label="Rise time (s)",
        x=[float(value) for value in propagation.vcont_v],
        x_markers=_gaps(propagation, [float(value) for value in propagation.vcont_v], values),
        series={"rise time": values},
        y_log=True,
    )


# [Baker] Sec. 10.1.3, Fig. 10.9, p. 333; Eq. (2.26), p. 49: t_HL, 90 to 10 %
# not in the reference texts: the output transitions drawn over a starving control, on the delays'
# log scale (both span several times over it)
@plot
def plot_fall_time_control(propagation: AnalysisPropagation) -> Plot:
    """A delay line's output fall time (90 to 10 %) over the control voltage."""
    values = [float(value) for value in propagation.fall_time_s]
    return Plot(
        name="fall_time_control",
        title=f"Line output fall time over the control{_supply(propagation)}",
        x_label="Control voltage (V)",
        y_label="Fall time (s)",
        x=[float(value) for value in propagation.vcont_v],
        x_markers=_gaps(propagation, [float(value) for value in propagation.vcont_v], values),
        series={"fall time": values},
        y_log=True,
    )


# [Baker] Eq. (11.15), p. 355: P_avg = C_tot V_DD^2 f_clk, a cycle's energy C_tot V_DD^2
# [Baker] Eq. (19.27), p. 572: the VCO's power without its bias mirror (the text after it: the mirror
# would double it), which this also leaves out
# not in the reference texts: the energy drawn over the control
@plot
def plot_energy_control(chain: AnalysisOscillation | AnalysisPropagation) -> Plot:
    """The energy per cycle from the chain's own supply over the control voltage, the bias
    generation excluded: a ring's own cycle, a delay line's input clock's."""
    cycle = "cycle" if isinstance(chain, AnalysisOscillation) else "input cycle"
    values = [float(value) for value in chain.energy_per_cycle_j]
    return Plot(
        name="energy_control",
        title=f"Energy per {cycle} over the control, bias excluded{_supply(chain)}",
        x_label="Control voltage (V)",
        y_label="Energy per cycle (J)",
        x=[float(value) for value in chain.vcont_v],
        x_markers=_gaps(chain, [float(value) for value in chain.vcont_v], values),
        series={"energy per cycle": values},
    )
