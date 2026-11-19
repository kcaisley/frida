"""The comparator's bench constants against the relations their comments state, each derived by
hand in its test (no simulator, no PDK)."""

import math

import numpy as np
import pytest

from . import params
from .params import TbParams


def test_the_noise_strobe_is_half_a_period_of_the_noise_bandwidth() -> None:
    """1 / (2 x 100 GHz) = 5 ps: the two constants are set together."""
    assert params.NOISE_STROBE_S == 1 / (2 * TbParams().noise_fmax_hz) == 5e-12


def test_a_run_without_a_supply_takes_the_nominal_common_mode_of_1p2_v() -> None:
    """13/24 of 1.2 V is 0.65 V."""
    tb = TbParams()
    assert tb.vin_cm_values_v == (0.65,) and tb.vin_cm_values_v[0] == pytest.approx(params.NOMINAL_CM * tb.vdd)


def test_the_clock_check_is_at_twice_the_reset_and_twice_the_evaluation() -> None:
    assert params.CHECK_CLOCK_S == (2e-9, 8e-9)
    assert params.EVALUATION_S == 2 * params.DECISION_S


def test_a_decision_is_read_two_transitions_before_its_cycles_end() -> None:
    """A cycle is 1 + 4 ns; two 20 ps transitions before its end is 4.96 ns, the next 9.96 ns."""
    tb = TbParams(vin_diff_values_v=(1e-3,), conversions=2)
    assert tb.decision_time_s.tolist() == pytest.approx([4.96e-9, 9.96e-9])


def test_the_kickback_source_holds_its_charge_for_many_cycles() -> None:
    """1 Mohm x 1 pF = 1 us, 200 cycles of 5 ns."""
    resistance_ohm, capacitance_f = params.KICKBACK_SOURCE
    assert resistance_ohm * capacitance_f == pytest.approx(1e-6)
    assert resistance_ohm * capacitance_f / TbParams().cycle_s == pytest.approx(200)


def test_the_delay_curves_inputs_bracket_any_offset_up_to_12_mv() -> None:
    """From 2 to 15 mV the inputs are 1, 1, 2, 2, 2, 2 and 3 mV apart (2, 3, 4, 6, 8, 10, 12, 15), so
    an offset anywhere within +-12 mV has an input at most 2 mV below it and one at most 2 mV above
    (the widest gap inside +-12 mV is 2 mV), and at least two within the fit's span, 3 mV."""
    magnitudes_mv = [value * 1e3 for value in params.METASTABILITY_V if 2e-3 <= value <= 15e-3]
    assert np.diff(magnitudes_mv).round(9).tolist() == [1, 1, 2, 2, 2, 2, 3]
    inputs = np.sort(np.asarray(params.METASTABILITY_RUN_V))
    for offset in np.linspace(-12e-3, 12e-3, 4801):
        below, above = inputs[inputs <= offset + 1e-12], inputs[inputs >= offset - 1e-12]
        assert offset - below[-1] <= 2e-3 + 1e-12 and above[0] - offset <= 2e-3 + 1e-12
        assert np.count_nonzero(np.abs(inputs - offset) <= params.REGENERATION_SPAN_V + 1e-12) >= 2


def test_the_scurve_grid_counts_the_points_its_comment_states() -> None:
    """LSB / sqrt(12) of a differential full scale of 2 x 0.8 x 1.2 V: 1.92 V / 2^14 / 3.4641 =
    33.8 uV and 1.92 V / 2^10 / 3.4641 = 541 uV. Within 2 sigma (67.7 uV): 0 and +-5, 10, 15, 20,
    25, 35, 50 uV, 15 points; within 1083 uV: 0 and the 14 magnitudes up to 1 mV a side, 29."""
    quiet, loud = (2 * params.ADC_FULL_SCALE * 1.2 / 2**bits / math.sqrt(12) for bits in (14, 10))
    assert quiet == pytest.approx(33.8e-6, rel=2e-3) and loud == pytest.approx(541e-6, rel=2e-3)
    inputs = np.asarray(params.SCURVE_V)
    assert len(inputs) == 33
    assert np.count_nonzero(np.abs(inputs) <= 2 * quiet) == 15
    assert np.count_nonzero(np.abs(inputs) <= 2 * loud) == 29


def test_a_design_that_only_scales_costs_least_at_the_noise_the_weights_set() -> None:
    """Energy and area proportional to a scale s and the noise power to 1 / s: with u = (noise /
    LSB-noise)^2 the cost goes as u^-(1 + a) (1 + u)^n, whose log-derivative -(1 + a) + n u / (1 +
    u) is zero at u = 1 / (n / (1 + a) - 1): u = 1 / 2 for a = 1, n = 6, a noise ratio of 0.707."""
    a, n = params.AREA_WEIGHT, params.NOISE_WEIGHT
    u = np.logspace(-3, 3, 600001)
    least = u[np.argmin(u ** -(1 + a) * (1 + u) ** n)]
    assert least == pytest.approx(0.5, rel=1e-3)
    assert (
        math.sqrt(least) == pytest.approx(1 / math.sqrt(n / (1 + a) - 1), rel=1e-3) == pytest.approx(0.7071, rel=1e-3)
    )


def test_the_supply_corners_stay_within_the_flows_largest() -> None:
    from flow.circuit import oppoint

    assert max(params.SUPPLY_SWEEP) == oppoint.SUPPLY_CORNER_MAX == 1.1 and min(params.SUPPLY_SWEEP) == 0.9


def test_fridas_fabricated_tail_is_drawn_at_an_even_count_of_whole_fingers(monkeypatch) -> None:
    """An analog device takes an even count of whole-unit fingers (``flow.circuit.devices.fingers``):
    two fingers of 5 / 2 = 2.5 units round to 3 each, 6 units for the 5 given, where a PDK states
    its fingers (here ten units a finger at most)."""
    import hdl21 as h

    from flow.circuit.devices import fingers

    kit = type("Kit", (), {"MOS_FINGER_UNITS": {"analog": 10, "logic_n": 1, "logic_p": 2}})
    monkeypatch.setattr(h.pdk, "default", lambda: kit)
    assert fingers(params.FRIDA1.tail_w, "analog") == (6, 2)
