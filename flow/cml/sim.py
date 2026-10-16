"""CML testbench and named TSMC65 Spectre simulation targets."""

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

from .subckt import CASES, Cml, CmlNets, CmlParams


def cml_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in CmlNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class CmlTbParams:
    """Parameters which determine the generated CML testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    cml = h.Param(dtype=CmlParams, desc="CML parameters", default=CmlParams())
    cload = h.Param(dtype=h.Prefixed, desc="Load capacitance on each output", default=2 * f)
    vhigh = h.Param(dtype=h.Scalar, desc="High level of the CML inputs", default=1.2)
    vlow = h.Param(dtype=h.Scalar, desc="Low level of the CML inputs", default=0.8)
    vbn = h.Param(dtype=h.Scalar, desc="NMOS bias", default=0.55)
    vbp = h.Param(dtype=h.Scalar, desc="PMOS bias", default=0.55)
    clock_period_s = h.Param(dtype=h.Scalar, desc="Clock (or second input) period", default=200e-12)
    data_period_s = h.Param(dtype=h.Scalar, desc="Data input period", default=520e-12)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Rise and fall time of every source", default=20e-12)


def _validate_cml_tb_params(params: CmlTbParams) -> None:
    values = (params.vdd, params.cload, params.vhigh, params.vlow, params.vbn, params.vbp)
    values += (params.clock_period_s, params.data_period_s, params.transition_time_s)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("CML testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0:
        raise ValueError("CML supply and load must be positive")
    edge = 2 * float(params.transition_time_s)
    if float(params.transition_time_s) <= 0 or min(float(params.clock_period_s), float(params.data_period_s)) <= edge:
        raise ValueError("CML periods must exceed both transitions, which must be positive")


@h.generator
def CmlTb(params: CmlTbParams) -> h.Module:
    """Generate a CML testbench: differential data and clock pulses between the CML levels,
    fixed biases, a load on each output."""

    _validate_cml_tb_params(params)

    CmlTb, connections = testbench_from_ports(
        "CmlTb", {net.name: net for net in CmlNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = CmlTb.vss
    hi, lo = params.vhigh, params.vlow
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    CmlTb.vvdd = Vdc(dc=params.vdd)(p=CmlTb.vdd, n=vss)
    for name, period in (("in", float(params.data_period_s)), ("clk", float(params.clock_period_s))):
        for side, (v1, v2) in (("p", (lo, hi)), ("n", (hi, lo))):
            net = getattr(CmlTb, f"{name}{side}")
            CmlTb.add(
                Vpulse(v1=v1, v2=v2, period=period, width=period / 2, delay=period / 4, **edge)(p=net, n=vss),
                name=f"v{name}{side}",
            )
    CmlTb.vvbn = Vdc(dc=params.vbn)(p=CmlTb.vbn, n=vss)
    CmlTb.vvbp = Vdc(dc=params.vbp)(p=CmlTb.vbp, n=vss)
    CmlTb.cloadp = C(c=params.cload)(p=CmlTb.outp, n=vss)
    CmlTb.cloadn = C(c=params.cload)(p=CmlTb.outn, n=vss)
    CmlTb.dut = Cml(params.cml)(**connections)
    return CmlTb


def _transient(run_dir: Path, params: CmlTbParams, tstop: float, check: bool) -> Path:
    """Run one CML testbench transient in TSMC65 (``check``: one tenth of it with Spectre's checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = CmlTb(params)
    h.pdk.compile(tb)
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([raw for raw in cml_signal_names() if raw != "time"]),
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


def buffer_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the NMOS-input buffer over three data periods."""

    params = CmlTbParams(cml=CASES["buffer"])
    return _transient(run_dir, params, 3 * float(params.data_period_s), check)


def divider_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the divide-by-two for twenty clock periods."""

    params = CmlTbParams(cml=CASES["divider"])
    return _transient(run_dir, params, 20 * float(params.clock_period_s), check)


def main() -> None:
    """Create one output directory and run one named CML target."""

    targets = {target.__name__: target for target in (buffer_transient, divider_transient)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available CML simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "cml"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
