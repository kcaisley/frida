"""OTA testbench and named TSMC65 Spectre simulation targets."""

import argparse
import math
from datetime import datetime
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import G, f
from hdl21.primitives import C, R, Vdc
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Ota, OtaNets, OtaParams


def ota_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"freq": "freq"}
    for net in OtaNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class OtaTbParams:
    """Parameters which determine the generated open-loop OTA testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    ota = h.Param(dtype=OtaParams, desc="Amplifier parameters", default=OtaParams())
    cload = h.Param(dtype=h.Prefixed, desc="Load capacitance on each output", default=50 * f)
    vcm = h.Param(dtype=h.Scalar, desc="Input common-mode voltage", default=0.6)
    vbn = h.Param(dtype=h.Scalar, desc="NMOS current-source bias", default=0.55)
    vbp = h.Param(dtype=h.Scalar, desc="PMOS current-source bias", default=0.65)
    vcasn = h.Param(dtype=h.Scalar, desc="NMOS cascode bias", default=0.75)
    vcasp = h.Param(dtype=h.Scalar, desc="PMOS cascode bias", default=0.45)


def _validate_ota_tb_params(params: OtaTbParams) -> None:
    values = (params.vdd, params.cload, params.vcm, params.vbn, params.vbp, params.vcasn, params.vcasp)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("OTA testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0:
        raise ValueError("OTA supply and load must be positive")
    if not all(0 <= float(v) <= float(params.vdd) for v in values[2:]):
        raise ValueError("OTA input and bias voltages must lie between the rails")


@h.generator
def OtaTb(params: OtaTbParams) -> h.Module:
    """Generate an open-loop OTA testbench: inp carries the AC stimulus on the common mode; inn
    follows outp at DC through a 1 GOhm resistor and is held at AC by 1 F, so the amplifier biases
    itself in unity gain while its AC gain stays open-loop."""

    _validate_ota_tb_params(params)

    OtaTb, connections = testbench_from_ports(
        "OtaTb", {net.name: net for net in OtaNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = OtaTb.vss
    OtaTb.vvdd = Vdc(dc=params.vdd)(p=OtaTb.vdd, n=vss)
    OtaTb.vinp = Vdc(dc=params.vcm, ac=1.0)(p=OtaTb.inp, n=vss)
    OtaTb.rfb = R(r=1 * G)(p=OtaTb.outp, n=OtaTb.inn)
    OtaTb.cfb = C(c=1.0)(p=OtaTb.inn, n=vss)
    for name, value in (("vbn", params.vbn), ("vbp", params.vbp), ("vcasn", params.vcasn), ("vcasp", params.vcasp)):
        OtaTb.add(Vdc(dc=value)(p=getattr(OtaTb, name), n=vss), name=f"v{name}")
    OtaTb.cloadp = C(c=params.cload)(p=OtaTb.outp, n=vss)
    OtaTb.cloadn = C(c=params.cload)(p=OtaTb.outn, n=vss)
    OtaTb.dut = Ota(params.ota)(**connections)
    return OtaTb


def _ac(run_dir: Path, params: OtaTbParams, check: bool) -> Path:
    """Run the operating point and the open-loop AC response from 1 kHz to 100 GHz in TSMC65
    (``check``: ten points a decade fewer, with Spectre's static checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = OtaTb(params)
    h.pdk.compile(tb)
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([raw for raw in ota_signal_names() if raw != "freq"]),
            *(
                [
                    h.Literal(
                        "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top "
                        "gate2power=on gate2ground=on\n"
                        "check_dcpath static_dcpath net=[xtop.vdd 0]"
                    ),
                ]
                if check
                else []
            ),
            hs.Op(name="op"),
            hs.Ac(sweep=hs.LogSweep(start=1e3, stop=1e11, npts=8 if check else 80), name="ac"),
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


def five_t_ac(run_dir: Path, *, check: bool = False) -> Path:
    """Open-loop AC response of the NMOS-input five-transistor amplifier."""

    return _ac(run_dir, OtaTbParams(ota=CASES["five_t"]), check)


def five_t_pmos_ac(run_dir: Path, *, check: bool = False) -> Path:
    """Open-loop AC response of the PMOS-input five-transistor amplifier."""

    return _ac(run_dir, OtaTbParams(ota=CASES["five_t_pmos"]), check)


def self_biased_ac(run_dir: Path, *, check: bool = False) -> Path:
    """Open-loop AC response of the self-biased complementary amplifier."""

    return _ac(run_dir, OtaTbParams(ota=CASES["self_biased"]), check)


def main() -> None:
    """Create one output directory and run one named OTA target."""

    targets = {target.__name__: target for target in (five_t_ac, five_t_pmos_ac, self_biased_ac)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available OTA simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "ota"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
