"""The KLayout-PEX extractor's own pieces that need no PDK: a kit's stack read from its ICT file, and
the permittivity of the dielectrics between two heights."""

from pathlib import Path

import pytest

from flow.layout import kpex

ICT = """
dielectric "field" {
        height              0
        thickness           0.4
        dielectric_constant 4.0
}
conductor "poly" {
        height              0.4
        thickness           0.2
}
dielectric "low" {
        thickness           0.6
        dielectric_constant 3.0
}
conductor "m1" {
        thickness           0.3
}
dielectric "cap" {
        conformal           TRUE
        thickness           0.05
        dielectric_constant 7.0
}
dielectric "high" {
        thickness           0.5
        dielectric_constant 6.0
}
conductor "m2" {
        delta_height        0.2
        delta_layer         m1
        thickness           0.4
}
"""


def test_a_kits_stack_places_each_conductor(tmp_path: Path) -> None:
    """A height where the file gives one; else a dielectric stacks on the planar ones before it, a
    conductor sits in the last of them, its top at theirs; or its ``delta_height`` above its
    ``delta_layer``. A conformal film is left out."""
    path = tmp_path / "stack.ict"
    path.write_text(ICT)
    stack = kpex.stack_from_ict(path, {"PO": "poly", "M1": "m1", "M2": "m2"})
    assert stack["conductors"] == {
        "PO": {"z": 0.4, "thickness": 0.2},
        "M1": {"z": 0.7, "thickness": 0.3},  # the top of "low", 1.0, less its thickness
        "M2": {"z": 1.2, "thickness": 0.4},  # 0.2 above m1's top
    }
    assert stack["dielectrics"] == [(0.0, 0.4, 4.0), (0.4, 1.0, 3.0), (1.0, 1.5, 6.0)]


def test_the_dielectrics_between_two_heights_are_in_series_across_and_in_parallel_along() -> None:
    slabs = [[0.0, 1.0, 2.0], [1.0, 2.0, 4.0]]
    assert kpex._k(slabs, 0.0, 2.0) == pytest.approx(2 / (1 / 2.0 + 1 / 4.0))
    assert kpex._k(slabs, 0.5, 1.0) == pytest.approx(2.0)
    # along them (a lateral field): their mean by thickness
    assert kpex._k(slabs, 0.0, 2.0, along=True) == pytest.approx(3.0)
    # beyond every slab: the nearest one's
    assert kpex._k(slabs, 3.0, 4.0) == pytest.approx(4.0)
