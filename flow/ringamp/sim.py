"""Ring amplifier testbench and named TSMC65 Spectre simulation targets."""

import argparse
import math
from datetime import datetime
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import f, p
from hdl21.primitives import C, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Ringamp, RingampNets, RingampParams


def ringamp_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in RingampNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class RingampTbParams:
    """Parameters which determine the generated ring amplifier testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    ringamp = h.Param(dtype=RingampParams, desc="Ring amplifier parameters", default=RingampParams())
    cload = h.Param(dtype=h.Prefixed, desc="Load capacitance on out", default=50 * f)
    vcm = h.Param(dtype=h.Scalar, desc="Input common mode", default=0.6)
    vstep = h.Param(dtype=h.Scalar, desc="Input excursion either side of vcm", default=0.3)
    vcmfb = h.Param(dtype=h.Scalar, desc="Tail bias", default=0.6)
    biasn = h.Param(dtype=h.Scalar, desc="Dead-zone NMOS bias", default=0.5)
    biasp = h.Param(dtype=h.Scalar, desc="Dead-zone PMOS bias", default=0.7)
    period_s = h.Param(dtype=h.Scalar, desc="Input ramp time", default=20e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Enable rise and fall time", default=50e-12)


def _validate_ringamp_tb_params(params: RingampTbParams) -> None:
    values = (params.vdd, params.cload, params.period_s, params.transition_time_s)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("ring amplifier testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0:
        raise ValueError("ring amplifier supply and load must be positive")
    if float(params.transition_time_s) <= 0 or float(params.period_s) <= 2 * float(params.transition_time_s):
        raise ValueError("ring amplifier period must exceed both transitions, which must be positive")


@h.generator
def RingampTb(params: RingampTbParams) -> h.Module:
    """Generate a ring amplifier testbench: en high (enb low) after a quarter period, inp a triangle about vcm (one period up, one down), fixed biases, a load on out."""

    _validate_ringamp_tb_params(params)

    RingampTb, connections = testbench_from_ports(
        "RingampTb", {net.name: net for net in RingampNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = RingampTb.vss
    vdd, period = float(params.vdd), float(params.period_s)
    vcm, step = float(params.vcm), float(params.vstep)
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    RingampTb.vvdd = Vdc(dc=vdd)(p=RingampTb.vdd, n=vss)
    RingampTb.ven = Vpulse(v1=0.0, v2=vdd, period=1.0, width=0.5, delay=period / 4, **edge)(p=RingampTb.en, n=vss)
    RingampTb.venb = Vpulse(v1=vdd, v2=0.0, period=1.0, width=0.5, delay=period / 4, **edge)(p=RingampTb.enb, n=vss)
    # a triangle: the rise and the fall each one period long
    RingampTb.vinp = Vpulse(
        v1=vcm - step, v2=vcm + step, period=3 * period, width=0.0, delay=period / 2, rise=period, fall=period
    )(p=RingampTb.inp, n=vss)
    RingampTb.vvcmfb = Vdc(dc=params.vcmfb)(p=RingampTb.vcmfb, n=vss)
    RingampTb.vbiasn = Vdc(dc=params.biasn)(p=RingampTb.biasn, n=vss)
    RingampTb.vbiasp = Vdc(dc=params.biasp)(p=RingampTb.biasp, n=vss)
    RingampTb.cload = C(c=params.cload)(p=RingampTb.out, n=vss)
    RingampTb.dut = Ringamp(params.ringamp)(**connections)
    return RingampTb


def _transient(run_dir: Path, params: RingampTbParams, tstop: float, check: bool) -> Path:
    """Run one ring amplifier testbench transient in TSMC65 (``check``: one tenth of it with Spectre's checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = RingampTb(params)
    h.pdk.compile(tb)
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([raw for raw in ringamp_signal_names() if raw != "time"]),
            *(
                [
                    h.Literal(
                        "check_caps static_capacitor type=distr\n"
                        "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top "
                        "gate2power=on gate2ground=on\n"
                        "check_highz static_highz node=[*] fanout=gate_has_driver_no_moscap\n"
                        "check_dcpath static_dcpath net=[xtop.vdd 0]\n"
                        "check_topology static_topology node=[*] pin2gnd=on"
                    ),
                ]
                if check
                else []
            ),
            hs.Tran(
                tstop=tstop / 10 if check else tstop,
                name="tran",
                options={"strobeperiod": 1 * p, "strobeoutput": "strobeonly"},
            ),
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


def se_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the single-ended ring amplifier over its input triangle."""

    params = RingampTbParams(ringamp=CASES["se"])
    return _transient(run_dir, params, 2.5 * float(params.period_s), check)


def main() -> None:
    """Create one output directory and run one named ring amplifier target."""

    targets = {target.__name__: target for target in (se_transient,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available ring amplifier simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "ringamp"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
