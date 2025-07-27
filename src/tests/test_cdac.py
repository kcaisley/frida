import pytest
from cdac import generate_weights

def test_generate_weights_case1():
    n_dac = 11
    n_redist = 8
    w_regroup = [5, 6]
    w_offset = 2
    expected_weights = [768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1]
    result, _, _ = generate_weights(n_dac, n_redist, w_regroup, w_offset)
    assert result == expected_weights