"""Current source testbench and named TSMC65 Spectre simulation targets."""

import argparse
import math
from datetime import datetime
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import u
from hdl21.primitives import Idc, MosType, Vdc
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Idac, IdacNets, IdacParams


def idac_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle: the voltages of the
    ports and the currents of the sources holding out and dump."""
    names = {}
    for net in IdacNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
    names.update({"xtop.vout:p": "i(out)", "xtop.vdump:p": "i(dump)"})
    return names


@h.paramclass
class IdacTbParams:
    """Parameters which determine the generated current source testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    idac = h.Param(dtype=IdacParams, desc="Current source parameters", default=IdacParams())
    vout = h.Param(dtype=h.Scalar, desc="Voltage held on out and dump", default=0.6)
    vbias = h.Param(dtype=h.Scalar, desc="Current source gate voltage (no diode)", default=0.5)
    iref = h.Param(dtype=h.Prefixed, desc="Reference current into vbias (with a diode)", default=10 * u)
    vcas = h.Param(dtype=h.Scalar, desc="Cascode gate voltage", default=0.8)
    en = h.Param(dtype=bool, desc="en high (enb low)", default=True)


def _validate_idac_tb_params(params: IdacTbParams) -> None:
    values = (params.vdd, params.vout, params.vbias, params.iref, params.vcas)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("current source testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.iref) <= 0:
        raise ValueError("current source supply and reference current must be positive")


@h.generator
def IdacTb(params: IdacTbParams) -> h.Module:
    """Generate a current source testbench: out and dump held by sources (their currents are the
    unit's), the bias a voltage or, with a diode, a reference current into vbias."""

    _validate_idac_tb_params(params)

    IdacTb, connections = testbench_from_ports(
        "IdacTb", {net.name: net for net in IdacNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss, vdd = IdacTb.vss, float(params.vdd)
    IdacTb.vvdd = Vdc(dc=vdd)(p=IdacTb.vdd, n=vss)
    IdacTb.vout = Vdc(dc=params.vout)(p=IdacTb.out, n=vss)
    IdacTb.vdump = Vdc(dc=params.vout)(p=IdacTb.dump, n=vss)
    IdacTb.ven = Vdc(dc=vdd if params.en else 0.0)(p=IdacTb.en, n=vss)
    IdacTb.venb = Vdc(dc=0.0 if params.en else vdd)(p=IdacTb.enb, n=vss)
    IdacTb.vvcas = Vdc(dc=params.vcas)(p=IdacTb.vcas, n=vss)
    if params.idac.diode:  # a PMOS reference draws its current out of vbias, an NMOS one takes it in
        pmos = params.idac.source_xtors == MosType.PMOS
        IdacTb.iref = Idc(dc=params.iref)(p=IdacTb.vbias if pmos else IdacTb.vdd, n=vss if pmos else IdacTb.vbias)
    else:
        IdacTb.vvbias = Vdc(dc=params.vbias)(p=IdacTb.vbias, n=vss)
    IdacTb.dut = Idac(params.idac)(**connections)
    return IdacTb


def _op(run_dir: Path, params: IdacTbParams, check: bool) -> Path:
    """Run the operating point in TSMC65 (``check``: with Spectre's static checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = IdacTb(params)
    h.pdk.compile(tb)
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save(list(idac_signal_names())),
            *([h.Literal("check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top")] if check else []),
            hs.Op(name="op"),
        ],
    )
    simulation.run(
        SimOptions(
            simulator=SupportedSimulators.SPECTRE,
            fmt=ResultFormat.NONE if check else ResultFormat.SIM_DATA,
            rundir=run_dir,
            simulator_args=(
                "+preset=mx",
                "+mt=4",
                "+lqtimeout",
                "3600",
                "+escchars",
                "+log",
                "spectre.log",
                *(("-ahdllint=warn", "-ahdllint_log", "ahdllint.log") if check else ()),
            ),
        )
    )
    return run_dir


def nmos_steer_op(run_dir: Path, *, check: bool = False) -> Path:
    """Operating point of the four steered NMOS units, steered to out."""

    return _op(run_dir, IdacTbParams(idac=CASES["nmos_steer"]), check)


def pmos_mirror_op(run_dir: Path, *, check: bool = False) -> Path:
    """Operating point of the PMOS bias mirror with 10 uA into its reference."""

    return _op(run_dir, IdacTbParams(idac=CASES["pmos_mirror"], vcas=0.4), check)


def main() -> None:
    """Create one output directory and run one named current source target."""

    targets = {target.__name__: target for target in (nmos_steer_op, pmos_mirror_op)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available current source simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "idac"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
