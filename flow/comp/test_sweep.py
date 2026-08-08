"""Software-only tests for the shared comparator sweep definition."""

from __future__ import annotations

import pytest

from flow.circuit.params import build_uniform_sweep_values, validate_uniform_sweep
from flow.comp.sim import CompTbParams, sim_input


def test_default_comparator_sweep_is_the_complete_physical_grid() -> None:
    params = CompTbParams()

    validate_uniform_sweep(params.sweep_min_v, params.sweep_max_v, params.sweep_step_v)
    values = build_uniform_sweep_values(params.sweep_min_v, params.sweep_max_v, params.sweep_step_v)
    assert params.vin_cm_values_v == (0.7, 0.8, 0.9, 1.0, 1.1, 1.2)
    assert len(values) == 251
    assert values[0] == 0.0
    assert values[-1] == pytest.approx(25.0e-3)
    assert params.conversions == 1_000


def test_standalone_comparator_simulation_consumes_its_typed_sweep() -> None:
    params = CompTbParams(
        vin_cm_values_v=(0.8,),
        sweep_min_v=9.0e-3,
        sweep_max_v=11.0e-3,
        sweep_step_v=1.0e-3,
        conversions=8,
    )

    assert build_uniform_sweep_values(params.sweep_min_v, params.sweep_max_v, params.sweep_step_v) == pytest.approx(
        (9.0e-3, 10.0e-3, 11.0e-3)
    )
    sim_input(params)


def test_comparator_sweep_rejects_misaligned_endpoints() -> None:
    with pytest.raises(ValueError, match="endpoints"):
        validate_uniform_sweep(0.0, 1.05e-3, 100.0e-6)
