"""The ADC's behavioral model: its blocks' models, each built from the same parameters its netlist
generator takes (``AdcParams``), switched by the SAR loop of ``flow.adc.behavioral``.

    model = AdcModel.of("tsmc65", AdcParams(adc_bits=12, cdac=..., samp=..., comp=...))
    tb = model.tb(conversions=8192, rate_hz=10e6, vin_diff=h.Vsin.Params(...))
    model.capture(tb, path)  # a MeasAdc, as a SPICE capture of the same AdcTbParams writes one

The blocks: the comparator (``flow.comp.model``), the sampling switch (``flow.samp.model``), the
capacitor array (``flow.caparray.model``) and its drivers (``flow.capdriver.model``), each from its
own characterization or extraction in the PDK. The SAR logic is the fixed digital netlist built by
OpenROAD: it is not characterized, so its energies are the ones fitted to the FRIDA-2 three-layer
PEX transient (``SALOGIC``). The DAC rail's noise (``RAIL_NOISE_V``) is assumed, not characterized.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import hdl21 as h
import numpy as np

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
from flow.caparray.model import CapArrayModel
from flow.caparray.subckt import get_caparray_weights
from flow.capdriver.model import CapDriverModel, stage_drivers
from flow.capdriver.subckt import CapDriverParams, Cells
from flow.comp.model import CompModel
from flow.samp.model import SampModel
from flow.scans.scan_adc import convert_dac_caps_to_adc_weights
from flow.scans.scan_behavioral import build_adc_interface_wave, calc_source_value

# The SAR logic's energies, fitted to the FRIDA-2 three-layer PEX transient (10 MS/s): 22.85 pJ a
# conversion and 1.338 uW idle on VDD_D over its 48 registers (flow.scans.scan_behavioral).
SALOGIC = SalogicBehavioralParams(clock_energy_j=25.5e-15, write_energy_j=31.9e-15, register_static_w=27.9e-9)
# FRIDA's input common mode at TSMC65's 1.2 V supply, scaled with the PDK's supply elsewhere
VIN_CM_FRACTION = 0.700 / 1.2
# The DAC reference rail's (VDD_DAC's) RMS noise at each decision, white from one decision to the
# next: an assumption about a decoupled on-chip supply, not a measurement. Each side's plates at the
# rail couple it to their top plate, so differentially it cancels where both sides hold equal
# capacitance at the rail (mid-scale) and grows toward either end of the codes.
RAIL_NOISE_V = 0.5e-3


@dataclass(frozen=True)
class AdcModel:
    """A SAR ADC's blocks, as their characterizations and extractions measured them."""

    pdk: str
    params: AdcParams
    comp: CompModel
    samp: SampModel
    cdac: CapArrayModel
    drivers: tuple[CapDriverModel, ...]
    rail_noise_v: float = RAIL_NOISE_V  # VDD_DAC's RMS noise at each decision (assumed)

    @classmethod
    def of(cls, pdk: str, params: AdcParams, *, simulate: bool = True, rail_noise_v: float = RAIL_NOISE_V) -> AdcModel:
        cdac = CapArrayModel.of(pdk, params.cdac)
        driver = CapDriverParams(n_stages=len(cdac.main_f), strengths=params.cdac.driver_strengths, cells=Cells.GENERIC)
        return cls(
            pdk=pdk,
            params=params,
            comp=CompModel.of(pdk, params.comp, simulate=simulate),
            samp=SampModel.of(pdk, params.samp, simulate=simulate),
            cdac=cdac,
            drivers=stage_drivers(pdk, driver, np.maximum(cdac.main_f, cdac.diff_f), simulate=simulate),
            rail_noise_v=rail_noise_v,
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
        """Each stage's top-plate settling time constant, C0 first: its driver through its plate in
        series with the rest of the load, the slower of its main and difference plates."""
        load = self.cdac.load_f
        return tuple(
            max(driver.resistance_ohm * plate * (load - plate) / load for plate in (main, diff))
            for driver, main, diff in zip(self.drivers, self.cdac.main_f, self.cdac.diff_f, strict=True)
        )

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
    ) -> AdcBehavioralParams:
        """The behavioral ADC: one capacitor draw from ``seed`` (none where ``unit_mismatch`` is 0);
        ``quiet`` silences the "sampling" noise, the DAC "rail" noise or the comparator's noise alone
        ("comparator_noise": its delay stays, so a late decision still holds the last bit), or makes
        the "comparator" ideal (no noise, never late). Each stage's plates start moving its driver's
        intrinsic delay after the LOGIC edge (the SAR register's clock-to-output is not modeled) and
        settle with the stage's own RC, times ``tau_scale`` (0: ideal, every step whole at once)."""
        rng = np.random.default_rng(seed)
        plates = {}
        for side in ("p", "n"):
            main, diff = self.cdac.draw(unit_mismatch=unit_mismatch, rng=rng)
            plates |= {f"main_{side}_f": tuple(map(float, main)), f"diff_{side}_f": tuple(map(float, diff))}
        samp = self.samp.behavioral(load_f=self.cdac.load_f)
        comp = self.comp.behavioral(vin_cm_v=float(tb.vin_cm.dc))
        if "sampling" in quiet:
            samp = type(samp)(**{**samp.__dict__, "noise_v": 0.0, "jitter_s": 0.0})
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
                stage_delay_s=tuple(driver.intrinsic_delay_s if tau_scale else 0.0 for driver in self.drivers),
                driver_energy_j=float(np.mean([driver.energy_j for driver in self.drivers])),
                reference_noise_v=0.0 if "rail" in quiet else self.rail_noise_v,
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
    ) -> MeasAdc:
        """Convert every conversion of ``tb`` and write the MeasAdc with its supply power to ``path``
        (kept in memory alone where it is None); its ``cap_table`` readback is the array's
        extraction, the decoding's "extracted" weights. ``quiet`` and ``tau_scale``: as
        ``behavioral``'s."""

        params = self.behavioral(tb, seed=seed, unit_mismatch=unit_mismatch, quiet=quiet, tau_scale=tau_scale)
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
