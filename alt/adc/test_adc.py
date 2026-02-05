"""
ADC testbench and test functions for FRIDA.

Provides:
- AdcTb: Testbench generator with PWL input
- AdcTbParams: Testbench parameters
- generate_staircase_pwl: Helper for staircase input waveform
- run_transfer_function: Run full INL/DNL characterization
- test_* functions: pytest entry points
"""

import hdl21 as h
from hdl21.prefix import m, n, p

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


def generate_staircase_pwl(
    v_start: float,
    v_stop: float,
    v_step: float,
    t_step: float,
    t_rise: float,
    t_delay: float = 0.0,
) -> list[tuple[float, float]]:
    """
    Generate staircase PWL points for ADC transfer function test.

    Each step holds for t_step duration (allowing multiple ADC conversions),
    then ramps over t_rise to the next level. This is quasi-static, matching
    physical measurement conditions with an SMU.

    Args:
        v_start: Starting voltage (V)
        v_stop: Ending voltage (V)
        v_step: Voltage increment per step (V)
        t_step: Hold time at each voltage level (s)
        t_rise: Transition time between levels (s)
        t_delay: Initial delay before first step (s)

    Returns:
        List of (time, voltage) tuples for PWL source
    """
    points: list[tuple[float, float]] = []
    n_steps = int(abs(v_stop - v_start) / v_step) + 1
    t = t_delay
    sign = 1 if v_stop >= v_start else -1

    for i in range(n_steps):
        v = v_start + sign * i * v_step
        points.append((t, v))
        t += t_step
        if i < n_steps - 1:
            points.append((t, v))  # Hold before transition
            t += t_rise

    return points


def pwl_to_spice_literal(
    name: str,
    p_node: str,
    n_node: str,
    points: list[tuple[float, float]],
) -> str:
    """
    Generate SPICE PWL source literal string.

    Args:
        name: Source name (e.g., "vin")
        p_node: Positive node name
        n_node: Negative node name
        points: List of (time, voltage) tuples

    Returns:
        SPICE PWL source string
    """
    pwl_str = " ".join(f"{t:.12e} {v:.6e}" for t, v in points)
    return f"V{name} {p_node} {n_node} PWL({pwl_str})"


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

    # This is a placeholder - actual implementation would:
    # 1. Generate the testbench
    # 2. Add PWL sources via simulation literals
    # 3. Run transient simulation
    # 4. Extract samples at clock edges
    # 5. Convert bits to codes and analyze

    # For now, return empty results structure
    return {
        "v_in": None,
        "codes": None,
        "inl_dnl": None,
        "static_error": None,
        "weights": weights,
        "n_codes": int(weights.sum()) + 1,
    }


# =============================================================================
# Pytest Entry Points
# =============================================================================


def test_adc_netlist(simtestmode):
    """Test ADC netlist generation."""
    from ..flow import SimTestMode

    if simtestmode != SimTestMode.NETLIST:
        return

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


def test_adc_tb_netlist(simtestmode):
    """Test ADC testbench netlist generation."""
    from ..flow import SimTestMode

    if simtestmode != SimTestMode.NETLIST:
        return

    # Generate testbench
    params = AdcTbParams()
    tb = AdcTb(params)

    # Verify structure
    assert hasattr(tb, "xadc")


def test_staircase_pwl():
    """Test staircase PWL generation."""
    points = generate_staircase_pwl(
        v_start=0.0,
        v_stop=1.0,
        v_step=0.1,
        t_step=1e-6,
        t_rise=1e-9,
    )

    # Should have 11 steps (0.0 to 1.0 in 0.1 increments)
    # Each step has 2 points (start and end of hold), except last
    assert len(points) > 0

    # First point should be at t=0, v=0
    assert points[0] == (0.0, 0.0)

    # Voltages should be monotonically increasing
    voltages = [v for t, v in points]
    for i in range(len(voltages) - 1):
        assert voltages[i] <= voltages[i + 1]


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
