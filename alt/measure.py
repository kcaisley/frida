"""
Shared measurement functions for FRIDA HDL21 generators.

Provides post-processing functions to extract metrics from simulation results.
These functions work with HDL21 SimResult objects from vlsirtools.
"""

from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import hdl21.sim as hs


# =============================================================================
# Waveform Helpers
# =============================================================================


def _find_crossings(
    signal: np.ndarray,
    time: np.ndarray,
    threshold: float,
    rising: bool = True,
) -> List[float]:
    """
    Find interpolated crossing times.

    Args:
        signal: Voltage/current waveform array
        time: Time array
        threshold: Crossing threshold value
        rising: True for rising edge, False for falling edge

    Returns:
        List of interpolated crossing times
    """
    crossings = []

    for i in range(len(signal) - 1):
        if rising:
            # Rising edge: signal goes from below to above threshold
            if signal[i] < threshold <= signal[i + 1]:
                # Linear interpolation
                t_cross = time[i] + (threshold - signal[i]) / (signal[i + 1] - signal[i]) * (time[i + 1] - time[i])
                crossings.append(t_cross)
        else:
            # Falling edge: signal goes from above to below threshold
            if signal[i] > threshold >= signal[i + 1]:
                t_cross = time[i] + (signal[i] - threshold) / (signal[i] - signal[i + 1]) * (time[i + 1] - time[i])
                crossings.append(t_cross)

    return crossings


def _get_waveform(result: hs.SimResult, name: str, analysis_idx: int = 0) -> Optional[np.ndarray]:
    """
    Extract waveform from SimResult.

    Args:
        result: SimResult object
        name: Signal name (e.g., "v(out)" or "xtop.out")
        analysis_idx: Index of analysis (for multiple analyses)

    Returns:
        Numpy array of waveform data, or None if not found
    """
    try:
        data = result.an[analysis_idx].data
        # Try exact name first, then with v() prefix
        if name in data:
            return np.array(data[name])
        elif f"v({name})" in data:
            return np.array(data[f"v({name})"])
        return None
    except (IndexError, KeyError, AttributeError):
        return None


def _get_time(result: hs.SimResult, analysis_idx: int = 0) -> Optional[np.ndarray]:
    """
    Extract time array from SimResult.

    Args:
        result: SimResult object
        analysis_idx: Index of analysis

    Returns:
        Numpy array of time data, or None if not found
    """
    try:
        data = result.an[analysis_idx].data
        if "time" in data:
            return np.array(data["time"])
        elif "TIME" in data:
            return np.array(data["TIME"])
        return None
    except (IndexError, KeyError, AttributeError):
        return None


# =============================================================================
# Comparator Measurements
# =============================================================================


def comp_offset_mV(
    result: hs.SimResult,
    inp: str = "xtop.inp",
    inn: str = "xtop.inn",
    outp: str = "xtop.outp",
    outn: str = "xtop.outn",
) -> float:
    """
    Extract input-referred offset from S-curve data.

    The offset is the differential input voltage where the comparator
    output has 50% probability of being high.

    For a single deterministic simulation, this finds where outp crosses outn.

    Args:
        result: SimResult from transient simulation
        inp: Positive input signal name
        inn: Negative input signal name
        outp: Positive output signal name
        outn: Negative output signal name

    Returns:
        Input-referred offset in mV
    """
    time = _get_time(result)
    v_inp = _get_waveform(result, inp)
    v_inn = _get_waveform(result, inn)
    v_outp = _get_waveform(result, outp)
    v_outn = _get_waveform(result, outn)

    if any(x is None for x in [time, v_inp, v_inn, v_outp, v_outn]):
        return float("nan")

    # Calculate differential signals
    v_diff_in = v_inp - v_inn
    v_diff_out = v_outp - v_outn

    # Find where output crosses zero (decision point)
    crossings = _find_crossings(v_diff_out, time, 0.0, rising=True)
    crossings.extend(_find_crossings(v_diff_out, time, 0.0, rising=False))

    if not crossings:
        return float("nan")

    # At the crossing time, find the input differential voltage
    t_cross = crossings[0]
    idx = np.searchsorted(time, t_cross)
    if idx >= len(v_diff_in):
        idx = len(v_diff_in) - 1

    offset_V = v_diff_in[idx]
    return offset_V * 1000  # Convert to mV


def comp_noise_sigma_mV(
    result: hs.SimResult,
    inp: str = "xtop.inp",
    inn: str = "xtop.inn",
    outp: str = "xtop.outp",
    outn: str = "xtop.outn",
) -> float:
    """
    Extract input-referred noise sigma from S-curve width.

    The noise sigma is derived from the slope of the S-curve at the transition.
    A steeper slope indicates lower noise.

    Note: This requires S-curve sweep data (multiple differential voltages).
    For single-point data, returns NaN.

    Args:
        result: SimResult from S-curve sweep
        inp: Positive input signal name
        inn: Negative input signal name
        outp: Positive output signal name
        outn: Negative output signal name

    Returns:
        Input-referred noise sigma in mV
    """
    # S-curve analysis requires sweep data
    # This is a placeholder - actual implementation needs sweep results
    return float("nan")


def comp_delay_ns(
    result: hs.SimResult,
    clk: str = "xtop.clk",
    outp: str = "xtop.outp",
    outn: str = "xtop.outn",
    vdd: float = 1.2,
) -> float:
    """
    Extract decision delay (clk edge to output crossing).

    Measures time from clock rising edge to when differential output
    crosses the decision threshold.

    Args:
        result: SimResult from transient simulation
        clk: Clock signal name
        outp: Positive output signal name
        outn: Negative output signal name
        vdd: Supply voltage for threshold calculation

    Returns:
        Decision delay in nanoseconds
    """
    time = _get_time(result)
    v_clk = _get_waveform(result, clk)
    v_outp = _get_waveform(result, outp)
    v_outn = _get_waveform(result, outn)

    if any(x is None for x in [time, v_clk, v_outp, v_outn]):
        return float("nan")

    # Find clock rising edge (50% of VDD)
    clk_threshold = vdd / 2
    clk_crossings = _find_crossings(v_clk, time, clk_threshold, rising=True)

    if not clk_crossings:
        return float("nan")

    t_clk = clk_crossings[0]

    # Find output crossing (when |outp - outn| exceeds VDD/2)
    v_diff_out = np.abs(v_outp - v_outn)
    out_threshold = vdd / 2

    out_crossings = _find_crossings(v_diff_out, time, out_threshold, rising=True)

    # Find first output crossing after clock edge
    for t_out in out_crossings:
        if t_out > t_clk:
            delay = t_out - t_clk
            return delay * 1e9  # Convert to ns

    return float("nan")


def comp_settling_ns(
    result: hs.SimResult,
    outp: str = "xtop.outp",
    outn: str = "xtop.outn",
    tol: float = 0.01,
    vdd: float = 1.2,
) -> float:
    """
    Extract settling time to within tolerance of final value.

    Args:
        result: SimResult from transient simulation
        outp: Positive output signal name
        outn: Negative output signal name
        tol: Relative tolerance (default 1%)
        vdd: Supply voltage

    Returns:
        Settling time in nanoseconds
    """
    time = _get_time(result)
    v_outp = _get_waveform(result, outp)
    v_outn = _get_waveform(result, outn)

    if any(x is None for x in [time, v_outp, v_outn]):
        return float("nan")

    # Use differential output
    v_diff = v_outp - v_outn

    # Final value is at end of simulation
    final_value = v_diff[-1]
    threshold = abs(final_value) * tol

    # Find when signal stays within tolerance of final value
    settled = np.abs(v_diff - final_value) < threshold

    # Find first time that stays settled to the end
    for i in range(len(settled)):
        if np.all(settled[i:]):
            return time[i] * 1e9  # Convert to ns

    return float("nan")


def comp_power_uW(
    result: hs.SimResult,
    vdd_src: str = "vvdd",
    vdd: float = 1.2,
) -> float:
    """
    Extract average power consumption.

    Args:
        result: SimResult from transient simulation
        vdd_src: VDD voltage source name for current measurement
        vdd: Supply voltage

    Returns:
        Average power in microwatts
    """
    time = _get_time(result)
    i_vdd = _get_waveform(result, f"i({vdd_src})")

    if any(x is None for x in [time, i_vdd]):
        return float("nan")

    # Average current (note: current into vsource is negative)
    avg_current = -np.mean(i_vdd)

    # Power = V * I
    power_W = vdd * avg_current
    return power_W * 1e6  # Convert to uW


# =============================================================================
# CDAC/ADC Measurements
# =============================================================================


def compute_inl_dnl(
    codes: np.ndarray,
    outputs: np.ndarray,
) -> Dict[str, Any]:
    """
    Compute INL and DNL from code sweep results.

    Args:
        codes: Array of DAC codes
        outputs: Array of corresponding output values

    Returns:
        Dict with 'inl', 'dnl', 'inl_max', 'dnl_max' arrays/values
    """
    n_codes = len(codes)

    if n_codes < 2:
        return {
            "dnl": np.array([]),
            "inl": np.array([]),
            "dnl_max": float("nan"),
            "inl_max": float("nan"),
            "lsb": float("nan"),
        }

    # Ideal LSB from endpoint fit
    lsb_ideal = (outputs[-1] - outputs[0]) / (n_codes - 1)

    if abs(lsb_ideal) < 1e-15:
        return {
            "dnl": np.zeros(n_codes - 1),
            "inl": np.zeros(n_codes),
            "dnl_max": 0.0,
            "inl_max": 0.0,
            "lsb": 0.0,
        }

    # DNL: difference from ideal step
    steps = np.diff(outputs)
    dnl = (steps / lsb_ideal) - 1

    # INL: cumulative deviation from ideal line
    ideal_line = outputs[0] + np.arange(n_codes) * lsb_ideal
    inl = (outputs - ideal_line) / lsb_ideal

    return {
        "dnl": dnl,
        "inl": inl,
        "dnl_max": np.max(np.abs(dnl)),
        "inl_max": np.max(np.abs(inl)),
        "lsb": lsb_ideal,
    }


def cdac_settling_ns(
    result: hs.SimResult,
    top: str = "xtop.top",
    tol: float = 0.01,
) -> float:
    """
    Extract CDAC settling time.

    Args:
        result: SimResult from transient simulation
        top: CDAC top plate signal name
        tol: Relative tolerance (default 1%)

    Returns:
        Settling time in nanoseconds
    """
    time = _get_time(result)
    v_top = _get_waveform(result, top)

    if any(x is None for x in [time, v_top]):
        return float("nan")

    final_value = v_top[-1]
    if abs(final_value) < 1e-15:
        return float("nan")

    threshold = abs(final_value) * tol
    settled = np.abs(v_top - final_value) < threshold

    for i in range(len(settled)):
        if np.all(settled[i:]):
            return time[i] * 1e9

    return float("nan")


# =============================================================================
# Monte Carlo Statistics
# =============================================================================


def mc_statistics(values: List[float]) -> Dict[str, float]:
    """
    Compute statistics from Monte Carlo results.

    Args:
        values: List of scalar results from MC runs

    Returns:
        Dict with mean, std, min, max, 3sigma values
    """
    arr = np.array(values)

    if len(arr) == 0:
        return {
            "mean": float("nan"),
            "std": float("nan"),
            "min": float("nan"),
            "max": float("nan"),
            "n": 0,
            "sigma3_low": float("nan"),
            "sigma3_high": float("nan"),
        }

    mean = np.mean(arr)
    std = np.std(arr)

    return {
        "mean": mean,
        "std": std,
        "min": np.min(arr),
        "max": np.max(arr),
        "n": len(arr),
        "sigma3_low": mean - 3 * std,
        "sigma3_high": mean + 3 * std,
    }


# =============================================================================
# Sampler Measurements
# =============================================================================


def samp_settling_ns(
    result: hs.SimResult,
    din: str = "xtop.din",
    dout: str = "xtop.dout",
    tol: float = 0.01,
) -> float:
    """
    Extract sampler settling time.

    Measures time for output to reach within tolerance of input.

    Args:
        result: SimResult from transient simulation
        din: Input signal name
        dout: Output signal name
        tol: Relative tolerance (default 1%)

    Returns:
        Settling time in nanoseconds
    """
    time = _get_time(result)
    v_in = _get_waveform(result, din)
    v_out = _get_waveform(result, dout)

    if any(x is None for x in [time, v_in, v_out]):
        return float("nan")

    # Target is the input voltage
    target = v_in[-1]  # Assume DC input
    threshold = abs(target) * tol if abs(target) > 1e-15 else tol

    error = np.abs(v_out - target)
    settled = error < threshold

    for i in range(len(settled)):
        if np.all(settled[i:]):
            return time[i] * 1e9

    return float("nan")


def samp_charge_injection_mV(
    result: hs.SimResult,
    dout: str = "xtop.dout",
    clk: str = "xtop.clk",
    vdd: float = 1.2,
) -> float:
    """
    Estimate charge injection from clock transition.

    Measures the output voltage change when clock goes low (switch opens).

    Args:
        result: SimResult from transient simulation
        dout: Output signal name
        clk: Clock signal name
        vdd: Supply voltage for threshold

    Returns:
        Charge injection in mV
    """
    time = _get_time(result)
    v_out = _get_waveform(result, dout)
    v_clk = _get_waveform(result, clk)

    if any(x is None for x in [time, v_out, v_clk]):
        return float("nan")

    # Find clock falling edge
    clk_threshold = vdd / 2
    falling_edges = _find_crossings(v_clk, time, clk_threshold, rising=False)

    if not falling_edges:
        return float("nan")

    t_fall = falling_edges[0]
    idx_fall = np.searchsorted(time, t_fall)

    if idx_fall >= len(v_out) - 10:
        return float("nan")

    # Voltage just before and after clock falling edge
    v_before = v_out[idx_fall - 1]
    v_after = v_out[min(idx_fall + 10, len(v_out) - 1)]  # Allow some settling

    delta_v = v_after - v_before
    return delta_v * 1000  # Convert to mV
