"""The capacitive DAC's behavioral model: each stage's settling to half the converter's LSB, its
drivers' delay and the time constant that reproduces it, each stage's step as drawn, and the
drawn array's gain against its design and its area, from the SPICE characterization of the same
``Params`` in the PDK (``flow.capdac.sweep``, looked up by ``flow.sweep.lookup``) and its layout; a
design that is not characterized, as designed (``Model.design``).

    model = capdac.Model.of("tsmc65", capdac.Params(bits=10, redundancy=capdac.Redundancy.BINARY, extra=0))
    dac = model.behavioral()  # the behavioral ADC's DAC: the drawn array's plates and settling

The behavioral ADC (``flow.adc.sim``) starts each stage's step its driver's delay after the
LOGIC edge and settles it as one exponential; with this model's time constants a step comes within
half an LSB exactly when the testbench's does. A characterization missing from the sweep's newest
run is simulated on first use (``simulate=True``) and kept under the build's models. The array's
plates are the design's at the reference the netlist draws them for, the PDK's typical supply, at
which the characterization runs (``Model.reference_v``), each stage's main plate drawn so that its
step, at the top plate's load the drawn gain gives, is the one measured (``Model.step_v``: a unit
drawn other than designed, at the PDK's smallest, moves its stage's step and the full scale); the
converter's reference only switches them (``Model.switch``).

``Model.drawn`` gives one of the characterization's Monte Carlo draws, the plates a converter on the
array calibrates on (``flow.adc.sim``): of one condition, the run at a percentile of what no
calibration recovers. ``Model.settling_meas`` is the measurement its settling run keeps, whose
steps, each stage's as measured (``Model.measured_steps``, ``Model.step_v``), are the weights a
converter on the array decodes with as its extracted ones
(``flow.analysis.io.read_cap_table``): the steps its plates give.

The switching is the model's own physics, which the behavioral ADC runs: ``Model.Behavioral``, the
DAC beyond its ``Params`` (what ``behavioral`` gives: each side's plates, the top plate's other
load, each stage's delay and time constant; and the reference's departures from
ideal, which the converter's reference study sets), and ``Model.switch``, a side's top-plate step,
the charge it draws from the reference and its bottom plates' transitions as its states change
(``Model.switch_stage`` where one stage alone switches). ``Model.weights`` and ``Model.plates`` are
the design's stage weights and plates (the arithmetic of ``params.py``, which the netlist and a
run's ``TbParams`` share), ``Model.draw`` a Pelgrom draw of plates.
"""

from __future__ import annotations

import importlib
import math
from dataclasses import dataclass
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.analysis.io import read_measurement
from flow.sweep.lookup import characterized, detail
from flow.sweep.runner import ROOT

from .analysis import analyze_mismatch, analyze_settling
from .params import Params, _design_plates, _weights


def _supply_v(pdk: str) -> float:
    """The PDK's typical supply: the reference at which the netlist draws an array's plates
    (``flow.capdac.subckt``) and the characterization runs (``flow.capdac.sweep.runs``)."""
    site = importlib.import_module(f"pdk.{pdk}.hdl21.site")
    return float(site.install.supply_voltage(h.pdk.Corner.TYP))


@dataclass(frozen=True)
class Model:
    """One capacitive DAC's per-stage settling and step, C0 first, and its drawn array's gain
    against its design and its area, as its SPICE characterization and its layout measured them, its
    plates designed at ``reference_v``."""

    pdk: str
    params: Params
    # the reference its plates are designed for: the PDK's typical supply, at which the netlist
    # draws them and the characterization runs (a design's own, ``Model.design``)
    reference_v: float
    settling_s: tuple[float, ...]  # from the state's edge to within half an LSB, the slower direction
    delay_s: tuple[float, ...]  # its driver's delay, from the state's edge to its bottom plate's 50 %
    tau_s: tuple[float, ...]  # (settling - delay) / ln(|step| / half an LSB)
    lsb_v: float
    gain: float  # the drawn steps against the design's: its plates over its top plate's whole load
    area_um2: float  # one side's layout, its drivers with it; NaN where it is not laid out
    # the measurement its settling run keeps, each stage's step as measured; None where none is kept
    # (a design's, ``Model.design``)
    settling_meas: Path | None = None
    # each stage's step in it (V, its slower direction's magnitude, ``Model.measured_steps``); None
    # where none is kept: the design's
    step_v: tuple[float, ...] | None = None

    @h.paramclass
    class Behavioral:
        """Capacitor array per side and its drivers; None capacitances are ideal."""

        main_p_f = h.Param(dtype=tuple[float, ...] | None, desc="C0-first P main capacitances", default=None)
        diff_p_f = h.Param(dtype=tuple[float, ...] | None, desc="C0-first P diff capacitances", default=None)
        main_n_f = h.Param(dtype=tuple[float, ...] | None, desc="C0-first N main capacitances", default=None)
        diff_n_f = h.Param(dtype=tuple[float, ...] | None, desc="C0-first N diff capacitances", default=None)
        parasitic_f = h.Param(dtype=float, desc="Top-plate capacitance to ground per side", default=0.0)
        settling_tau_s = h.Param(
            dtype=float, desc="Single-pole top-plate settling time constant; 0 is ideal", default=0.0
        )
        stage_tau_s = h.Param(
            dtype=tuple[float, ...] | None,
            desc="C0-first settling time constant after each stage switches; None uses settling_tau_s",
            default=None,
        )
        stage_delay_s = h.Param(
            dtype=tuple[float, ...] | None,
            desc="C0-first delay from the LOGIC edge to each stage's plates starting to move; None is 0",
            default=None,
        )
        driver_energy_j = h.Param(dtype=float, desc="Driver energy per bottom-plate transition", default=0.0)
        driver_static_w = h.Param(dtype=float, desc="Static power per bottom-plate driver", default=0.0)
        # the reference (VDD_DAC) as a driver of output resistance reference_r_ohm onto a decoupling
        # capacitance reference_c_f, with white noise reference_noise_v at the node; the defaults are
        # an ideal reference (the front end's own characterization), the reference study sets them
        reference_r_ohm = h.Param(dtype=float, desc="Reference driver's output resistance; 0 is ideal", default=0.0)
        reference_c_f = h.Param(dtype=float, desc="Reference node's decoupling capacitance; 0 is ideal", default=0.0)
        reference_noise_v = h.Param(
            dtype=float, desc="RMS reference noise at each decision, coupled by the plates held at it", default=0.0
        )

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        record = characterized("capdac", pdk, params, simulate=simulate)
        metrics = record["metrics"]
        stages = detail(record, "model_stage")["series"]
        # a record the layout step has not reached has no area
        area = metrics.get("layout_area_um2")
        kept = record.get("waves") or {}
        settling_meas = ROOT / kept["settling"] if "settling" in kept else None
        return cls(
            pdk=pdk,
            params=params,
            reference_v=_supply_v(pdk),
            settling_s=tuple(detail(record, "settling_stage")["series"]["settling"]),
            delay_s=tuple(stages["delay"]),
            tau_s=tuple(stages["time constant"]),
            lsb_v=metrics["lsb_v"],
            gain=metrics["gain"],
            area_um2=math.nan if area is None else float(area),
            settling_meas=settling_meas,
            step_v=None if settling_meas is None else tuple(map(float, Model.measured_steps(settling_meas))),
        )

    @classmethod
    def design(cls, pdk: str, params: Params, *, reference_v: float | None = None) -> Model:
        """``params`` as designed, where it is not characterized in ``pdk``: its top plates loaded by
        its plates alone (gain 1), not laid out (no area) and no measurement kept; each stage's
        drivers without delay and of the time constant ``flow.capdac.subckt`` sizes them for, which
        settles its step to half an LSB in ``settle_ps`` over ``settle_margin``: ln(2^(N+1) w / W)
        time constants for a stage of weight w of the total W. Its plates are designed at the
        reference ``reference_v`` and its LSB is at it; where None, the PDK's typical supply, at which
        the netlist draws the plates and the characterization runs."""
        if reference_v is None:
            reference_v = _supply_v(pdk)
        weights = _weights(params)
        settling_s = params.settle_ps * 1e-12 / params.settle_margin
        main_f, diff_f = _design_plates(params, reference_v)
        full_scale_v = reference_v * float(main_f.sum() - diff_f.sum()) / float(main_f.sum() + diff_f.sum())
        return cls(
            pdk=pdk,
            params=params,
            reference_v=reference_v,
            settling_s=(settling_s,) * len(weights),
            delay_s=(0.0,) * len(weights),
            tau_s=tuple(settling_s / math.log(2 ** (params.bits + 1) * weight / sum(weights)) for weight in weights),
            lsb_v=2 * full_scale_v / 2**params.bits,
            gain=1.0,
            area_um2=math.nan,
        )

    @classmethod
    def drawn(
        cls, pdk: str, params: Params, run: str, percentile: float
    ) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
        """One Monte Carlo draw of the characterization's run ``run`` (a condition of
        ``flow.capdac.sweep.runs``): its plates, (main, difference) for the P side then the N side (F,
        C0 first). The draw is the one at ``percentile`` of its runs ranked by what no calibration
        recovers, the converter's INL with its design weights breaking ties
        (``flow.capdac.analysis.analyze_mismatch``). Looked up, never simulated."""
        record = characterized("capdac", pdk, params, simulate=False)
        if run not in record.get("waves", {}):
            raise LookupError(f"the capacitive DAC's characterization has no Monte Carlo run {run}")
        result = analyze_mismatch(read_measurement(ROOT / record["waves"][run]))
        ranked = np.lexsort((result.inl_lsb, result.gap_lsb))
        index = int(ranked[round(percentile / 100 * (len(ranked) - 1))])
        return (
            (result.main_p_f[index], result.diff_p_f[index]),
            (result.main_n_f[index], result.diff_n_f[index]),
        )

    def behavioral(
        self,
        plates: tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]] | None = None,
    ) -> Model.Behavioral:
        """The behavioral ADC's DAC: each side's plates as drawn, (main, difference) for the P side
        then the N side: the design's at the reference they are drawn for (``Model.plates`` at
        ``reference_v``, whatever reference the converter switches them to), or ``plates`` drawn
        about them (a Monte Carlo draw: ``Model.drawn``, ``Model.draw`` of the design's), each top
        plate's whole load the design's plates over the drawn gain (the least-squares fit of the
        steps, which the heavy stages, drawn as designed, set), each stage's main plate taking the
        excess of its measured step over its design's at that load (``step_v``, each side half of
        the differential step): the plates give the measured steps, so their full scale is half the
        steps' sum and their weights are the extracted ones a converter decodes with; the rest of the
        load the parasitic. Each stage's delay and time constant, ``settling_tau_s`` the slowest's.
        The drivers' energy is not characterized: none. The reference is ideal: the converter sets
        its departures (``reference_*``) and scales the time constants."""
        main_f, diff_f = Model.plates(self.params, self.reference_v)
        design_f = float(main_f.sum() + diff_f.sum())
        # each stage's switched plate whose step at the load the gain gives is its measured one (each
        # side's half), less the design's: none as designed
        excess_f = (
            np.zeros_like(main_f)
            if self.step_v is None
            else np.asarray(self.step_v) / 2 * design_f / self.gain / self.reference_v - (main_f - diff_f)
        )
        (main_p, diff_p), (main_n, diff_n) = ((main_f, diff_f), (main_f, diff_f)) if plates is None else plates
        return Model.Behavioral(
            main_p_f=tuple(map(float, np.asarray(main_p) + excess_f)),
            diff_p_f=tuple(map(float, diff_p)),
            main_n_f=tuple(map(float, np.asarray(main_n) + excess_f)),
            diff_n_f=tuple(map(float, diff_n)),
            # the gain is the design's plates over the whole load: the rest of it, beside the plates
            # as drawn, is the parasitic
            parasitic_f=design_f * (1 / self.gain - 1) - float(excess_f.sum()),
            settling_tau_s=max(self.tau_s),
            stage_tau_s=self.tau_s,
            stage_delay_s=self.delay_s,
        )

    def full_scale_v(self, supply_v: float) -> float:
        """The differential full scale (+-) of a converter on this DAC at the reference ``supply_v``:
        the reference across the switched plates' share of the top plate's whole load
        (``behavioral``), main less difference with the difference plates in use; half the sum of
        the measured steps where its characterization keeps them."""
        dac = self.behavioral()
        load_f = float(np.sum(dac.main_p_f) + np.sum(dac.diff_p_f)) + dac.parasitic_f
        effective = float(np.sum(dac.main_p_f) - np.sum(dac.diff_p_f))
        return supply_v * effective / load_f

    @staticmethod
    def measured_steps(path: Path) -> np.ndarray:
        """Each stage's step the settling measurement ``path`` holds (V, C0 first, one that
        ``Model.settling_meas`` names), as ``analyze_settling`` measures it, in its slower direction:
        its magnitude, whose sign is that direction's. In proportion to its plates' switched
        capacitance as drawn: the steps the behavioral DAC's plates give (``behavioral``), and a
        converter's extracted weights (``flow.analysis.io.read_cap_table``)."""
        return np.abs(analyze_settling(read_measurement(path)).step_v)

    @staticmethod
    def weights(params: Params) -> tuple[int, ...]:
        """Each stage's weight in units, C0 first: its redundancy's, or the array's own
        (``Params.weights``). Twice each is its decision's weight in the converter's code, whose last
        decision weighs one."""
        return _weights(params)

    @staticmethod
    def plates(params: Params, reference_v: float) -> tuple[np.ndarray, np.ndarray]:
        """Each stage's main and difference plates as designed (F, C0 first) at the reference
        ``reference_v``: each side switches ``scale`` kT/C minimums at a full scale of the reference,
        a unit of weight its share of it, and a stage's main less its difference plates is its weight
        in units (unit capacitors have no difference plates). A run's ``TbParams.main_f`` and
        ``diff_f`` at its ``vdd``."""
        return _design_plates(params, reference_v)

    @staticmethod
    def plates_f(dac: Model.Behavioral, side: str, params: Params, reference_v: float) -> tuple[np.ndarray, np.ndarray]:
        """The behavioral DAC ``dac``'s plates of one side (``"p"`` or ``"n"``), main and difference (F,
        C0 first): its own, or where it gives none, those ``params`` designs at the reference
        ``reference_v`` (``plates``)."""
        ideal_main_f, ideal_diff_f = _design_plates(params, reference_v)
        main = getattr(dac, f"main_{side}_f")
        diff = getattr(dac, f"diff_{side}_f")
        return (
            ideal_main_f if main is None else np.asarray(main),
            ideal_diff_f if diff is None else np.asarray(diff),
        )

    @staticmethod
    def draw(capacitance_f: np.ndarray, *, pelgrom: float, rng: np.random.Generator) -> np.ndarray:
        """One Pelgrom draw of each capacitor of ``capacitance_f`` (F): sigma_C = ``pelgrom`` sqrt(C 1
        fF), Pelgrom's coefficient a fraction (0.001 is 0.1 %·sqrt(fF)), as the characterization's
        Monte Carlo draws a plate (``flow.layout.devices.momcap.netlist``); a capacitor of none stays
        none. Every capacitor draws from ``rng``, whatever the coefficient."""
        capacitance_f = np.asarray(capacitance_f, dtype=np.float64)
        return capacitance_f + rng.normal(0.0, pelgrom * np.sqrt(capacitance_f * 1e-15))

    @staticmethod
    def switch(
        main_f: np.ndarray,
        diff_f: np.ndarray,
        parasitic_f: float,
        vref_v: float,
        diffcaps: int,
        before: np.ndarray,
        after: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """One side switching from the states ``before`` to ``after`` (0 or 1, a row a conversion, a
        column a stage, C0 first), its bottom plates between ground and the reference ``vref_v``:
        its floating top plate's step, the charge it draws from the reference and its bottom plates'
        transitions (two a stage that switches), a value a conversion. The top plate is loaded by
        the main plates ``main_f``, the difference plates ``diff_f`` and ``parasitic_f``; each plate
        at the reference after the switch draws C (dV_bottom - dV_top).

        A stage's main bottom plate follows its state, its difference plate the state XOR
        ``diffcaps``. 1: the complement, as capdac's arrays switch, whose difference drivers invert
        and main drivers do not (an odd and an even chain of inverters): the subtraction is wired
        in, and the converter's logic sets the states alone. 0: with the main plate, adding to it
        (FRIDA-1's array switches either way)."""
        total_f = np.sum(main_f) + np.sum(diff_f) + parasitic_f
        main_step = vref_v * (after - before)
        diff_after = after ^ diffcaps
        diff_step = vref_v * (diff_after - (before ^ diffcaps))
        top_step = (main_step @ main_f + diff_step @ diff_f) / total_f
        charge = (after * (main_step - top_step[:, None])) @ main_f + (
            diff_after * (diff_step - top_step[:, None])
        ) @ diff_f
        transitions = 2 * np.sum(after != before, axis=1)
        return top_step, charge, transitions

    @staticmethod
    def switch_stage(
        main_f: np.ndarray,
        diff_f: np.ndarray,
        parasitic_f: float,
        vref_v: float,
        diffcaps: int,
        stage: int,
        before: np.ndarray,
        after: np.ndarray,
        at_vref_f: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """``switch`` where the stage ``stage`` alone switches, from ``before`` to ``after`` (its
        column, a value a conversion): the same top-plate step, charge and transitions in one
        column's work, ``at_vref_f`` the capacitance whose bottom plates sit at the reference after
        the switch (main and difference plates, a value a conversion)."""
        total_f = np.sum(main_f) + np.sum(diff_f) + parasitic_f
        main_step = vref_v * (after - before)
        diff_after = after ^ diffcaps
        diff_step = vref_v * (diff_after - (before ^ diffcaps))
        top_step = (main_step * main_f[stage] + diff_step * diff_f[stage]) / total_f
        # switch's charge: the switching stage's own term, less the top-plate step across every
        # plate at the reference
        charge = after * main_step * main_f[stage] + diff_after * diff_step * diff_f[stage] - top_step * at_vref_f
        return top_step, charge, 2 * (after != before)
