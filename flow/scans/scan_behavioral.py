"""Behavioral FRIDA-2 ADC experiments that write native MeasAdc captures.

Run from /local/frida:

    uv run python -m flow.scans.scan_behavioral            # list targets
    uv run python -m flow.scans.scan_behavioral <target>

Each target builds HDL21 ``AdcTbParams`` exactly as a SPICE target would and
converts them with ``flow.adc.behavioral``, writing one ``MeasAdc`` per case
beneath ``build/scan_behavioral/<timestamp>_<target>/``. The stored DOUT is
the nominal design-weight decoding the FPGA performs. The model switches the
reviewed three-layer PEX main and diff capacitances; the sampler,
comparator, and SAR-logic blocks carry rough 65-nm and PEX-derived
parameters, with energy pinned per action.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import hdl21 as h
import numpy as np
from hdl21.prefix import G

from flow.adc.behavioral import (
    AdcBehavioralParams,
    CdacBehavioralParams,
    CompBehavioralParams,
    SalogicBehavioralParams,
    SampBehavioralParams,
    build_continuous_sequence,
    calc_capacitor_mismatch,
    calc_ideal_capacitances,
    cdac,
    comp,
    convert_behavioral,
    samp,
)
from flow.adc.sequences import AdcSequence, symbol160_init4_samp20_comp11110000_logic00001111
from flow.adc.sim import AdcTbParams
from flow.adc.subckt import AdcNets, AdcParams
from flow.analysis.io import write_measurement
from flow.analysis.types import MeasAdc, MeasCdac, MeasComp, MeasInfo, Wave
from flow.caparray import get_caparray_weights
from flow.caparray.subckt import CapArrayConfig, RedunStrat
from flow.comp.sim import CompTbParams
from flow.scans.params import AdcScanParams
from flow.scans.scan_adc import convert_dac_caps_to_adc_weights


def calc_pwl_value(source: h.Vpwl.Params, time_s: np.ndarray) -> np.ndarray:
    """Evaluate a PWL source that repeats after its last time point."""

    if isinstance(source.wave, str):
        values = np.asarray([float(value) for value in source.wave.split()], dtype=np.float64)
        pwl_time_s, pwl_value_v = values[0::2], values[1::2]
    else:
        pwl_time_s = np.asarray([float(time) for time, _value in source.wave.points], dtype=np.float64)
        pwl_value_v = np.asarray([float(value) for _time, value in source.wave.points], dtype=np.float64)
    period_s = pwl_time_s[-1] - pwl_time_s[0]
    return np.interp(pwl_time_s[0] + np.mod(time_s - pwl_time_s[0], period_s), pwl_time_s, pwl_value_v)


def calc_source_value(source, time_s: np.ndarray) -> np.ndarray:
    """Evaluate a DC, sine, or repeating PWL differential source."""

    if isinstance(source, h.Vpwl.Params):
        return calc_pwl_value(source, time_s)
    if isinstance(source, h.Vsin.Params):
        return float(source.voff) + float(source.vamp) * np.sin(
            2.0 * np.pi * float(source.freq) * time_s + np.deg2rad(float(source.phase or 0.0))
        )
    return np.full_like(time_s, float(source.dc), dtype=np.float64)


def build_adc_interface_wave(
    params: AdcTbParams,
    bout: Sequence[int],
    *,
    conversion_index: int = 0,
    samples_per_symbol: int = 4,
) -> Wave:
    """Build one dense behavioral ADC-interface waveform from test parameters."""

    if samples_per_symbol <= 0:
        raise ValueError("samples_per_symbol must be positive")
    bout_array = np.asarray(bout, dtype=np.uint8)
    if bout_array.ndim != 1 or np.any((bout_array != 0) & (bout_array != 1)):
        raise ValueError("Bout must be one binary decision vector")

    sequence_length = len(params.seq_init_pattern)

    def sampled_pattern(name: str) -> np.ndarray:
        pattern = getattr(params, f"seq_{name}_pattern")
        return np.repeat(
            np.fromiter((int(bit) for bit in pattern), dtype=np.uint8),
            samples_per_symbol,
        )

    seq_comp = sampled_pattern("comp")
    seq_logic = sampled_pattern("logic")
    comp_symbols = seq_comp.reshape(sequence_length, samples_per_symbol)[:, 0]
    falling_symbols = np.flatnonzero((comp_symbols[:-1] == 1) & (comp_symbols[1:] == 0)) + 1
    if len(falling_symbols) < len(bout_array):
        raise ValueError(
            f"sequencer has {len(falling_symbols)} comparator decisions, but Bout contains {len(bout_array)} bits"
        )
    comp_out_symbols = np.zeros(sequence_length, dtype=np.uint8)
    state = 0
    decision_index = 0
    for symbol in range(sequence_length):
        if decision_index < len(bout_array) and symbol == falling_symbols[decision_index]:
            state = int(bout_array[decision_index])
            decision_index += 1
        comp_out_symbols[symbol] = state

    symbol_period_s = 1.0 / float(params.symbol_rate)
    time_s = np.arange(sequence_length * samples_per_symbol, dtype=np.float64)
    time_s *= symbol_period_s / samples_per_symbol
    vin_diff_v = calc_source_value(params.vin_diff, time_s + conversion_index * sequence_length * symbol_period_s)
    logic_high_v = float(params.vdd_d.dc)
    return Wave(
        record_index=np.asarray([conversion_index], dtype=np.int64),
        time_s=time_s,
        v={
            "vin_diff": vin_diff_v[None, :],
            AdcNets.seq_comp.name: (logic_high_v * seq_comp)[None, :],
            AdcNets.seq_logic.name: (logic_high_v * seq_logic)[None, :],
            AdcNets.comp_out.name: (logic_high_v * np.repeat(comp_out_symbols, samples_per_symbol))[None, :],
        },
    )


# FRIDA-2 three-layer configuration with the 160-symbol continuous recipe.
TB = AdcTbParams(
    view="frida2",
    pex_cell="adc_12b_17step",
    dut=AdcParams(adc_bits=12, cdac=CapArrayConfig()),
    symbol_rate=1.6 * G,
    vin_cm=h.Vdc.Params(dc=0.700),
    **symbol160_init4_samp20_comp11110000_logic00001111.as_tb_fields(),
)
# Reviewed standalone three-layer extraction: main and diff per stage, one side.
CAP_TABLE = Path("/local/frida/build/layout/cdac/caparray_3layer_radix17/20260905_122920/capacitance_table.csv")
# Full-ADC PEX VDAC load per side for frida2_3layer_radix17 (docs/cdac_pex.md);
# the remainder after the array's main and diff plates is top-plate parasitic.
TOTAL_LOAD_F = 1209.8e-15
# Relative mismatch of a 1-fF capacitor, A_C = 0.85 %·sqrt(fF), measured for
# single-layer lateral MOM capacitors by Tripathi and Murmann (TCAS-I 2014).
UNIT_MISMATCH = 0.0085
# Random part of Harpe's measured unit-length DAC linearity (JSSC 2018, 65 nm,
# M6/M7 fingers): DNL_max 0.21 LSB with C_tot 250 fF and a 125-aF LSB implies
# roughly 0.05-0.15 %·sqrt(fF); 0.10 % is that rough midpoint.
UNIT_MISMATCH_HARPE = 0.0010
SAMP = SampBehavioralParams(
    # kT/C of the 1209.8-fF top-plate load on each side, sqrt(2 kT / C) = 82.7 uV
    # differential at 300 K; the PEX run holds 81.5 uV (docs/cdac_pex.md).
    noise_v=float(np.sqrt(2 * 1.380649e-23 * 300.0 / TOTAL_LOAD_F)),
    # ASSUMED 2-ps RMS aperture jitter of the on-chip sampling clock.
    jitter_s=2e-12,
    # Triode conductances come from the TB SampParams sizing (rough 65-nm
    # k' of 300 and 100 uA/V^2, calc_switch_conductances).
    n_threshold_v=0.3,
    p_threshold_v=0.3,
)
COMP = CompBehavioralParams(
    # Simulated comparator input noise from the design notes (docs/literature.md:
    # "130 uV, 30 uW, 2-3 ns"). The 0.36-0.47 mV board S-curve calibrations in
    # map_board.yaml include the external pad and source path, and the best
    # physical fixed-input code noise (about 0.2-0.3 LSB) bounds the comparator
    # near 100 uV. Offsets only shift the transfer and are left out.
    noise_v=130e-6,
    # analyze_adc_power on the FRIDA-2 three-layer PEX transient
    # frida-20260906_124442_994752 .../frida2_3layer_radix17/original
    # (10 MS/s active): 27.07 uW over 17 decisions per 100-ns conversion.
    decision_energy_j=27.071e-6 / 10e6 / 17,
    static_power_w=0.080e-6,
)
# Energies and leakage fitted to the FRIDA-2 three-layer PEX transient
# frida-20260906_124442_994752 .../frida2_3layer_radix17/original (10 MS/s,
# 50 mV): VDD_D 22.85 pJ per conversion and 1.338 uW idle, VDD_DAC 0.883 uW
# idle. The logic energies keep the rough 65-nm ratio of a register's clock
# (about 14 fF) to a state change (about 17 fF), scaled by 1.275 so 48
# registers reproduce the VDD_D energy; leakage is the idle power over 48.
SALOGIC = SalogicBehavioralParams(
    clock_energy_j=25.5e-15,
    write_energy_j=31.9e-15,
    register_static_w=27.9e-9,
)
# ASSUMED single-pole top-plate settling. The FRIDA-2 PEX run settles C7 and
# C15 to 1 mV within 0.2-0.5 ns, which this time constant approximates; it is
# not a fitted extraction and sets the rate where ENOB degrades. The computed
# CDAC charge alone gives 1.33 pJ against the PEX run's 1.38 pJ on VDD_DAC, so
# each of the about 64 bottom-plate transitions adds the remaining 0.8 fJ, and
# the 64 drivers share the 0.883-uW idle power.
SETTLING_TAU_S = 0.2e-9
DRIVER_ENERGY_J = 0.8e-15
DRIVER_STATIC_W = 13.8e-9
SCAN_OUTDIR = Path(__file__).resolve().parents[2] / "build" / "scan_behavioral"


def build_frida2_params(
    tb: AdcTbParams, *, seed: int, unit_mismatch: float = 0.0, noise_seed: int | None = None
) -> AdcBehavioralParams:
    """Return FRIDA-2 three-layer block parameters, with a capacitor mismatch draw when ``unit_mismatch`` > 0."""

    with CAP_TABLE.open(newline="") as table:
        rows = list(csv.DictReader(table))
    main_f = np.asarray([float(row["main_ff"]) for row in rows]) * 1e-15
    diff_f = np.asarray([float(row["diff_ff"]) for row in rows]) * 1e-15
    rng = np.random.default_rng(seed)
    plates = {}
    for side in ("p", "n"):
        for kind, nominal in (("main", main_f), ("diff", diff_f)):
            drawn = calc_capacitor_mismatch(nominal, unit_mismatch=unit_mismatch, rng=rng) if unit_mismatch else nominal
            plates[f"{kind}_{side}_f"] = tuple(float(value) for value in drawn)
    return AdcBehavioralParams(
        tb=tb,
        samp=SAMP,
        comp=COMP,
        cdac=CdacBehavioralParams(
            **plates,
            parasitic_f=TOTAL_LOAD_F - float(np.sum(main_f + diff_f)),
            settling_tau_s=SETTLING_TAU_S,
            driver_energy_j=DRIVER_ENERGY_J,
            driver_static_w=DRIVER_STATIC_W,
        ),
        salogic=SALOGIC,
        seed=seed if noise_seed is None else noise_seed,
    )


def capture_behavioral(
    params: AdcBehavioralParams,
    path: Path,
    *,
    group: int | None = None,
    unit_mismatch: float = 0.0,
    cap_table: str = str(CAP_TABLE),
) -> Path:
    """Convert every configured conversion and write the MeasAdc with its supply power.

    A Monte Carlo draw passes its seed as ``group`` (iteration 0); a nominal
    capture leaves both identity fields ``None``.
    """

    tb = params.tb
    sample_rate_hz = float(tb.symbol_rate) / len(tb.seq_init_pattern)
    time_s = np.arange(tb.conversions) / sample_rate_hz
    vin_diff_v = calc_source_value(tb.vin_diff, time_s)
    # A centered difference over 1 ps gives the slope the sampler tracks.
    slope = (
        calc_source_value(tb.vin_diff, time_s + 0.5e-12) - calc_source_value(tb.vin_diff, time_s - 0.5e-12)
    ) / 1e-12
    result = convert_behavioral(params, vin_diff_v, slope)
    code_weights = np.asarray(convert_dac_caps_to_adc_weights(get_caparray_weights(tb.dut.cdac)), dtype=np.int64)
    dout_raw = result.bout.astype(np.int64) @ code_weights
    dout = np.rint(dout_raw * ((1 << tb.dut.adc_bits) - 1) / code_weights.sum()).astype(np.int64)
    # Active power averages one conversion window, as for SPICE captures.
    active_rate_hz = float(tb.symbol_rate) / AdcSequence.from_tb_params(tb).conversion_symbols
    readbacks: dict[str, str | int | float | bool] = {
        "cap_table": cap_table,
        "unit_mismatch": unit_mismatch,
    }
    for rail in ("vdd_a", "vdd_d", "vdd_dac"):
        static_w = result.static_power_w[rail]
        readbacks[f"{rail}_static_average_power_w"] = static_w
        readbacks[f"{rail}_active_average_power_w"] = static_w + float(np.mean(result.energy_j[rail])) * active_rate_hz
    measurement = MeasAdc(
        group=group,
        index=None if group is None else 0,
        dut=tb.dut,
        info=MeasInfo(
            backend="behavioral",
            timestamp_utc=datetime.now().astimezone(),
            instruments={"model": f"{convert_behavioral.__module__}.{convert_behavioral.__name__}"},
            readbacks=readbacks,
        ),
        param=params,
        conversion_index=np.arange(tb.conversions),
        bout=result.bout,
        dout_raw=dout_raw,
        dout=dout,
        vin_diff_v=vin_diff_v,
        wave=build_adc_interface_wave(tb, result.bout[0]),
    )
    return write_measurement(path, measurement)


def frida2_ramp_code_density(run_dir: Path) -> None:
    """Eight full-scale sawtooth periods, 1,000,000 conversions, twice per capacitor draw.

    Seed 0 has no random capacitor mismatch; seeds 1-4 are drawn at the
    Harpe-derived and the Tripathi-Murmann unit mismatch. Each draw is
    captured once for calibration training and once more, with the same
    capacitors and independent noise, as a held-out check.
    """

    tb = AdcTbParams(**{**TB.__dict__, "conversions": 1_000_000, "vin_diff": h.Vpwl.Params(wave="0 -0.8 0.0125 0.8")})
    cases = [(0, 0.0)] + [
        (seed, mismatch) for mismatch in (UNIT_MISMATCH_HARPE, UNIT_MISMATCH) for seed in (1, 2, 3, 4)
    ]
    for seed, mismatch in cases:
        for role, noise_seed in (("train", seed), ("check", seed + 1000)):
            path = capture_behavioral(
                build_frida2_params(tb, seed=seed, unit_mismatch=mismatch, noise_seed=noise_seed),
                run_dir / f"seed{seed:02d}_ac{round(mismatch * 1e4):03d}_{role}.h5",
                group=seed,
                unit_mismatch=mismatch,
            )
            print(f"Saved {path}")


def frida2_energy_vs_input(run_dir: Path) -> None:
    """129 DC inputs across the full scale, 2,000 conversions each, without mismatch."""

    full_scale_v = 0.765
    params, paths = [], []
    for index, vin_v in enumerate(np.linspace(-full_scale_v, full_scale_v, 129)):
        tb = AdcTbParams(**{**TB.__dict__, "conversions": 2_000, "vin_diff": h.Vdc.Params(dc=float(vin_v))})
        params.append(build_frida2_params(tb, seed=0))
        paths.append(run_dir / f"{index:03d}_vin{1e3 * vin_v:+04.0f}mv.h5")
    with ProcessPoolExecutor(max_workers=12) as executor:
        list(executor.map(capture_behavioral, params, paths))
    print(f"Saved {len(paths)} captures in {run_dir}")


def frida2_sample_rate(run_dir: Path) -> None:
    """A -0.5 dBFS sine at 0.2-6.4 GBd (1.25-40 MS/s), 8,192 conversions each, without mismatch."""

    conversions = 8_192
    amplitude_v = 0.765 * 10 ** (-0.5 / 20)
    for symbol_rate_gbd in (0.2, 0.4, 0.8, 1.2, 1.6, 2.4, 3.2, 4.8, 6.4):
        sample_rate_hz = symbol_rate_gbd * 1e9 / len(TB.seq_init_pattern)
        # 1,021 cycles in 8,192 conversions: coprime and near fs / 8.
        frequency_hz = 1_021 * sample_rate_hz / conversions
        tb = AdcTbParams(
            **{
                **TB.__dict__,
                "symbol_rate": symbol_rate_gbd * G,
                "conversions": conversions,
                "vin_diff": h.Vsin.Params(voff=0.0, vamp=amplitude_v, freq=frequency_hz),
            }
        )
        name = f"{round(symbol_rate_gbd * 1e3):04d}mbd.h5"
        path = capture_behavioral(build_frida2_params(tb, seed=0), run_dir / name)
        print(f"Saved {path} ({sample_rate_hz / 1e6:.3g} MS/s, f_in {frequency_hz / 1e6:.4g} MHz)")


def frida2_noise_sources(run_dir: Path) -> None:
    """A fixed 50-mV input at 10 MS/s, 100,000 conversions, with one noise source at a time.

    The baseline has the sampling and comparator noise; the reference case
    adds an ASSUMED 100-uV RMS VDD_DAC noise to it. Jitter does not affect a
    DC input.
    """

    tb = AdcTbParams(**{**TB.__dict__, "conversions": 100_000, "vin_diff": h.Vdc.Params(dc=0.05)})
    base = build_frida2_params(tb, seed=0)
    quiet_samp = SampBehavioralParams(**{**SAMP.__dict__, "noise_v": 0.0, "jitter_s": 0.0})
    quiet_comp = CompBehavioralParams(**{**COMP.__dict__, "noise_v": 0.0})
    reference = CdacBehavioralParams(**{**base.cdac.__dict__, "reference_noise_v": 100e-6})
    # A source alone below one LSB leaves a DC input on one code, so the
    # reference noise is shown on top of the baseline sources instead.
    cases = {
        "sampling": {"comp": quiet_comp},
        "comparator": {"samp": quiet_samp},
        "baseline": {},
        "reference": {"cdac": reference},
    }
    for name, blocks in cases.items():
        params = AdcBehavioralParams(**{**base.__dict__, **blocks})
        print(f"Saved {capture_behavioral(params, run_dir / f'noise_{name}.h5')}")


def frida2_input_frequency(run_dir: Path) -> None:
    """A -0.5 dBFS sine at nine input frequencies up to Nyquist, at 2, 6, and 10 MS/s, 8,192 conversions each."""

    conversions = 8_192
    amplitude_v = 0.765 * 10 ** (-0.5 / 20)
    # Odd cycle counts, coprime with 8,192, from 0.4 % to 49 % of the sample rate.
    cycles = (31, 101, 257, 509, 1021, 1531, 2039, 3067, 4013)
    for symbol_rate_gbd in (0.32, 0.96, 1.6):
        sample_rate_hz = symbol_rate_gbd * 1e9 / len(TB.seq_init_pattern)
        for count in cycles:
            frequency_hz = count * sample_rate_hz / conversions
            tb = AdcTbParams(
                **{
                    **TB.__dict__,
                    "symbol_rate": symbol_rate_gbd * G,
                    "conversions": conversions,
                    "vin_diff": h.Vsin.Params(voff=0.0, vamp=amplitude_v, freq=frequency_hz),
                }
            )
            name = f"{round(symbol_rate_gbd * 1e3):04d}mbd_{count:04d}cycles.h5"
            capture_behavioral(build_frida2_params(tb, seed=0), run_dir / name)
        print(f"Saved {len(cycles)} captures at {sample_rate_hz / 1e6:g} MS/s")


def frida2_trajectory(run_dir: Path) -> None:
    """A fixed input on the C0 decision threshold, 2,000 conversions at 10 MS/s with every noise source.

    Comparator noise makes B0 random at 0 V, so the redundant later stages
    must recover whichever direction it takes.
    """

    tb = AdcTbParams(**{**TB.__dict__, "conversions": 2_000, "vin_diff": h.Vdc.Params(dc=0.0)})
    print(f"Saved {capture_behavioral(build_frida2_params(tb, seed=0), run_dir / 'trajectory_0mv.h5')}")


def frida2_cdac_ab(run_dir: Path) -> None:
    """The CDAC and comparator blocks alone: the physical cdac_ab S-curve campaign for every capacitor draw.

    For each side, element, direction, and dac_diffcaps, INIT loads an all-one
    or all-zero A state, the held input is sampled, one LOGIC edge loads the B
    state that flips only that element, and the comparator decides once.
    Forty-one inputs within four noise sigma of the expected transition get
    200 trials each. A comparator S-curve at the same 0.8-V common mode is the
    reference of every step. The draws and their seeds match the ramp target.
    """

    vin_cm_v = 0.8
    trials = 200
    cases = [(0, 0.0)] + [
        (seed, mismatch) for mismatch in (UNIT_MISMATCH_HARPE, UNIT_MISMATCH) for seed in (1, 2, 3, 4)
    ]
    for seed, mismatch in cases:
        draw_dir = run_dir / f"seed{seed:02d}_ac{round(mismatch * 1e4):03d}"
        rng = np.random.default_rng(seed + 2000)
        params = build_frida2_params(TB, seed=seed, unit_mismatch=mismatch, noise_seed=seed + 2000)
        sigma_v = float(np.hypot(params.comp.noise_v, params.samp.noise_v))
        stages = len(TB.dac_astate_p)
        info = MeasInfo(
            backend="behavioral",
            timestamp_utc=datetime.now().astimezone(),
            instruments={"model": f"{comp.__module__}.{comp.__name__}"},
            readbacks={"cap_table": str(CAP_TABLE), "unit_mismatch": mismatch, "seed": seed},
        )

        comp_tb = CompTbParams(
            comp=TB.dut.comp,
            vin_cm_values_v=(vin_cm_v,),
            vin_diff_values_v=tuple(float(value) for value in np.linspace(-4 * sigma_v, 4 * sigma_v, 41)),
            conversions=trials,
        )
        vin_diff_v = np.repeat(np.asarray(comp_tb.vin_diff_values_v, dtype=np.float64), trials)
        comparator = MeasComp(
            group=seed,
            index=0,
            dut=comp_tb.comp,
            info=info,
            param=comp_tb,
            trial_index=np.arange(len(vin_diff_v)),
            vin_diff_v=vin_diff_v,
            vin_cm_v=np.full(len(vin_diff_v), vin_cm_v),
            decision=comp(TB.dut.comp, params.comp, vin_diff_v, rng, vin_cm_v=vin_cm_v).astype(np.uint8),
        )
        write_measurement(draw_dir / "comparator.h5", comparator)

        for side in ("p", "n"):
            for element in range(stages):
                for direction in ("1to0", "0to1"):
                    for diffcaps in (0, 1):
                        start = 1 if direction == "1to0" else 0
                        before = {"p": [start] * stages, "n": [start] * stages}
                        after = {"p": list(before["p"]), "n": list(before["n"])}
                        after[side][element] = 1 - start
                        tb = AdcTbParams(
                            **{
                                **TB.__dict__,
                                "dac_mode": 0,
                                "dac_diffcaps": diffcaps,
                                "dac_astate_p": tuple(before["p"]),
                                "dac_bstate_p": tuple(after["p"]),
                                "dac_astate_n": tuple(before["n"]),
                                "dac_bstate_n": tuple(after["n"]),
                                "vin_cm": h.Vdc.Params(dc=vin_cm_v),
                            }
                        )
                        step_v = 0.0
                        for plate in ("p", "n"):
                            top_step, _charge, _toggles = cdac(
                                params.cdac,
                                tb,
                                plate,
                                np.asarray([before[plate]]),
                                np.asarray([after[plate]]),
                            )
                            step_v += float(top_step[0]) * (1.0 if plate == "p" else -1.0)
                        # The comparator flips where the held input cancels the step.
                        transition_v = params.comp.offset_v - step_v
                        grid = transition_v + np.linspace(-4 * sigma_v, 4 * sigma_v, 41)
                        vin_diff_v = np.repeat(grid, trials)
                        held = samp(
                            TB.dut.samp,
                            params.samp,
                            {"p": vin_cm_v + vin_diff_v / 2, "n": vin_cm_v - vin_diff_v / 2},
                            {"p": np.zeros(len(vin_diff_v)), "n": np.zeros(len(vin_diff_v))},
                            load_f={"p": TOTAL_LOAD_F, "n": TOTAL_LOAD_F},
                            gate_v=float(tb.vdd_d.dc),
                            rng=rng,
                        )
                        decision = comp(
                            TB.dut.comp, params.comp, held["p"] - held["n"] + step_v, rng, vin_cm_v=vin_cm_v
                        )
                        point = AdcScanParams(
                            tb=AdcTbParams(**{**tb.__dict__, "vin_diff": h.Vdc.Params(dc=float(transition_v))}),
                            campaign="cdac_ab",
                            sampling_mode="hold",
                            sweep_stage="fine",
                            cdac_side=side,
                            cdac_element=element,
                            cdac_direction=direction,
                            settling_time_s=20e-9,
                        )
                        rows = len(vin_diff_v)
                        measurement = MeasCdac(
                            group=seed,
                            index=0,
                            dut=tb.dut.cdac,
                            info=info,
                            param=point,
                            trial_index=np.arange(rows),
                            dac_state_p=np.tile(after["p"], (rows, 1)).astype(np.uint8),
                            dac_state_n=np.tile(after["n"], (rows, 1)).astype(np.uint8),
                            vin_diff_v=vin_diff_v,
                            decision=decision.astype(np.uint8),
                            dac_state_before_p=np.tile(before["p"], (rows, 1)).astype(np.uint8),
                            dac_state_before_n=np.tile(before["n"], (rows, 1)).astype(np.uint8),
                            vin_cm_v=np.full(rows, vin_cm_v),
                        )
                        name = f"cdac_{side}_c{element:02d}_{direction}_diff{diffcaps}.h5"
                        write_measurement(draw_dir / name, measurement)
        print(f"Saved comparator and {4 * 2 * stages} switching curves in {draw_dir}")


def architecture_variants(run_dir: Path) -> None:
    """Compare redundant and binary 12-bit arrays built from unit-length or unit-element capacitors.

    Every variant has the FRIDA-2 three-layer array's 1011-fF physical
    capacitance and the same parasitic, sampler, comparator, settling, and
    rough logic energies, with ideal (not extracted) capacitor values. The
    redundant arrays have 16 capacitors and 17 decisions; the binary arrays 11
    capacitors and 12 decisions, run with a recipe of their own length at the
    same 1.6-GBd symbol rate. A unit-length stage is a main/diff pair sized like
    CapArray; a unit-element stage is one plain capacitor. Each draw has an
    eight-period ramp for calibration training and a held-out repeat.
    """

    with CAP_TABLE.open(newline="") as table:
        array_f = sum(float(row["main_ff"]) + float(row["diff_ff"]) for row in csv.DictReader(table)) * 1e-15
    parasitic_f = TOTAL_LOAD_F - array_f
    configs = {
        "redundant": CapArrayConfig(),
        "binary": CapArrayConfig(n_dac=11, n_extra=0, redun_strat=RedunStrat.RDX2),
    }
    cases = [(0, 0.0), (1, UNIT_MISMATCH_HARPE), (2, UNIT_MISMATCH_HARPE), (1, UNIT_MISMATCH), (2, UNIT_MISMATCH)]
    for weighting, cdac_config in configs.items():
        weights = np.asarray(get_caparray_weights(cdac_config), dtype=np.float64)
        stages = len(weights)
        alternating = tuple(index % 2 for index in range(stages))
        ideal_main_f, ideal_diff_f = calc_ideal_capacitances(cdac_config)
        for style in ("unitlength", "unitelement"):
            if style == "unitlength":
                scale = array_f / float(np.sum(ideal_main_f + ideal_diff_f))
                main_f, diff_f = ideal_main_f * scale, ideal_diff_f * scale
            else:
                main_f, diff_f = weights * array_f / float(np.sum(weights)), np.zeros(stages)
            # Each array's own differential full scale; a ramp 5 % beyond it reaches every code.
            full_scale_v = float(TB.vdd_dac.dc) * float(np.sum(main_f - diff_f)) / TOTAL_LOAD_F
            tb = AdcTbParams(
                **{
                    **TB.__dict__,
                    "dut": AdcParams(adc_bits=12, cdac=cdac_config),
                    "conversions": 1_000_000,
                    "vin_diff": h.Vpwl.Params(wave=f"0 {-1.05 * full_scale_v:.4f} 0.0125 {1.05 * full_scale_v:.4f}"),
                    "dac_astate_p": alternating,
                    "dac_astate_n": alternating,
                    "dac_bstate_p": (0,) * stages,
                    "dac_bstate_n": (0,) * stages,
                    **build_continuous_sequence(stages).as_tb_fields(),
                }
            )
            for seed, mismatch in cases:
                for role, noise_seed in (("train", seed), ("check", seed + 1000)):
                    rng = np.random.default_rng(seed)
                    plates = {}
                    for side in ("p", "n"):
                        for kind, nominal in (("main", main_f), ("diff", diff_f)):
                            drawn = (
                                calc_capacitor_mismatch(nominal, unit_mismatch=mismatch, rng=rng)
                                if mismatch
                                else nominal
                            )
                            plates[f"{kind}_{side}_f"] = tuple(float(value) for value in drawn)
                    params = AdcBehavioralParams(
                        tb=tb,
                        samp=SAMP,
                        comp=COMP,
                        cdac=CdacBehavioralParams(
                            **plates,
                            parasitic_f=parasitic_f,
                            settling_tau_s=SETTLING_TAU_S,
                            driver_energy_j=DRIVER_ENERGY_J,
                            driver_static_w=DRIVER_STATIC_W,
                        ),
                        salogic=SALOGIC,
                        seed=noise_seed,
                    )
                    name = f"{weighting}_{style}/seed{seed:02d}_ac{round(mismatch * 1e4):03d}_{role}.h5"
                    capture_behavioral(params, run_dir / name, group=seed, unit_mismatch=mismatch, cap_table="")
            print(f"Saved {weighting} {style} captures")


def frida2_comparator(run_dir: Path) -> None:
    """The comparator block alone: 61 differential inputs within +/-1.5 mV at 0.7 V, 400 decisions each."""

    tb = CompTbParams(
        comp=TB.dut.comp,
        vin_cm_values_v=(0.7,),
        vin_diff_values_v=tuple(float(value) for value in np.linspace(-1.5e-3, 1.5e-3, 61)),
        conversions=400,
    )
    vin_diff_v = np.repeat(np.asarray(tb.vin_diff_values_v, dtype=np.float64), tb.conversions)
    decision = comp(tb.comp, COMP, vin_diff_v, np.random.default_rng(0), vin_cm_v=0.7)
    measurement = MeasComp(
        group=None,
        index=None,
        dut=tb.comp,
        info=MeasInfo(
            backend="behavioral",
            timestamp_utc=datetime.now().astimezone(),
            instruments={"model": f"{comp.__module__}.{comp.__name__}"},
        ),
        param=tb,
        trial_index=np.arange(len(vin_diff_v)),
        vin_diff_v=vin_diff_v,
        vin_cm_v=np.full(len(vin_diff_v), 0.7),
        decision=decision.astype(np.uint8),
    )
    print(f"Saved {write_measurement(run_dir / 'comparator.h5', measurement)}")


def main() -> None:
    """Select one behavioral experiment."""

    targets = {
        target.__name__: target
        for target in (
            frida2_ramp_code_density,
            frida2_energy_vs_input,
            frida2_sample_rate,
            frida2_noise_sources,
            frida2_input_frequency,
            frida2_trajectory,
            frida2_cdac_ab,
            architecture_variants,
            frida2_comparator,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=list(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available behavioral targets:")
        for name in targets:
            print(f"  {name}")
        return
    run_dir = SCAN_OUTDIR / (datetime.now().astimezone().strftime("%Y%m%d_%H%M%S") + "_" + args.target)
    run_dir.mkdir(parents=True, exist_ok=False)
    print(f"Behavioral output: {run_dir}")
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
