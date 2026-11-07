"""The ADC's behavioral model (its SAR loop is ``flow.adc.sim``'s, ``flow/adc/test_sim.py``): the model
on stand-in blocks and a stand-in characterization of its DAC (``Model.behavioral``, ``Model.capture``),
the DAC's characterization it composes or its design where there is none (``Model.of``), and the
reference buffer's requirements it sets (``Model.reference_requirements``)."""

import importlib
import math
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import flow.capdac.model as capdac_model
import flow.comp.model as comp_model
import flow.samp.model as samp_model
from flow import capdac
from flow.adc.model import Model, _enob_floor
from flow.adc.params import (
    DECAP_COVERAGE,
    DRAWN_PERCENTILE,
    DRAWN_RUN,
    REFERENCE_QUIET,
    REFERENCE_SHARE,
    Params,
    Quiet,
    Recipe,
    TbParams,
)
from flow.adc.plots import plot_reference_noise, plot_reference_r_out

TB = TbParams(pdk="tsmc65", params=Params(adc_bits=12, cdac=capdac.Params())).sequenced(
    Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00001111.rows, symbol_rate=1.6e9
)


def _dac(params: Params, *, gain: float = 1.0, settling_meas: Path | None = None) -> capdac.Model:
    """A stand-in characterization of the converter's DAC: its plates designed at 1.2 V, its drawn
    gain, each stage's driver 20 ps late and its step settling with a time constant of its own, one
    side's layout of 1000 um^2."""
    stages = len(capdac.Model.weights(params.cdac))
    return capdac.Model(
        pdk="none",
        params=params.cdac,
        reference_v=1.2,
        settling_s=(300e-12,) * stages,
        delay_s=(20e-12,) * stages,
        tau_s=tuple(10e-12 * (stage + 1) for stage in range(stages)),
        lsb_v=1e-3,
        gain=gain,
        area_um2=1000.0,
        settling_meas=settling_meas,
    )


class _Model(Model):
    """The model in a PDK of a 1.2 V supply, without its kit."""

    supply_v = 1.2


def _stand_in(dac: capdac.Model) -> Model:
    """The model on stand-in blocks: a comparator and a sampler of known impairments, and ``dac``."""
    return _Model(
        pdk="none",
        params=TB.params,
        comp=SimpleNamespace(
            behavioral=lambda vin_cm_v: comp_model.Model.Behavioral(
                noise_v=1e-4, delay_table_v=(1e-6, 1e-3), delay_table_s=(200e-12, 50e-12)
            )
        ),
        samp=SimpleNamespace(
            behavioral=lambda load_f: samp_model.Model.Behavioral(
                noise_v=1e-4, jitter_s=2e-12, ron_table_v=(0.2, 1.0), ron_table_ohm=(100.0, 300.0)
            )
        ),
        cdac=dac,
    )


def test_the_model_switches_its_dacs_design_plates_as_characterized() -> None:
    """The DAC's plates are its design's at its reference, its top plates loaded beyond them by the
    parasitic of its drawn gain; its delays and time constants are its characterization's, and its
    drivers draw no energy. The full scale is the switched plates' share of that load; a capture's
    extracted weights name the measurement the DAC's settling run keeps, none where it is designed."""
    main_f, diff_f = capdac.Model.plates(TB.params.cdac, 1.2)
    model = _stand_in(_dac(TB.params, gain=0.8, settling_meas=Path("/runs/settling/result.h5")))
    dac = model.behavioral(TB).cdac
    assert dac.main_p_f == dac.main_n_f == tuple(main_f) and dac.diff_p_f == dac.diff_n_f == tuple(diff_f)
    plates_f = float(np.sum(main_f) + np.sum(diff_f))
    assert plates_f / (plates_f + dac.parasitic_f) == pytest.approx(0.8, rel=1e-12)
    assert model.load_f == pytest.approx(plates_f / 0.8, rel=1e-12)
    assert model.full_scale_v == pytest.approx(1.2 * 0.8 * float(np.sum(main_f - diff_f)) / plates_f, rel=1e-12)
    assert dac.stage_tau_s == model.stage_tau_s == model.cdac.tau_s and dac.settling_tau_s == model.cdac.tau_s[-1]
    assert dac.stage_delay_s == model.stage_delay_s == (20e-12,) * len(main_f)
    assert dac.driver_energy_j == 0.0 and dac.driver_static_w == 0.0
    tb = TbParams(**{**TB.__dict__, "conversions": 4})
    assert model.capture(tb, None).info.readbacks["cap_table"] == "/runs/settling/result.h5"
    assert _stand_in(_dac(TB.params)).capture(tb, None).info.readbacks["cap_table"] == ""


def test_the_model_converts_on_its_dacs_array_as_drawn() -> None:
    """A DAC whose measured steps are not its design's (a unit drawn other than designed, at the
    PDK's smallest): its top plate's load is the design's plates at the drawn gain, and each stage's
    switched plate gives its measured step at that load (each side half the differential step), so
    the steps the conversion switches are the decoding's extracted weights and the full scale is
    half their sum; a Pelgrom draw is of the design's plates, as the DAC's Monte Carlo draws them,
    and drawn so too."""
    main_f, diff_f = capdac.Model.plates(TB.params.cdac, 1.2)
    plates_f = float(np.sum(main_f + diff_f))
    # the design's steps at a gain of 0.8, the last stage drawn three times as heavy, the first 2 %
    # light
    steps = 2 * 1.2 * 0.8 * (main_f - diff_f) / plates_f
    steps[-1] *= 3.0
    steps[0] *= 0.98
    model = _stand_in(replace(_dac(TB.params, gain=0.8), step_v=tuple(steps)))
    dac = model.behavioral(TB).cdac
    switched = np.asarray(dac.main_p_f) - np.asarray(dac.diff_p_f)
    assert dac.main_n_f == dac.main_p_f and dac.diff_p_f == dac.diff_n_f == tuple(diff_f)
    assert model.load_f == pytest.approx(plates_f / 0.8, rel=1e-12)
    np.testing.assert_allclose(2 * 1.2 * switched / model.load_f, steps, rtol=1e-12)
    assert model.full_scale_v == pytest.approx(steps.sum() / 2, rel=1e-12)
    rng = np.random.default_rng(7)
    expected = [capdac.Model.draw(plate, pelgrom=0.01, rng=rng) for _side in "pn" for plate in (main_f, diff_f)]
    seeded = model.behavioral(replace(TB, mismatch_seed=7, unit_mismatch=0.01)).cdac
    excess_f = np.asarray(dac.main_p_f) - main_f
    np.testing.assert_allclose(seeded.main_p_f, expected[0] + excess_f, rtol=1e-12)
    np.testing.assert_allclose(seeded.main_n_f, expected[2] + excess_f, rtol=1e-12)
    assert (seeded.diff_p_f, seeded.diff_n_f) == (tuple(expected[1]), tuple(expected[3]))


def test_the_model_quiets_each_source_alone_and_scales_the_settling() -> None:
    main_f, diff_f = capdac.Model.plates(TB.params.cdac, float(TB.vdd_dac.dc))
    model = _stand_in(_dac(TB.params))
    # the DAC's SPICE draw where a capture asks for it, the nominal plates where none is characterized
    heavy = (main_f * 1.01, diff_f)
    drawn = replace(model, drawn=(heavy, (main_f, diff_f))).behavioral(replace(TB, drawn=True)).cdac
    assert drawn.main_p_f == tuple(heavy[0]) and drawn.main_n_f == tuple(main_f)
    assert model.behavioral(replace(TB, drawn=True)).cdac.main_p_f == tuple(main_f)
    # a Pelgrom draw from the seed, the P side's main and difference plates, then the N side's;
    # none without mismatch, which takes nothing from the seed's stream
    rng = np.random.default_rng(7)
    expected = [capdac.Model.draw(plate, pelgrom=0.01, rng=rng) for _side in "pn" for plate in (main_f, diff_f)]
    seeded = model.behavioral(replace(TB, mismatch_seed=7, unit_mismatch=0.01)).cdac
    assert [seeded.main_p_f, seeded.diff_p_f, seeded.main_n_f, seeded.diff_n_f] == [tuple(e) for e in expected]
    assert model.behavioral(replace(TB, mismatch_seed=7)).cdac.main_p_f == tuple(main_f)
    # the reference is ideal unless one is given (the reference study's)
    ideal = model.behavioral(TB).cdac
    assert ideal.reference_r_ohm == ideal.reference_c_f == ideal.reference_noise_v == 0.0
    given = model.behavioral(replace(TB, reference_r_ohm=3.0, reference_c_f=200e-12, reference_noise_v=1e-4)).cdac
    assert (given.reference_r_ohm, given.reference_c_f, given.reference_noise_v) == (3.0, 200e-12, 1e-4)
    # the comparator's noise alone: its delay stays, so a late decision still holds
    noiseless = model.behavioral(replace(TB, quiet=frozenset({Quiet.COMPARATOR_NOISE}))).comp
    assert noiseless.noise_v == 0.0 and noiseless.delay_table_v == (1e-6, 1e-3)
    ideal = model.behavioral(replace(TB, quiet=frozenset({Quiet.COMPARATOR}))).comp
    assert ideal.noise_v == 0.0 and ideal.delay_table_v is None
    # a perfect track-and-hold: no on-resistance (so no tracking lag), its noise and jitter kept
    sampler = model.behavioral(replace(TB, quiet=frozenset({Quiet.SAMPLER}))).samp
    assert sampler.ron_table_v is None and sampler.n_conductance_s_per_v == sampler.p_conductance_s_per_v == 0.0
    assert sampler.noise_v == 1e-4 and sampler.jitter_s == 2e-12
    resistance = samp_model.Model.resistance(TB.params.samp, sampler, np.asarray([0.2, 0.6, 1.0]), 1.2)
    assert not np.any(resistance)
    quiet = model.behavioral(replace(TB, quiet=frozenset({Quiet.SAMPLING}))).samp
    assert quiet.noise_v == quiet.jitter_s == 0.0 and quiet.ron_table_v == (0.2, 1.0)
    with pytest.raises(ValueError, match="quiet takes Quiet members"):
        replace(TB, quiet=frozenset({"samplers"}))
    # the settling time constants scale, the drivers' delays do not; at 0 settling is ideal, the
    # drivers' delay gone too
    nominal, slower = model.behavioral(TB).cdac, model.behavioral(replace(TB, tau_scale=4.0)).cdac
    np.testing.assert_allclose(slower.stage_tau_s, 4 * np.asarray(nominal.stage_tau_s))
    assert slower.stage_delay_s == nominal.stage_delay_s == (20e-12,) * len(main_f)
    settled = model.behavioral(replace(TB, tau_scale=0.0)).cdac
    assert not any(settled.stage_tau_s) and not any(settled.stage_delay_s) and settled.settling_tau_s == 0.0


def test_the_model_composes_its_dacs_characterization_or_else_its_design(monkeypatch: pytest.MonkeyPatch) -> None:
    """``Model.of``: the DAC's characterization of the same parameters, looked up and never
    simulated, and its Monte Carlo draw the converter calibrates on (``DRAWN_RUN`` at
    ``DRAWN_PERCENTILE``); where there is none, the DAC as designed and its draws nominal, each with
    a warning."""
    asked = []
    characterized = _dac(TB.params, gain=0.8)
    main_f, diff_f = capdac.Model.plates(TB.params.cdac, 1.2)
    draw = ((main_f, diff_f), (main_f, diff_f))

    def of(cls, pdk, params, *, simulate=True):
        asked.append(("of", pdk, params, simulate))
        return characterized

    def drawn(cls, pdk, params, run, percentile):
        asked.append(("drawn", pdk, params, run, percentile))
        return draw

    monkeypatch.setattr(capdac.Model, "of", classmethod(of))
    monkeypatch.setattr(capdac.Model, "drawn", classmethod(drawn))
    for block in (comp_model, samp_model):
        monkeypatch.setattr(block.Model, "of", classmethod(lambda cls, pdk, params, *, simulate=True: None))
    model = Model.of("tsmc65", TB.params)
    assert model.cdac is characterized and model.drawn is draw
    assert asked == [
        ("of", "tsmc65", TB.params.cdac, False),
        ("drawn", "tsmc65", TB.params.cdac, DRAWN_RUN, DRAWN_PERCENTILE),
    ]

    def missing(cls, *args, **kwargs):
        raise LookupError("not characterized")

    monkeypatch.setattr(capdac.Model, "of", classmethod(missing))
    monkeypatch.setattr(capdac.Model, "drawn", classmethod(missing))
    monkeypatch.setattr(capdac_model, "_supply_v", lambda pdk: 1.2)
    with pytest.warns(UserWarning) as warned:
        designed = Model.of("tsmc65", TB.params)
    assert [str(warning.message).split(" (")[0] for warning in warned] == [
        "the DAC is not characterized",
        "the DAC's Monte Carlo is not characterized",
    ]
    assert designed.cdac == capdac.Model.design("tsmc65", TB.params.cdac) and designed.drawn is None
    assert designed.cdac.gain == 1.0 and designed.cdac.settling_meas is None

    # a record whose kept settling run (or Monte Carlo) cannot be read converts as designed too
    def unreadable(cls, *args, **kwargs):
        raise FileNotFoundError("build/capdac/run/tsmc65/digest/settling/result.h5")

    monkeypatch.setattr(capdac.Model, "of", classmethod(unreadable))
    monkeypatch.setattr(capdac.Model, "drawn", classmethod(unreadable))
    with pytest.warns(UserWarning) as warned:
        unread = Model.of("tsmc65", TB.params)
    assert [str(warning.message).split(" (")[0] for warning in warned] == [
        "the DAC is not characterized",
        "the DAC's Monte Carlo is not characterized",
    ]
    assert unread.cdac == designed.cdac and unread.drawn is None


def test_an_error_of_the_quantization_noise_costs_an_ideal_quantizer_half_a_bit() -> None:
    assert _enob_floor(12, 12.0) == pytest.approx(11.5)
    assert _enob_floor(12, 12.0, REFERENCE_SHARE) == pytest.approx(12 - 0.5 * math.log2(1 + REFERENCE_SHARE))
    # a converter already far from its resolution loses less of it to the same error
    assert 0 < 11.0 - _enob_floor(12, 11.0) < 0.5 - 1e-3


def test_the_decoupling_is_the_decap_share_of_both_dac_sides_to_one_figure(monkeypatch) -> None:
    pdk = SimpleNamespace(pdk_logic=SimpleNamespace(DECAP_FF_PER_UM2=4.0))
    monkeypatch.setattr(importlib, "import_module", lambda name: pdk)
    # both sides' 2000 um^2 at 4 fF/um^2, 30 % of it: 2.4 pF, to one figure
    assert DECAP_COVERAGE == 0.30
    # the property of a stand-in model: its PDK and one side's layout area, its drivers with it;
    # none where the DAC is not laid out
    decoupling_f = Model.decoupling_f.fget
    assert decoupling_f(SimpleNamespace(pdk="any", cdac=SimpleNamespace(area_um2=1000.0))) == 2e-12
    assert math.isnan(decoupling_f(SimpleNamespace(pdk="any", cdac=SimpleNamespace(area_um2=0.0))))
    assert math.isnan(decoupling_f(SimpleNamespace(pdk="any", cdac=SimpleNamespace(area_um2=math.nan))))


def test_each_requirement_is_where_its_loss_reaches_its_share_of_the_quantization_noise(monkeypatch) -> None:
    """A stand-in converter whose added error power grows as the square of the reference's noise
    and of its driver's time constant over 1 ns: each requirement lands within the search's
    resolution of the analytic one, and each figure is the loss over its grid."""
    bits, enob_bits = 12, 11.0
    lsb2 = 1.0 / 12  # the quantization noise power, in LSB^2

    def measured(tb: TbParams) -> float:
        # an ideal reference gives the converter's own ENOB
        error = (tb.reference_noise_v / 100e-6) ** 2 + (tb.reference_r_ohm * tb.reference_c_f / 1e-9) ** 2
        return bits - 0.5 * math.log2(2.0 ** (2 * (bits - enob_bits)) + error / lsb2)

    monkeypatch.setattr("flow.adc.model._enob", measured)
    quiets = set()

    def converted(tb, path) -> TbParams:
        quiets.add(tb.quiet)
        return tb

    # a stand-in model: its resolution, its capture and its decoupling
    model = SimpleNamespace(params=SimpleNamespace(adc_bits=bits), capture=converted, decoupling_f=1e-12)
    reference = Model.reference_requirements(model, TB)
    # every point on the DAC alone: the sampler and the comparator ideal
    assert quiets == {REFERENCE_QUIET}
    # the error may reach REFERENCE_SHARE of the quantization noise power: (x / x0)^2 = REFERENCE_SHARE / 12
    within = math.sqrt(REFERENCE_SHARE * lsb2)
    assert reference.noise_max_v == pytest.approx(100e-6 * within, rel=0.05)
    assert reference.noise_max_v <= 100e-6 * within
    assert reference.r_max_ohm == pytest.approx(1e3 * within, rel=0.05)
    assert reference.decap_f == 1e-12
    assert reference.enob_loss_max_bits == pytest.approx(enob_bits - _enob_floor(bits, enob_bits, REFERENCE_SHARE))
    details = [plot_reference_noise(reference), plot_reference_r_out(reference)]
    assert [plot.name for plot in details] == ["reference_noise", "reference_r_out"]
    losses = details[0].series["ENOB loss"]
    assert losses == sorted(losses) and losses[0] == pytest.approx(0.0, abs=1e-3)
