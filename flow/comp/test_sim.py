"""Software-only tests for comparator simulation targets and campaigns."""

from .sim import (
    TARGETS,
    TSMC65_AREA_UNIT_UM2,
    build_candidates,
    frida65_fabricated_params,
)
from .subckt import is_valid_comp_params


def test_candidate_campaign_covers_all_topologies_and_fabricated_baseline() -> None:
    candidates = build_candidates()

    assert len(candidates) == 297
    assert len({candidate.candidate_id for candidate in candidates}) == 297
    assert sum(candidate.size_profile == "half" for candidate in candidates) == 148
    assert sum(candidate.size_profile == "double" for candidate in candidates) == 148
    assert sum(candidate.size_profile == "fabricated" for candidate in candidates) == 1
    assert all(is_valid_comp_params(candidate.comp) for candidate in candidates)

    baseline = candidates[-1]
    assert baseline.candidate_id == "frida65_fabricated_baseline"
    assert baseline.comp == frida65_fabricated_params()
    assert (
        baseline.comp.diffpair_w,
        baseline.comp.diffpair_l,
        baseline.comp.tail_w,
        baseline.comp.tail_l,
        baseline.comp.rst_w,
        baseline.comp.rst_l,
        baseline.comp.latch_on_w,
        baseline.comp.latch_on_l,
        baseline.comp.latch_init_w,
        baseline.comp.latch_init_l,
    ) == (37, 5, 5, 13, 8, 1, 25, 6, 33, 17)
    assert baseline.total_width_units == sum(width for _name, width in baseline.device_width_signature)
    assert baseline.total_active_area_units == sum(
        width * length for _name, width, length in baseline.device_geometry_signature
    )
    assert baseline.total_active_area_um2 == baseline.total_active_area_units * TSMC65_AREA_UNIT_UM2


def test_comparator_runner_exposes_separate_artifact_and_campaign_targets() -> None:
    assert set(TARGETS) == {
        "frida65_baseline_netlist",
        "frida65_candidate_netlists",
        "frida65_candidate_smoke",
        "frida65_baseline_noise",
        "frida65_candidates",
    }
