"""The CDAC model from its characterization record, and the ADC model settling by it."""

from types import SimpleNamespace

import numpy as np
import pytest

from flow.adc.behavioral import CompBehavioralParams, SampBehavioralParams, calc_ideal_capacitances
from flow.adc.sim import AdcTbParams
from flow.capdriver.subckt import CapDriverParams

from . import model as cdac_model
from .subckt import CdacParams
from .sweep import CdacSettling

TB = AdcTbParams()
SETTLING = CdacSettling(
    dac=CdacParams(driver=CapDriverParams(n_stages=2), main_f=(2e-13, 1e-13), diff_f=(0.0, 0.0), parasitic_f=1e-13),
    adc_bits=3,
)


def _record(stages: int) -> dict:
    return {
        "metrics": {"lsb_v": 1e-3},
        "details": [
            {"name": "settling_stage", "series": {"settling": [1e-9 * (stages - k) for k in range(stages)]}},
            {
                "name": "model_stage",
                "series": {"delay": [50e-12] * stages, "time constant": [1e-10 * (k + 1) for k in range(stages)]},
            },
        ],
    }


def test_the_model_reads_its_record_by_the_adcs_array_and_resolution(monkeypatch):
    asked = {}

    def settling_params(pdk, config, adc_bits, cells):
        asked.update(pdk=pdk, config=config, adc_bits=adc_bits)
        return SETTLING

    monkeypatch.setattr(cdac_model, "settling_params", settling_params)
    monkeypatch.setattr(cdac_model, "characterized", lambda block, pdk, params, simulate: _record(2))
    adc = SimpleNamespace(cdac="the array", adc_bits=11)
    model = cdac_model.CdacModel.of("tsmc65", adc)
    assert asked == {"pdk": "tsmc65", "config": "the array", "adc_bits": 11}
    assert model.tau_s == (1e-10, 2e-10) and model.delay_s == (50e-12, 50e-12) and model.lsb_v == 1e-3
    cdac_model.CdacModel.of("tsmc65", "the array", 9)
    assert asked["adc_bits"] == 9
    with pytest.raises(ValueError):
        cdac_model.CdacModel.of("tsmc65", "the array")


def test_the_adc_settles_each_stage_by_its_characterization_and_falls_back_to_rc():
    from flow.adc.model import AdcModel

    main_f, diff_f = calc_ideal_capacitances(TB.dut.cdac)
    stages = len(main_f)
    settling = SimpleNamespace(tau_s=tuple(1e-10 * (k + 1) for k in range(stages)), delay_s=(30e-12,) * stages)
    blocks = {
        "pdk": "none",
        "params": TB.dut,
        "comp": SimpleNamespace(behavioral=lambda vin_cm_v: CompBehavioralParams()),
        "samp": SimpleNamespace(behavioral=lambda load_f: SampBehavioralParams()),
        "cdac": SimpleNamespace(
            draw=lambda unit_mismatch, rng: (main_f, diff_f),
            parasitic_f=0.0,
            main_f=main_f,
            diff_f=diff_f,
            load_f=float(np.sum(main_f) + np.sum(diff_f)),
        ),
        "drivers": tuple(SimpleNamespace(resistance_ohm=1.0, intrinsic_delay_s=20e-12, energy_j=0.0) for _ in main_f),
    }
    spice = AdcModel(**blocks, settling=settling)
    assert spice.stage_tau_s == settling.tau_s and spice.settling_tau_s == settling.tau_s[-1]
    cdac = spice.behavioral(TB, quiet=("comparator",), tau_scale=2.0).cdac
    np.testing.assert_allclose(cdac.stage_tau_s, 2 * np.asarray(settling.tau_s))
    assert cdac.stage_delay_s == settling.delay_s  # the delay does not scale
    assert not any(spice.behavioral(TB, quiet=("comparator",), tau_scale=0.0).cdac.stage_delay_s)
    rc = AdcModel(**blocks)
    assert rc.stage_delay_s == (20e-12,) * stages
    assert rc.stage_tau_s != spice.stage_tau_s
