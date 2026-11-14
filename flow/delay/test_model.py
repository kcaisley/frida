"""The chain's behavioral model on a given stage delay curve: no characterization, no PDK."""

import pytest

from .model import Model
from .params import Params


def test_a_lines_delay_is_its_stages_delays_interpolated_over_the_supply() -> None:
    model = Model(pdk="tsmc65", params=Params(stages=4), supply=(0.9, 1.0, 1.1), stage_delay_s=(12e-12, 10e-12, 9e-12))
    assert model.stage_delay() == pytest.approx(10e-12)
    assert model.delay_s() == pytest.approx(40e-12)
    assert model.delay_s(supply=0.95) == pytest.approx(44e-12)
    # held flat past the measured supplies
    assert model.delay_s(supply=0.8) == pytest.approx(48e-12)
    assert model.delay_s(supply=1.3) == pytest.approx(36e-12)


def test_a_rings_frequency_is_two_passes_around_it() -> None:
    model = Model(
        pdk="tsmc65", params=Params(stages=5, ring=True), supply=(0.9, 1.0, 1.1), stage_delay_s=(12e-12, 10e-12, 9e-12)
    )
    assert model.oscillation_frequency_hz() == pytest.approx(10e9)
    assert model.oscillation_frequency_hz(supply=1.1) == pytest.approx(1 / (10 * 9e-12))
