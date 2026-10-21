"""
Cascode bias generator for FRIDA.

From one reference current, the four gate voltages a cascoded current source of each type needs
 (the wide-swing bias of Johns and Martin):
- ``vbn``, ``vbp``: each a self-cascoded diode, its mirror device under a cascode on ``vcasn`` or
  ``vcasp``, so the reference's mirror device sits at the drain-source voltage an output's does
- ``vcasn``, ``vcasp``: each a diode-connected device weaker than the mirror device (its W/L a
  fraction of the mirror's), at the same current: its gate-source voltage exceeds the mirror
  device's by what the cascode leaves across it (an overdrive for a quarter in strong inversion;
  in weak inversion only n Ut ln 4, so a sixteenth keeps the mirror device saturated)

The reference current flows into ``vbn``; cascoded copies of it, on ``vbn`` and ``vbp``, feed the
PMOS reference and the two cascode diodes: uncascoded, a copy's drain-source voltage, far above
the reference's, would raise its current by its barrier lowering, several times over in weak
inversion. Cascoded, the copies need ``vcasn`` to conduct, and ``vcasn`` needs them: a start-up
follower from ``vbn`` onto ``vcasn`` lifts it while the reference current has nowhere to go (and
drives ``vbn`` up), and turns off once the generator runs, with ``vcasn`` above ``vbn``.
"""

from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.comp.subckt import _mos
from flow.comp.subckt import write_netlist as _write_netlist


@h.paramclass
class BiasParams:
    """Cascode bias generator parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=4 means 4×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Device sizing (multipliers of Wmin/Lmin): the mirror devices and their cascodes, the
    # cascode-gate diodes (a quarter of the mirror device's W/L by default)
    n_w = h.Param(dtype=int, desc="NMOS mirror and copy width multiplier", default=8)
    n_l = h.Param(dtype=int, desc="NMOS mirror and copy length multiplier", default=8)
    p_w = h.Param(dtype=int, desc="PMOS mirror and copy width multiplier", default=16)
    p_l = h.Param(dtype=int, desc="PMOS mirror and copy length multiplier", default=8)
    cas_l = h.Param(dtype=int, desc="Cascode length multiplier", default=1)
    casn_w = h.Param(dtype=int, desc="vcasn diode width multiplier", default=2)
    casn_l = h.Param(dtype=int, desc="vcasn diode length multiplier", default=8)
    casp_w = h.Param(dtype=int, desc="vcasp diode width multiplier", default=4)
    casp_l = h.Param(dtype=int, desc="vcasp diode length multiplier", default=8)
    start_w = h.Param(dtype=int, desc="Start-up follower width multiplier", default=1)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_bias_params(param: BiasParams) -> bool:
    """Check if this generator is valid: every size positive."""
    sizes = (param.n_w, param.n_l, param.p_w, param.p_l, param.cas_l, param.start_w)
    return min((*sizes, param.casn_w, param.casn_l, param.casp_w, param.casp_l)) > 0


@h.bundle
class BiasNets:
    vbn = h.Inout(desc="NMOS mirror gate; the reference current flows in here")
    vcasn = h.Output(desc="NMOS cascode gate")
    vbp = h.Output(desc="PMOS mirror gate")
    vcasp = h.Output(desc="PMOS cascode gate")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Bias(param: BiasParams) -> h.Module:
    """
    Cascode bias generator.

    Generates self-cascoded NMOS and PMOS reference diodes and weak diodes for the cascode gates,
    fed by cascoded copies of the reference current, and a start-up follower, every body on its
    rail.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_bias_params(param):
        raise ValueError(f"Invalid cascode bias params: {param}")

    Bias = module_from_ports("Bias", BiasNets.signals)
    vdd, vss, vth = Bias.vdd, Bias.vss, param.vth
    nmos = {"tp": MosType.NMOS, "vth": vth, "w": param.n_w, "l": param.n_l}
    pmos = {"tp": MosType.PMOS, "vth": vth, "w": param.p_w, "l": param.p_l}
    Bias.nx, Bias.px = h.Signal(desc="NMOS mirror device's drain"), h.Signal(desc="PMOS mirror device's drain")

    # the NMOS reference: the mirror device under its cascode, the pair diode-connected at vbn
    Bias.Mn = _mos(**nmos)(d=Bias.nx, g=Bias.vbn, s=vss, b=vss)
    Bias.Mn_cas = _mos(tp=MosType.NMOS, vth=vth, w=param.n_w, l=param.cas_l)(d=Bias.vbn, g=Bias.vcasn, s=Bias.nx, b=vss)
    # the PMOS reference, fed a cascoded copy of the current
    ncas = {"tp": MosType.NMOS, "vth": vth, "w": param.n_w, "l": param.cas_l}
    pcas = {"tp": MosType.PMOS, "vth": vth, "w": param.p_w, "l": param.cas_l}
    Bias.ny_p, Bias.ny_casp = h.Signal(desc="Copies' drains"), h.Signal()
    Bias.py_casn = h.Signal(desc="PMOS copy's drain")
    Bias.Mn_to_p = _mos(**nmos)(d=Bias.ny_p, g=Bias.vbn, s=vss, b=vss)
    Bias.Mn_to_p_cas = _mos(**ncas)(d=Bias.vbp, g=Bias.vcasn, s=Bias.ny_p, b=vss)
    Bias.Mp = _mos(**pmos)(d=Bias.px, g=Bias.vbp, s=vdd, b=vdd)
    Bias.Mp_cas = _mos(**pcas)(d=Bias.vbp, g=Bias.vcasp, s=Bias.px, b=vdd)
    # the cascode gates: weak diodes, each fed a cascoded copy of the current by the other type
    Bias.Mp_to_casn = _mos(**pmos)(d=Bias.py_casn, g=Bias.vbp, s=vdd, b=vdd)
    Bias.Mp_to_casn_cas = _mos(**pcas)(d=Bias.vcasn, g=Bias.vcasp, s=Bias.py_casn, b=vdd)
    Bias.Mcasn = _mos(tp=MosType.NMOS, vth=vth, w=param.casn_w, l=param.casn_l)(
        d=Bias.vcasn, g=Bias.vcasn, s=vss, b=vss
    )
    Bias.Mn_to_casp = _mos(**nmos)(d=Bias.ny_casp, g=Bias.vbn, s=vss, b=vss)
    Bias.Mn_to_casp_cas = _mos(**ncas)(d=Bias.vcasp, g=Bias.vcasn, s=Bias.ny_casp, b=vss)
    Bias.Mcasp = _mos(tp=MosType.PMOS, vth=vth, w=param.casp_w, l=param.casp_l)(
        d=Bias.vcasp, g=Bias.vcasp, s=vdd, b=vdd
    )
    # start-up: with no current, vbn rises and lifts vcasn; running, vcasn sits above vbn
    Bias.Mstart = _mos(tp=MosType.NMOS, vth=vth, w=param.start_w, l=1)(d=vdd, g=Bias.vbn, s=Bias.vcasn, b=vss)
    return Bias


def write_netlist(params: BiasParams, path: Path, pdk) -> Path:
    """The generator after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.comp.subckt.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Bias, nets=BiasNets)


# ==== Named generators ====

CASES = {
    # wide swing: diodes of a quarter of the mirror device's W/L, an overdrive across it in strong inversion
    "wide": BiasParams(),
    # margin: diodes of a sixteenth, saturation kept in weak inversion too
    "margin": BiasParams(casn_w=1, casn_l=16, casp_w=2, casp_l=16),
}
