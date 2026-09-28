"""SAR weight-redundancy calculation and plotting contracts."""

from pathlib import Path

import numpy as np
import pytest

from flow.adc.behavioral import SAR_ADC
from flow.analysis.plots import plot_adc_redundancy
from flow.caparray.subckt import CapArrayConfig, RedunStrat, get_caparray_weights


def test_redundancy_calculator(tmp_path: Path) -> None:
    margins = SAR_ADC.calculate_redundancy((4, 3, 2, 1))
    assert margins.tolist() == pytest.approx((20.0, 0.0, -100 / 3))
    with pytest.raises(ValueError, match="positive SAR weights"):
        SAR_ADC.calculate_redundancy((4, 0, 1))
    (path,) = plot_adc_redundancy(margins, output_path=tmp_path / "single")
    assert path.read_bytes().startswith(b"%PDF")


def test_14_bit_weight_comparison(tmp_path: Path) -> None:
    binary = tuple(2**bit for bit in range(13, -1, -1))
    redistributed_18 = tuple(
        get_caparray_weights(CapArrayConfig(n_dac=14, n_extra=4, redun_strat=RedunStrat.SUBRDX2_OVLY))
    )
    redistributed_20 = tuple(
        get_caparray_weights(CapArrayConfig(n_dac=14, n_extra=6, redun_strat=RedunStrat.SUBRDX2_OVLY))
    )
    assert tuple(map(len, (binary, redistributed_18, redistributed_20))) == (14, 18, 20)
    assert tuple(map(sum, (binary, redistributed_18, redistributed_20))) == (16383,) * 3
    binary_margin = SAR_ADC.calculate_redundancy(binary)
    redistributed_18_margin = SAR_ADC.calculate_redundancy(redistributed_18)
    redistributed_20_margin = SAR_ADC.calculate_redundancy(redistributed_20)
    assert np.all(binary_margin < 0)
    assert np.all(redistributed_18_margin[:14] > 0)
    assert np.all(redistributed_20_margin[:16] > 0)

    (path,) = plot_adc_redundancy(
        {
            "14-bit binary": binary_margin,
            "14-bit redistributed (18 stages)": redistributed_18_margin,
            "14-bit redistributed (20 stages)": redistributed_20_margin,
        },
        output_path=tmp_path / "redundancy",
    )
    assert path.name == "redundancy.pdf"
    assert path.read_bytes().startswith(b"%PDF")
