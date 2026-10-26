"""The ADC's behavioral model: its blocks' models, each built from the same parameters its netlist
generator takes (``AdcParams``), switched by the SAR loop of ``flow.adc.behavioral``.

    model = AdcModel.of("tsmc65", AdcParams(adc_bits=12, cdac=..., samp=..., comp=...))
    tb = model.tb(conversions=8192, rate_hz=10e6, vin_diff=h.Vsin.Params(...))
    model.capture(tb, path)  # a MeasAdc, as a SPICE capture of the same AdcTbParams writes one

The blocks: the comparator (``flow.comp.model``), the sampling switch (``flow.samp.model``), the
capacitor array (``flow.caparray.model``) and its drivers (``flow.capdriver.model``, derived from the
array's plates: ``flow.capdriver.model.driver_strengths``), each from its own characterization or
extraction in the PDK; the DAC's settling, stage by stage, from the SPICE characterization of the
array with its drivers (``flow.cdac.model``, of the converter's array at its resolution,
``cdac.adc_array``: ``python -m flow run cdac`` runs it ahead), or, where there is none, estimated
from the drivers' resistance and delay with a warning. The SAR logic is the fixed digital netlist built by
OpenROAD: it is not characterized, so its energies are the ones fitted to the FRIDA-2 three-layer
PEX transient (``SALOGIC``). The DAC's reference is ideal here, the front end's own characterization;
a ``Reference`` (driver resistance, decoupling capacitance, noise) is what the reference study
(``flow.adc.reference``) varies to find the reference buffer's requirements.
"""

from __future__ import annotations

import importlib
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import hdl21 as h
import numpy as np

import flow.cdac.model as cdac_model
import flow.comp.model as comp_model
import flow.samp.model as samp_model
from flow import cdac
from flow.adc.behavioral import (
    AdcBehavioralParams,
    CdacBehavioralParams,
    SalogicBehavioralParams,
    build_continuous_sequence,
    convert_behavioral,
)
from flow.adc.sequences import AdcSequence
from flow.adc.sim import AdcTbParams
from flow.adc.subckt import AdcParams
from flow.analysis.io import write_measurement
from flow.analysis.types import MeasAdc, MeasInfo
from flow.caparray.layout import array_name
from flow.caparray.model import CapArrayModel
from flow.caparray.subckt import get_caparray_weights
from flow.capdriver.model import CapDriverModel, driver_strengths, stage_drivers
from flow.capdriver.subckt import CapDriverParams, Cells
from flow.scans.scan_adc import convert_dac_caps_to_adc_weights
from flow.scans.scan_behavioral import build_adc_interface_wave, calc_source_value

# The SAR logic's energies, fitted to the FRIDA-2 three-layer PEX transient (10 MS/s): 22.85 pJ a
# conversion and 1.338 uW idle on VDD_D over its 48 registers (flow.scans.scan_behavioral).
SALOGIC = SalogicBehavioralParams(clock_energy_j=25.5e-15, write_energy_j=31.9e-15, register_static_w=27.9e-9)
# FRIDA's input common mode at TSMC65's 1.2 V supply, scaled with the PDK's supply elsewhere
VIN_CM_FRACTION = 0.700 / 1.2


@dataclass(frozen=True)
class Reference:
    """The DAC's reference (VDD_DAC) as its buffer would supply it: a driver of output resistance
    ``r_ohm`` onto a decoupling capacitance ``c_f`` (each switch draws its charge from the
    capacitance, the driver restores it with R C: a code-dependent dip at the next comparison), and
    white noise ``noise_v`` RMS at the node at each decision. Zero is ideal: no dip without both,
    no noise."""

    r_ohm: float = 0.0
    c_f: float = 0.0
    noise_v: float = 0.0


IDEAL_REFERENCE = Reference()
# what ``AdcModel.behavioral``'s ``quiet`` silences or makes ideal
QUIET = frozenset({"sampler", "sampling", "comparator", "comparator_noise"})
# the array a converter calibrates on (``AdcModel.drawn``): of its CDAC's Monte Carlo
# (``flow.cdac``), the middle condition's draw (0.5 %·sqrt(fF), 50 ppm/mm) at the 90th percentile
# of what no calibration recovers
DRAWN_RUN = "mc_a5_g50"
DRAWN_PERCENTILE = 90.0


@dataclass(frozen=True)
class AdcModel:
    """A SAR ADC's blocks, as their characterizations and extractions measured them."""

    pdk: str
    params: AdcParams
    comp: comp_model.Model
    samp: samp_model.Model
    cdac: CapArrayModel
    drivers: tuple[CapDriverModel, ...]
    settling: cdac_model.Model | None = None  # the DAC's SPICE settling by stage; None: the RC estimate
    # the plates the converter calibrates on, (main, diff) for the P side then the N side: its CDAC's
    # Monte Carlo draw (DRAWN_RUN at DRAWN_PERCENTILE, drawn in SPICE); None where none is characterized
    drawn: tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]] | None = None

    @classmethod
    def of(cls, pdk: str, params: AdcParams, *, simulate: bool = True) -> AdcModel:
        array = CapArrayModel.of(pdk, params.cdac)
        # the drivers the array's plates call for (flow.capdriver.model.driver_strengths)
        strengths = driver_strengths(pdk, params.cdac, array, simulate=simulate)
        driver = CapDriverParams(n_stages=len(array.main_f), strengths=strengths, cells=Cells.GENERIC)
        # the DAC's characterization, of the converter's array at its resolution (n_dac + 1 bits), is
        # looked up, never run here (minutes of SPICE an array, which every converter on the array
        # would wait for)
        try:
            dac = cdac.adc_array(pdk=pdk, array=array_name(params.cdac))
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
        return len(get_caparray_weights(self.params.cdac))

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

    def tb(self, *, conversions: int, rate_hz: float, vin_diff) -> AdcTbParams:
        """The testbench of ``conversions`` at ``rate_hz`` with the continuous sequence (8 symbols a
        decision), an alternating A state and the PDK's supply on every rail."""
        sequence = build_continuous_sequence(self.stages)
        supply = h.Vdc.Params(dc=round(self.supply_v, 4))
        return AdcTbParams(
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
        tb: AdcTbParams,
        *,
        seed: int = 0,
        unit_mismatch: float = 0.0,
        quiet: tuple[str, ...] = (),
        tau_scale: float = 1.0,
        reference: Reference | None = None,
        drawn: bool = False,
    ) -> AdcBehavioralParams:
        """The behavioral ADC: the CDAC's SPICE draw where ``drawn`` (``AdcModel.drawn``; nominal
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
            cdac=CdacBehavioralParams(
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
            salogic=SALOGIC,
            seed=seed,
        )

    def capture(
        self,
        tb: AdcTbParams,
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
        code_weights = np.asarray(convert_dac_caps_to_adc_weights(get_caparray_weights(tb.dut.cdac)), dtype=np.int64)
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
                instruments={"model": f"{AdcModel.__module__}.AdcModel"},
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
