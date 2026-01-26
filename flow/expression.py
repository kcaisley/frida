"""
Measurement expression functions for PyOPUS PerformanceEvaluator.

These functions are called from the 'expression' field in cell measures dicts.
Each function receives waveform accessors and returns a scalar metric.

Function signature convention:
    func(v, scale, ...) -> float

    v: Voltage accessor - v('node') returns voltage waveform array
    i: Current accessor - i('source') returns current waveform array
    scale: Time scale function - scale() returns time array in seconds
"""

import numpy as np


# ============================================================
# Helper Functions
# ============================================================


def _find_crossings(signal, time, threshold, rising=True):
    """
    Find time points where signal crosses threshold.

    Args:
        signal: Voltage waveform array
        time: Time array
        threshold: Crossing threshold voltage
        rising: If True, find rising edges; if False, find falling edges

    Returns:
        List of crossing times (interpolated)
    """
    if rising:
        # Rising: signal goes from below to above threshold
        below = signal[:-1] < threshold
        above = signal[1:] >= threshold
        cross_idx = np.where(below & above)[0]
    else:
        # Falling: signal goes from above to below threshold
        above = signal[:-1] >= threshold
        below = signal[1:] < threshold
        cross_idx = np.where(above & below)[0]

    # Interpolate to find exact crossing times
    crossings = []
    for idx in cross_idx:
        v0, v1 = signal[idx], signal[idx + 1]
        t0, t1 = time[idx], time[idx + 1]
        if v1 != v0:
            t_cross = t0 + (threshold - v0) * (t1 - t0) / (v1 - v0)
            crossings.append(t_cross)

    return crossings


# ============================================================
# Comparator Measurements
# ============================================================


def comp_offset_mV(v, scale, inp_p, inp_n, out_p, out_n):
    """
    Measure comparator input-referred offset voltage.

    Finds the differential input voltage at which the comparator
    makes 50% high decisions. Uses the swept Vdiff testbench.

    Args:
        v: Voltage accessor v('node')
        scale: Time scale function
        inp_p: Positive input node name
        inp_n: Negative input node name
        out_p: Positive output node name
        out_n: Negative output node name

    Returns:
        Input-referred offset in millivolts
    """
    time = scale()
    v_inp = v(inp_p)
    v_inn = v(inp_n)
    v_outp = v(out_p)
    v_outn = v(out_n)

    # Differential signals
    v_in_diff = v_inp - v_inn
    v_out_diff = v_outp - v_outn

    # Sample at end of each clock period (settled decision)
    # Clock period is 10ns, sample at 90% of each period
    clk_period = 10e-9
    n_cycles = int(time[-1] / clk_period)

    decisions = []
    vin_at_decision = []

    for i in range(n_cycles):
        t_sample = (i + 0.9) * clk_period
        idx = np.searchsorted(time, t_sample)
        if idx < len(v_out_diff):
            decisions.append(v_out_diff[idx] > 0)
            vin_at_decision.append(v_in_diff[idx])

    if not decisions:
        return float('nan')

    # Find transition region where decisions change
    decisions = np.array(decisions)
    vin_at_decision = np.array(vin_at_decision)

    # Estimate offset as input voltage where P(high) ≈ 0.5
    # Use linear interpolation in transition region
    p_high = np.convolve(decisions.astype(float), np.ones(10)/10, mode='same')

    # Find where p_high crosses 0.5
    cross_idx = np.where((p_high[:-1] <= 0.5) & (p_high[1:] > 0.5))[0]
    if len(cross_idx) == 0:
        cross_idx = np.where((p_high[:-1] >= 0.5) & (p_high[1:] < 0.5))[0]

    if len(cross_idx) > 0:
        idx = cross_idx[len(cross_idx)//2]  # Use middle crossing
        offset_V = vin_at_decision[idx]
    else:
        # Fallback: use mean of inputs where decisions differ
        offset_V = np.mean(vin_at_decision)

    return float(offset_V * 1e3)  # Convert to mV


def comp_delay_ns(v, scale, clk, out_p, out_n):
    """
    Measure comparator decision delay.

    Time from clock rising edge to differential output crossing zero.

    Args:
        v: Voltage accessor v('node')
        scale: Time scale function
        clk: Clock node name
        out_p: Positive output node name
        out_n: Negative output node name

    Returns:
        Average decision delay in nanoseconds
    """
    time = scale()
    v_clk = v(clk)
    v_outp = v(out_p)
    v_outn = v(out_n)
    v_out_diff = v_outp - v_outn

    # Find clock rising edges (threshold at VDD/2 = 0.5V)
    clk_edges = _find_crossings(v_clk, time, 0.5, rising=True)

    delays = []
    for clk_time in clk_edges:
        # Find next output transition after this clock edge
        # Look for differential output crossing zero
        mask = time > clk_time
        if not np.any(mask):
            continue

        t_after = time[mask]
        v_after = v_out_diff[mask]

        # Find zero crossing (either direction)
        rising_cross = _find_crossings(v_after, t_after, 0.0, rising=True)
        falling_cross = _find_crossings(v_after, t_after, 0.0, rising=False)

        all_cross = rising_cross + falling_cross
        if all_cross:
            # Take first crossing after clock
            next_cross = min(all_cross)
            if next_cross < clk_time + 20e-9:  # Within 2 clock periods
                delays.append(next_cross - clk_time)

    if not delays:
        return float('nan')

    return float(np.mean(delays) * 1e9)  # Convert to ns


def comp_settling_ns(v, scale, out_p, out_n, tolerance):
    """
    Measure comparator output settling time.

    Time for differential output to settle within tolerance of final value
    after clock edge.

    Args:
        v: Voltage accessor v('node')
        scale: Time scale function
        out_p: Positive output node name
        out_n: Negative output node name
        tolerance: Settling tolerance as fraction of final value

    Returns:
        Average settling time in nanoseconds
    """
    time = scale()
    v_outp = v(out_p)
    v_outn = v(out_n)
    v_out_diff = v_outp - v_outn

    clk_period = 10e-9
    n_cycles = int(time[-1] / clk_period)

    settling_times = []

    for i in range(n_cycles - 1):
        t_start = i * clk_period
        t_end = (i + 1) * clk_period

        mask = (time >= t_start) & (time < t_end)
        t_seg = time[mask]
        v_seg = v_out_diff[mask]

        if len(v_seg) < 10:
            continue

        # Final value is at end of period
        v_final = v_seg[-1]
        if abs(v_final) < 0.1:  # Skip if no clear decision
            continue

        # Find when output enters settling band
        settling_band = tolerance * abs(v_final)
        settled_mask = np.abs(v_seg - v_final) <= settling_band

        # Find first point where it stays settled
        for j in range(len(settled_mask) - 1):
            if np.all(settled_mask[j:]):
                settling_times.append(t_seg[j] - t_start)
                break

    if not settling_times:
        return float('nan')

    return float(np.mean(settling_times) * 1e9)  # Convert to ns


def comp_overshoot_pct(v, scale, out_p, out_n):
    """
    Measure comparator output overshoot.

    Peak excursion beyond final value as percentage of total swing.

    Args:
        v: Voltage accessor v('node')
        scale: Time scale function
        out_p: Positive output node name
        out_n: Negative output node name

    Returns:
        Maximum overshoot as percentage of swing
    """
    time = scale()
    v_outp = v(out_p)
    v_outn = v(out_n)

    clk_period = 10e-9
    n_cycles = int(time[-1] / clk_period)

    max_overshoot = 0.0

    for i in range(n_cycles - 1):
        t_start = i * clk_period
        t_end = (i + 1) * clk_period

        mask = (time >= t_start) & (time < t_end)
        vp_seg = v_outp[mask]
        vn_seg = v_outn[mask]

        if len(vp_seg) < 10:
            continue

        # Check each output for overshoot beyond rails
        # Assume VDD=1.0, VSS=0.0
        vdd, vss = 1.0, 0.0

        # Overshoot above VDD
        overshoot_high_p = np.max(vp_seg) - vdd
        overshoot_high_n = np.max(vn_seg) - vdd

        # Undershoot below VSS
        overshoot_low_p = vss - np.min(vp_seg)
        overshoot_low_n = vss - np.min(vn_seg)

        max_os = max(overshoot_high_p, overshoot_high_n,
                     overshoot_low_p, overshoot_low_n, 0)
        max_overshoot = max(max_overshoot, max_os)

    # Convert to percentage of rail-to-rail swing
    swing = 1.0  # VDD - VSS
    return float(max_overshoot / swing * 100)


def comp_slew_Vns(v, scale, node):
    """
    Measure output slew rate.

    dV/dt at the 50% crossing point during transitions.

    Args:
        v: Voltage accessor v('node')
        scale: Time scale function
        node: Output node to measure

    Returns:
        Average slew rate in V/ns
    """
    time = scale()
    v_out = v(node)

    # Find all 50% crossings
    threshold = 0.5  # VDD/2
    rising = _find_crossings(v_out, time, threshold, rising=True)
    falling = _find_crossings(v_out, time, threshold, rising=False)

    slew_rates = []

    for t_cross in rising + falling:
        idx = np.searchsorted(time, t_cross)
        if idx < 2 or idx >= len(v_out) - 2:
            continue

        # Calculate local slope using 5-point stencil
        dt = time[idx+1] - time[idx-1]
        dv = v_out[idx+1] - v_out[idx-1]

        if dt > 0:
            slew = abs(dv / dt)
            slew_rates.append(slew)

    if not slew_rates:
        return float('nan')

    # Return in V/ns
    return float(np.mean(slew_rates) * 1e-9)


# ============================================================
# Power Measurements
# ============================================================


def comp_scurve(v, scale, inp_p, inp_n, out_p, out_n, clk_period=10e-9):
    """
    Generate S-curve: P(high) vs differential input voltage.

    Args:
        v: Voltage accessor v('node')
        scale: Time scale function
        inp_p: Positive input node name
        inp_n: Negative input node name
        out_p: Positive output node name
        out_n: Negative output node name
        clk_period: Clock period in seconds

    Returns:
        Tuple of (vin_diff_mV, p_high) numpy arrays
    """
    time = scale()
    v_in_diff = v(inp_p) - v(inp_n)
    v_out_diff = v(out_p) - v(out_n)

    n_cycles = int(time[-1] / clk_period)
    decisions = []
    vin_at_decision = []

    for i in range(n_cycles):
        t_sample = (i + 0.9) * clk_period
        idx = np.searchsorted(time, t_sample)
        if idx < len(v_out_diff):
            decisions.append(1 if v_out_diff[idx] > 0 else 0)
            vin_at_decision.append(v_in_diff[idx])

    if not decisions:
        return np.array([]), np.array([])

    # Group by input voltage (round to nearest mV)
    vin_mV = np.round(np.array(vin_at_decision) * 1000)
    decisions = np.array(decisions)

    unique_vin = np.unique(vin_mV)
    p_high = np.array([np.mean(decisions[vin_mV == vin]) for vin in unique_vin])

    return unique_vin, p_high


def comp_noise_sigma_mV(v, scale, inp_p, inp_n, out_p, out_n, clk_period=10e-9):
    """
    Extract input-referred noise sigma from S-curve width.

    Fits cumulative Gaussian (erf) to S-curve.

    Args:
        v: Voltage accessor v('node')
        scale: Time scale function
        inp_p: Positive input node name
        inp_n: Negative input node name
        out_p: Positive output node name
        out_n: Negative output node name
        clk_period: Clock period in seconds

    Returns:
        Noise sigma in millivolts
    """
    from scipy.optimize import curve_fit
    from scipy.special import erf

    vin_mV, p_high = comp_scurve(v, scale, inp_p, inp_n, out_p, out_n, clk_period)

    if len(vin_mV) < 3:
        return float('nan')

    def cdf(x, offset, sigma):
        return 0.5 * (1 + erf((x - offset) / (sigma * np.sqrt(2))))

    try:
        popt, _ = curve_fit(cdf, vin_mV, p_high, p0=[0, 5], bounds=([-50, 0.1], [50, 50]))
        return float(popt[1])  # sigma in mV
    except Exception:
        return float('nan')


# ============================================================
# Power Measurements
# ============================================================


def avg_power_uW(v, i, scale, supply):
    """
    Measure average power consumption.

    Integrates instantaneous power over simulation time.

    Args:
        v: Voltage accessor v('node')
        i: Current accessor i('source')
        scale: Time scale function
        supply: Supply voltage source name (e.g., 'Vvdd')

    Returns:
        Average power in microwatts
    """
    time = scale()

    # Get supply voltage and current
    v_supply = v(supply.lower().replace('v', '', 1))  # 'Vvdd' -> 'vdd'
    i_supply = i(supply)

    # Instantaneous power (current flows into source, so negate)
    power = v_supply * np.abs(i_supply)

    if len(time) < 2:
        return float('nan')

    # Average power over simulation
    avg_power = np.trapz(power, time) / (time[-1] - time[0])

    return float(avg_power * 1e6)  # Convert to µW
