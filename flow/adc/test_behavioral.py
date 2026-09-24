"""SAR weight-redundancy calculation and plotting contracts."""

from pathlib import Path

import numpy as np
import pytest

from flow.adc.behavioral import SAR_ADC
from flow.analysis.plots import plot_adc_redundancy


def test_redundancy_calculator(tmp_path: Path) -> None:
    margins = SAR_ADC.calculate_redundancy((4, 3, 2, 1))
    assert margins.tolist() == pytest.approx((20.0, 0.0, -100 / 3))
    with pytest.raises(ValueError, match="positive SAR weights"):
        SAR_ADC.calculate_redundancy((4, 0, 1))
    (path,) = plot_adc_redundancy(margins, output_path=tmp_path / "single")
    assert path.read_bytes().startswith(b"%PDF")


def test_14_bit_weight_comparison(tmp_path: Path) -> None:
    weights = {
        "14-bit binary (14 stages)": (8192, 4096, 2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4, 2, 1),
        "14-bit redistributed (18 stages)": (
            7680,
            4096,
            2176,
            1152,
            576,
            320,
            160,
            96,
            48,
            32,
            16,
            12,
            6,
            5,
            4,
            2,
            1,
            1,
        ),
        "14-bit redistributed (20 stages)": (
            7168,
            4096,
            2304,
            1280,
            640,
            384,
            192,
            128,
            64,
            48,
            24,
            20,
            10,
            9,
            4,
            4,
            4,
            2,
            1,
            1,
        ),
    }
    assert tuple(map(len, weights.values())) == (14, 18, 20)
    assert all(sum(values) == 16383 for values in weights.values())
    margins = {label: SAR_ADC.calculate_redundancy(values) for label, values in weights.items()}
    binary, redistributed_18, redistributed_20 = margins.values()
    assert np.all(binary < 0)
    assert np.all(redistributed_18[:14] > 0)
    assert np.all(redistributed_20[:16] > 0)

    (path,) = plot_adc_redundancy(margins, output_path=tmp_path / "comparison")
    assert path.read_bytes().startswith(b"%PDF")
