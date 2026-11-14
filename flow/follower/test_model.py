"""The follower's behavioral model (``Model.output``) on a given curve: no characterization, no PDK."""

import numpy as np
import pytest

from .model import Model
from .params import Params


def test_the_output_level_follows_the_measured_curve() -> None:
    model = Model(
        pdk="tsmc65",
        params=Params(),
        vin_v=(0.0, 0.4, 0.8, 1.2),
        vout_v=(0.0, 0.05, 0.4, 0.75),
        gain_dc=0.85,
        bandwidth_hz=1e9,
        zout_dc_ohm=2e3,
    )
    # between its points, and held flat past its ends
    assert model.output(np.asarray([0.6, 1.0])) == pytest.approx([0.225, 0.575])
    assert model.output(np.asarray([-0.1, 1.5])) == pytest.approx([0.0, 0.75])
