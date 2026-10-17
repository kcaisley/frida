"""Comparator timing, power and candidate analyses, and the topology plots, on synthetic records."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.comp import analyze_comp_common_mode, analyze_comp_offset_noise
from flow.analysis.test_comp import comparator_measurement
from flow.analysis.types import MeasComp
from flow.comp.analysis import analyze_comp_candidate, analyze_comp_delay, analyze_comp_power, analyze_comp_timing
from flow.comp.plots import plot_comp_common_mode, plot_comp_delay, plot_comp_energy


def test_comp_timing_and_power_use_internal_waveforms() -> None:
    msmt = comparator_measurement()
    timing = analyze_comp_timing([msmt])
    assert timing.clock_to_decision_s[0] == pytest.approx(2e-9, abs=20e-12)
    np.testing.assert_array_equal(timing.unresolved, (0, 1, 0))

    power = analyze_comp_power([msmt])
    assert power.average_power_w[0] == pytest.approx(12e-6)
    assert power.energy_per_decision_j[0] == pytest.approx(480e-15)


def test_comp_settling_starts_at_the_interpolated_clock_trigger() -> None:
    msmt = comparator_measurement()
    assert msmt.wave is not None
    time_s = np.asarray((0.0, 2.0, 4.0)) * 1e-9
    voltage = {name: values[:, :3] for name, values in msmt.wave.v.items()}
    voltage.update(
        clk=np.tile((0.0, 1.2, 1.2), (3, 1)),
        latch_p=np.tile((0.5, 0.75, 1.0), (3, 1)),
        latch_n=np.tile((0.5, 0.25, 0.0), (3, 1)),
    )
    msmt = replace(
        msmt,
        wave=replace(msmt.wave, time_s=time_s, v=voltage, i={"vdd": np.zeros((3, 3))}),
    )
    assert msmt.wave is not None
    timing = analyze_comp_timing([msmt])
    # Clock crosses at 1 ns, where the differential output is 0.25 V.
    # Its 1% band starts at 0.9925 V, reached at 3.97 ns.
    np.testing.assert_allclose(timing.clock_to_decision_s, 1e-9)
    np.testing.assert_allclose(timing.settling_s, 2.97e-9)


def test_comp_power_time_weights_each_trial_and_preserves_stored_power() -> None:
    msmt = comparator_measurement()
    assert msmt.wave is not None
    time_s = np.asarray((0.0, 1.0, 10.0)) * 1e-9
    current = np.asarray((10.0, 20.0, -30.0))[:, None] * np.asarray((0.0, 1.0, 1.0)) * 1e-6
    msmt = replace(
        msmt,
        wave=replace(
            msmt.wave,
            time_s=time_s,
            v={name: values[:, :3] for name, values in msmt.wave.v.items()},
            i={"vdd": current},
        ),
    )
    assert msmt.wave is not None
    # The ramp occupies 1 ns and the plateau 9 ns: each rectified mean
    # is 95% of its plateau, then the three trial powers are averaged.
    power = analyze_comp_power([msmt])
    assert power.average_power_w[0] == pytest.approx(22.8e-6)
    msmt = replace(msmt, info=replace(msmt.info, readbacks={"vdd_active_average_power_w": 77e-6}))
    assert msmt.wave is not None
    assert analyze_comp_power([msmt]).average_power_w[0] == pytest.approx(77e-6)


def test_comp_candidate_sweep_reuses_metrics_and_orders_by_total_active_area() -> None:
    base = comparator_measurement()
    inputs = np.repeat(np.linspace(-2e-3, 2e-3, 5), 100)
    decisions = np.concatenate(
        [
            np.concatenate((np.ones(ones, dtype=np.uint8), np.zeros(100 - ones, dtype=np.uint8)))
            for ones in (0, 25, 50, 75, 100)
        ]
    )
    daq = {
        "trial_index": np.arange(len(inputs)),
        "vin_diff_v": inputs,
        "vin_cm_v": np.full(len(inputs), 0.8),
        "decision": decisions,
    }

    def candidate(candidate_id: str, width: int, area: int) -> MeasComp:
        return replace(
            base,
            info=replace(
                base.info,
                readbacks={
                    "vdd_v": 1.2,
                    "vdd_active_average_power_w": width * 1e-9,
                    "energy_per_decision_j": width * 40e-18,
                    "candidate_id": candidate_id,
                    "candidate_label": candidate_id,
                    "topology_index": width,
                    "size_profile": "half",
                    "total_width_units": width,
                    "device_width_signature": f"M0:{width}",
                    "total_active_area_units": area,
                    "total_active_area_um2": area * 0.0072,
                    "device_geometry_signature": f"M0:{width}:{area}",
                },
            ),
            **daq,
        )

    candidates = []
    for measurement in (
        candidate("larger-area", width=100, area=200),
        candidate("smaller-area", width=200, area=100),
    ):
        candidates.append(
            analyze_comp_candidate(
                measurement,
                offset=analyze_comp_offset_noise([measurement]),
                timing=analyze_comp_timing([measurement]),
                power=analyze_comp_power([measurement]),
            )
        )
    np.testing.assert_allclose([candidate.total_active_area_um2 for candidate in candidates], [1.44, 0.72])
    np.testing.assert_allclose([candidate.average_power_w for candidate in candidates], [100e-9, 200e-9])
    assert all(candidate.validity == "valid" for candidate in candidates)
    np.testing.assert_allclose([candidate.maximum_settling_s for candidate in candidates], 30e-9)
    assert [candidate.total_width_units for candidate in candidates] == [100, 200]


def test_comp_candidate_rejects_a_prior_result_of_another_design() -> None:
    measurement = comparator_measurement()
    other_params = replace(measurement.param, comp=replace(measurement.param.comp, tail_w=99))
    other = replace(measurement, dut=other_params.comp, param=other_params)
    with pytest.raises(ValueError, match="does not match"):
        analyze_comp_candidate(
            measurement,
            offset=analyze_comp_offset_noise([other]),
            timing=analyze_comp_timing([measurement]),
            power=analyze_comp_power([measurement]),
        )


def test_delay_maps_resolved_trials_onto_the_swept_inputs() -> None:
    measurement = comparator_measurement()
    delay = analyze_comp_delay([measurement], timing=analyze_comp_timing([measurement]))
    np.testing.assert_allclose(delay.vin_cm_v, [0.6])
    np.testing.assert_allclose(delay.vin_diff_v, [-1e-3, 0.0, 1e-3])
    # the middle trial never resolves, the outer two decide 2 ns after the clock
    np.testing.assert_allclose(delay.delay_s[0], [2e-9, np.nan, 2e-9], atol=20e-12)


def test_characterization_plots_render(tmp_path: Path) -> None:
    measurement = comparator_measurement()
    delay = analyze_comp_delay([measurement], timing=analyze_comp_timing([measurement]))
    offset = analyze_comp_offset_noise([measurement])
    common_mode = analyze_comp_common_mode([measurement], offsets=[offset])
    power = analyze_comp_power([measurement])
    paths = (
        *plot_comp_delay([delay, delay], labels=["a", "b"], output_path=tmp_path / "delay"),
        *plot_comp_common_mode([delay], [common_mode], labels=["a"], output_path=tmp_path / "common_mode"),
        *plot_comp_energy([power], [common_mode], labels=["a"], output_path=tmp_path / "energy"),
    )
    assert paths and all(path.exists() for path in paths)
