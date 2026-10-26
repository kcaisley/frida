import importlib
import math
from types import SimpleNamespace

import pytest

from flow.adc import reference
from flow.adc.model import Reference
from flow.adc.reference import DECAP_COVERAGE, SHARE, decoupling_f, enob_floor, requirements


def test_an_error_of_the_quantization_noise_costs_an_ideal_quantizer_half_a_bit() -> None:
    assert enob_floor(12, 12.0) == pytest.approx(11.5)
    assert enob_floor(12, 12.0, SHARE) == pytest.approx(12 - 0.5 * math.log2(1 + SHARE))
    # a converter already far from its resolution loses less of it to the same error
    assert 0 < 11.0 - enob_floor(12, 11.0) < 0.5 - 1e-3


def test_the_decoupling_is_the_decap_share_of_both_arrays_to_one_figure(monkeypatch) -> None:
    pdk = SimpleNamespace(pdk_logic=SimpleNamespace(DECAP_FF_PER_UM2=4.0))
    monkeypatch.setattr(importlib, "import_module", lambda name: pdk)
    # both arrays' 2000 um^2 at 4 fF/um^2, 30 % of it: 2.4 pF, to one figure
    assert DECAP_COVERAGE == 0.30
    assert decoupling_f(SimpleNamespace(pdk="any", cdac=SimpleNamespace(area_um2=1000.0))) == 2e-12
    assert math.isnan(decoupling_f(SimpleNamespace(pdk="any", cdac=SimpleNamespace(area_um2=0.0))))


def test_each_requirement_is_where_its_loss_reaches_its_share_of_the_quantization_noise(monkeypatch) -> None:
    """A stand-in converter whose added error power grows as the square of the reference's noise
    and of its driver's time constant over 1 ns: each requirement lands within the search's
    resolution of the analytic one, and each figure is the loss over its grid."""
    bits, enob_bits = 12, 11.0
    lsb2 = 1.0 / 12  # the quantization noise power, in LSB^2

    def measured(ref: Reference) -> float:
        error = (ref.noise_v / 100e-6) ** 2 + (ref.r_ohm * ref.c_f / 1e-9) ** 2
        return bits - 0.5 * math.log2(2.0 ** (2 * (bits - enob_bits)) + error / lsb2)

    monkeypatch.setattr(reference, "dynamic_enob", measured)
    monkeypatch.setattr(reference, "decoupling_f", lambda model: 1e-12)
    capture = SimpleNamespace(tb=None, seed=0, noise_seed=0, unit_mismatch=0.0, quiet=(), tau_scale=1.0)
    model = SimpleNamespace(params=SimpleNamespace(adc_bits=bits), capture=lambda tb, path, reference, **_: reference)
    metrics, details = requirements(model, capture, enob_bits)
    # the error may reach SHARE of the quantization noise power: (x / x0)^2 = SHARE / 12
    within = math.sqrt(SHARE * lsb2)
    assert metrics["ref_noise_max_v"] == pytest.approx(100e-6 * within, rel=0.05)
    assert metrics["ref_noise_max_v"] <= 100e-6 * within
    assert metrics["ref_r_max_ohm"] == pytest.approx(1e3 * within, rel=0.05)
    assert metrics["ref_decap_f"] == 1e-12
    assert metrics["ref_enob_loss_max_bits"] == pytest.approx(enob_bits - enob_floor(bits, enob_bits, SHARE))
    assert [plot.name for plot in details] == ["reference_noise", "reference_r_out"]
    losses = details[0].series["ENOB loss"]
    assert losses == sorted(losses) and losses[0] == pytest.approx(0.0, abs=1e-3)
