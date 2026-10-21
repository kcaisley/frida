"""The ADC campaign declares every capture its figures need, for any testbench builder."""

import hdl21 as h

from flow.adc.campaign import FIN_CYCLES, FIN_RATES_HZ, RATES_HZ, UNIT_MISMATCH, campaign
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
    assert len(FIGURES) == 12
