"""A 14-bit SAR ADC specification and the capacitor arrays proposed for it (``flow.sweep``): does
redundancy pay at this specification, and in which arrays?

The specification: 14 bits; 1.4 pF of switched capacitance a side in 7 pF of top-plate load (the
rest routing, the sampler, the comparator and dummies); FRIDA-1's transmission gate at 32 minimum
widths and minimum length; a comparator of about 300 uV input-referred noise. The topologies are
three comparators near that noise, from slow to fast (their delay decides whether the comparator or
the DAC limits the conversion); the sizings are the arrays, each scaled to the same 1.4 pF.

Each array is given as its search steps, as a spreadsheet lists them (each its nominal weight plus a
non-binary addition; the first the converter's free first comparison, then each switched
capacitor): plain binary, binary with added
LSB-end decisions (``lsb_add``) with double or triple conversion at the LSB or the LSB+1 (``dc_*``,
``tc_lsb``), mildly non-binary steps there (``nb_*``), additions at both ends and at the MSB
(``msb*``). The arrays are ideal (``CapArrayConfig.parasitic_cap``: each stage its weight in unit
capacitors, nothing extracted), so the comparison is of the schemes alone. Each instance runs the
ADC's campaign and figures (``flow.adc.sweep.characterize``), the redundancy study included.

    uv run python -m flow adc14.sweep
"""

from __future__ import annotations

from flow.adc.subckt import AdcParams
from flow.adc.sweep import GENERATOR, characterize  # noqa: F401 - the runner's interface
from flow.caparray.subckt import CapArrayConfig, RedunStrat
from flow.comp import sweep as comp_sweep
from flow.samp import sweep as samp_sweep

BITS = 14  # the specification's; the converter's code has one bit more (``weights``)
SWITCHED_F = 1.4e-12  # a side's switched capacitance, every array scaled to it
TOTAL_F = 7.0e-12  # a side's top-plate load: the switched plates and the rest
SAMPLER = ("frida1", "x1")  # the transmission gate, 32 minimum widths and minimum length
# comparators near 300 uV (input-referred noise and delay at 0.1 mV in TSMC65), slow to fast
COMPARATORS = {
    "strongarm_frida1": ("strongarm", "frida1_like"),  # 249 uV, 2.5 ns
    "double_tail": ("double_tail_modified", "frida1_like"),  # 264 uV, 1.5 ns
    "strongarm_x4": ("strongarm", "x4"),  # 327 uV, 0.14 ns
}
# each array's search steps, MSB first, in units of the 14-bit LSB (a 64th of the spreadsheet's unit):
# every step its nominal weight plus its non-binary addition, as the spreadsheet's step ratios check
STEPS = {
    "cdac1_binary": (8192, 4096, 2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4, 2, 1),
    "cdac2_lsb_add": (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 2, 1),
    "cdac3_dc_lsb1": (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 2, 2, 1),
    "cdac4_dc_lsb": (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 2, 1, 1),
    "cdac5_nb_lsb": (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 3, 2, 1),
    "cdac6_dc_lsb_lsb1": (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 2, 2, 1, 1),
    "cdac7_tc_lsb": (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 2, 1, 1, 1),
    "cdac8_nb_dc_lsb_lsb1": (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 4, 3, 2, 1, 1),
    "cdac8_1_nb_lsb": (4096, 4096, 4096, 2048, 1152, 768, 512, 256, 128, 96, 64, 32, 16, 12, 8, 5, 3, 2, 1),
    "cdac9_lsb_msb": (4096, 4096, 4096, 2048, 1024, 576, 384, 256, 128, 64, 48, 32, 16, 8, 6, 4, 2, 1),
    "cdac10_lsb_msb_dc_lsb": (4096, 4096, 4096, 2048, 1024, 576, 384, 256, 128, 64, 48, 32, 16, 8, 6, 4, 2, 1, 1),
    "cdac11_nb_lsb_msb": (4096, 4096, 4096, 2048, 1024, 576, 384, 256, 128, 64, 48, 32, 16, 8, 6, 4, 2, 2, 1),
    "cdac12_nb_lsb_msb": (4096, 4096, 4096, 3072, 2048, 1024, 576, 384, 256, 128, 64, 48, 32, 16, 8, 6, 4, 2, 2, 1),
    "cdac13_msb2": (4096, 4096, 4096, 2048, 1024, 512, 288, 192, 128, 64, 32, 24, 16, 8, 4, 3, 2, 1),
    "cdac14_nb_msb2": (4096, 4096, 4096, 3072, 2048, 1024, 512, 288, 192, 128, 64, 32, 24, 16, 8, 4, 3, 2, 1),
    "cdac15_nb_msb2_dc_lsb": (4096, 4096, 4096, 3072, 2048, 1024, 512, 288, 192, 128, 64, 32, 24, 16, 8, 4, 3, 2, 1, 1),
}  # fmt: skip


def weights(steps: tuple[int, ...]) -> tuple[int, ...]:
    """The switched capacitors' weights: every step a capacitor, as the spreadsheet's arrays have
    them (so every capacitor and every step's margin as it computes them). This converter samples on
    its top plates and makes one more decision, a free first comparison at mid-scale, alike for
    every array: its levels are twice the spreadsheet's (a 15-bit code over the same full scale in
    volts), so the arrays compare by ENOB and SNDR, not by counts of the finer LSB."""
    return tuple(steps)


TOPOLOGIES = {name: {"comp": comp} for name, comp in COMPARATORS.items()}
SIZINGS = {name: {"weights": weights(steps)} for name, steps in STEPS.items()}


def array(sizing: str) -> CapArrayConfig:
    """The sizing's array: its weights at the unit that switches 1.4 pF, the top plate's rest as
    the ideal array's parasitic."""
    stage_weights = SIZINGS[sizing]["weights"]
    return CapArrayConfig(
        n_dac=BITS,
        n_extra=len(stage_weights) - BITS,
        redun_strat=RedunStrat.RDX2 if len(stage_weights) == BITS else RedunStrat.RDX2_RPT,
        weights=stage_weights,
        unit_cap=SWITCHED_F / sum(stage_weights),
        parasitic_cap=TOTAL_F - SWITCHED_F,
    )


def params(pdk: str, topology: str, sizing: str) -> AdcParams | None:
    if pdk != "tsmc65":  # the comparators and the sampler as TSMC65 characterized them
        return None
    return AdcParams(
        adc_bits=BITS + 1,
        cdac=array(sizing),
        samp=samp_sweep.params(pdk, *SAMPLER),
        comp=comp_sweep.params(pdk, *TOPOLOGIES[topology]["comp"]),
    )


def cost(pdk: str, topology: str, sizing: str) -> float:
    """An instance's relative run time, for the runner's longest-first order: its decisions."""
    return float(len(SIZINGS[sizing]["weights"]))
