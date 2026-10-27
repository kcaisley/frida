"""The ADC's design space (``flow.sweep``), by the behavioral model (``flow.adc.model``) of its
characterized blocks: the plain product of its components, each converter given by its parameters;
in TSMC65 the full product below, in the other PDKs a smaller one.

Every converter samples on its top plates, makes one free comparison before any capacitor switches
and fires the comparator again after the last one switches: an N-bit converter has an N-1-step DAC
(``adc_bits = n_dac + 1``) and n_dac + n_extra + 1 decisions. Its arrays are the ADC study's
(``flow.caparray.layout.ADC_ARRAYS``: three-metal unit-length arrays, each sized through its 3-D
extraction in each PDK, ``flow.caparray.sizing``). Every
array's full scale is at least 80 % of the reference and its sampled noise at most its quantization
noise there: each resolution's least switched capacitance is the larger of the two constraints'
for its most demanding array, and each array switches one or two times it (``cap_scale``) at the
split between its length-scaled binary and unary rows that keeps both with its outline nearest
twice as tall as wide (one side's array: the two side by side make about a square). Its
drivers are derived from its extracted plates (``flow.capdriver.model.driver_strengths``), each stage
sized to settle in about 1 ns.

The product, nothing pruned:

- the comparators of the comparator grid (``COMP_GRID``: five noise levels by four
  delays, FRIDA-1's StrongARM among them at its fabricated sizes);
- the samplers (``SAMPLER_STEPS``), an on-resistance ladder: FRIDA-1's transmission gate (32
  minimum widths, minimum length) the worst, then the bootstrapped NMOS switch at 32, 64, 112 and
  160 minimum widths (``samp.boost_ladder``, each boosted alike), about a half, a
  quarter, a seventh and a tenth of the gate's resistance; none with half-size dummy switches, as
  FRIDA-1's;
- the arrays, 10 at each resolution and scale: binary, and each scheme
  (``flow.caparray.subckt.RedunStrat``: the MSBs split, the LSBs split, FRIDA's MSB redistribution)
  with 2, 4 and 6 extra cycles, every one of the binary total weight;
- the resolutions, 10, 12 and 14 bits;
- the switched capacitance, one and two times the resolution's least (``cap_scale``);
- and FRIDA-1's array (``RADIX17``: 12 bits on MSB redistribution with 5 extra cycles, 17
  decisions) at two times the 12-bit least, near its drawn size.

20 x 5 x (10 x 3 x 2 + 1) = 6,100 converters in TSMC65. In the other PDKs, where the arrays and
the blocks are the same study's but the comparator grid is the PDK's own (``flow.comp.sweep``), each
array with the PDK's StrongARM noise ladder at about FRIDA-1's speed (``comparators``) and the widest
bootstrapped switch (``samplers``): 244 to 305 converters a PDK. The design space is a grid
(``converters``, docs/pipeline.md): one space per resolution, its arrays, comparators and samplers
values by name.

Each instance runs the campaign of ``flow.adc.campaign`` and draws its figures
(``flow.adc.figures``) for the viewer; its captures stay in memory, so its run is its record.
"""

from __future__ import annotations

import math
from pathlib import Path

import hdl21 as h

from flow import comp, samp
from flow.caparray.layout import ADC_ARRAYS, ADC_BITS, FRIDA1_ADC_ARRAY, adc_arrays
from flow.caparray.subckt import CapArray, CapArrayConfig, CapArrayParams
from flow.pipeline import Pdk, Record, grid, values, widen

from .subckt import AdcParams

# The comparator grid: five levels of input-referred noise (rows, at the nominal common mode) by
# four of delay (columns, at 0.5 mV), each cell the characterized TSMC65 comparator of least energy
# per decision within 15 % of the noise and 20 % of the delay (flow/comp/readme.md), FRIDA-1's at
# 200 uV and 2 ns; each from the comparator's grids by name (comp.base_strongarm, comp.dynamic_bias)
GRID_NOISE_V = (200e-6, 150e-6, 100e-6, 70e-6, 50e-6)
GRID_DELAY_S = (0.5e-9, 1.0e-9, 1.5e-9, 2.0e-9)
_STRONGARM = {name: space.base for name, space in comp.base_strongarm.spaces(Pdk.TSMC65).items()}
_DYNAMIC = {name: space.base for name, space in comp.dynamic_bias.spaces(Pdk.TSMC65).items()}
COMP_GRID = (
    # 0.5 ns                       1 ns                           1.5 ns                          2 ns
    _STRONGARM["tail_l=14, k=3"],  _DYNAMIC["ratio=3.5, k=0.75"], _DYNAMIC["ratio=2.75, k=0.75"], comp.FRIDA1,  # 200 uV
    _STRONGARM["tail_l=14, k=6"],  _DYNAMIC["ratio=3.5, k=1.5"],  _DYNAMIC["ratio=2.75, k=1.5"],  _DYNAMIC["ratio=2.25, k=1.5"],  # 150 uV
    _STRONGARM["tail_l=14, k=12"], _DYNAMIC["ratio=3.5, k=3"],    _DYNAMIC["ratio=2.75, k=3"],    _DYNAMIC["ratio=2.25, k=3"],  # 100 uV
    _STRONGARM["tail_l=14, k=32"], _DYNAMIC["ratio=3.5, k=6"],    _DYNAMIC["ratio=2.75, k=6"],    _DYNAMIC["ratio=2.25, k=6"],  # 70 uV
    _STRONGARM["tail_l=14, k=64"], _DYNAMIC["ratio=3.5, k=12"],   _DYNAMIC["ratio=2.75, k=12"],   _DYNAMIC["ratio=2.25, k=12"],  # 50 uV
)  # fmt: skip
# each cell's noise and delay, in COMP_GRID's order (the noise outer)
COMP_GRID_TARGETS = tuple((noise, delay) for noise in GRID_NOISE_V for delay in GRID_DELAY_S)
# FRIDA-1's comparator, then each quieter at about its speed (the grid's 2 ns column)
COMP_NOISE_STEPS = COMP_GRID[len(GRID_DELAY_S) - 1 :: len(GRID_DELAY_S)]
COMPARATORS: tuple[comp.Params, ...] = COMP_GRID
# the samplers, an on-resistance ladder: FRIDA-1's transmission gate (32 minimum widths, minimum
# length) the worst, then the bootstrapped NMOS switch's rungs (samp.boost_ladder: 32 minimum widths
# with the doubled boost capacitor, then 64, 112 and 160, boosted alike); none with dummy switches
TGATE = samp.FRIDA1
SAMPLER_STEPS = (TGATE, *(space.base for space in samp.boost_ladder.spaces(Pdk.TSMC65).values()))
RESOLUTIONS = ADC_BITS  # 10, 12 and 14 bits
# FRIDA-1's converter: its array (12 bits in 16 stages, MSB redistribution with 5 extra cycles) at
# two of the 12-bit least switched capacitance
FRIDA1_BITS = 12
FRIDA1_ARRAY = FRIDA1_ADC_ARRAY


def arrays(bits: int, cap_scale: int = 1) -> list[CapArrayConfig]:
    """A ``bits`` converter's 10 arrays at ``cap_scale``: binary, and each scheme with 2, 4 and 6
    extra cycles (``flow.caparray.layout.adc_arrays``)."""
    return adc_arrays(bits, cap_scale)


def comparators(pdk: str) -> dict[str, comp.Params]:
    """The comparators of ``pdk``'s converters by name: TSMC65's grid (``COMP_GRID``, by noise and
    delay, ``200uV_2ns``); elsewhere the PDK's StrongARM noise ladder at its longest tail (its
    comparator grid's, ``comp.base_strongarm``: 200 to 50 uV where its noise floor reaches them,
    about 2 ns at 0.5 mV, FRIDA-1's speed), by its width factor (``k2.5``)."""
    if pdk == "tsmc65":
        return {
            f"{noise * 1e6:g}uV_{delay * 1e9:g}ns": params
            for (noise, delay), params in zip(COMP_GRID_TARGETS, COMP_GRID, strict=True)
        }
    ladder = {name: space.base for name, space in comp.base_strongarm.spaces(pdk).items()}
    longest = max(params.tail_l for params in ladder.values())
    return {f"k{name.rsplit('k=', 1)[1]}": params for name, params in ladder.items() if params.tail_l == longest}


def samplers(pdk: str) -> dict[str, samp.Params]:
    """The samplers of ``pdk``'s converters by name: TSMC65's ladder (``SAMPLER_STEPS``: FRIDA-1's
    transmission gate, ``frida1``, then ``samp.boost_ladder``'s rungs by name); elsewhere the
    bootstrapped switch's widest rung alone, so the array and the comparator set the converter."""
    ladder = {f"boost_{name}": space.base for name, space in samp.boost_ladder.spaces(pdk).items()}
    if pdk == "tsmc65":
        return {"frida1": TGATE, **ladder}
    return dict([list(ladder.items())[-1]])


@grid
def converters(pdk: Pdk) -> dict[str, AdcParams]:
    """Every comparator with every sampler and ADC array (``ADC_ARRAYS``: each resolution's arrays
    at both scales, and FRIDA-1's), one space per resolution, each array at its resolution
    (``adc_bits = n_dac + 1``): in TSMC65 the full product, elsewhere the PDK's smaller one
    (``comparators``, ``samplers``), each array sized through its extraction there. A converter is
    labelled by its resolution and its parts' names, ``converters(12b, cdac=12b_binary_x1,
    comp=200uV_2ns, samp=frida1)``."""
    folder = pdk.name.lower()
    spaces = {}
    for bits in RESOLUTIONS:
        space = widen(AdcParams(adc_bits=bits, comp=comp.FRIDA1, samp=samp.FRIDA1))
        space.cdac = values({name: cdac for name, cdac in ADC_ARRAYS.items() if cdac.n_dac + 1 == bits})
        space.comp = values(comparators(folder))
        space.samp = values(samplers(folder))
        spaces[f"{bits}b"] = space
    return spaces


def _metastability(model) -> dict[str, float]:
    """The comparator's regeneration time constant, the time a decision has at the nominal rate
    (the shortest of its sequence's windows), and the input below which it is late there, in LSB:
    the measured delay extrapolated by the time constant, V0 * exp(-(window - t0) / tau)."""
    from .behavioral import calc_decision_windows
    from .campaign import NOMINAL_RATE_HZ

    tb = model.tb(conversions=1, rate_hz=NOMINAL_RATE_HZ, vin_diff=h.Vdc.Params(dc=0.0))
    window_s = float(min(calc_decision_windows(tb, model.stages + 1)))
    tau_s = model.comp.regeneration_tau_s
    # a delay curve that does not grow as the input falls (a fast latch measured above its
    # regeneration) has no time constant to extrapolate: no input is known to be late
    late_v = (
        model.comp.delay_table_v[0] * math.exp(-(window_s - model.comp.delay_table_s[0]) / tau_s)
        if tau_s > 0
        else math.nan
    )
    return {
        "comp_regeneration_tau_s": tau_s,
        "decision_window_s": window_s,
        "metastable_input_lsb": late_v / (2 * model.full_scale_v / 2**model.params.adc_bits),
    }


def AdcBlocks(params: AdcParams) -> h.Module:
    """The ADC's analog blocks for the geometry metrics: the comparator, and a sampler and a
    capacitor array a side (the SAR logic is the fixed digital netlist)."""
    blocks = h.Module(name="AdcBlocks")

    def place(module: h.Module, name: str) -> None:
        # each port on a signal of its own: the compile wants every port connected
        connections = {
            port: blocks.add(h.Signal(width=signal.width), name=f"{name}_{port}")
            for port, signal in module.ports.items()
        }
        blocks.add(module(**connections), name=name)

    place(comp.netlist(params.comp), "comp")
    for side in ("p", "n"):
        place(samp.netlist(params.samp), f"samp_{side}")
        place(CapArray(CapArrayParams(cdac=params.cdac)), f"cap_{side}")
    return blocks


GENERATOR = AdcBlocks
# a converter is characterized in Python alone (the behavioral model on its blocks' records, no
# circuit compiled), so a worker process runs this many as one task
tasks_per_worker = 10


def cost(pdk: str, params: AdcParams) -> float:
    """An instance's relative run time, for the runner's longest-first order: its conversions grow
    with the codes, each conversion with its decisions."""
    return 2.0**params.adc_bits * (params.cdac.n_dac + params.cdac.n_extra + 1)


def characterize(run_dir: Path, pdk: str, params: AdcParams) -> Record:
    """The campaign's captures, converted and kept in memory, and the metrics and figures they
    give (``flow.adc.figures``): the viewer shows the figures (the record's details) and no
    waveform of an ADC instance, so no capture is written (a run is its ``instance.json``)."""
    from .campaign import campaign, ladder_names
    from .figures import adc_figures
    from .model import AdcModel
    from .reference import requirements

    model = AdcModel.of(pdk, params)
    plan = campaign(model.tb, model.full_scale_v, params.adc_bits)
    captures = {}
    for name, capture in plan.items():
        captures[name] = model.capture(
            capture.tb,
            None,
            seed=capture.seed,
            noise_seed=capture.noise_seed,
            unit_mismatch=capture.unit_mismatch,
            quiet=("sampling", "comparator") if capture.noise_free else capture.quiet,
            tau_scale=capture.tau_scale,
            drawn=capture.drawn,
        )
    # the behavioral model alone can keep one noise source at a time
    for name, quiet in (("noise_sampling", ("comparator",)), ("noise_comparator", ("sampling",))):
        captures[name] = model.capture(plan["noise"].tb, None, quiet=quiet)
    metrics, details = adc_figures(captures)
    # the reference buffer's requirements this converter sets, apart from its own ENOB
    reference_metrics, reference_details = requirements(model, plan[ladder_names()[-1]])
    metrics |= reference_metrics | {
        "stages": float(model.stages),  # the switched capacitors a side
        "decisions": float(model.stages + 1),  # a conversion's comparator decisions
        "full_scale_v": model.full_scale_v,
        "settling_tau_s": model.settling_tau_s,
        "comp_noise_v": model.comp.noise_v,
        "comp_delay_s": model.comp.delay_s,
        **_metastability(model),
    }
    return Record(metrics=metrics, details=details + reference_details)
