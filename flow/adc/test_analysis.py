"""The ADC's analyses: the redundancy of a SAR's weights, each scheme's at every resolution."""

from pathlib import Path

import numpy as np
import pytest

from flow.adc.analysis import _redundancy_margins
from flow.analysis.plots import plot_adc_redundancy
from flow.cdac.caparray.subckt import CapArrayConfig, RedunStrat, get_caparray_weights


def test_redundancy_calculator(tmp_path: Path) -> None:
    # q_k = sum_{j=k+1}^{M-1} w_j - w_k + w_{M-1} over sum_{j=k}^{M-1} w_j (Ogawa et al., IEICE 2010, Eq. 5)
    margins = _redundancy_margins((4, 3, 2, 1))
    assert margins.tolist() == pytest.approx((30.0, 100 / 6, 0.0, 0.0))
    # binary weights tolerate nothing; one more LSB decision tolerates one LSB weight at each stage
    assert _redundancy_margins((8, 4, 2, 1)).tolist() == pytest.approx((0.0,) * 4)
    assert _redundancy_margins((8, 4, 2, 1, 1)).tolist() == pytest.approx((6.25, 12.5, 25.0, 50.0, 0.0))
    with pytest.raises(ValueError, match="positive SAR weights"):
        _redundancy_margins((4, 0, 1))
    (path,) = plot_adc_redundancy(margins, output_path=tmp_path / "single")
    assert path.read_bytes().startswith(b"%PDF")


def test_14_bit_weight_comparison(tmp_path: Path) -> None:
    binary = tuple(2**bit for bit in range(13, -1, -1))
    redistributed_18 = tuple(
        get_caparray_weights(CapArrayConfig(n_dac=14, n_extra=4, redun_strat=RedunStrat.MSB_REDIST))
    )
    redistributed_20 = tuple(
        get_caparray_weights(CapArrayConfig(n_dac=14, n_extra=6, redun_strat=RedunStrat.MSB_REDIST))
    )
    assert tuple(map(len, (binary, redistributed_18, redistributed_20))) == (14, 18, 20)
    assert tuple(map(sum, (binary, redistributed_18, redistributed_20))) == (16383,) * 3
    binary_margin = _redundancy_margins(binary)
    redistributed_18_margin = _redundancy_margins(redistributed_18)
    redistributed_20_margin = _redundancy_margins(redistributed_20)
    assert np.allclose(binary_margin, 0.0)
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


def ideal_sar_codes(weights: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Every code's centre converted by an ideal top-plate SAR on ``weights``: the free first
    comparison, each capacitor's step both ways, the comparison after the last; the codes it gives."""
    codes = np.arange(2 * sum(weights) + 2)
    residue = codes + 0.5 - len(codes) / 2
    found = np.zeros_like(codes)
    for weight in weights:
        decision = residue > 0
        found += decision * 2 * weight
        residue = residue - np.where(decision, weight, -weight)
    return codes, found + (residue > 0)


@pytest.mark.parametrize("bits", (10, 11, 12, 13, 14))
def test_every_scheme_reaches_every_code(bits: int) -> None:
    # the decisions' weights of an N-bit converter on its N-1-step DAC: each capacitor's step both
    # ways, then the comparison after the last one switches
    arrays = [CapArrayConfig(n_dac=bits - 1, n_extra=0, redun_strat=RedunStrat.BINARY)] + [
        CapArrayConfig(n_dac=bits - 1, n_extra=extra, redun_strat=scheme)
        for scheme in (RedunStrat.MSB_SPLIT, RedunStrat.LSB_SPLIT, RedunStrat.MSB_REDIST)
        for extra in range(1, 7)
    ]
    for cdac in arrays:
        weights = get_caparray_weights(cdac)
        assert sum(weights) == 2 ** (bits - 1) - 1  # every scheme the binary total
        margins = _redundancy_margins((*(2 * weight for weight in weights), 1))
        # no stage's error band is lost (a negative margin would be missing codes); the split MSBs
        # and the redistribution give the free first comparison its tolerance, the split LSBs none
        assert np.all(margins >= 0.0), (bits, cdac)
        assert (margins[0] > 0.0) == (cdac.redun_strat in (RedunStrat.MSB_SPLIT, RedunStrat.MSB_REDIST)), cdac
        # and an ideal SAR on the weights converts every code to itself
        codes, found = ideal_sar_codes(weights)
        assert len(codes) == 2**bits and np.array_equal(codes, found), cdac
