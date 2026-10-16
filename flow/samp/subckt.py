"""
Sampling Switch generator for FRIDA.

Supports NMOS, PMOS, and transmission gate topologies
with configurable device sizing and threshold voltage,
half-size charge-injection dummies, and a bootstrapped NMOS gate.

Note: Generators use h.Mos primitives with MosType/MosVth parameters.
Call pdk.compile(module) after generation to convert to PDK-specific devices.
"""

from enum import Enum, auto
from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.comp.subckt import _mos
from flow.comp.subckt import write_netlist as _write_netlist


class SwitchType(Enum):
    """Sampling switch topology."""

    NMOS = auto()
    PMOS = auto()
    TGATE = auto()


@h.paramclass
class SampParams:
    """Sampling switch parameters.

    Device sizing uses multiplier-based scaling:
    - mos_w: Width multiplier (the default 32 is approximately 4µm in FRIDA65A)
    - mos_l: Length multiplier (l=1 means 1×Lmin, e.g., 60nm for a 65nm node)

    This approach allows the same design to be portable across PDKs.
    """

    switch_type = h.Param(dtype=SwitchType, desc="Switch topology", default=SwitchType.TGATE)
    mos_w = h.Param(dtype=int, desc="Width multiplier (× Wmin)", default=32)
    mos_l = h.Param(dtype=int, desc="Length multiplier (× Lmin)", default=1)
    mos_vth = h.Param(dtype=MosVth, desc="Threshold voltage flavor", default=MosVth.LOW)
    dummy = h.Param(dtype=bool, desc="Half-size dummies on dout, clocked opposite their switch", default=False)
    bootstrap = h.Param(dtype=bool, desc="Bootstrapped NMOS gate (NMOS switch only)", default=False)
    boot_w = h.Param(dtype=int, desc="Bootstrap helper device width multiplier", default=4)
    cap_w = h.Param(dtype=int, desc="Bootstrap MOS capacitor width multiplier", default=16)
    cap_l = h.Param(dtype=int, desc="Bootstrap MOS capacitor length multiplier", default=8)


def is_valid_samp_params(param: SampParams) -> bool:
    """Check if this switch combination is valid.

    Every size is positive. A bootstrap boosts one NMOS gate, so it needs the NMOS switch.
    A dummy is half its switch, so the switch needs at least two width units.
    """
    if min(param.mos_w, param.mos_l, param.boot_w, param.cap_w, param.cap_l) <= 0:
        return False
    if param.bootstrap and param.switch_type != SwitchType.NMOS:
        return False
    return not (param.dummy and param.mos_w < 2)


@h.bundle
class SampNets:
    din = h.Input(desc="Data input")
    dout = h.Output(desc="Data output")
    clk, clk_b = h.Clock(), h.Clock()
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Samp(param: SampParams) -> h.Module:
    """
    Sampling switch generator.

    Generates NMOS, PMOS, or transmission gate switches
    based on the switch_type parameter.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_samp_params(param):
        raise ValueError(f"Invalid sampler params: {param}")

    Samp = module_from_ports("Samp", SampNets.signals)
    nmos = param.switch_type in (SwitchType.NMOS, SwitchType.TGATE)
    pmos = param.switch_type in (SwitchType.PMOS, SwitchType.TGATE)

    # Instantiate devices based on switch type; a bootstrap drives the NMOS gate from its boosted node
    if param.bootstrap:
        _build_bootstrap(Samp, param)
    if nmos:
        Samp.MN = _mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.mos_w, l=param.mos_l)(
            d=Samp.dout, g=Samp.gate if param.bootstrap else Samp.clk, s=Samp.din, b=Samp.vss
        )
    if pmos:
        Samp.MP = _mos(tp=MosType.PMOS, vth=param.mos_vth, w=param.mos_w, l=param.mos_l)(
            d=Samp.dout, g=Samp.clk_b, s=Samp.din, b=Samp.vdd
        )

    # Half-size dummies with drain and source on dout absorb the charge their switch's channel
    # releases at turn-off: each is clocked opposite its switch
    if param.dummy:
        half = param.mos_w // 2
        if nmos:
            Samp.MN_dummy = _mos(tp=MosType.NMOS, vth=param.mos_vth, w=half, l=param.mos_l)(
                d=Samp.dout, g=Samp.clk_b, s=Samp.dout, b=Samp.vss
            )
        if pmos:
            Samp.MP_dummy = _mos(tp=MosType.PMOS, vth=param.mos_vth, w=half, l=param.mos_l)(
                d=Samp.dout, g=Samp.clk, s=Samp.dout, b=Samp.vdd
            )

    return Samp


def _build_bootstrap(module, param: SampParams):
    """Build the boosted gate of the NMOS switch.

    During hold (clk low) the capacitor's bottom plate ``boot_bot`` is pulled to vss and its top
    plate ``boot_top`` charged to vdd, while a stacked pull-down holds ``gate`` low. During
    sampling a transmission gate puts din on the bottom plate and a PMOS joins ``gate`` to the
    top plate, which then sits one supply above din: the switch's gate-source voltage stays
    near vdd whatever the input. The PMOS bodies sit on vdd, so the boosted node's junctions
    leak toward vdd while sampling.
    """

    module.gate = h.Signal(desc="Boosted switch gate")
    module.boot_top, module.boot_bot, module.gate_off = h.Signal(), h.Signal(), h.Signal()
    aux = {"vth": param.mos_vth, "w": param.boot_w, "l": 1}

    # Transmission gate: the bottom plate follows din while sampling
    module.Mtg_n = _mos(tp=MosType.NMOS, **aux)(d=module.boot_bot, g=module.clk, s=module.din, b=module.vss)
    module.Mtg_p = _mos(tp=MosType.PMOS, **aux)(d=module.boot_bot, g=module.clk_b, s=module.din, b=module.vdd)
    # Bottom plate to vss during hold
    module.Mbot = _mos(tp=MosType.NMOS, **aux)(d=module.boot_bot, g=module.clk_b, s=module.vss, b=module.vss)
    # Gate pull-down during hold: a stack of two, so the boosted gate splits over two off devices
    # (the references cascode with a device gated by vdd; a gate on a rail has no route here)
    module.Mgate_cas = _mos(tp=MosType.NMOS, **aux)(d=module.gate, g=module.clk_b, s=module.gate_off, b=module.vss)
    module.Mgate_off = _mos(tp=MosType.NMOS, **aux)(d=module.gate_off, g=module.clk_b, s=module.vss, b=module.vss)
    # Top plate to the gate while sampling
    module.Mgate = _mos(tp=MosType.PMOS, **aux)(d=module.boot_top, g=module.clk_b, s=module.gate, b=module.vdd)
    # Top plate to vdd while the gate is low (hold)
    module.Mpre = _mos(tp=MosType.PMOS, **aux)(d=module.vdd, g=module.gate, s=module.boot_top, b=module.vdd)
    # The boost capacitor: an NMOS whose channel (drain and source on the bottom plate) faces its gate
    module.Mcap = _mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.cap_w, l=param.cap_l)(
        d=module.boot_bot, g=module.boot_top, s=module.boot_bot, b=module.vss
    )


def write_netlist(params: SampParams, path: Path, pdk) -> Path:
    """The sampler after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.comp.subckt.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Samp, nets=SampNets)


def main() -> None:
    """Write a sampler netlist: the FRIDA-1 transmission gate or a named variant."""

    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("case", choices=sorted(CASES), help="sampler case")
    parser.add_argument("output", type=Path, help="SPICE file to write (its stem names the subcircuit)")
    parser.add_argument("--pdk", default="tsmc65")
    args = parser.parse_args()
    pdk = __import__(f"pdk.{args.pdk}.hdl21", fromlist=["pdk_logic"]).pdk_logic
    print(write_netlist(CASES[args.case], args.output, pdk))


# ==== Named switches ====

FRIDA1 = SampParams()  # the fabricated FRIDA-1 sampler: transmission gate, 32 units each
CASES = {
    "frida1": FRIDA1,
    "tgate_dummy": SampParams(dummy=True),
    "nmos": SampParams(switch_type=SwitchType.NMOS),
    "bootstrap": SampParams(switch_type=SwitchType.NMOS, bootstrap=True),
}


if __name__ == "__main__":
    main()
