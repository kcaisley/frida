"""The amplifier's behavioral model (``Model.amplitude``) on a given curve: no characterization, no PDK."""

import numpy as np
import pytest

from .model import Model
from .params import Params


def test_the_amplitude_follows_the_measured_curve() -> None:
    model = Model(
        pdk="tsmc65",
        params=Params(),
        charge_c=(0.25e-15, 0.5e-15, 1e-15, 2e-15),
        amplitude_v=(0.03, 0.06, 0.12, 0.23),
        charge_gain_v_per_c=1.2e14,
        peaking_time_s=9e-9,
        enc_electrons=140.0,
    )
    # between its points, by magnitude, and held flat past its ends
    assert model.amplitude(np.asarray([0.75e-15, -1.5e-15])) == pytest.approx([0.09, 0.175])
    assert model.amplitude(np.asarray([0.1e-15, 3e-15])) == pytest.approx([0.03, 0.23])
