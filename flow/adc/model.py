"""The ADC's behavioral model: its blocks' models, each built from the same parameters its netlist
generator takes (``Params``), switched by its SAR loop (``convert_behavioral``, below).

    model = Model.of("tsmc65", Params(adc_bits=12, cdac=..., samp=..., comp=...))
    tb = model.tb(conversions=8192, rate_hz=10e6, vin_diff=h.Vsin.Params(...))
    model.capture(tb, path)  # a MeasAdc, as a SPICE capture of the same TbParams writes one

The blocks: the comparator (``flow.comp.model``), the sampling switch (``flow.samp.model``), the
capacitor array (``flow.cdac.caparray.model``) and its drivers (``flow.cdac.capdriver.model``, derived from the
array's plates: ``flow.cdac.capdriver.model.driver_strengths``), each from its own characterization or
extraction in the PDK; the DAC's settling, stage by stage, from the SPICE characterization of the
array with its drivers (``flow.cdac.model``, of the converter's array at its resolution,
``cdac.adc_array``, by the array's name: ``python -m flow run cdac`` runs it ahead), or, where there is none, estimated
from the drivers' resistance and delay with a warning. The converter's DAC is a ``capdac.Params``;
these legacy characterizations are of the same array (``flow.adc.subckt._legacy_array``) until the
model composes capdac's own. The SAR logic is the fixed digital netlist built by
OpenROAD: it is not characterized, so its energies are the ones fitted to the FRIDA-2 three-layer
PEX transient (``_SALOGIC``). The DAC's reference is ideal here, the front end's own characterization;
a ``Reference`` (driver resistance, decoupling capacitance, noise) is what the reference study
(``Model.reference_requirements``, below) varies to find the reference buffer's requirements.

The SAR loop (``convert_behavioral``) runs four blocks driven by HDL21 parameters. The sampler, the
comparator and the capacitor array with its drivers are their blocks' models
(``flow.samp.model.Model.sample``, ``flow.comp.model.Model.compare`` and ``capdac.Model.switch``,
each with its physics as ``Model.Behavioral``); ``salogic`` models the SAR logic. Each takes its
own behavioral parameters and can run alone; ``convert_behavioral`` wires them into the ADC loop of
``TbParams``. Stage and decision counts come from the CDAC configuration, and every time from
the programmed SEQ rows and symbol rate, so resolution and speed are free parameters.

The SAR logic is a stage counter and a branch select: INIT loads the A state,
then each LOGIC edge writes the counted stage, ``1 - B`` on the P side and
``B`` on the N side (``dac_mode=1``), or reloads the B state (``dac_mode=0``).
Diff bottom plates follow ``state XOR dac_diffcaps``. Logic, comparator, and
driver energies are fixed amounts pinned to these actions. The CDAC charge is
computed: every top plate is one floating node loaded by its main and diff
capacitors and a parasitic capacitance, and the plates at VDD_DAC after an
edge draw ``C * (dV_bottom - dV_top)`` from it.

The reference buffer's requirements a converter sets (``Model.reference_requirements``): the
largest output resistance and noise of the buffer driving its DAC's reference (VDD_DAC) for which
the error the reference adds stays within the converter's quantization noise. They are the
converter's metrics ``ref_*``, so the reference buffer is specified by the converter it serves, and
not part of the converter's ENOB (its front end's, on an ideal reference).

- The decoupling the reference node has: decap cells over ``DECAP_COVERAGE`` of the converter's
  footprint (taken as its two capacitor arrays'), the supplies shared, at the PDK's decap density
  (``DECAP_FF_PER_UM2`` in its ``pdk_logic``), rounded to one significant figure
  (``ref_decap_f``).
- Kickback: each switch draws its charge from that capacitance and the buffer restores it through
  its output resistance, so the dip left at the next comparison is a code-dependent error: the
  largest output resistance the converter tolerates (``ref_r_max_ohm``), and the ENOB it loses over
  the resistance (figure ``reference_r_out``).
- Noise: the largest white noise at the node, RMS at each decision (``ref_noise_max_v``), and the
  ENOB lost over it (figure ``reference_noise``).

The two add in power, and each may add ``REFERENCE_SHARE`` of an ideal quantizer's noise power
(LSB^2 / 12) of the converter's resolution, so a buffer meeting both adds no more than the
quantization noise: each may cost ``ref_enob_loss_max_bits``. Each requirement is the largest value
on its grid within that loss, refined by bisection on a log scale to the next grid point that is
not. Every point converts the sine at the nominal rate with that capture's seeds, so only the
reference moves, on the converter with an ideal sampler and comparator (``REFERENCE_QUIET``): its
DAC alone, whose settling takes the time and the redundancy the reference's error competes for. An
error the size of the quantization noise cannot be told from one capture of a converter whose own
error is many times it, and the comparator does not see the reference.
"""

from __future__ import annotations

import importlib
import math
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path

import hdl21 as h
import numpy as np

import flow.cdac.model as cdac_model
import flow.comp.model as comp_model
import flow.samp.model as samp_model
from flow import capdac
from flow import cdac as cdac_block  # the CDAC block; ``cdac`` here is the behavioral array's switching
from flow.adc.analysis import analyze_dynamic
from flow.adc.params import (
    DECAP_COVERAGE,
    DRAWN_PERCENTILE,
    DRAWN_RUN,
    IDEAL_REFERENCE,
    NOMINAL_RATE_HZ,
    QUIET,
    REFERENCE_HALVINGS,
    REFERENCE_NOISE_V,
    REFERENCE_QUIET,
    REFERENCE_R_OUT_OHM,
    REFERENCE_SHARE,
    VIN_CM_FRACTION,
    Capture,
    Params,
    Reference,
    TbParams,
)
from flow.adc.sim import AdcSequence, build_adc_interface_wave, calc_source_value
from flow.adc.subckt import _legacy_array, calc_side_capacitances
from flow.adc.types import AnalysisReference
from flow.analysis.io import read_extracted_calibration, write_measurement
from flow.analysis.types import MeasAdc, MeasInfo
from flow.cdac.caparray.layout import array_name
from flow.cdac.caparray.model import CapArrayModel
from flow.cdac.capdriver.model import CapDriverModel, driver_strengths, stage_drivers
from flow.cdac.capdriver.subckt import CapDriverParams, Cells
from flow.pipeline import Space


@cache
def _cdac_arrays(pdk: str) -> dict[str, Space]:
    """The PDK's CDACs by their arrays' names (``cdac.adc_array``), built once a process."""
    return cdac_block.adc_array.spaces(pdk)


@h.paramclass
class SalogicBehavioralParams:
    """SAR stage counter and branch select; energy is pinned per action and register."""

    clock_energy_j = h.Param(dtype=float, desc="Energy per register per LOGIC edge", default=0.0)
    write_energy_j = h.Param(dtype=float, desc="Energy per state-register value change", default=0.0)
    register_static_w = h.Param(dtype=float, desc="Static power per register with its logic", default=0.0)


@h.paramclass
class AdcBehavioralParams:
    """One HDL21 testbench configuration plus the block physics it does not describe."""

    tb = h.Param(dtype=TbParams, desc="ADC stimulus and digital configuration", default=TbParams())
    samp = h.Param(dtype=samp_model.Model.Behavioral, desc="Sampler", default=samp_model.Model.Behavioral())
    comp = h.Param(dtype=comp_model.Model.Behavioral, desc="Comparator", default=comp_model.Model.Behavioral())
    cdac = h.Param(dtype=capdac.Model.Behavioral, desc="Capacitor array and drivers", default=capdac.Model.Behavioral())
    salogic = h.Param(dtype=SalogicBehavioralParams, desc="SAR logic", default=SalogicBehavioralParams())
    seed = h.Param(dtype=int, desc="Noise random seed", default=0)


@dataclass(frozen=True, slots=True)
class BehavioralConversions:
    """Decisions, per-conversion energy by rail, and static power by rail."""

    bout: np.ndarray
    energy_j: dict[str, np.ndarray]
    static_power_w: dict[str, float]


# The SAR logic's energies, fitted to the FRIDA-2 three-layer PEX transient (10 MS/s): 22.85 pJ a
# conversion and 1.338 uW idle on VDD_D over its 48 registers (flow.scans.scan_behavioral).
_SALOGIC = SalogicBehavioralParams(clock_energy_j=25.5e-15, write_energy_j=31.9e-15, register_static_w=27.9e-9)


@dataclass(frozen=True)
class Model:
    """A SAR ADC's blocks, as their characterizations and extractions measured them."""

    pdk: str
    params: Params
    comp: comp_model.Model
    samp: samp_model.Model
    cdac: CapArrayModel
    drivers: tuple[CapDriverModel, ...]
    settling: cdac_model.Model | None = None  # the DAC's SPICE settling by stage; None: the RC estimate
    # the plates the converter calibrates on, (main, diff) for the P side then the N side: its CDAC's
    # Monte Carlo draw (DRAWN_RUN at DRAWN_PERCENTILE, drawn in SPICE); None where none is characterized
    drawn: tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]] | None = None

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        # the legacy characterizations of the converter's array
        legacy = _legacy_array(params.cdac)
        array = CapArrayModel.of(pdk, legacy)
        # the drivers the array's plates call for (flow.cdac.capdriver.model.driver_strengths)
        strengths = driver_strengths(pdk, legacy, array, simulate=simulate)
        driver = CapDriverParams(n_stages=len(array.main_f), strengths=strengths, cells=Cells.GENERIC)
        # the DAC's characterization, of the converter's array at its resolution, is looked up, never
        # run here (minutes of SPICE an array, which every converter on the array would wait for)
        try:
            dac = _cdac_arrays(pdk)[array_name(legacy)].base
            if dac.adc_bits != params.adc_bits:
                raise LookupError(
                    f"the CDAC is characterized at {dac.adc_bits} bits, the converter has {params.adc_bits}"
                )
            settling = cdac_model.Model.of(pdk, dac, simulate=False)
        except (KeyError, LookupError, RuntimeError) as error:
            warnings.warn(
                f"the DAC's settling is not characterized ({error}); it settles by the RC estimate instead",
                stacklevel=2,
            )
            dac, settling = None, None
        try:
            drawn = cdac_model.Model.drawn(pdk, dac, DRAWN_RUN, DRAWN_PERCENTILE) if dac is not None else None
        except (KeyError, LookupError, OSError) as error:
            warnings.warn(
                f"the DAC's Monte Carlo is not characterized ({error}); its draws convert nominal", stacklevel=2
            )
            drawn = None
        return cls(
            pdk=pdk,
            params=params,
            comp=comp_model.Model.of(pdk, params.comp, simulate=simulate),
            samp=samp_model.Model.of(pdk, params.samp, simulate=simulate),
            cdac=array,
            drivers=stage_drivers(pdk, driver, np.maximum(array.main_f, array.diff_f), simulate=simulate),
            settling=settling,
            drawn=drawn,
        )

    @property
    def stages(self) -> int:
        return len(capdac.Model.weights(self.params.cdac))

    @property
    def supply_v(self) -> float:
        return importlib.import_module(f"pdk.{self.pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)

    @property
    def full_scale_v(self) -> float:
        """The differential full scale (+-): the reference across the switched plates' share of the
        top plate, main less difference with the difference plates in use."""
        effective = float(np.sum(self.cdac.main_f) - np.sum(self.cdac.diff_f))
        return self.supply_v * effective / self.cdac.load_f

    @property
    def stage_tau_s(self) -> tuple[float, ...]:
        """Each stage's top-plate settling time constant, C0 first: the one that brings its step
        within half an LSB when SPICE does (``flow.cdac.model``); without that characterization, its
        driver through its plate in series with the rest of the load, the slower of its main and
        difference plates."""
        if self.settling is not None:
            return self.settling.tau_s
        load = self.cdac.load_f
        return tuple(
            max(driver.resistance_ohm * plate * (load - plate) / load for plate in (main, diff))
            for driver, main, diff in zip(self.drivers, self.cdac.main_f, self.cdac.diff_f, strict=True)
        )

    @property
    def stage_delay_s(self) -> tuple[float, ...]:
        """Each stage's delay from the LOGIC edge until its step starts, C0 first: its driver's delay
        to 50 % in SPICE (``flow.cdac.model``); without it, its driver's intrinsic delay."""
        if self.settling is not None:
            return self.settling.delay_s
        return tuple(driver.intrinsic_delay_s for driver in self.drivers)

    @property
    def settling_tau_s(self) -> float:
        """The slowest stage's settling time constant."""
        return max(self.stage_tau_s)

    @property
    def decoupling_f(self) -> float:
        """The reference node's decoupling: decap cells over ``DECAP_COVERAGE`` of the two arrays'
        footprint at the PDK's density, to one significant figure; NaN where the PDK gives none."""
        density = getattr(importlib.import_module(f"pdk.{self.pdk}.hdl21").pdk_logic, "DECAP_FF_PER_UM2", math.nan)
        capacitance_f = DECAP_COVERAGE * 2 * self.cdac.area_um2 * density * 1e-15
        return float(f"{capacitance_f:.0e}") if capacitance_f > 0 else math.nan

    def tb(self, *, conversions: int, rate_hz: float, vin_diff) -> TbParams:
        """The testbench of ``conversions`` at ``rate_hz`` with the continuous sequence (8 symbols a
        decision), an alternating A state and the PDK's supply on every rail."""
        sequence = AdcSequence.continuous(self.stages)
        supply = h.Vdc.Params(dc=round(self.supply_v, 4))
        return TbParams(
            dut=self.params,
            symbol_rate=rate_hz * len(sequence.init),
            conversions=conversions,
            vin_diff=vin_diff,
            vin_cm=h.Vdc.Params(dc=round(VIN_CM_FRACTION * self.supply_v, 4)),
            vdd_a=supply,
            vdd_d=supply,
            vdd_dac=supply,
            dac_astate_p=tuple(stage % 2 for stage in range(self.stages)),
            dac_astate_n=tuple(stage % 2 for stage in range(self.stages)),
            dac_bstate_p=(0,) * self.stages,
            dac_bstate_n=(0,) * self.stages,
            **sequence.as_tb_fields(),
        )

    def behavioral(
        self,
        tb: TbParams,
        *,
        seed: int = 0,
        unit_mismatch: float = 0.0,
        quiet: tuple[str, ...] = (),
        tau_scale: float = 1.0,
        reference: Reference | None = None,
        drawn: bool = False,
    ) -> AdcBehavioralParams:
        """The behavioral ADC: the CDAC's SPICE draw where ``drawn`` (``Model.drawn``; nominal
        where there is none), else one capacitor draw from ``seed`` (none where ``unit_mismatch`` is 0);
        ``quiet`` silences the "sampling" noise (kT/C and the aperture jitter) or the comparator's
        noise alone ("comparator_noise": its delay stays, so a late decision
        still holds the last bit), or makes the "comparator" ideal (no noise, never late) or the
        "sampler" a perfect track-and-hold (no on-resistance, so no tracking error: its noise is
        "sampling"'s). Each stage's step starts its delay after the LOGIC edge (the SAR register's
        clock-to-output is not modeled) and settles with the stage's time constant, times
        ``tau_scale`` (0: ideal, every step whole at once)."""
        if unknown := set(quiet) - QUIET:
            raise ValueError(f"nothing to quiet by {sorted(unknown)}: expected some of {sorted(QUIET)}")
        rng = np.random.default_rng(seed)
        plates = {}
        for index, side in enumerate(("p", "n")):
            if drawn:
                main, diff = self.drawn[index] if self.drawn is not None else (self.cdac.main_f, self.cdac.diff_f)
            else:
                main, diff = self.cdac.draw(unit_mismatch=unit_mismatch, rng=rng)
            plates |= {f"main_{side}_f": tuple(map(float, main)), f"diff_{side}_f": tuple(map(float, diff))}
        samp = self.samp.behavioral(load_f=self.cdac.load_f)
        comp = self.comp.behavioral(vin_cm_v=float(tb.vin_cm.dc))
        if "sampling" in quiet:
            samp = type(samp)(**{**samp.__dict__, "noise_v": 0.0, "jitter_s": 0.0})
        if "sampler" in quiet:
            # a perfect track-and-hold: the held value is the input at the sampling instant (the
            # switch's on-resistance, which lags the input by R(v) C dv/dt, gone)
            samp = type(samp)(
                **{
                    **samp.__dict__,
                    "ron_table_v": None,
                    "ron_table_ohm": None,
                    "n_conductance_s_per_v": 0.0,
                    "p_conductance_s_per_v": 0.0,
                }
            )
        if "comparator" in quiet:
            # an ideal comparator: no noise, and never late
            comp = type(comp)(**{**comp.__dict__, "noise_v": 0.0, "delay_table_v": None, "delay_table_s": None})
        elif "comparator_noise" in quiet:
            comp = type(comp)(**{**comp.__dict__, "noise_v": 0.0})
        return AdcBehavioralParams(
            tb=tb,
            samp=samp,
            comp=comp,
            cdac=capdac.Model.Behavioral(
                **plates,
                parasitic_f=self.cdac.parasitic_f,
                settling_tau_s=self.settling_tau_s * tau_scale,
                stage_tau_s=tuple(tau_s * tau_scale for tau_s in self.stage_tau_s),
                # ideal settling: the drivers' delay goes too
                stage_delay_s=tuple(delay_s if tau_scale else 0.0 for delay_s in self.stage_delay_s),
                driver_energy_j=float(np.mean([driver.energy_j for driver in self.drivers])),
                reference_r_ohm=(reference or IDEAL_REFERENCE).r_ohm,
                reference_c_f=(reference or IDEAL_REFERENCE).c_f,
                reference_noise_v=(reference or IDEAL_REFERENCE).noise_v,
            ),
            salogic=_SALOGIC,
            seed=seed,
        )

    def capture(
        self,
        tb: TbParams,
        path: Path | None,
        *,
        seed: int = 0,
        noise_seed: int | None = None,
        unit_mismatch: float = 0.0,
        quiet: tuple[str, ...] = (),
        tau_scale: float = 1.0,
        reference: Reference | None = None,
        drawn: bool = False,
    ) -> MeasAdc:
        """Convert every conversion of ``tb`` and write the MeasAdc with its supply power to ``path``
        (kept in memory alone where it is None); its ``cap_table`` readback is the array's
        extraction, the decoding's "extracted" weights. ``quiet``, ``tau_scale``, ``reference`` and
        ``drawn``: as ``behavioral``'s."""

        params = self.behavioral(
            tb,
            seed=seed,
            unit_mismatch=unit_mismatch,
            quiet=quiet,
            tau_scale=tau_scale,
            reference=reference,
            drawn=drawn,
        )
        if noise_seed is not None:
            params = AdcBehavioralParams(**{**params.__dict__, "seed": noise_seed})
        sample_rate_hz = float(tb.symbol_rate) / len(tb.seq_init_pattern)
        time_s = np.arange(tb.conversions) / sample_rate_hz
        vin_diff_v = calc_source_value(tb.vin_diff, time_s)
        # a centred difference over 1 ps gives the slope the sampler tracks
        slope = (
            calc_source_value(tb.vin_diff, time_s + 0.5e-12) - calc_source_value(tb.vin_diff, time_s - 0.5e-12)
        ) / 1e-12
        result = convert_behavioral(params, vin_diff_v, slope)
        # each capacitor's decision weighs twice its weight (both sides move), the last decision one
        code_weights = np.asarray([2 * weight for weight in capdac.Model.weights(tb.dut.cdac)] + [1], dtype=np.int64)
        dout_raw = result.bout.astype(np.int64) @ code_weights
        dout = np.rint(dout_raw * ((1 << tb.dut.adc_bits) - 1) / code_weights.sum()).astype(np.int64)
        # active power averages one conversion window, as for SPICE captures
        active_rate_hz = float(tb.symbol_rate) / AdcSequence.from_tb_params(tb).conversion_symbols
        readbacks: dict[str, str | int | float | bool] = {
            "cap_table": str(self.cdac.table),
            "unit_mismatch": unit_mismatch,
            "drawn": bool(drawn and self.drawn is not None),
            "tau_scale": tau_scale,
            "pdk": self.pdk,
        }
        for rail in ("vdd_a", "vdd_d", "vdd_dac"):
            static_w = result.static_power_w[rail]
            readbacks[f"{rail}_static_average_power_w"] = static_w
            readbacks[f"{rail}_active_average_power_w"] = (
                static_w + float(np.mean(result.energy_j[rail])) * active_rate_hz
            )
        measurement = MeasAdc(
            group=seed if unit_mismatch else None,
            index=0 if unit_mismatch else None,
            dut=tb.dut,
            info=MeasInfo(
                backend="behavioral",
                timestamp_utc=datetime.now().astimezone(),
                instruments={"model": f"{Model.__module__}.Model"},
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
        if path is not None:
            write_measurement(path, measurement)
        return measurement

    def metastability(self) -> dict[str, float]:
        """The comparator's regeneration time constant, the time a decision has at the nominal rate
        (the shortest of its sequence's windows), and the input below which it is late there, in LSB:
        the measured delay extrapolated by the time constant, V0 * exp(-(window - t0) / tau)."""
        tb = self.tb(conversions=1, rate_hz=NOMINAL_RATE_HZ, vin_diff=h.Vdc.Params(dc=0.0))
        window_s = float(min(calc_decision_windows(tb, self.stages + 1)))
        tau_s = self.comp.regeneration_tau_s
        # a delay curve that does not grow as the input falls (a fast latch measured above its
        # regeneration) has no time constant to extrapolate: no input is known to be late
        late_v = (
            self.comp.delay_table_v[0] * math.exp(-(window_s - self.comp.delay_table_s[0]) / tau_s)
            if tau_s > 0
            else math.nan
        )
        return {
            "comp_regeneration_tau_s": tau_s,
            "decision_window_s": window_s,
            "metastable_input_lsb": late_v / (2 * self.full_scale_v / 2**self.params.adc_bits),
        }

    def reference_requirements(self, capture: Capture) -> AnalysisReference:
        """The reference's requirements for this converter at ``capture`` (the nominal rate's sine),
        and the ENOB it loses over each."""

        def enob(reference: Reference) -> float:
            measurement = self.capture(
                capture.tb,
                None,
                seed=capture.seed,
                noise_seed=capture.noise_seed,
                unit_mismatch=capture.unit_mismatch,
                quiet=REFERENCE_QUIET,
                tau_scale=capture.tau_scale,
                reference=reference,
            )
            return _enob(measurement)

        enob_bits = enob(IDEAL_REFERENCE)
        budget_bits = enob_bits - _enob_floor(self.params.adc_bits, enob_bits, REFERENCE_SHARE)

        def loss(reference: Reference) -> float:
            return enob_bits - enob(reference)

        def tolerated(make: Callable[[float], Reference], grid: np.ndarray) -> tuple[list[float], float]:
            # the loss at each grid point, and the largest value within the budget: below the first
            # point over it, bisected towards it; the grid's last where none is, NaN where the first is
            losses = [loss(make(value)) for value in grid]
            over = np.flatnonzero(np.asarray(losses) > budget_bits)
            if not over.size:
                return losses, float(grid[-1])
            if over[0] == 0:
                return losses, math.nan
            low, high = float(grid[over[0] - 1]), float(grid[over[0]])
            for _ in range(REFERENCE_HALVINGS):
                middle = math.sqrt(low * high)
                low, high = (middle, high) if loss(make(middle)) <= budget_bits else (low, middle)
            return losses, low

        decap_f = self.decoupling_f
        noise_losses, noise_max_v = tolerated(lambda noise_v: Reference(noise_v=noise_v), REFERENCE_NOISE_V)
        # the driver's resistance only where the node has decoupling to restore
        r_out_ohm, r_losses, r_max_ohm = np.zeros(0), [], math.nan
        if decap_f > 0:
            r_out_ohm = REFERENCE_R_OUT_OHM
            r_losses, r_max_ohm = tolerated(lambda r_ohm: Reference(r_ohm=r_ohm, c_f=decap_f), REFERENCE_R_OUT_OHM)
        return AnalysisReference(
            group=None,
            index=None,
            dut=self.params,
            decap_f=decap_f,
            noise_v=REFERENCE_NOISE_V,
            noise_loss_bits=np.asarray(noise_losses, dtype=np.float64),
            r_out_ohm=r_out_ohm,
            r_out_loss_bits=np.asarray(r_losses, dtype=np.float64),
            noise_max_v=noise_max_v,
            r_max_ohm=r_max_ohm,
            enob_loss_max_bits=budget_bits,
        )


def _enob(measurement: MeasAdc) -> float:
    """A sine capture's spectral ENOB referred to full scale, decoded as the record's ``enob_bits``
    is (the extracted weights of its ``cap_table`` readback, unrounded)."""
    extracted = read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)
    return analyze_dynamic(measurement, calibration=extracted).spectral_enob_fs_bits


def _enob_floor(bits: int, enob_bits: float, share: float = 1.0) -> float:
    """The ENOB a converter of ``bits`` reaches when an error of ``share`` of its quantization noise
    power (LSB^2 / 12) adds to the noise and distortion it has at ``enob_bits``."""
    return bits - 0.5 * math.log2(2.0 ** (2 * (bits - enob_bits)) + share)


def _sequence_times(tb: TbParams, decisions: int) -> tuple[np.ndarray, np.ndarray]:
    """Return COMP and post-INIT LOGIC rising times relative to the INIT rise."""

    sequence = AdcSequence.from_tb_params(tb).relative_to_init()
    symbol_s = 1.0 / float(tb.symbol_rate)

    def rising(row: str) -> np.ndarray:
        bits = np.asarray([int(bit) for bit in row])
        return np.flatnonzero((bits == 1) & (np.roll(bits, 1) == 0)) * symbol_s

    comp_s = rising(sequence.comp)
    logic_s = rising(sequence.logic)
    logic_s = logic_s[logic_s > symbol_s * sequence.init.count("1")]
    if len(comp_s) != decisions or len(logic_s) < decisions - 1:
        raise ValueError(f"sequence must contain {decisions} COMP and {decisions - 1} LOGIC rises after INIT")
    return comp_s, logic_s[: decisions - 1]


def calc_decision_windows(tb: TbParams, decisions: int) -> np.ndarray:
    """Return, for each COMP rise, the time until the comparator resets (COMP falls) or the SAR
    logic reads it (LOGIC rises), whichever comes first, wrapping into the next conversion."""

    sequence = AdcSequence.from_tb_params(tb).relative_to_init()
    symbol_s = 1.0 / float(tb.symbol_rate)
    comp = np.asarray([int(bit) for bit in sequence.comp])
    logic = np.asarray([int(bit) for bit in sequence.logic])
    rises = np.flatnonzero((comp == 1) & (np.roll(comp, 1) == 0))
    ends = np.flatnonzero(((comp == 0) & (np.roll(comp, 1) == 1)) | ((logic == 1) & (np.roll(logic, 1) == 0)))
    if len(rises) != decisions or not len(ends):
        raise ValueError(f"sequence must contain {decisions} COMP rises and a COMP fall or LOGIC rise")
    # symbols from each rise to every end, the next conversion's ends a whole conversion later
    after = (ends[None, :] - rises[:, None] - 1) % len(comp) + 1
    return np.min(after, axis=1) * symbol_s


def salogic(tb: TbParams, state: dict[str, np.ndarray], stage: int, decided: np.ndarray):
    """Write the counted stage from the decision, or reload the B state; return the new state."""

    after = {}
    for side, target in (("p", 1 - decided), ("n", decided)):
        after[side] = state[side].copy()
        if tb.dac_mode:
            after[side][:, stage] = target
        else:
            after[side][:] = np.asarray(getattr(tb, f"dac_bstate_{side}"), dtype=np.int64)
    return after


def convert_behavioral(
    params: AdcBehavioralParams, vin_diff_v: np.ndarray, vin_diff_slope_v_per_s: np.ndarray | None = None
) -> BehavioralConversions:
    """Convert one differential input per conversion, in order, through the four blocks.

    ``vin_diff_slope_v_per_s`` is the input slope at each sampling instant;
    the sampler's tracking lag needs it, and it defaults to a static input.
    """

    tb = params.tb
    vin_diff_v = np.asarray(vin_diff_v, dtype=np.float64)
    conversions = len(vin_diff_v)
    stages = len(capdac.Model.weights(tb.dut.cdac))
    comp_s, logic_s = _sequence_times(tb, stages + 1)
    windows_s = calc_decision_windows(tb, stages + 1)
    stage_tau_s = params.cdac.stage_tau_s or (params.cdac.settling_tau_s,) * stages
    stage_delay_s = params.cdac.stage_delay_s or (0.0,) * stages
    initial = {side: np.asarray(getattr(tb, f"dac_astate_{side}"), dtype=np.int64) for side in ("p", "n")}
    if any(len(value) != stages for value in initial.values()):
        raise ValueError(f"A states must hold one value per capacitor ({stages})")
    rng = np.random.default_rng(params.seed)
    # the reference's noise draws from a stream of its own, so the other sources draw alike with and
    # without it
    reference_rng = rng.spawn(1)[0]
    vin_cm_v = float(tb.vin_cm.dc)
    slope = np.zeros(conversions) if vin_diff_slope_v_per_s is None else np.asarray(vin_diff_slope_v_per_s)
    caps = {side: calc_side_capacitances(params.cdac, tb, side) for side in ("p", "n")}
    parasitic_f = params.cdac.parasitic_f
    load_f = {side: float(np.sum(main_f) + np.sum(diff_f)) + parasitic_f for side, (main_f, diff_f) in caps.items()}
    vref_v, diffcaps = float(tb.vdd_dac.dc), int(tb.dac_diffcaps)
    top = samp_model.Model.sample(
        tb.dut.samp,
        params.samp,
        {"p": vin_cm_v + vin_diff_v / 2, "n": vin_cm_v - vin_diff_v / 2},
        {"p": slope / 2, "n": -slope / 2},
        load_f=load_f,
        gate_v=float(tb.vdd_d.dc),
        rng=rng,
    )
    sampled = {side: top[side].copy() for side in ("p", "n")}
    state = {side: np.broadcast_to(initial[side], (conversions, stages)).copy() for side in ("p", "n")}
    dac_charge = np.zeros(conversions)
    transitions = np.zeros(conversions)
    writes = np.zeros(conversions)
    steps: list[tuple[float, float, np.ndarray]] = []
    bout = np.empty((conversions, stages + 1), dtype=np.uint8)
    # the comparator's SR latch holds its last decision: the previous conversion's last, a coin
    # toss here, before the first
    held = rng.integers(0, 2, conversions)
    # each side's capacitance whose bottom plates sit at the reference (main and difference plates),
    # kept up to date stage by stage
    at_main_f = {side: state[side] @ caps[side][0] for side in ("p", "n")}
    at_diff_f = {side: (state[side] ^ diffcaps) @ caps[side][1] for side in ("p", "n")}
    # the reference node's dip below its value, each conversion's, as of dip_s: every switch draws its
    # charge from the decoupling capacitance and the driver restores it with R C; the node has
    # recovered over the sampling phase by the first decision
    reference_tau_s = params.cdac.reference_r_ohm * params.cdac.reference_c_f
    droop = reference_tau_s > 0
    dip = np.zeros(conversions)
    dip_s = 0.0
    for decision in range(stages + 1):
        # Unsettled remainders of earlier updates decay with one time constant.
        seen = top["p"] - top["n"]
        if params.cdac.reference_noise_v or droop:
            # the reference's error (its dip, a noise sample) reaches each top plate through the
            # fraction of its load whose bottom plates sit at the reference
            reference_v = dip * np.exp(-(comp_s[decision] - dip_s) / reference_tau_s) if droop else 0.0
            if params.cdac.reference_noise_v:
                reference_v = reference_v + reference_rng.normal(0.0, params.cdac.reference_noise_v, conversions)
            for side, sign in (("p", 1.0), ("n", -1.0)):
                main_f, diff_f = caps[side]
                at_vref_f = state[side] @ main_f + (state[side] ^ diffcaps) @ diff_f
                seen = seen + sign * reference_v * at_vref_f / load_f[side]
        # each stage's step starts after its driver's delay and settles with its own time constant;
        # one not yet started is missing whole. A step 36 time constants on (2e-16 of itself, below a
        # double's resolution of it) or without settling is done and leaves the list
        unsettled = []
        for start_s, tau_s, step in steps:
            elapsed_s = comp_s[decision] - start_s
            if elapsed_s < 0:
                seen = seen - step
                unsettled.append((start_s, tau_s, step))
            elif tau_s > 0 and elapsed_s < 36 * tau_s:
                seen = seen - step * np.exp(-elapsed_s / tau_s)
                unsettled.append((start_s, tau_s, step))
        steps = unsettled
        decided = comp_model.Model.compare(
            tb.dut.comp, params.comp, seen, rng, vin_cm_v=vin_cm_v, window_s=float(windows_s[decision]), held=held
        )
        bout[:, decision] = decided
        held = decided
        if decision == stages:
            break
        differential_step = np.zeros(conversions)
        step_charge = np.zeros(conversions)
        if tb.dac_mode:
            # the counted stage alone switches: its column, in place
            for side, target in (("p", 1 - decided), ("n", decided)):
                main_f, diff_f = caps[side]
                before = state[side][:, decision].copy()
                state[side][:, decision] = target
                at_main_f[side] += (target - before) * main_f[decision]
                at_diff_f[side] += ((target ^ diffcaps) - (before ^ diffcaps)) * diff_f[decision]
                at_vref_f = at_main_f[side] + at_diff_f[side]
                top_step, charge, toggled = capdac.Model.switch_stage(
                    main_f, diff_f, parasitic_f, vref_v, diffcaps, decision, before, target, at_vref_f
                )
                top[side] = top[side] + top_step
                dac_charge += charge
                step_charge += charge
                transitions += toggled
                writes += target != before
                differential_step += top_step if side == "p" else -top_step
        else:
            after = salogic(tb, state, decision, decided)
            for side in ("p", "n"):
                main_f, diff_f = caps[side]
                top_step, charge, toggled = capdac.Model.switch(
                    main_f, diff_f, parasitic_f, vref_v, diffcaps, state[side], after[side]
                )
                top[side] = top[side] + top_step
                dac_charge += charge
                step_charge += charge
                transitions += toggled
                writes += np.sum(after[side] != state[side], axis=1)
                differential_step += top_step if side == "p" else -top_step
                at_main_f[side] = after[side] @ caps[side][0]
                at_diff_f[side] = (after[side] ^ diffcaps) @ caps[side][1]
            state = after
        switch_s = logic_s[decision] + stage_delay_s[decision]
        steps.append((switch_s, stage_tau_s[decision], differential_step))
        if droop:
            dip = dip * np.exp(-(switch_s - dip_s) / reference_tau_s) - step_charge / params.cdac.reference_c_f
            dip_s = switch_s

    # INIT reloads the A state with floating top plates, then SAMP forces them
    # to the new input; both edges start from the previous conversion's end.
    for side in ("p", "n"):
        previous_state = np.roll(state[side], 1, axis=0)
        init_state = np.broadcast_to(initial[side], (conversions, stages))
        main_f, diff_f = caps[side]
        top_step, charge, toggled = capdac.Model.switch(
            main_f, diff_f, parasitic_f, vref_v, diffcaps, previous_state, init_state
        )
        at_vref_f = init_state @ main_f + (init_state ^ diffcaps) @ diff_f
        dac_charge += charge - at_vref_f * (sampled[side] - (np.roll(top[side], 1) + top_step))
        transitions += toggled
        writes += np.sum(init_state != previous_state, axis=1)

    # Two registers per stage hold the P and N states and one the one-hot
    # stage counter, whose bits each rise and fall once per conversion. Every
    # LOGIC edge, including the INIT load, clocks all registers.
    registers = 3 * stages
    logic_edges = stages + 1
    writes += 2 * stages
    return BehavioralConversions(
        bout=bout,
        energy_j={
            "vdd_a": np.full(conversions, params.comp.decision_energy_j * (stages + 1)),
            "vdd_d": registers * logic_edges * params.salogic.clock_energy_j + writes * params.salogic.write_energy_j,
            "vdd_dac": float(tb.vdd_dac.dc) * dac_charge + transitions * params.cdac.driver_energy_j,
        },
        static_power_w={
            "vdd_a": params.comp.static_power_w,
            "vdd_d": registers * params.salogic.register_static_w,
            "vdd_dac": 4 * stages * params.cdac.driver_static_w,
        },
    )
