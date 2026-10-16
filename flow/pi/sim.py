"""Phase interpolator testbench and named TSMC65 Spectre simulation targets."""

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

from .subckt import CASES, Pi, PiNets, PiParams, Style


def pi_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in PiNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class PiTbParams:
    """Parameters which determine the generated phase interpolator testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    pi = h.Param(dtype=PiParams, desc="Interpolator parameters", default=PiParams())
    cload = h.Param(dtype=h.Prefixed, desc="Load capacitance on each output", default=2 * f)
    cml_low = h.Param(dtype=h.Scalar, desc="Low level of the CML phases", default=0.8)
    vbn = h.Param(dtype=h.Scalar, desc="CML tail bias", default=0.55)
    vbp = h.Param(dtype=h.Scalar, desc="CML load bias", default=0.55)
    period_s = h.Param(dtype=h.Scalar, desc="Phase period", default=400e-12)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Rise and fall time of every source", default=40e-12)


def _validate_pi_tb_params(params: PiTbParams) -> None:
    values = (params.vdd, params.cload, params.period_s, params.transition_time_s)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("phase interpolator testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0:
        raise ValueError("phase interpolator supply and load must be positive")
    if float(params.transition_time_s) <= 0 or float(params.period_s) <= 2 * float(params.transition_time_s):
        raise ValueError("phase interpolator period must exceed both transitions, which must be positive")


@h.generator
def PiTb(params: PiTbParams) -> h.Module:
    """Generate a phase interpolator testbench: phase A and phase B, a quarter period later, full-swing (CMOS) or at CML levels, both complements; fixed biases, a load on each output."""

    _validate_pi_tb_params(params)

    PiTb, connections = testbench_from_ports(
        "PiTb", {net.name: net for net in PiNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = PiTb.vss
    vdd = float(params.vdd)
    low = 0.0 if params.pi.style == Style.CMOS else float(params.cml_low)
    period = float(params.period_s)
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    PiTb.vvdd = Vdc(dc=vdd)(p=PiTb.vdd, n=vss)
    for phase, delay in (("a", period / 4), ("b", period / 2)):
        for side, (v1, v2) in (("p", (low, vdd)), ("n", (vdd, low))):
            net = getattr(PiTb, f"{phase}{side}")
            PiTb.add(
                Vpulse(v1=v1, v2=v2, period=period, width=period / 2, delay=delay, **edge)(p=net, n=vss),
                name=f"vphase_{phase}{side}",
            )
    PiTb.vvbn = Vdc(dc=params.vbn)(p=PiTb.vbn, n=vss)
    PiTb.vvbp = Vdc(dc=params.vbp)(p=PiTb.vbp, n=vss)
    PiTb.cloadp = C(c=params.cload)(p=PiTb.outp, n=vss)
    PiTb.cloadn = C(c=params.cload)(p=PiTb.outn, n=vss)
    PiTb.dut = Pi(params.pi)(**connections)
    return PiTb


def _transient(run_dir: Path, params: PiTbParams, tstop: float, check: bool) -> Path:
    """Run one phase interpolator testbench transient in TSMC65 (``check``: one tenth of it with Spectre's checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = PiTb(params)
    h.pdk.compile(tb)
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([raw for raw in pi_signal_names() if raw != "time"]),
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


def cml_half_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the CML interpolator at equal weights over five periods."""

    params = PiTbParams(pi=CASES["cml_half"])
    return _transient(run_dir, params, 5 * float(params.period_s), check)


def cmos_half_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the CMOS interpolator at equal weights over five periods."""

    params = PiTbParams(pi=CASES["cmos_half"])
    return _transient(run_dir, params, 5 * float(params.period_s), check)


def main() -> None:
    """Create one output directory and run one named phase interpolator target."""

    targets = {
        target.__name__: target
        for target in (
            cml_half_transient,
            cmos_half_transient,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available phase interpolator simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "pi"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
