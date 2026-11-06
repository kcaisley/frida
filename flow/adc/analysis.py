"""The ADC's analyses: pure functions of its captures and of earlier results (no file I/O). The
redundancy of a SAR's weights (``_redundancy_margins``, after Ogawa et al.) grades each stage's error
tolerance, for the figures (``flow.adc.figures``) and the mismatch statistics
(``flow.adc.statistics``).
"""

from __future__ import annotations

import numpy as np


def _redundancy_margins(weights) -> np.ndarray:
    """Return each SAR stage's error tolerance as a percentage of the residue range left at it.

    T. Ogawa, H. Kobayashi, Y. Takahashi, N. Takai, M. Hotta, H. San, T. Matsuura, A. Abe,
    K. Yagi and T. Mori, "SAR ADC Algorithm with Redundancy and Digital Error Correction," IEICE
    Trans. Fundamentals, vol. E93-A, no. 2, pp. 415-423, Feb. 2010, doi:10.1587/transfun.E93.A.415.

    Their Eq. (5) defines the redundancy of step k as q(k) = -p(k+1) + 1 + sum_{i=k+2}^{M} p(i),
    and Proposition 1 shows that a wrong decision at step k still gives the right output code
    when |Vin - Vref(k)| < q(k). They count from 1: p(1) is the initial mid-scale reference, p(k+1)
    the step that decision k sets, and the +1 the last comparison's LSB. Here everything counts
    from 0: the M weights w_0 (C0, the first decision's) to w_{M-1} (the last decision's), w_k the
    step that decision k sets (+-w_k, as the CDAC switches). Their q(k+1) is then::

        q_k = sum_{j=k+1}^{M-1} w_j - w_k + w_{M-1}

    returned as 100 * q_k / sum_{j=k}^{M-1} w_j. Binary weights give 0 at every stage; a positive
    value is the dynamic error (comparator noise or metastability, incomplete DAC settling,
    reference ripple) that stage tolerates; a negative one an error band the later stages cannot
    recover. The last stage's is 0: nothing after it corrects it. The tolerance is a worst-case
    bound per stage, and every stage may err within its own at once. Static weight errors
    (capacitor mismatch) are not tolerated: they need the decoder's weights calibrated.
    """
    values = np.asarray(weights, dtype=float)
    if values.ndim != 1 or len(values) < 2 or not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("expected at least two finite, positive SAR weights in conversion order")
    remaining = np.cumsum(values[::-1])[::-1]
    # q_k = sum_{j=k+1}^{M-1} w_j - w_k + w_{M-1} (Ogawa et al. Eq. 5, counted from 0). Until
    # 2026-10-21 this was (sum_{j=k+1}^{M-1} w_j - w_k) / sum_{j=k}^{M-1} w_j for k < M-1: without
    # the w_{M-1} term every stage read w_{M-1} low, so binary weights went negative toward the LSB
    return (remaining - 2 * values + values[-1]) / remaining * 100
