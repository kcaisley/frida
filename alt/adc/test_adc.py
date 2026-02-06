"""
ADC testbench and test functions for FRIDA.

Provides:
- AdcTb: Testbench generator with PWL input
- AdcTbParams: Testbench parameters
- run_transfer_function: Run full INL/DNL characterization
- test_* functions: pytest entry points
"""

import hdl21 as h
import pytest
from hdl21.prefix import m, n, p
from hdl21.primitives import Vdc

from ..flow.params import Pvt, SupplyVals
from .adc import Adc, AdcParams, get_adc_weights


@h.paramclass
class AdcTbParams:
    """ADC testbench parameters."""

    pvt = h.Param(dtype=Pvt, desc="PVT conditions", default=Pvt())
    adc = h.Param(dtype=AdcParams, desc="ADC parameters", default=AdcParams())

    # Input voltage sweep (staircase PWL)
    v_start = h.Param(dtype=h.Scalar, desc="Starting input voltage", default=0 * m)
    v_stop = h.Param(dtype=h.Scalar, desc="Ending input voltage", default=1200 * m)
    v_step = h.Param(dtype=h.Scalar, desc="Voltage step size", default=1 * m)
    t_step = h.Param(dtype=h.Scalar, desc="Duration per step", default=200 * n)
    t_rise = h.Param(dtype=h.Scalar, desc="Rise time between steps", default=100 * p)

    # Common mode voltage
    vcm = h.Param(dtype=h.Scalar, desc="Common-mode voltage", default=600 * m)


@h.generator
def AdcTb(p: AdcTbParams) -> h.Module:
    """
    ADC testbench generator.

    Creates a testbench with:
    - Staircase PWL input for transfer function characterization
    - Supply sources
    - Clock/sequencer stimulus (simplified)
    """
    supplies = SupplyVals.corner(p.pvt.v)

    @h.module
    class AdcTb:
        """ADC testbench module."""

        # Ground reference
        vss = h.Port(desc="Ground")

        # Internal signals
        vdd_a = h.Signal(desc="Analog supply")
        vdd_d = h.Signal(desc="Digital supply")
        vin_p = h.Signal(desc="Input positive")
        vin_n = h.Signal(desc="Input negative")
        vcm = h.Signal(desc="Common mode")

        # Sequencer signals
        seq_init = h.Signal()
        seq_samp = h.Signal()
        seq_comp = h.Signal()
        seq_update = h.Signal()

        # Enable signals (active high)
        en_init = h.Signal()
        en_samp_p = h.Signal()
        en_samp_n = h.Signal()
        en_comp = h.Signal()
        en_update = h.Signal()

        # Control signals
        dac_mode = h.Signal()
        dac_diffcaps = h.Signal()

        # DAC state inputs (all zeros for normal operation)
        dac_astate_p = h.Signal(width=16)
        dac_bstate_p = h.Signal(width=16)
        dac_astate_n = h.Signal(width=16)
        dac_bstate_n = h.Signal(width=16)

        # Outputs
        dac_state_p = h.Signal(width=16)
        dac_state_n = h.Signal(width=16)

    # Supply sources
    AdcTb.vvdd_a = Vdc(dc=supplies.VDD)(p=AdcTb.vdd_a, n=AdcTb.vss)
    AdcTb.vvdd_d = Vdc(dc=supplies.VDD)(p=AdcTb.vdd_d, n=AdcTb.vss)

    # Instantiate ADC
    AdcTb.xadc = Adc(p.adc)(
        vin_p=AdcTb.vin_p,
        vin_n=AdcTb.vin_n,
        seq_init=AdcTb.seq_init,
        seq_samp=AdcTb.seq_samp,
        seq_comp=AdcTb.seq_comp,
        seq_update=AdcTb.seq_update,
        en_init=AdcTb.en_init,
        en_samp_p=AdcTb.en_samp_p,
        en_samp_n=AdcTb.en_samp_n,
        en_comp=AdcTb.en_comp,
        en_update=AdcTb.en_update,
        dac_mode=AdcTb.dac_mode,
        dac_diffcaps=AdcTb.dac_diffcaps,
        dac_astate_p=AdcTb.dac_astate_p,
        dac_bstate_p=AdcTb.dac_bstate_p,
        dac_astate_n=AdcTb.dac_astate_n,
        dac_bstate_n=AdcTb.dac_bstate_n,
        dac_state_p=AdcTb.dac_state_p,
        dac_state_n=AdcTb.dac_state_n,
        vdd_a=AdcTb.vdd_a,
        vss_a=AdcTb.vss,
        vdd_d=AdcTb.vdd_d,
        vss_d=AdcTb.vss,
    )

    # Note: Actual voltage sources need to be added via simulation setup
    # since HDL21 doesn't have native Vpwl. The testbench provides the
    # structure and the simulation config adds the sources.

    return AdcTb


def run_transfer_function(
    p: AdcTbParams,
    sim_options: dict | None = None,
) -> dict:
    """
    Run ADC transfer function characterization.

    Performs a staircase sweep and computes INL/DNL.

    Args:
        p: Testbench parameters
        sim_options: Optional simulation options dict

    Returns:
        Dict with results including:
        - v_in: Input voltage array
        - codes: Output code array
        - inl_dnl: INL/DNL analysis results
        - weights: Capacitor weights used
    """
    # Import here to avoid circular imports
    from ..flow.measure import (
        code_to_voltage,
        compute_static_error,
        histogram_inl_dnl,
        redundant_bits_to_code,
    )

    weights = get_adc_weights(p.adc)

    # Placeholder pipeline using synthetic data for shared measurement functions.
    n_bits = len(weights)
    dummy_bits = [[0] * n_bits, [1] * n_bits]
    codes = redundant_bits_to_code(dummy_bits, weights)
    v_est = code_to_voltage(codes, v_ref=1.2, total_weight=int(weights.sum()))
    inl_dnl = histogram_inl_dnl(codes, n_codes=int(weights.sum()) + 1)
    static_error = compute_static_error(v_est, v_est)

    # TODO: replace with real simulation and waveform extraction
    return {
        "v_in": v_est,
        "codes": codes,
        "inl_dnl": inl_dnl,
        "static_error": static_error,
        "weights": weights,
        "n_codes": int(weights.sum()) + 1,
    }


# =============================================================================
# Pytest Entry Points
# =============================================================================


def test_adc_netlist(flowmode):
    """Test ADC netlist generation."""
    from ..flow import FlowMode

    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    # Generate ADC with default params
    params = AdcParams()
    adc = Adc(params)

    # Verify structure
    assert hasattr(adc, "xdigital")
    assert hasattr(adc, "xcdac_p")
    assert hasattr(adc, "xcdac_n")
    assert hasattr(adc, "xsamp_p")
    assert hasattr(adc, "xsamp_n")
    assert hasattr(adc, "xcomp")


def test_adc_tb_netlist(flowmode):
    """Test ADC testbench netlist generation."""
    from ..flow import FlowMode

    if flowmode != FlowMode.NETLIST:
        pytest.skip("Only runs in flow mode NETLIST")

    # Generate testbench
    params = AdcTbParams()
    tb = AdcTb(params)

    # Verify structure
    assert hasattr(tb, "xadc")


def test_adc_weights():
    """Test ADC weight calculation with SUBRDX2_OVLY strategy."""
    import numpy as np

    params = AdcParams()
    weights = get_adc_weights(params)

    # Should have 16 weights for default n_dac=11, n_extra=5
    assert len(weights) == 16

    # Total weight should be exactly 2047 (2^11 - 1) for 11-bit equivalent
    assert weights.sum() == 2047

    # Verify first weight (MSB) is 768 for FRIDA 65nm config
    assert weights[0] == 768

    # Verify full weight sequence matches expected FRIDA 65nm values
    expected = np.array([768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1])
    np.testing.assert_array_equal(weights, expected)
