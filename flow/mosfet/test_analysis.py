"""MOSFET analyses and plots on a synthetic square-law device of known threshold and mismatch."""

import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo
from flow.mosfet.analysis import (
    MeasMosfetMismatch,
    MeasMosfetNoise,
    MeasMosfetOutput,
    MeasMosfetTranNoise,
    MeasMosfetTransfer,
    analyze_mosfet_mismatch,
    analyze_mosfet_noise,
    analyze_mosfet_output,
    analyze_mosfet_trannoise,
    analyze_mosfet_transfer,
)
from flow.mosfet.plots import (
    plot_mosfet_gm_id,
    plot_mosfet_mismatch,
    plot_mosfet_noise,
    plot_mosfet_output,
    plot_mosfet_simulators,
    plot_mosfet_trannoise,
    plot_mosfet_transfer,
)
from flow.mosfet.sim import MosfetTbParams

VTH, BETA, LAMBDA = 0.4, 2e-3, 0.1  # V, A/V^2, 1/V
PARAMS = MosfetTbParams(vdd=1.2, steps=120)
COMMON = {
    "group": None,
    "index": None,
    "dut": PARAMS.mosfet,
    "param": PARAMS,
    "info": MeasInfo(
        backend="spice", timestamp_utc=datetime(2026, 10, 20, tzinfo=UTC), readbacks={"w_m": 1e-6, "l_m": 1e-7}
    ),
}


def _square_law(vgs: np.ndarray, vds: float) -> np.ndarray:
    """Triode and saturation with channel-length modulation, a 1 pA floor below threshold."""
    overdrive = np.maximum(vgs - VTH, 0.0)
    triode = BETA * (overdrive - vds / 2) * vds
    saturated = BETA / 2 * overdrive**2
    return np.where(vds < overdrive, triode, saturated) * (1 + LAMBDA * vds) + 1e-12


def _transfer() -> MeasMosfetTransfer:
    vgs = np.linspace(0, PARAMS.vdd, PARAMS.steps + 1)
    return MeasMosfetTransfer(
        **COMMON,
        vgs_v=vgs,
        id_lin_a=_square_law(vgs, PARAMS.vds_lin),
        id_sat_a=_square_law(vgs, PARAMS.vdd),
    )


def test_threshold_and_currents() -> None:
    result = analyze_mosfet_transfer(_transfer())
    # a square law's linear-region tangent extrapolates to the threshold plus half of Vds, less it
    assert result.vth_v == pytest.approx(VTH, abs=0.02)
    assert result.ion_a == pytest.approx(BETA / 2 * (PARAMS.vdd - VTH) ** 2 * (1 + LAMBDA * PARAMS.vdd), rel=1e-6)
    assert result.ioff_a == pytest.approx(1e-12)
    # in strong inversion gm/Id = 2 / overdrive
    at = int(np.argmin(np.abs(result.gm_vgs_v - 0.8)))
    assert result.gm_over_id[at] == pytest.approx(2 / (result.gm_vgs_v[at] - VTH), rel=0.02)
    expected = np.interp(result.gm_vgs_v[at], result.vgs_v, result.id_sat_a) / 1e-6
    assert result.current_density_a_m[at] == pytest.approx(expected, rel=0.02)


def test_output_conductance_and_gain() -> None:
    vds = np.linspace(0, PARAMS.vdd, PARAMS.steps + 1)
    family = np.asarray(PARAMS.family) * PARAMS.vdd
    curves = np.stack([[_square_law(np.array([vgs]), v)[0] for v in vds] for vgs in family], axis=1)
    result = analyze_mosfet_output(MeasMosfetOutput(**COMMON, vds_v=vds, id_family_a=curves))
    saturated = (family - VTH < result.bias_vds_v) & (family > VTH + 0.05)
    overdrive = family[saturated] - VTH
    assert result.gds_s[saturated] == pytest.approx(BETA / 2 * overdrive**2 * LAMBDA, rel=0.02)
    assert result.early_voltage_v[saturated] == pytest.approx(1 / LAMBDA + result.bias_vds_v, rel=0.05)
    assert np.all(result.intrinsic_gain[saturated] > 0)


def test_noise_floor_and_corner() -> None:
    frequency = np.logspace(0, 10, 101)
    white, corner = 5e-9, 1e5
    gate = white * np.sqrt(1 + corner / frequency)
    result = analyze_mosfet_noise(
        MeasMosfetNoise(**COMMON, frequency_hz=frequency, drain_noise_a_rthz=gate * 1e-3, gate_noise_v_rthz=gate)
    )
    assert result.white_v_rthz == pytest.approx(white, rel=0.01)
    assert result.flicker_corner_hz == pytest.approx(corner, rel=0.05)
    assert result.gate_1khz_v_rthz == pytest.approx(white * math.sqrt(1 + corner / 1e3), rel=0.01)


def test_transient_noise_density_and_mismatch() -> None:
    rate, density = 2e9, 1e-12  # white noise of 1 pA/rtHz
    rng = np.random.default_rng(1)
    current = 1e-4 + rng.normal(0, density * math.sqrt(rate / 2), 2**16)
    tran = analyze_mosfet_trannoise(MeasMosfetTranNoise(**COMMON, time_s=np.arange(len(current)) / rate, id_a=current))
    assert np.median(tran.drain_noise_a_rthz) == pytest.approx(density, rel=0.1)
    transfer = analyze_mosfet_transfer(_transfer())
    runs = 1e-4 * (1 + rng.normal(0, 0.02, 400))
    mismatch = analyze_mosfet_mismatch(MeasMosfetMismatch(**COMMON, id_a=runs), transfer=transfer)
    assert mismatch.sigma_id_relative == pytest.approx(0.02, rel=0.15)
    gm = np.interp(PARAMS.bias * PARAMS.vdd, transfer.gm_vgs_v, transfer.gm_s)
    assert mismatch.sigma_vgs_v == pytest.approx(np.std(runs, ddof=1) / gm)
    assert mismatch.avt_v_m == pytest.approx(mismatch.sigma_vgs_v * math.sqrt(1e-6 * 1e-7))


def test_plots_render(tmp_path: Path) -> None:
    transfer = analyze_mosfet_transfer(_transfer())
    vds = np.linspace(0, PARAMS.vdd, 13)
    curves = np.stack([[_square_law(np.array([g]), v)[0] for v in vds] for g in np.asarray(PARAMS.family)], axis=1)
    output = analyze_mosfet_output(MeasMosfetOutput(**COMMON, vds_v=vds, id_family_a=curves))
    frequency = np.logspace(0, 10, 21)
    noise = analyze_mosfet_noise(
        MeasMosfetNoise(
            **COMMON,
            frequency_hz=frequency,
            drain_noise_a_rthz=np.full(21, 1e-12),
            gate_noise_v_rthz=1e-6 / frequency**0.5,
        )
    )
    tran = analyze_mosfet_trannoise(
        MeasMosfetTranNoise(
            **COMMON, time_s=np.arange(1024) * 1e-9, id_a=np.random.default_rng(2).normal(1e-4, 1e-8, 1024)
        )
    )
    mismatch = analyze_mosfet_mismatch(
        MeasMosfetMismatch(**COMMON, id_a=np.random.default_rng(3).normal(1e-4, 1e-6, 50)), transfer=transfer
    )
    paths = (
        *plot_mosfet_transfer([[transfer, transfer]], labels=["a"], output_path=tmp_path / "transfer"),
        *plot_mosfet_gm_id([[transfer]], labels=["a"], output_path=tmp_path / "gm_id"),
        *plot_mosfet_output([output, output], labels=["a", "b"], output_path=tmp_path / "output"),
        *plot_mosfet_noise([[noise]], lengths_m=[[1e-7]], labels=["a"], output_path=tmp_path / "noise"),
        *plot_mosfet_trannoise([tran], noises=[noise], labels=["a"], output_path=tmp_path / "trannoise"),
        *plot_mosfet_mismatch([[mismatch]], transfers=[[transfer]], labels=["a"], output_path=tmp_path / "mismatch"),
        *plot_mosfet_simulators(
            [transfer],
            ngspice=[transfer],
            noise_spectre=[noise],
            noise_ngspice=[noise],
            labels=["a"],
            output_path=tmp_path / "simulators",
        ),
    )
    assert paths and all(path.exists() for path in paths)
