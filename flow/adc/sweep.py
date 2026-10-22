"""The ADC's design space (``flow.sweep``), in TSMC65, by the behavioral model (``flow.adc.model``)
of its characterized blocks: two studies of where redundancy pays.

The redundancy study: five comparators (216 uV to 1.2 mV of noise, 0.13 to 4.6 ns of delay) at 10
to 14 bits, each with 0 to 6 redundant decisions spent five ways (FRIDA's sub-radix-2 overlay, or
repeated binary weights at the start, along the chain, at the end or at both ends), so 10 to 20
decisions a conversion, on the three-metal difference-capacitor arrays (the ADC variants,
``flow.caparray.layout.ADC_VARIANTS``, each extracted in TSMC65 only, so the other PDKs give no
instance); the three samplers compared on the FRIDA-like comparators with binary or overlay arrays,
every other converter with the four-times-wider gate.

The comparators: a StrongARM near FRIDA-1's (its long-channel sizes in round multiples; 249 uV,
2.1 ns at 0.5 mV in TSMC65) and the lowest-noise double tail that decides well within the
comparator's 2.5 ns at 10 MS/s with 16 stages (the modified double tail at the same sizes: 264 uV,
1.3 ns). The model takes their noise and offset over the common mode, their energy, and their delay
over the input: a decision too small to regenerate before the SAR logic reads it is late. The
samplers: FRIDA-1's transmission gate (179-562 ohm over the input, its tracking distortion limits
the 12-bit converters near Nyquist), the same four times wider (54-160 ohm, about 11 dB more SFDR)
and the bootstrapped switch with the doubled boost capacitor (191-283 ohm, the flattest, about
90 dB).

The specification study: a 14-bit converter with 1.4 pF of switched capacitance a side in 7 pF of
top-plate load (the rest routing, the sampler, the comparator and dummies), FRIDA-1's transmission
gate at 32 minimum widths and minimum length, and a comparator of about 300 uV input-referred
noise: sixteen proposed arrays, each scaled to the same 1.4 pF, with three comparators near that
noise from slow (2.5 ns) to fast (0.14 ns), whose delay decides whether the comparator or the DAC
limits the conversion. Each array is given as its search steps (each its nominal weight plus a
non-binary addition), every step a capacitor: plain binary, binary with added LSB-end decisions,
double or triple conversion at the LSB or the LSB+1, mildly non-binary steps there, and additions
at both ends and at the MSB. The arrays are ideal (``CapArrayConfig.parasitic_cap``: each stage its
weight in unit capacitors, nothing extracted), so the comparison is of the schemes alone. The
converter samples on its top plates and makes one more decision, a free first comparison at
mid-scale, alike for every array: its code has a bit more than the specification's (15 bits over
the same full scale in volts), so the arrays compare by ENOB and SNDR, not by counts of the finer
LSB.

Each instance runs the campaign of ``flow.adc.campaign`` (about 10 M behavioral conversions, most
of them the mismatch study's) and draws its figures (``flow.adc.figures``) for the viewer.
"""

from __future__ import annotations

import math
from pathlib import Path

import hdl21 as h

from flow.caparray.layout import ADC_VARIANTS
from flow.caparray.subckt import CapArray, CapArrayConfig, CapArrayParams, RedunStrat
from flow.comp.sim import TOPOLOGIES as COMP
from flow.comp.subckt import Comp
from flow.comp.sweep import FRIDA1_LIKE, FRIDA1_LIKE_LONG, X0P5, X4, comparator
from flow.samp import sweep as samp_sweep
from flow.samp.subckt import Samp, SampParams, SwitchType
from flow.sweep import Record

from .subckt import AdcParams

# the comparators (input-referred noise and delay at 0.1 mV in TSMC65), from quiet and slow to fast
# and noisy: where the comparator's delay limits the conversion, and how much of its noise
# redundancy can absorb
DOUBLE_TAIL_LONG = comparator(COMP["double_tail_self_timed"], FRIDA1_LIKE_LONG)  # 216 uV, 4.6 ns
STRONGARM_FRIDA1 = comparator(COMP["strongarm"], FRIDA1_LIKE)  # 249 uV, 2.5 ns
DOUBLE_TAIL = comparator(COMP["double_tail_modified"], FRIDA1_LIKE)  # 264 uV, 1.5 ns
STRONGARM_X4 = comparator(COMP["strongarm"], X4)  # 327 uV, 0.14 ns
STRONGARM = comparator(COMP["strongarm"])  # 449 uV, 0.13 ns
DOUBLE_TAIL_X0P5 = comparator(COMP["double_tail_modified"], X0P5)  # 1.2 mV, 0.13 ns
# the samplers: FRIDA-1's transmission gate (32 minimum widths, minimum length), the same four
# times wider, and the bootstrapped NMOS switch with the doubled boost capacitor
TGATE = SampParams()
TGATE_X4 = SampParams(**samp_sweep.X4)
BOOTSTRAP = SampParams(switch_type=SwitchType.NMOS, bootstrap=True, **samp_sweep.BOOST_X2)

# the redundancy study: every comparator with every ADC variant's array, at its resolution (one bit
# more than its nominal: the free first comparison) and with the four-times-wider gate; the
# samplers compared on the FRIDA-like comparators with binary or overlay arrays
COMPARATORS = (DOUBLE_TAIL_LONG, STRONGARM_FRIDA1, DOUBLE_TAIL, STRONGARM, DOUBLE_TAIL_X0P5)
SAMPLERS = (TGATE, TGATE_X4, BOOTSTRAP)
STUDY_SAMPLER = TGATE_X4
SAMPLER_STUDY = (STRONGARM_FRIDA1, DOUBLE_TAIL)
SAMPLER_ARRAYS = (RedunStrat.RDX2, RedunStrat.SUBRDX2_OVLY)  # binary, and FRIDA's overlay

# the specification study: 14 bits, every array switching 1.4 pF a side in 7 pF of top-plate load,
# FRIDA-1's gate, comparators near 300 uV from slow to fast
SPEC_BITS = 14  # the converter's code has one bit more
SWITCHED_F = 1.4e-12  # a side's switched capacitance, every array scaled to it
TOTAL_F = 7.0e-12  # a side's top-plate load: the switched plates and the rest
SPEC_SAMPLER = TGATE
SPEC_COMPARATORS = (STRONGARM_FRIDA1, DOUBLE_TAIL, STRONGARM_X4)
# each array's search steps, MSB first, in units of the 14-bit LSB: every step its nominal weight
# plus its non-binary addition
SPEC_STEPS = (
    (8192, 4096, 2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4, 2, 1),  # binary
    (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 2, 1),  # added LSB-end decisions
    (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 2, 2, 1),  # double conversion at the LSB+1
    (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 2, 1, 1),  # double conversion at the LSB
    (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 3, 2, 1),  # non-binary at the LSB end
    (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 2, 2, 1, 1),  # double conversion at the LSB and LSB+1
    (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 2, 1, 1, 1),  # triple conversion at the LSB
    (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 3, 2, 1, 1),  # non-binary, double at the LSB and LSB+1
    (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 5, 3, 2, 1),  # non-binary at the LSB end
    (4096, 4096, 4096, 2048, 1024, 576, 384, 256, 128, 64, 48, 32, 16, 8, 6, 4, 2, 1),  # added decisions at the LSB end and the MSB
    (4096, 4096, 4096, 2048, 1024, 576, 384, 256, 128, 64, 48, 32, 16, 8, 6, 4, 2, 1, 1),  # the same, double at the LSB
    (4096, 4096, 4096, 2048, 1024, 576, 384, 256, 128, 64, 48, 32, 16, 8, 6, 4, 2, 2, 1),  # the same, non-binary at the LSB end
    (4096, 4096, 4096, 3072, 2048, 1024, 576, 384, 256, 128, 64, 48, 32, 16, 8, 6, 4, 2, 2, 1),  # the same, non-binary at both ends
    (4096, 4096, 4096, 2048, 1024, 512, 288, 192, 128, 64, 32, 24, 16, 8, 4, 3, 2, 1),  # added decisions near the MSB
    (4096, 4096, 4096, 3072, 2048, 1024, 512, 288, 192, 128, 64, 32, 24, 16, 8, 4, 3, 2, 1),  # the same, non-binary
    (4096, 4096, 4096, 3072, 2048, 1024, 512, 288, 192, 128, 64, 32, 24, 16, 8, 4, 3, 2, 1, 1),  # the same, double at the LSB
)  # fmt: skip


def spec_array(steps: tuple[int, ...]) -> CapArrayConfig:
    """An array of the specification: every search step a switched capacitor of that weight (so
    every capacitor and every step's margin as proposed), at the unit that switches 1.4 pF, the top
    plate's rest as the ideal array's parasitic."""
    return CapArrayConfig(
        n_dac=SPEC_BITS,
        n_extra=len(steps) - SPEC_BITS,
        redun_strat=RedunStrat.RDX2 if len(steps) == SPEC_BITS else RedunStrat.RDX2_RPT,
        weights=tuple(steps),
        unit_cap=SWITCHED_F / sum(steps),
        parasitic_cap=TOTAL_F - SWITCHED_F,
    )


def instances(pdk: str) -> list[AdcParams]:
    """Both studies' converters; none outside TSMC65, where the variants' arrays are extracted and
    the blocks characterized for them."""
    if pdk != "tsmc65":
        return []
    redundancy = [
        AdcParams(adc_bits=cdac.n_dac + 1, cdac=cdac, samp=samp, comp=comp)
        for comp in COMPARATORS
        for samp in SAMPLERS
        for cdac in ADC_VARIANTS.values()
        if samp == STUDY_SAMPLER or (comp in SAMPLER_STUDY and cdac.redun_strat in SAMPLER_ARRAYS)
    ]
    specification = [
        AdcParams(adc_bits=SPEC_BITS + 1, cdac=spec_array(steps), samp=SPEC_SAMPLER, comp=comp)
        for comp in SPEC_COMPARATORS
        for steps in SPEC_STEPS
    ]
    return redundancy + specification


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

    place(Comp(params.comp), "comp")
    for side in ("p", "n"):
        place(Samp(params.samp), f"samp_{side}")
        place(CapArray(CapArrayParams(cdac=params.cdac)), f"cap_{side}")
    return blocks


GENERATOR = AdcBlocks


def cost(pdk: str, params: AdcParams) -> float:
    """An instance's relative run time, for the runner's longest-first order: its conversions grow
    with the codes, each conversion with its decisions."""
    return 2.0**params.adc_bits * (params.cdac.n_dac + params.cdac.n_extra + 1)


def characterize(run_dir: Path, pdk: str, params: AdcParams) -> Record:
    from .campaign import campaign
    from .figures import adc_figures
    from .model import AdcModel

    model = AdcModel.of(pdk, params)
    captures = {}
    for name, capture in campaign(model.tb, model.full_scale_v, params.adc_bits).items():
        captures[name] = model.capture(
            capture.tb,
            # the mismatch and Hsu studies' many captures stay in memory: their figures keep them
            None if name.startswith(("mc_", "hsu_")) else run_dir / f"{name}.h5",
            seed=capture.seed,
            noise_seed=capture.noise_seed,
            unit_mismatch=capture.unit_mismatch,
            quiet=("sampling", "comparator", "rail") if capture.noise_free else capture.quiet,
            tau_scale=capture.tau_scale,
        )
    # the behavioral model alone can keep one noise source at a time
    noise = campaign(model.tb, model.full_scale_v, params.adc_bits)["noise"]
    for name, quiet in (("noise_sampling", ("comparator", "rail")), ("noise_comparator", ("sampling", "rail"))):
        captures[name] = model.capture(noise.tb, run_dir / f"{name}.h5", quiet=quiet)
    metrics, details = adc_figures(captures, run_dir / "figures")
    metrics |= {
        "stages": float(model.stages),  # the switched capacitors a side
        "decisions": float(model.stages + 1),  # a conversion's comparator decisions
        "full_scale_v": model.full_scale_v,
        "settling_tau_s": model.settling_tau_s,
        "comp_noise_v": model.comp.noise_v,
        "rail_noise_v": model.rail_noise_v,  # assumed, not characterized
        "comp_delay_s": model.comp.delay_s,
        **_metastability(model),
    }
    return Record(metrics=metrics, details=details)
