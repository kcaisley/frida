"""The comparator's physics in the behavioral ADC (``Model.compare``, ``Model.strongarm_noise``), on
given parameters: no characterization, no PDK."""

import numpy as np

from .model import Model
from .params import Params


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
