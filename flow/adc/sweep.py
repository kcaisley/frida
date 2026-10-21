"""The ADC's design space (``flow.sweep``): two comparators, 10 and 12 bits with 0, 2, 4 or 5
redundant stages, on the three-metal difference-capacitor arrays, in TSMC65, by the behavioral
model (``flow.adc.model``) of its characterized blocks.

The comparators: a StrongARM near FRIDA-1's (``frida1_like``: its long-channel sizes in round
multiples; 249 uV, 2.1 ns at 0.5 mV in TSMC65) and the lowest-noise double tail that decides well
within the comparator's 2.5 ns at 10 MS/s with 16 stages (the modified double tail at
``frida1_like``: 264 uV, 1.3 ns). The model takes their noise, offset and energy, not their delay. The
sampler is FRIDA-1's (``frida1`` at ``x1``); the arrays are the ADC variants'
(``flow.caparray.layout.ADC_VARIANTS``), each extracted in TSMC65 only, so the other PDKs give no
instance. Each instance runs the campaign of ``flow.adc.campaign`` (about 1.7 M behavioral
conversions) and draws its figures (``flow.adc.figures``) for the viewer.
"""

from __future__ import annotations

from pathlib import Path

import hdl21 as h

from flow.caparray.layout import ADC_VARIANTS
from flow.caparray.subckt import CapArray, CapArrayParams
from flow.comp import sweep as comp_sweep
from flow.comp.subckt import Comp
from flow.samp import sweep as samp_sweep
from flow.samp.subckt import Samp
from flow.sweep import Detail, Record

from .subckt import AdcParams

# each topology's comparator: (comparator topology, sizing) of the comparator sweep
TOPOLOGIES = {
    "strongarm_frida1": {"comp": ("strongarm", "frida1_like")},
    "double_tail": {"comp": ("double_tail_modified", "frida1_like")},
}
SIZINGS = {name: {"cdac": cdac} for name, cdac in ADC_VARIANTS.items()}


def params(pdk: str, topology: str, sizing: str) -> AdcParams | None:
    if pdk != "tsmc65":  # the variants' arrays are extracted in TSMC65 only
        return None
    cdac = SIZINGS[sizing]["cdac"]
    return AdcParams(
        adc_bits=cdac.n_dac + 1,
        cdac=cdac,
        samp=samp_sweep.params(pdk, "frida1", "x1"),
        comp=comp_sweep.params(pdk, *TOPOLOGIES[topology]["comp"]),
    )


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


def characterize(run_dir: Path, pdk: str, params: AdcParams) -> Record:
    from flow.sweep.runner import ROOT

    from .campaign import campaign
    from .figures import FIGURES, adc_figures
    from .model import AdcModel

    model = AdcModel.of(pdk, params)
    captures = {}
    for name, capture in campaign(model.tb, model.full_scale_v).items():
        captures[name] = model.capture(
            capture.tb,
            run_dir / f"{name}.h5",
            seed=capture.seed,
            noise_seed=capture.noise_seed,
            unit_mismatch=capture.unit_mismatch,
        )
    # the behavioral model alone can silence one noise source at a time
    noise = campaign(model.tb, model.full_scale_v)["noise"]
    for name, quiet in (("noise_sampling", ("comparator",)), ("noise_comparator", ("sampling",))):
        captures[name] = model.capture(noise.tb, run_dir / f"{name}.h5", quiet=quiet)
    metrics, figures = adc_figures(captures, run_dir / "figures")
    metrics |= {
        "stages": float(model.stages),
        "full_scale_v": model.full_scale_v,
        "settling_tau_s": model.settling_tau_s,
        "comp_noise_v": model.comp.noise_v,
        "comp_delay_s": model.comp.delay_s,
    }
    return Record(
        metrics=metrics,
        details=[
            Detail(
                name=name,
                title=FIGURES[name],
                x_label="",
                y_label="",
                x=[],
                series={},
                figure=str(path.relative_to(ROOT)),
            )
            for name, path in figures.items()
        ],
    )
