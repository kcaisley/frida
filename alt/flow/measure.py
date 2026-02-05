"""
Shared measurement functions for FRIDA HDL21 generators.

Architecture Overview
---------------------
This module separates EXTRACTION (sim-specific) from MEASUREMENT (shared):

SIMULATION:                              DAQ:
─────────────────────────────────────────────────────────────────
SimResult                                SMU + FPGA
    │                                        │
    ▼                                        │
sim_extract_*() functions                    │
    │                                        │
    └──────────► numpy arrays ◄──────────────┘
                     │
                     ▼
            Shared measurement functions
            (work on numpy arrays only)
                     │
                     ▼
                 metrics dict

Extraction functions (sim-only):
- sim_get_time() - extract time array
- sim_get_waveform() - extract single waveform
- sim_get_waveforms() - extract multiple waveforms
- sim_sample_at_edges() - sample signals at clock edges

Measurement functions (shared, numpy arrays only):
- find_crossings() - find threshold crossing times
- diff_to_single() - differential to single-ended
- quantize_to_bits() - analog to digital threshold
- redundant_bits_to_code() - weighted bit sum for redundant SAR
- code_to_voltage() - code to estimated voltage
- measure_settling() - settling time measurement
- measure_delay() - delay between events
- measure_average_power() - power from V*I
- measure_offset_crossing() - offset from zero-crossing
- histogram_inl_dnl() - INL/DNL from histogram
- endpoint_inl_dnl() - INL/DNL from endpoint fit
- compute_static_error() - offset/gain/RMS error
- compute_enob_fft() - ENOB from FFT analysis
- mc_statistics() - Monte Carlo statistics
"""

from typing import Any

import hdl21.sim as hs
import numpy as np


# =============================================================================
# Simulation Extraction Functions (SimResult -> numpy arrays)
# =============================================================================


def sim_get_time(result: hs.SimResult, analysis_idx: int = 0) -> np.ndarray:
    """
    Extract time array from SimResult.

    Args:
        result: SimResult object
        analysis_idx: Index of analysis

    Returns:
        Numpy array of time data

    Raises:
        KeyError: If time data not found
    """
    data = result.an[analysis_idx].data
    if "time" in data:
        return np.array(data["time"])
    elif "TIME" in data:
        return np.array(data["TIME"])
    raise KeyError("Time data not found in SimResult")


def sim_get_waveform(
    result: hs.SimResult, name: str, analysis_idx: int = 0
) -> np.ndarray:
    """
    Extract a single waveform from SimResult.

    Args:
        result: SimResult object
        name: Signal name (e.g., "xtop.out" or "v(out)")
        analysis_idx: Index of analysis

    Returns:
        Numpy array of waveform data

    Raises:
        KeyError: If signal not found
    """
    data = result.an[analysis_idx].data
    # Try exact name first, then with v() prefix
    if name in data:
        return np.array(data[name])
    elif f"v({name})" in data:
        return np.array(data[f"v({name})"])
    raise KeyError(f"Signal '{name}' not found in SimResult")


def sim_get_waveforms(
    result: hs.SimResult,
    names: list[str],
    analysis_idx: int = 0,
) -> dict[str, np.ndarray]:
    """
    Extract multiple waveforms from SimResult.

    Args:
        result: SimResult object
        names: List of signal names to extract
        analysis_idx: Index of analysis

    Returns:
        Dict mapping signal name -> waveform array (only for found signals)
    """
    waveforms = {}
    for name in names:
        try:
            waveforms[name] = sim_get_waveform(result, name, analysis_idx)
        except KeyError:
            pass  # Skip missing signals
    return waveforms


def sim_sample_at_edges(
    result: hs.SimResult,
    clock_name: str,
    signal_names: list[str],
    edge: str = "falling",
    threshold: float | None = None,
    sample_offset: float = 0.5,
    analysis_idx: int = 0,
) -> dict[str, np.ndarray]:
    """
    Sample signals at clock edges from SimResult.

    For ADC simulations:
    - Sample Vin at CLK_SAMP falling edge
    - Sample comparator outputs at each CLK_COMP falling edge

    The sample_offset controls where in the clock period to sample:
    - 0.0 = at exact crossing time
    - 0.5 = halfway between crossings (default, mid-stable)
    - 1.0 = just before next crossing

    Args:
        result: SimResult from transient simulation
        clock_name: Clock signal name
        signal_names: Signal names to sample
        edge: "rising" or "falling"
        threshold: Clock threshold (defaults to midpoint of swing)
        sample_offset: Fraction of period after edge (0.0-1.0)
        analysis_idx: Analysis index

    Returns:
        Dict mapping signal name -> sampled values array
    """
    time = sim_get_time(result, analysis_idx)
    clock = sim_get_waveform(result, clock_name, analysis_idx)

    # Auto-detect threshold from clock swing
    if threshold is None:
        threshold = float((np.max(clock) + np.min(clock)) / 2)

    # Find clock edge times
    rising = edge == "rising"
    edge_times = find_crossings(clock, time, threshold, rising=rising)

    if len(edge_times) < 2:
        return {}

    # Calculate sample times with offset
    sample_times: list[float] = []
    for i, t_edge in enumerate(edge_times):
        if i < len(edge_times) - 1:
            period = edge_times[i + 1] - t_edge
            sample_times.append(t_edge + sample_offset * period)
        elif i > 0:
            # Last edge: use previous period
            period = t_edge - edge_times[i - 1]
            t_sample = t_edge + sample_offset * period
            if t_sample <= time[-1]:
                sample_times.append(t_sample)

    # Sample each signal
    samples: dict[str, np.ndarray] = {}
    for name in signal_names:
        try:
            sig = sim_get_waveform(result, name, analysis_idx)
            samples[name] = np.interp(sample_times, time, sig)
        except KeyError:
            pass

    return samples


# =============================================================================
# Waveform Utilities (numpy arrays)
# =============================================================================


def find_crossings(
    signal: np.ndarray,
    time: np.ndarray,
    threshold: float,
    rising: bool = True,
) -> list[float]:
    """
    Find interpolated threshold crossing times.

    Args:
        signal: Waveform array
        time: Time array (same length)
        threshold: Crossing threshold
        rising: True for rising edge, False for falling

    Returns:
        List of interpolated crossing times
    """
    crossings: list[float] = []

    for i in range(len(signal) - 1):
        if rising:
            if signal[i] < threshold <= signal[i + 1]:
                t = time[i] + (threshold - signal[i]) / (signal[i + 1] - signal[i]) * (
                    time[i + 1] - time[i]
                )
                crossings.append(float(t))
        else:
            if signal[i] > threshold >= signal[i + 1]:
                t = time[i] + (signal[i] - threshold) / (signal[i] - signal[i + 1]) * (
                    time[i + 1] - time[i]
                )
                crossings.append(float(t))

    return crossings


# =============================================================================
# Analog Preprocessing (numpy arrays)
# =============================================================================


def diff_to_single(pos: np.ndarray, neg: np.ndarray) -> np.ndarray:
    """Convert differential to single-ended: pos - neg."""
    return pos - neg


def quantize_to_bits(
    values: np.ndarray,
    v_low: float,
    v_high: float,
) -> np.ndarray:
    """
    Convert analog values to bits using midpoint threshold.

    Args:
        values: Analog values (any shape)
        v_low: Logic low level
        v_high: Logic high level

    Returns:
        Array of int 0 or 1 (same shape)
    """
    threshold = (v_low + v_high) / 2
    return (values > threshold).astype(np.int32)


# =============================================================================
# Digital Processing (numpy arrays)
# =============================================================================


def redundant_bits_to_code(
    bits: np.ndarray,
    weights: np.ndarray,
) -> np.ndarray:
    """
    Convert redundant SAR bits to code using weighted sum.

    Args:
        bits: Shape (n_samples, n_bits) or (n_bits,), values 0/1, MSB first
        weights: Shape (n_bits,), e.g., FRIDA_IDEAL_WEIGHTS

    Returns:
        Weighted sum. Shape (n_samples,) or scalar.
    """
    return np.dot(bits, np.asarray(weights))


def code_to_voltage(
    codes: np.ndarray,
    v_ref: float,
    total_weight: float,
) -> np.ndarray:
    """
    Convert codes to estimated input voltage.

    For charge-redistribution SAR: Vin_est = code * v_ref / total_weight

    Args:
        codes: Digital codes (any shape)
        v_ref: Reference voltage
        total_weight: Sum of capacitor weights

    Returns:
        Estimated voltage (same shape)
    """
    return codes * v_ref / total_weight


# =============================================================================
# Core Measurement Functions (numpy arrays - shared by sim and DAQ)
# =============================================================================


def measure_settling(
    time: np.ndarray,
    signal: np.ndarray,
    target: float | None = None,
    tol: float = 0.01,
) -> float:
    """
    Measure settling time to within tolerance of target.

    Args:
        time: Time array
        signal: Signal waveform
        target: Target value (defaults to final value)
        tol: Relative tolerance (default 1%)

    Returns:
        Settling time (same units as time), or NaN
    """
    if len(signal) == 0:
        return float("nan")

    if target is None:
        target = float(signal[-1])

    threshold = tol if abs(target) < 1e-15 else abs(target) * tol
    settled = np.abs(signal - target) < threshold

    for i in range(len(settled)):
        if np.all(settled[i:]):
            return float(time[i])

    return float("nan")


def measure_delay(
    time: np.ndarray,
    trigger: np.ndarray,
    response: np.ndarray,
    trigger_thresh: float,
    response_thresh: float,
    trigger_rising: bool = True,
    response_rising: bool = True,
) -> float:
    """
    Measure delay from trigger event to response event.

    Args:
        time: Time array
        trigger: Trigger signal
        response: Response signal
        trigger_thresh: Trigger threshold
        response_thresh: Response threshold
        trigger_rising: Trigger on rising edge
        response_rising: Response on rising edge

    Returns:
        Delay (same units as time), or NaN
    """
    t_trig = find_crossings(trigger, time, trigger_thresh, trigger_rising)
    t_resp = find_crossings(response, time, response_thresh, response_rising)

    if not t_trig:
        return float("nan")

    t0 = t_trig[0]
    for t in t_resp:
        if t > t0:
            return t - t0

    return float("nan")


def measure_average_power(
    current: np.ndarray,
    voltage: float,
) -> float:
    """
    Measure average power from current waveform.

    Args:
        current: Current waveform (positive = into device)
        voltage: Supply voltage

    Returns:
        Average power (V * mean|I|)
    """
    if len(current) == 0:
        return float("nan")
    return voltage * float(np.mean(np.abs(current)))


def measure_offset_crossing(
    v_in_diff: np.ndarray,
    v_out_diff: np.ndarray,
    time: np.ndarray | None = None,
) -> float:
    """
    Measure input-referred offset from output zero-crossing.

    Finds the input differential voltage where output crosses zero.

    Args:
        v_in_diff: Differential input
        v_out_diff: Differential output
        time: Time array (uses indices if None)

    Returns:
        Input voltage at crossing, or NaN
    """
    if len(v_in_diff) != len(v_out_diff):
        return float("nan")

    if time is None:
        time = np.arange(len(v_in_diff), dtype=float)

    crossings = find_crossings(v_out_diff, time, 0.0, rising=True)
    crossings.extend(find_crossings(v_out_diff, time, 0.0, rising=False))

    if not crossings:
        return float("nan")

    return float(np.interp(crossings[0], time, v_in_diff))


def measure_charge_injection(v_before: float, v_after: float) -> float:
    """Measure voltage change from charge injection."""
    return v_after - v_before


# =============================================================================
# Static Linearity Analysis (numpy arrays)
# =============================================================================


def histogram_inl_dnl(
    codes: np.ndarray,
    n_codes: int,
) -> dict[str, Any]:
    """
    Compute INL/DNL using histogram method (for ramp input).

    Args:
        codes: Output codes array
        n_codes: Total possible codes (e.g., 2048)

    Returns:
        Dict with dnl, inl, dnl_max, inl_max, missing_codes, histogram,
        first_code, last_code
    """
    histogram, _ = np.histogram(codes, bins=n_codes, range=(0, n_codes))

    nonzero = histogram > 0
    if not np.any(nonzero):
        return {
            "dnl": np.zeros(n_codes),
            "inl": np.zeros(n_codes),
            "dnl_max": float("nan"),
            "inl_max": float("nan"),
            "missing_codes": list(range(n_codes)),
            "histogram": histogram,
            "first_code": 0,
            "last_code": 0,
        }

    first_code = int(np.argmax(nonzero))
    last_code = n_codes - 1 - int(np.argmax(nonzero[::-1]))

    if first_code >= last_code:
        return {
            "dnl": np.zeros(n_codes),
            "inl": np.zeros(n_codes),
            "dnl_max": float("nan"),
            "inl_max": float("nan"),
            "missing_codes": list(range(n_codes)),
            "histogram": histogram,
            "first_code": first_code,
            "last_code": last_code,
        }

    total = int(np.sum(histogram[first_code : last_code + 1]))
    n_active = last_code - first_code + 1
    ideal = total / n_active

    dnl = np.zeros(n_codes)
    if ideal > 0:
        for c in range(first_code, last_code + 1):
            dnl[c] = (histogram[c] / ideal) - 1

    inl = np.cumsum(dnl)
    missing = [c for c in range(first_code, last_code + 1) if histogram[c] == 0]

    return {
        "dnl": dnl,
        "inl": inl,
        "dnl_max": float(np.max(np.abs(dnl[first_code : last_code + 1]))),
        "inl_max": float(np.max(np.abs(inl[first_code : last_code + 1]))),
        "missing_codes": missing,
        "histogram": histogram,
        "first_code": first_code,
        "last_code": last_code,
    }


def endpoint_inl_dnl(
    codes: np.ndarray,
    outputs: np.ndarray,
) -> dict[str, Any]:
    """
    Compute INL/DNL using endpoint-fit method (for DAC characterization).

    Args:
        codes: DAC codes (sorted)
        outputs: Corresponding output values

    Returns:
        Dict with dnl, inl, dnl_max, inl_max, lsb
    """
    n = len(codes)

    if n < 2:
        return {
            "dnl": np.array([]),
            "inl": np.array([]),
            "dnl_max": float("nan"),
            "inl_max": float("nan"),
            "lsb": float("nan"),
        }

    lsb = (outputs[-1] - outputs[0]) / (n - 1)

    if abs(lsb) < 1e-15:
        return {
            "dnl": np.zeros(n - 1),
            "inl": np.zeros(n),
            "dnl_max": 0.0,
            "inl_max": 0.0,
            "lsb": 0.0,
        }

    steps = np.diff(outputs)
    dnl = (steps / lsb) - 1

    ideal_line = outputs[0] + np.arange(n) * lsb
    inl = (outputs - ideal_line) / lsb

    return {
        "dnl": dnl,
        "inl": inl,
        "dnl_max": float(np.max(np.abs(dnl))),
        "inl_max": float(np.max(np.abs(inl))),
        "lsb": float(lsb),
    }


def find_code_transitions(
    v_in: np.ndarray,
    codes: np.ndarray,
) -> dict[int, float]:
    """
    Find input voltage at each code transition.

    Args:
        v_in: Input voltage array
        codes: Output codes

    Returns:
        Dict mapping code -> transition voltage
    """
    sort_idx = np.argsort(v_in)
    v_sorted = v_in[sort_idx]
    codes_sorted = codes[sort_idx]

    transitions: dict[int, float] = {}
    prev = int(codes_sorted[0])

    for i in range(1, len(codes_sorted)):
        curr = int(codes_sorted[i])
        if curr != prev:
            transitions[curr] = float(v_sorted[i])
            prev = curr

    return transitions


def compute_static_error(
    v_in: np.ndarray,
    v_estimated: np.ndarray,
) -> dict[str, float]:
    """
    Compute static transfer error.

    Args:
        v_in: True input voltage
        v_estimated: Estimated voltage from codes

    Returns:
        Dict with offset, gain_error, rms_error, max_error
    """
    if len(v_in) < 2:
        return {
            "offset": float("nan"),
            "gain_error": float("nan"),
            "rms_error": float("nan"),
            "max_error": float("nan"),
        }

    coeffs = np.polyfit(v_in, v_estimated, 1)
    gain, offset = float(coeffs[0]), float(coeffs[1])

    v_corrected = (v_estimated - offset) / gain
    residual = v_in - v_corrected

    return {
        "offset": offset,
        "gain_error": gain - 1.0,
        "rms_error": float(np.sqrt(np.mean(residual**2))),
        "max_error": float(np.max(np.abs(residual))),
    }


# =============================================================================
# Dynamic Performance Analysis (numpy arrays)
# =============================================================================


def compute_enob_fft(
    codes: np.ndarray,
    fs: float,
    fin: float,
    window: str = "hann",
    n_harmonics: int = 5,
) -> dict[str, float]:
    """
    Compute ENOB using FFT method (for sine wave input).

    Args:
        codes: ADC output codes (1D array)
        fs: Sampling frequency (Hz)
        fin: Input frequency (Hz)
        window: Window function ('hann', 'blackman', 'hamming', 'none')
        n_harmonics: Number of harmonics for THD

    Returns:
        Dict with enob, snr_db, thd_db, sinad_db, sfdr_db,
        signal_power, noise_power
    """
    n = len(codes)

    if n < 16:
        return {
            "enob": float("nan"),
            "snr_db": float("nan"),
            "thd_db": float("nan"),
            "sinad_db": float("nan"),
            "sfdr_db": float("nan"),
            "signal_power": float("nan"),
            "noise_power": float("nan"),
        }

    # Remove DC
    codes_ac = codes - np.mean(codes)

    # Window
    if window == "hann":
        win = np.hanning(n)
    elif window == "blackman":
        win = np.blackman(n)
    elif window == "hamming":
        win = np.hamming(n)
    else:
        win = np.ones(n)

    cg = float(np.sum(win) / n)  # coherent gain
    codes_win = codes_ac * win

    # FFT
    fft_out = np.fft.rfft(codes_win)
    pwr = np.abs(fft_out) ** 2
    freq = np.fft.rfftfreq(n, 1 / fs)

    # Signal bin
    sig_bin = int(np.argmin(np.abs(freq - fin)))
    sig_width = max(3, n // 100)
    sig_start = max(1, sig_bin - sig_width // 2)
    sig_end = min(len(pwr), sig_bin + sig_width // 2 + 1)
    sig_pwr = float(np.sum(pwr[sig_start:sig_end]))

    # Harmonics
    harm_pwr = 0.0
    for h in range(2, n_harmonics + 1):
        hf = h * fin
        if hf >= fs / 2:
            break
        hb = int(np.argmin(np.abs(freq - hf)))
        hs = max(1, hb - sig_width // 2)
        he = min(len(pwr), hb + sig_width // 2 + 1)
        harm_pwr += float(np.sum(pwr[hs:he]))

    # Noise
    total_pwr = float(np.sum(pwr[1:]))
    noise_pwr = max(total_pwr - sig_pwr - harm_pwr, 1e-20)

    # Normalize
    sig_pwr /= cg**2
    harm_pwr /= cg**2
    noise_pwr /= cg**2

    # Metrics
    snr = 10 * np.log10(sig_pwr / noise_pwr)
    thd = 10 * np.log10(harm_pwr / sig_pwr) if harm_pwr > 0 else -120.0
    sinad = 10 * np.log10(sig_pwr / (noise_pwr + harm_pwr))

    # SFDR
    spur = pwr.copy()
    spur[sig_start:sig_end] = 0
    spur[0] = 0
    max_spur = float(np.max(spur))
    sfdr = 10 * np.log10(sig_pwr / max_spur) if max_spur > 0 else 120.0

    enob = (sinad - 1.76) / 6.02

    return {
        "enob": float(enob),
        "snr_db": float(snr),
        "thd_db": float(thd),
        "sinad_db": float(sinad),
        "sfdr_db": float(sfdr),
        "signal_power": sig_pwr,
        "noise_power": noise_pwr,
    }


# =============================================================================
# Monte Carlo Statistics (numpy arrays)
# =============================================================================


def mc_statistics(values: list[float] | np.ndarray) -> dict[str, float]:
    """
    Compute statistics from Monte Carlo results.

    Args:
        values: Scalar results from MC runs

    Returns:
        Dict with mean, std, min, max, n, sigma3_low, sigma3_high
    """
    arr = np.asarray(values)

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

    mean = float(np.mean(arr))
    std = float(np.std(arr))

    return {
        "mean": mean,
        "std": std,
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "n": len(arr),
        "sigma3_low": mean - 3 * std,
        "sigma3_high": mean + 3 * std,
    }


# =============================================================================
# Legacy API Aliases (backward compatibility)
# =============================================================================

# Old function names that delegate to new implementations


def comp_offset_mV(
    result: hs.SimResult,
    inp: str = "xtop.inp",
    inn: str = "xtop.inn",
    outp: str = "xtop.outp",
    outn: str = "xtop.outn",
) -> float:
    """Legacy: comparator offset in mV."""
    try:
        time = sim_get_time(result)
        v_inp = sim_get_waveform(result, inp)
        v_inn = sim_get_waveform(result, inn)
        v_outp = sim_get_waveform(result, outp)
        v_outn = sim_get_waveform(result, outn)
    except KeyError:
        return float("nan")

    v_in_diff = diff_to_single(v_inp, v_inn)
    v_out_diff = diff_to_single(v_outp, v_outn)
    return measure_offset_crossing(v_in_diff, v_out_diff, time) * 1000


def comp_delay_ns(
    result: hs.SimResult,
    clk: str = "xtop.clk",
    outp: str = "xtop.outp",
    outn: str = "xtop.outn",
    vdd: float = 1.2,
) -> float:
    """Legacy: comparator delay in ns."""
    try:
        time = sim_get_time(result)
        v_clk = sim_get_waveform(result, clk)
        v_outp = sim_get_waveform(result, outp)
        v_outn = sim_get_waveform(result, outn)
    except KeyError:
        return float("nan")

    v_out_abs = np.abs(diff_to_single(v_outp, v_outn))
    delay = measure_delay(time, v_clk, v_out_abs, vdd / 2, vdd / 2, True, True)
    return delay * 1e9 if not np.isnan(delay) else float("nan")


def comp_settling_ns(
    result: hs.SimResult,
    outp: str = "xtop.outp",
    outn: str = "xtop.outn",
    tol: float = 0.01,
    vdd: float = 1.2,
) -> float:
    """Legacy: comparator settling time in ns."""
    try:
        time = sim_get_time(result)
        v_outp = sim_get_waveform(result, outp)
        v_outn = sim_get_waveform(result, outn)
    except KeyError:
        return float("nan")

    v_diff = diff_to_single(v_outp, v_outn)
    settling = measure_settling(time, v_diff, tol=tol)
    return settling * 1e9 if not np.isnan(settling) else float("nan")


def comp_power_uW(
    result: hs.SimResult,
    vdd_src: str = "vvdd",
    vdd: float = 1.2,
) -> float:
    """Legacy: comparator power in uW."""
    try:
        current = sim_get_waveform(result, f"i({vdd_src})")
    except KeyError:
        return float("nan")

    # SPICE convention: current into source is negative
    return measure_average_power(-current, vdd) * 1e6


def comp_noise_sigma_mV(
    result: hs.SimResult,
    inp: str = "xtop.inp",
    inn: str = "xtop.inn",
    outp: str = "xtop.outp",
    outn: str = "xtop.outn",
) -> float:
    """Legacy: S-curve noise (requires sweep data, placeholder)."""
    return float("nan")


def cdac_settling_ns(
    result: hs.SimResult,
    top: str = "xtop.top",
    tol: float = 0.01,
) -> float:
    """Legacy: CDAC settling time in ns."""
    try:
        time = sim_get_time(result)
        v_top = sim_get_waveform(result, top)
    except KeyError:
        return float("nan")

    settling = measure_settling(time, v_top, tol=tol)
    return settling * 1e9 if not np.isnan(settling) else float("nan")


def samp_settling_ns(
    result: hs.SimResult,
    din: str = "xtop.din",
    dout: str = "xtop.dout",
    tol: float = 0.01,
) -> float:
    """Legacy: sampler settling time in ns."""
    try:
        time = sim_get_time(result)
        v_in = sim_get_waveform(result, din)
        v_out = sim_get_waveform(result, dout)
    except KeyError:
        return float("nan")

    target = float(v_in[-1])
    settling = measure_settling(time, v_out, target, tol)
    return settling * 1e9 if not np.isnan(settling) else float("nan")


def samp_charge_injection_mV(
    result: hs.SimResult,
    dout: str = "xtop.dout",
    clk: str = "xtop.clk",
    vdd: float = 1.2,
) -> float:
    """Legacy: sampler charge injection in mV."""
    try:
        time = sim_get_time(result)
        v_out = sim_get_waveform(result, dout)
        v_clk = sim_get_waveform(result, clk)
    except KeyError:
        return float("nan")

    edges = find_crossings(v_clk, time, vdd / 2, rising=False)
    if not edges:
        return float("nan")

    idx = int(np.searchsorted(time, edges[0]))
    if idx < 1 or idx >= len(v_out) - 10:
        return float("nan")

    v_before = float(v_out[idx - 1])
    v_after = float(v_out[min(idx + 10, len(v_out) - 1)])
    return measure_charge_injection(v_before, v_after) * 1000


def compute_inl_dnl(codes: np.ndarray, outputs: np.ndarray) -> dict[str, Any]:
    """Legacy alias for endpoint_inl_dnl."""
    return endpoint_inl_dnl(codes, outputs)
