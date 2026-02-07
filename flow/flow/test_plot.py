"""
Unit tests for plotting functions in flow/flow/plot.py.

These tests verify the plotting functions run without errors and return
proper figure objects. They use matplotlib's Agg backend for headless testing.

Tests are automatically skipped if matplotlib is not installed.
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest

# Check if matplotlib is available
try:
    import matplotlib  # noqa: F401

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

pytestmark = pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib not installed")

if HAS_MATPLOTLIB:
    from .plot import (
        configure_matplotlib,
        plot_enob_vs_frequency,
        plot_fft_spectrum,
        plot_histogram,
        plot_inl_dnl,
        plot_monte_carlo_histogram,
        plot_transfer_function,
        plot_waveforms,
        save_plot,
    )


@pytest.fixture(scope="module")
def plt():
    """Configure matplotlib for tests."""
    from .plot import configure_matplotlib

    return configure_matplotlib()


# =============================================================================
# Test Configuration
# =============================================================================


class TestConfigureMatplotlib:
    """Tests for configure_matplotlib function."""

    def test_returns_pyplot(self):
        """Should return pyplot module."""
        plt = configure_matplotlib()
        assert hasattr(plt, "figure")
        assert hasattr(plt, "subplot")
        assert hasattr(plt, "close")

    def test_uses_agg_backend(self):
        """Should use Agg backend for headless operation."""
        import matplotlib

        configure_matplotlib()
        assert matplotlib.get_backend() == "Agg"


# =============================================================================
# Test Save Plot
# =============================================================================


class TestSavePlot:
    """Tests for save_plot function."""

    def test_save_creates_files(self, plt):
        """Should create PDF and PNG files."""
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])

        with tempfile.TemporaryDirectory() as tmpdir:
            saved = save_plot(fig, "test_plot", output_dir=Path(tmpdir))

            assert len(saved) == 2
            assert any("pdf" in s for s in saved)
            assert any("png" in s for s in saved)

            for path in saved:
                assert Path(path).exists()

        plt.close(fig)

    def test_creates_output_dir(self, plt):
        """Should create output directory if it doesn't exist."""
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])

        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "new_subdir"
            saved = save_plot(fig, "test", output_dir=new_dir)

            assert new_dir.exists()
            assert len(saved) > 0

        plt.close(fig)


# =============================================================================
# Test INL/DNL Plot
# =============================================================================


class TestPlotInlDnl:
    """Tests for plot_inl_dnl function."""

    def test_basic_plot(self, plt):
        """Should create figure with INL/DNL subplots."""
        result = {
            "dnl": np.random.randn(256) * 0.3,
            "inl": np.cumsum(np.random.randn(256) * 0.3),
            "dnl_max": 0.5,
            "inl_max": 2.0,
            "first_code": 10,
            "last_code": 245,
        }

        fig = plot_inl_dnl(result)

        assert fig is not None
        # Should have 2 subplots (DNL and INL)
        assert len(fig.axes) == 2

        plt.close(fig)

    def test_with_title(self, plt):
        """Should include title when provided."""
        result = {
            "dnl": np.zeros(100),
            "inl": np.zeros(100),
            "first_code": 0,
            "last_code": 99,
        }

        fig = plot_inl_dnl(result, title="Test Title")

        assert fig._suptitle is not None or "Test Title" in fig._suptitle.get_text()

        plt.close(fig)

    def test_save_option(self, plt):
        """Should save figure when save_path provided."""
        result = {
            "dnl": np.zeros(100),
            "inl": np.zeros(100),
            "first_code": 0,
            "last_code": 99,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = str(Path(tmpdir) / "inl_dnl")
            fig = plot_inl_dnl(result, save_path=save_path)

            # Note: save_path in plot_inl_dnl calls save_plot() which saves to 'scratch' by default
            # This is a smoke test that the save code path doesn't error

        plt.close(fig)


# =============================================================================
# Test Histogram Plot
# =============================================================================


class TestPlotHistogram:
    """Tests for plot_histogram function."""

    def test_basic_histogram(self, plt):
        """Should create histogram figure."""
        result = {
            "histogram": np.random.poisson(100, 256),
            "first_code": 5,
            "last_code": 250,
            "missing_codes": [],
        }

        fig = plot_histogram(result)

        assert fig is not None
        assert len(fig.axes) == 1

        plt.close(fig)

    def test_with_missing_codes(self, plt):
        """Should mark missing codes."""
        hist = np.ones(100) * 50
        hist[42] = 0  # Missing code
        result = {
            "histogram": hist,
            "first_code": 0,
            "last_code": 99,
            "missing_codes": [42],
        }

        fig = plot_histogram(result, title="Histogram with Missing Code")

        assert fig is not None

        plt.close(fig)


# =============================================================================
# Test Transfer Function Plot
# =============================================================================


class TestPlotTransferFunction:
    """Tests for plot_transfer_function function."""

    def test_basic_transfer_function(self, plt):
        """Should create transfer function plot."""
        v_in = np.linspace(0, 1.2, 1000)
        codes = np.clip(np.floor(v_in / 1.2 * 2048), 0, 2047).astype(int)

        fig = plot_transfer_function(v_in, codes)

        assert fig is not None
        ax = fig.axes[0]
        assert ax.get_xlabel() != ""
        assert ax.get_ylabel() != ""

        plt.close(fig)

    def test_with_title(self, plt):
        """Should include title when provided."""
        v_in = np.linspace(0, 1, 100)
        codes = np.floor(v_in * 100).astype(int)

        fig = plot_transfer_function(v_in, codes, title="Transfer Function")

        assert fig is not None

        plt.close(fig)


# =============================================================================
# Test FFT Spectrum Plot
# =============================================================================


class TestPlotFftSpectrum:
    """Tests for plot_fft_spectrum function."""

    def test_basic_fft(self, plt):
        """Should create FFT spectrum plot."""
        fs = 1e6
        fin = 100e3
        n = 1024
        t = np.arange(n) / fs
        codes = np.round(500 * np.sin(2 * np.pi * fin * t) + 1024).astype(int)

        fig = plot_fft_spectrum(codes, fs)

        assert fig is not None
        ax = fig.axes[0]
        assert "Frequency" in ax.get_xlabel()

        plt.close(fig)

    def test_with_harmonic_markers(self, plt):
        """Should add harmonic markers when fin provided."""
        fs = 1e6
        fin = 50e3
        n = 1024
        t = np.arange(n) / fs
        codes = np.round(500 * np.sin(2 * np.pi * fin * t) + 1024).astype(int)

        fig = plot_fft_spectrum(codes, fs, fin=fin, n_harmonics=3)

        assert fig is not None
        # Should have legend with harmonic labels
        ax = fig.axes[0]
        legend = ax.get_legend()
        assert legend is not None

        plt.close(fig)


# =============================================================================
# Test Waveforms Plot
# =============================================================================


class TestPlotWaveforms:
    """Tests for plot_waveforms function."""

    def test_single_waveform(self, plt):
        """Should plot single waveform."""
        time = np.linspace(0, 1e-6, 100)
        waveforms = {"signal": np.sin(2 * np.pi * 1e6 * time)}

        fig = plot_waveforms(time, waveforms)

        assert fig is not None
        ax = fig.axes[0]
        assert "ns" in ax.get_xlabel()  # Should auto-detect ns scale

        plt.close(fig)

    def test_multiple_waveforms(self, plt):
        """Should plot multiple waveforms with legend."""
        time = np.linspace(0, 1e-3, 100)
        waveforms = {
            "vin": np.sin(2 * np.pi * 1e3 * time),
            "vout": np.sin(2 * np.pi * 1e3 * time - 0.1) * 0.9,
        }

        fig = plot_waveforms(time, waveforms, title="Input and Output")

        assert fig is not None
        ax = fig.axes[0]
        legend = ax.get_legend()
        assert legend is not None

        plt.close(fig)

    def test_time_units(self, plt):
        """Should auto-detect appropriate time units."""
        # Nanosecond scale
        time_ns = np.linspace(0, 100e-9, 100)
        fig_ns = plot_waveforms(time_ns, {"sig": np.ones(100)})
        assert "ns" in fig_ns.axes[0].get_xlabel()
        plt.close(fig_ns)

        # Microsecond scale
        time_us = np.linspace(0, 100e-6, 100)
        fig_us = plot_waveforms(time_us, {"sig": np.ones(100)})
        xlabel = fig_us.axes[0].get_xlabel()
        assert "s" in xlabel  # us contains 's'
        plt.close(fig_us)


# =============================================================================
# Test ENOB vs Frequency Plot
# =============================================================================


class TestPlotEnobVsFrequency:
    """Tests for plot_enob_vs_frequency function."""

    def test_basic_enob_plot(self, plt):
        """Should create ENOB vs frequency plot."""
        frequencies = np.array([1e3, 10e3, 100e3, 1e6])
        enob_values = np.array([10.5, 10.3, 9.8, 8.5])

        fig = plot_enob_vs_frequency(frequencies, enob_values)

        assert fig is not None
        ax = fig.axes[0]
        assert "Frequency" in ax.get_xlabel()
        assert "ENOB" in ax.get_ylabel()

        plt.close(fig)

    def test_with_nominal_bits(self, plt):
        """Should add reference line for nominal bits."""
        frequencies = np.array([1e3, 10e3, 100e3])
        enob_values = np.array([10.8, 10.5, 10.0])

        fig = plot_enob_vs_frequency(frequencies, enob_values, nominal_bits=11)

        assert fig is not None
        # Should have legend with reference line
        ax = fig.axes[0]
        legend = ax.get_legend()
        assert legend is not None

        plt.close(fig)


# =============================================================================
# Test Monte Carlo Histogram Plot
# =============================================================================


class TestPlotMonteCarloHistogram:
    """Tests for plot_monte_carlo_histogram function."""

    def test_basic_mc_histogram(self, plt):
        """Should create MC histogram with statistics."""
        values = np.random.randn(1000) * 2 + 5  # mean=5, std=2

        fig = plot_monte_carlo_histogram(values, xlabel="Offset (mV)")

        assert fig is not None
        ax = fig.axes[0]
        assert "Offset" in ax.get_xlabel()
        assert "Count" in ax.get_ylabel()

        plt.close(fig)

    def test_statistics_annotation(self, plt):
        """Should include mean and sigma annotations."""
        values = np.ones(100) * 3.0  # All same value

        fig = plot_monte_carlo_histogram(values, xlabel="Value")

        # Should have stats annotation (mean line, 3-sigma lines)
        assert fig is not None
        ax = fig.axes[0]
        # Check that there are vertical lines (mean and 3-sigma markers)
        assert len(ax.lines) >= 2

        plt.close(fig)

    def test_custom_bins(self, plt):
        """Should respect n_bins parameter."""
        values = np.random.randn(500)

        fig = plot_monte_carlo_histogram(values, xlabel="Value", n_bins=50)

        assert fig is not None

        plt.close(fig)


# =============================================================================
# Integration Tests
# =============================================================================


class TestPlottingIntegration:
    """Integration tests combining measurement and plotting."""

    def test_inl_dnl_analysis_to_plot(self, plt):
        """Full pipeline from codes to INL/DNL plot."""
        from .measure import histogram_inl_dnl

        # Simulate ADC output with slight nonlinearity
        n_codes = 256
        codes = np.repeat(np.arange(n_codes), 100)
        # Add some noise
        codes = codes + np.random.randint(-1, 2, len(codes))
        codes = np.clip(codes, 0, n_codes - 1)

        # Compute INL/DNL
        result = histogram_inl_dnl(codes, n_codes)

        # Plot results
        fig = plot_inl_dnl(result, title="ADC INL/DNL Analysis")

        assert fig is not None
        assert len(fig.axes) == 2

        plt.close(fig)

    def test_fft_analysis_to_plot(self, plt):
        """Full pipeline from sine wave to FFT plot."""
        from .measure import compute_enob_fft

        fs = 1e6
        fin = 100e3
        n = 2048
        t = np.arange(n) / fs
        codes = np.round(500 * np.sin(2 * np.pi * fin * t) + 1024).astype(int)

        # Compute ENOB
        result = compute_enob_fft(codes, fs, fin)

        # Plot spectrum
        fig = plot_fft_spectrum(
            codes,
            fs,
            fin=fin,
            title=f"ADC FFT Spectrum (ENOB={result['enob']:.1f})",
        )

        assert fig is not None
        assert result["enob"] > 5.0  # Sanity check

        plt.close(fig)
