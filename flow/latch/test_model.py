"""The latch's behavioral model (``Model.captures``, ``Model.delay_s``) on given numbers: no
characterization, no PDK."""

import numpy as np

from .model import Model
from .params import Params


def test_data_is_taken_from_the_setup_time_on_and_kept_out_from_the_hold_time_on() -> None:
    model = Model(
        pdk="tsmc65",
        params=Params(flop=True),
        delay_rise_s=45e-12,
        delay_fall_s=40e-12,
        energy_per_cycle_j=20e-15,
        setup_s=50e-12,
        hold_s=-25e-12,
    )
    taken = model.captures(np.asarray([200e-12, 50e-12, 40e-12, 25e-12, -100e-12]))
    np.testing.assert_array_equal(taken, [1.0, 1.0, np.nan, 0.0, 0.0])
    assert (model.delay_s(rising=True), model.delay_s(rising=False)) == (45e-12, 40e-12)
