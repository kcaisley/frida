"""
Unit tests for measurement functions in flow/flow/measure.py.

These tests verify the numpy-based measurement functions without requiring
SPICE simulation. They test the shared measurement pipeline that works
for both simulation and DAQ data.
"""

import numpy as np
import pytest

from .measure import (
    code_to_voltage,
    compute_enob_fft,
    compute_static_error,
    diff_to_single,
    endpoint_inl_dnl,
    find_code_transitions,
    find_crossings,
    histogram_inl_dnl,
    mc_statistics,
    measure_average_power,
    measure_charge_injection,
    measure_delay,
    measure_offset_crossing,
    measure_settling,
    quantize_to_bits,
    redundant_bits_to_code,
)


# =============================================================================
# Test CDAC Weights
# =============================================================================


def test_cdac_default_weights():
    """Verify default CdacParams produces expected weights."""
    from ..cdac import CdacParams, get_cdac_weights

    weights = np.array(get_cdac_weights(CdacParams()))
    assert len(weights) == 16
    assert weights[0] == 768  # MSB
    assert weights[-1] == 1  # LSB
    # Total should be 2047 for 11-bit equivalent
    assert weights.sum() == 2047


# =============================================================================
# Test Waveform Utilities
# =============================================================================


class TestFindCrossings:
    """Tests for find_crossings function."""

    def test_rising_edge(self):
        """Find rising edge crossings."""
        time = np.array([0, 1, 2, 3, 4])
        signal = np.array([0, 0.5, 1.5, 1.5, 0.5])
        crossings = find_crossings(signal, time, 1.0, rising=True)
        assert len(crossings) == 1
        assert 1.0 < crossings[0] < 2.0

    def test_falling_edge(self):
        """Find falling edge crossings."""
        time = np.array([0, 1, 2, 3, 4])
        signal = np.array([1.5, 1.5, 0.5, 0.5, 1.5])
        crossings = find_crossings(signal, time, 1.0, rising=False)
        assert len(crossings) == 1
        assert 1.0 < crossings[0] < 2.0

    def test_multiple_crossings(self):
        """Find multiple crossings in oscillating signal."""
        # Use 2 full periods to get multiple crossings
        time = np.linspace(0, 4 * np.pi, 200)
        signal = np.sin(time)
        crossings = find_crossings(signal, time, 0.0, rising=True)
        # Sin crosses zero rising at 0, 2*pi, 4*pi (but we start slightly after 0)
        # so we should get crossings near 2*pi
        assert len(crossings) >= 1

    def test_no_crossings(self):
        """Return empty list when no crossings."""
        time = np.array([0, 1, 2])
        signal = np.array([0.5, 0.6, 0.7])
        crossings = find_crossings(signal, time, 1.0, rising=True)
        assert len(crossings) == 0

    def test_interpolation_accuracy(self):
        """Verify interpolation gives correct crossing time."""
        time = np.array([0.0, 1.0, 2.0])
        signal = np.array([0.0, 1.0, 2.0])
        crossings = find_crossings(signal, time, 0.5, rising=True)
        assert len(crossings) == 1
        assert abs(crossings[0] - 0.5) < 1e-10


# =============================================================================
# Test Analog Preprocessing
# =============================================================================


class TestDiffToSingle:
    """Tests for diff_to_single function."""

    def test_basic(self):
        """Basic differential to single-ended conversion."""
        pos = np.array([1.0, 1.2, 0.8])
        neg = np.array([0.0, 0.2, 0.4])
        result = diff_to_single(pos, neg)
        np.testing.assert_array_almost_equal(result, [1.0, 1.0, 0.4])

    def test_negative_result(self):
        """Handle negative differential."""
        pos = np.array([0.5])
        neg = np.array([0.7])
        result = diff_to_single(pos, neg)
        assert result[0] == pytest.approx(-0.2)


class TestQuantizeToBits:
    """Tests for quantize_to_bits function."""

    def test_basic(self):
        """Basic quantization with default threshold."""
        values = np.array([0.0, 0.4, 0.6, 1.2])
        bits = quantize_to_bits(values, v_low=0.0, v_high=1.2)
        # Threshold is 0.6, values > 0.6 become 1
        np.testing.assert_array_equal(bits, [0, 0, 0, 1])

    def test_midpoint_threshold(self):
        """Verify midpoint threshold behavior."""
        values = np.array([0.59, 0.61])
        bits = quantize_to_bits(values, v_low=0.0, v_high=1.2)
        # Threshold = 0.6
        np.testing.assert_array_equal(bits, [0, 1])

    def test_output_dtype(self):
        """Output should be int32."""
        values = np.array([0.0, 1.0])
        bits = quantize_to_bits(values, v_low=0.0, v_high=1.0)
        assert bits.dtype == np.int32


# =============================================================================
# Test Digital Processing
# =============================================================================


class TestRedundantBitsToCode:
    """Tests for redundant_bits_to_code function."""

    def test_single_sample(self):
        """Convert single sample of bits to code."""
        bits = np.array([1, 0, 1, 0])
        weights = np.array([8, 4, 2, 1])
        code = redundant_bits_to_code(bits, weights)
        assert code == 10  # 8 + 0 + 2 + 0

    def test_multiple_samples(self):
        """Convert multiple samples."""
        bits = np.array([[1, 0, 0, 0], [0, 1, 1, 1]])
        weights = np.array([8, 4, 2, 1])
        codes = redundant_bits_to_code(bits, weights)
        np.testing.assert_array_equal(codes, [8, 7])

    def test_frida_weights(self):
        """Test with actual FRIDA weights."""
        from ..cdac import CdacParams, get_cdac_weights

        weights = np.array(get_cdac_weights(CdacParams()))
        # All ones should give total weight
        bits = np.ones(16, dtype=int)
        code = redundant_bits_to_code(bits, weights)
        assert code == 2047

    def test_all_zeros(self):
        """All zeros should give code 0."""
        from ..cdac import CdacParams, get_cdac_weights

        weights = np.array(get_cdac_weights(CdacParams()))
        bits = np.zeros(16, dtype=int)
        code = redundant_bits_to_code(bits, weights)
        assert code == 0


class TestCodeToVoltage:
    """Tests for code_to_voltage function."""

    def test_basic(self):
        """Basic code to voltage conversion."""
        codes = np.array([0, 1023, 2047])
        v_out = code_to_voltage(codes, v_ref=1.2, total_weight=2047)
        assert v_out[0] == pytest.approx(0.0)
        assert v_out[1] == pytest.approx(1.2 * 1023 / 2047)
        assert v_out[2] == pytest.approx(1.2)

    def test_full_scale(self):
        """Full scale code gives reference voltage."""
        code = np.array([2047])
        v_out = code_to_voltage(code, v_ref=1.2, total_weight=2047)
        assert v_out[0] == pytest.approx(1.2)


# =============================================================================
# Test Core Measurements
# =============================================================================


class TestMeasureSettling:
    """Tests for measure_settling function."""

    def test_exponential_settling(self):
        """Measure settling of exponential decay."""
        time = np.linspace(0, 10, 1000)
        tau = 1.0
        final = 1.0
        signal = final * (1 - np.exp(-time / tau))
        settling = measure_settling(time, signal, target=final, tol=0.01)
        # Should settle around 4-5 tau for 1%
        assert 4 * tau < settling < 6 * tau

    def test_already_settled(self):
        """Return early time if already settled."""
        time = np.array([0.0, 1.0, 2.0])
        signal = np.array([1.0, 1.0, 1.0])
        settling = measure_settling(time, signal, target=1.0, tol=0.01)
        assert settling == 0.0

    def test_never_settles(self):
        """Return NaN if never settles."""
        time = np.array([0.0, 1.0, 2.0])
        signal = np.array([0.0, 0.5, 0.8])
        settling = measure_settling(time, signal, target=1.0, tol=0.01)
        assert np.isnan(settling)

    def test_empty_signal(self):
        """Return NaN for empty signal."""
        settling = measure_settling(np.array([]), np.array([]))
        assert np.isnan(settling)

    def test_default_target(self):
        """Use final value as default target."""
        time = np.array([0.0, 1.0, 2.0, 3.0])
        signal = np.array([0.0, 0.9, 0.99, 1.0])
        settling = measure_settling(time, signal, tol=0.02)
        assert settling < 3.0


class TestMeasureDelay:
    """Tests for measure_delay function."""

    def test_basic_delay(self):
        """Measure basic propagation delay."""
        time = np.linspace(0, 10, 1000)
        trigger = np.where(time > 2, 1.0, 0.0)
        response = np.where(time > 3, 1.0, 0.0)
        delay = measure_delay(
            time,
            trigger,
            response,
            trigger_thresh=0.5,
            response_thresh=0.5,
            trigger_rising=True,
            response_rising=True,
        )
        assert delay == pytest.approx(1.0, abs=0.02)

    def test_no_trigger(self):
        """Return NaN if no trigger event."""
        time = np.array([0, 1, 2])
        trigger = np.array([0, 0, 0])  # Never crosses threshold
        response = np.array([0, 1, 1])
        delay = measure_delay(time, trigger, response, 0.5, 0.5, True, True)
        assert np.isnan(delay)


class TestMeasureAveragePower:
    """Tests for measure_average_power function."""

    def test_constant_current(self):
        """Power with constant current."""
        current = np.array([1e-3, 1e-3, 1e-3])  # 1mA
        power = measure_average_power(current, voltage=1.2)
        assert power == pytest.approx(1.2e-3)  # 1.2mW

    def test_varying_current(self):
        """Power with varying current."""
        current = np.array([0, 2e-3, 4e-3])  # 0, 2, 4 mA
        power = measure_average_power(current, voltage=1.0)
        assert power == pytest.approx(2e-3)  # mean(0,2,4)*1 = 2mW

    def test_empty_current(self):
        """Return NaN for empty current."""
        power = measure_average_power(np.array([]), voltage=1.2)
        assert np.isnan(power)


class TestMeasureOffsetCrossing:
    """Tests for measure_offset_crossing function."""

    def test_zero_offset(self):
        """Comparator with no offset crosses at zero."""
        v_in_diff = np.linspace(-0.1, 0.1, 100)
        v_out_diff = v_in_diff * 1000  # High gain
        offset = measure_offset_crossing(v_in_diff, v_out_diff)
        assert offset == pytest.approx(0.0, abs=0.002)

    def test_positive_offset(self):
        """Comparator with positive offset."""
        v_in_diff = np.linspace(-0.1, 0.1, 100)
        v_out_diff = (v_in_diff - 0.02) * 1000  # 20mV offset
        offset = measure_offset_crossing(v_in_diff, v_out_diff)
        assert offset == pytest.approx(0.02, abs=0.002)

    def test_length_mismatch(self):
        """Return NaN if arrays have different lengths."""
        offset = measure_offset_crossing(np.array([1, 2]), np.array([1, 2, 3]))
        assert np.isnan(offset)


class TestMeasureChargeInjection:
    """Tests for measure_charge_injection function."""

    def test_positive_injection(self):
        """Positive charge injection (voltage increase)."""
        delta = measure_charge_injection(v_before=0.6, v_after=0.65)
        assert delta == pytest.approx(0.05)

    def test_negative_injection(self):
        """Negative charge injection (voltage decrease)."""
        delta = measure_charge_injection(v_before=0.6, v_after=0.55)
        assert delta == pytest.approx(-0.05)


# =============================================================================
# Test Static Linearity Analysis
# =============================================================================


class TestHistogramInlDnl:
    """Tests for histogram_inl_dnl function."""

    def test_ideal_adc(self):
        """Ideal ADC should have zero INL/DNL."""
        # Simulate ideal ramp with equal code distribution
        n_samples_per_code = 100
        n_codes = 256
        codes = np.repeat(np.arange(n_codes), n_samples_per_code)
        result = histogram_inl_dnl(codes, n_codes)

        assert result["dnl_max"] == pytest.approx(0.0, abs=0.01)
        assert result["inl_max"] == pytest.approx(0.0, abs=0.1)
        assert len(result["missing_codes"]) == 0

    def test_missing_codes(self):
        """Detect missing codes."""
        # Create codes with gap (missing code 5)
        codes = np.array([0, 1, 2, 3, 4, 6, 7, 8, 9])
        result = histogram_inl_dnl(codes, n_codes=10)
        assert 5 in result["missing_codes"]
        # DNL for missing code should be -1
        assert result["dnl"][5] == pytest.approx(-1.0)

    def test_wide_code(self):
        """Detect wide code (positive DNL)."""
        # Code 5 appears twice as often as others
        codes = np.concatenate(
            [
                np.arange(10),
                np.array([5]),  # Extra occurrence of code 5
            ]
        )
        result = histogram_inl_dnl(codes, n_codes=10)
        assert result["dnl"][5] > 0

    def test_empty_codes(self):
        """Handle empty codes array."""
        result = histogram_inl_dnl(np.array([]), n_codes=256)
        assert np.isnan(result["dnl_max"])
        assert np.isnan(result["inl_max"])


class TestEndpointInlDnl:
    """Tests for endpoint_inl_dnl function."""

    def test_ideal_dac(self):
        """Ideal DAC should have zero INL/DNL."""
        codes = np.arange(256)
        outputs = codes * 1.0  # Linear
        result = endpoint_inl_dnl(codes, outputs)

        assert result["dnl_max"] == pytest.approx(0.0, abs=1e-10)
        assert result["inl_max"] == pytest.approx(0.0, abs=1e-10)

    def test_nonlinear_dac(self):
        """Detect nonlinearity in DAC."""
        codes = np.arange(100)
        # Add quadratic nonlinearity
        outputs = codes + 0.01 * codes**2
        result = endpoint_inl_dnl(codes, outputs)

        assert result["inl_max"] > 0
        assert "lsb" in result

    def test_single_point(self):
        """Handle single point."""
        result = endpoint_inl_dnl(np.array([0]), np.array([0.0]))
        assert np.isnan(result["dnl_max"])


class TestFindCodeTransitions:
    """Tests for find_code_transitions function."""

    def test_basic_transitions(self):
        """Find basic code transitions."""
        v_in = np.array([0.0, 0.3, 0.6, 0.9, 1.2])
        codes = np.array([0, 1, 2, 3, 4])
        transitions = find_code_transitions(v_in, codes)

        assert 1 in transitions
        assert transitions[1] == pytest.approx(0.3)
        assert transitions[4] == pytest.approx(1.2)

    def test_unsorted_input(self):
        """Handle unsorted input voltage."""
        v_in = np.array([0.9, 0.0, 0.6, 0.3, 1.2])
        codes = np.array([3, 0, 2, 1, 4])
        transitions = find_code_transitions(v_in, codes)

        # Should still find correct transitions
        assert transitions[1] == pytest.approx(0.3)


class TestComputeStaticError:
    """Tests for compute_static_error function."""

    def test_perfect_match(self):
        """Perfect match should have zero error."""
        v_in = np.linspace(0, 1, 100)
        v_est = v_in.copy()
        result = compute_static_error(v_in, v_est)

        assert result["offset"] == pytest.approx(0.0, abs=1e-10)
        assert result["gain_error"] == pytest.approx(0.0, abs=1e-10)
        assert result["rms_error"] == pytest.approx(0.0, abs=1e-10)

    def test_offset_error(self):
        """Detect offset error."""
        v_in = np.linspace(0, 1, 100)
        v_est = v_in + 0.05  # 50mV offset
        result = compute_static_error(v_in, v_est)

        assert result["offset"] == pytest.approx(0.05, abs=0.01)

    def test_gain_error(self):
        """Detect gain error."""
        v_in = np.linspace(0, 1, 100)
        v_est = v_in * 1.05  # 5% gain error
        result = compute_static_error(v_in, v_est)

        assert result["gain_error"] == pytest.approx(0.05, abs=0.01)

    def test_insufficient_points(self):
        """Handle insufficient points."""
        result = compute_static_error(np.array([0.5]), np.array([0.5]))
        assert np.isnan(result["offset"])


# =============================================================================
# Test Dynamic Performance Analysis
# =============================================================================


class TestComputeEnobFft:
    """Tests for compute_enob_fft function."""

    def test_ideal_sine(self):
        """Ideal sine wave should give reasonable ENOB."""
        fs = 1e6  # 1 MHz sampling
        fin = 100e3  # 100 kHz input
        n_samples = 1024

        t = np.arange(n_samples) / fs
        # 11-bit ideal ADC (codes 0-2047)
        amplitude = 1023
        codes = np.round(amplitude * np.sin(2 * np.pi * fin * t) + 1024).astype(int)

        result = compute_enob_fft(codes, fs, fin)

        # Ideal quantization noise limited ENOB is ~6.02*N + 1.76 dB SINAD
        # With non-coherent sampling and windowing, we expect ~8+ ENOB for 11-bit
        assert result["enob"] > 7.0
        assert result["snr_db"] > 45

    def test_noisy_sine(self):
        """Noisy sine should have lower ENOB."""
        fs = 1e6
        fin = 100e3
        n_samples = 1024

        t = np.arange(n_samples) / fs
        amplitude = 500
        noise = np.random.randn(n_samples) * 50  # Large noise
        codes = np.round(amplitude * np.sin(2 * np.pi * fin * t) + 1024 + noise).astype(
            int
        )

        result = compute_enob_fft(codes, fs, fin)

        # ENOB should be lower due to noise
        assert result["enob"] < 8.0

    def test_insufficient_samples(self):
        """Return NaN for insufficient samples."""
        result = compute_enob_fft(np.array([1, 2, 3]), fs=1e6, fin=100e3)
        assert np.isnan(result["enob"])

    def test_different_windows(self):
        """Test different window functions."""
        fs = 1e6
        fin = 100e3
        n_samples = 1024
        t = np.arange(n_samples) / fs
        codes = np.round(500 * np.sin(2 * np.pi * fin * t) + 1024).astype(int)

        for window in ["hann", "blackman", "hamming", "none"]:
            result = compute_enob_fft(codes, fs, fin, window=window)
            assert not np.isnan(result["enob"])


# =============================================================================
# Test Monte Carlo Statistics
# =============================================================================


class TestMcStatistics:
    """Tests for mc_statistics function."""

    def test_basic_statistics(self):
        """Compute basic statistics."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = mc_statistics(values)

        assert result["mean"] == pytest.approx(3.0)
        assert result["min"] == pytest.approx(1.0)
        assert result["max"] == pytest.approx(5.0)
        assert result["n"] == 5

    def test_3sigma_bounds(self):
        """Verify 3-sigma bounds."""
        values = np.random.randn(1000) * 1.0 + 5.0  # mean=5, std=1
        result = mc_statistics(values)

        assert result["sigma3_low"] == pytest.approx(result["mean"] - 3 * result["std"])
        assert result["sigma3_high"] == pytest.approx(
            result["mean"] + 3 * result["std"]
        )

    def test_empty_values(self):
        """Handle empty values."""
        result = mc_statistics([])
        assert np.isnan(result["mean"])
        assert result["n"] == 0

    def test_numpy_array_input(self):
        """Accept numpy array input."""
        values = np.array([1.0, 2.0, 3.0])
        result = mc_statistics(values)
        assert result["mean"] == pytest.approx(2.0)


# =============================================================================
# Integration Tests
# =============================================================================


class TestAdcPipelineIntegration:
    """Integration tests for full ADC measurement pipeline."""

    def test_bits_to_codes_to_voltage(self):
        """Full pipeline: bits -> codes -> voltage."""
        from ..cdac import CdacParams, get_cdac_weights

        weights = np.array(get_cdac_weights(CdacParams()))
        # Simulate ADC output bits for a mid-scale input
        bits = np.array(
            [
                [
                    1,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                ],  # ~768/2047 * 1.2 = 0.45V
                [
                    1,
                    1,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                ],  # ~1280/2047 * 1.2 = 0.75V
            ]
        )

        codes = redundant_bits_to_code(bits, weights)
        voltages = code_to_voltage(codes, v_ref=1.2, total_weight=2047)

        assert codes[0] == 768
        assert codes[1] == 1280
        assert voltages[0] == pytest.approx(768 * 1.2 / 2047)
        assert voltages[1] == pytest.approx(1280 * 1.2 / 2047)

    def test_transfer_function_analysis(self):
        """Test transfer function analysis pipeline."""
        # Simulate staircase input
        n_codes = 256
        v_in = np.linspace(0, 1.2, n_codes * 10)

        # Ideal ADC response with some quantization
        codes = np.clip(np.floor(v_in / 1.2 * n_codes), 0, n_codes - 1).astype(int)

        # Compute INL/DNL
        result = histogram_inl_dnl(codes, n_codes)

        # Should have reasonable linearity
        assert result["dnl_max"] < 1.0
        assert len(result["missing_codes"]) == 0

    def test_quantization_pipeline(self):
        """Test analog-to-digital quantization pipeline."""
        # Differential comparator outputs
        comp_out_p = np.array([1.2, 0.0, 1.2, 0.0])
        comp_out_n = np.array([0.0, 1.2, 0.0, 1.2])

        # Convert to single-ended
        comp_diff = diff_to_single(comp_out_p, comp_out_n)
        np.testing.assert_array_almost_equal(comp_diff, [1.2, -1.2, 1.2, -1.2])

        # Quantize to bits
        bits = quantize_to_bits(comp_diff, v_low=-1.2, v_high=1.2)
        np.testing.assert_array_equal(bits, [1, 0, 1, 0])
