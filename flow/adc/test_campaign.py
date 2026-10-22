"""The ADC campaign declares every capture its figures need, for any testbench builder."""

import hdl21 as h

from flow.adc.campaign import (
    FIN_CYCLES,
    FIN_RATES_HZ,
    MISMATCH_COEFFICIENTS,
    RATES_HZ,
    TAU_SCALES,
    UNIT_MISMATCH,
    VALIDATION_DRAWS,
    campaign,
)
from flow.adc.figures import FIGURES


def test_the_campaign_has_every_capture_the_figures_read() -> None:
    def tb(*, conversions, rate_hz, vin_diff):
        return {"conversions": conversions, "rate_hz": rate_hz, "vin_diff": vin_diff}

    captures = campaign(tb, 0.7)
    names = set(captures)
    assert {"ramp_train", "ramp_check", "trajectory", "noise"} <= names
    assert sum(name.startswith("rate_") for name in names) == len(RATES_HZ)
    assert sum(name.startswith("fin_") for name in names) == len(FIN_RATES_HZ) * len(FIN_CYCLES)
    assert sum(name.startswith("dc_") for name in names) == 33
    # one capacitor draw for both ramps, independent noise: the calibration's training and check
    train, check = captures["ramp_train"], captures["ramp_check"]
    assert train.seed == check.seed and train.unit_mismatch == check.unit_mismatch == UNIT_MISMATCH
    assert train.noise_seed != check.noise_seed
    # sines at -0.5 dBFS of the full scale, DC inputs across it
    assert abs(captures["rate_10"].tb["vin_diff"].vamp - 0.7 * 10 ** (-0.5 / 20)) < 1e-9
    assert isinstance(captures["dc_00"].tb["vin_diff"], h.Vdc.Params)
    assert captures["dc_00"].tb["vin_diff"].dc == -0.7 and captures["dc_32"].tb["vin_diff"].dc == 0.7
    assert next(iter(FIGURES)) == "redundancy" and {"noise_input", "hsu_map", "hsu_rate", "hsu_fastest"} <= set(FIGURES)
    # the noise over the input, and Hsu's study: every rate at every settling scale, and at each rate
    # a reference with ideal timing at the same rate
    assert "noise_input" in names
    hsu = [name for name in names if name.startswith("hsu_r") and "_t" in name]
    references = [name for name in names if name.startswith("hsu_reference_r")]
    assert len(hsu) == len(RATES_HZ) * len(TAU_SCALES) and len(references) == len(RATES_HZ)
    for index, rate in enumerate(RATES_HZ):
        reference = captures[f"hsu_reference_r{index}"]
        assert reference.tb["rate_hz"] == rate == captures[f"hsu_r{index}_t0"].tb["rate_hz"]
        assert reference.tau_scale == 0.0 and "comparator" in reference.quiet
    # the mismatch is predicted, not drawn: the Monte Carlo that checks it only where asked for
    assert not any(name.startswith("mc_") for name in names)
    assert {"mismatch_weight_sigma", "mismatch_transition_sigma", "mismatch_margin"} <= set(FIGURES)
    drawn = campaign(tb, 0.7, mismatch_draws=VALIDATION_DRAWS)
    studies = [capture for name, capture in drawn.items() if name.startswith("mc_")]
    assert len(studies) == len(MISMATCH_COEFFICIENTS) * VALIDATION_DRAWS and all(c.noise_free for c in studies)
    assert {c.unit_mismatch for c in studies} == set(MISMATCH_COEFFICIENTS)
