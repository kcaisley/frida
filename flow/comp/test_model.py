"""The comparator's physics in the behavioral ADC (``Model.compare``, ``Model.strongarm_noise``), on
given parameters: no characterization, no PDK."""

import numpy as np
import pytest

from .model import Model, _tau
from .params import REGENERATION_SPAN_V, Bias, Params


def test_strongarm_noise_falls_with_larger_pq_capacitance() -> None:
    small = Model.strongarm_noise(Params(), 0.7)
    large = Model.strongarm_noise(Params(diffpair_w=64, rst_w=16), 0.7)
    assert 1e-3 < small < 5e-3
    assert large < small


def test_a_decision_too_small_to_regenerate_in_time_holds_the_last() -> None:
    """With a delay curve and a window, an input whose decision takes longer than the window is
    late: the SR latch still holds its last decision. Without a window it is never late."""
    behavioral = Model.Behavioral(noise_v=0.0, delay_table_v=(1e-6, 1e-3), delay_table_s=(2e-9, 0.6e-9))
    # 1 mV decides in 0.6 ns, within 1 ns; 1 nV, below the curve's smallest input (2 ns at 1 uV),
    # takes longer still
    vin_diff_v = np.asarray([-1e-3, 1e-3, 1e-9, -1e-9])
    held = np.asarray([1, 0, 0, 1])
    rng = np.random.default_rng(0)
    late = Model.compare(Params(), behavioral, vin_diff_v, rng, vin_cm_v=0.7, window_s=1e-9, held=held)
    assert late.tolist() == [0, 1, 0, 1]
    assert Model.compare(Params(), behavioral, vin_diff_v, rng, vin_cm_v=0.7).tolist() == [0, 1, 1, 0]


def test_the_noise_estimate_refuses_a_dynamic_bias() -> None:
    """Its node capacitance counts the devices' own alone: with C_P added on the drains (a dynamic
    bias) it is another circuit's."""
    with pytest.raises(ValueError, match="switched tail"):
        Model.strongarm_noise(Params(bias=Bias.DYNAMIC), 0.7)


def test_the_tables_slope_is_over_the_entries_within_the_regeneration_span() -> None:
    """A table falling 10 ps per e-fold up to 3 mV and flat above it: the slope is the 10 ps of the
    entries within the span (0.1, 0.3, 1 and 3 mV), not the flat part's."""
    import math

    inputs = (0.1e-3, 0.3e-3, 1e-3, 3e-3, 10e-3, 30e-3)
    delays = tuple(100e-12 + 10e-12 * math.log(3e-3 / min(x, 3e-3)) for x in inputs)
    assert REGENERATION_SPAN_V == 3e-3
    assert _tau(inputs, delays) == pytest.approx(10e-12, rel=1e-9)


def test_a_models_parameters_carry_the_toggling_energy_where_it_was_measured() -> None:
    model = Model(
        pdk="tsmc65",
        params=Params(),
        noise_v=0.4e-3,
        offset_v=0.0,
        delay_s=0.3e-9,
        energy_j=80e-15,
        delay_table_v=(1e-4, 1e-3),
        delay_table_s=(0.4e-9, 0.3e-9),
        cm_table_v=(0.65,),
        noise_table_v=(0.4e-3,),
        offset_table_v=(0.0,),
        toggle_energy_j=120e-15,
    )
    behavioral = model.behavioral()
    assert (behavioral.decision_energy_j, behavioral.toggle_energy_j) == (80e-15, 120e-15)
    assert behavioral.static_power_w == 0.0
    assert Model.Behavioral().toggle_energy_j is None
