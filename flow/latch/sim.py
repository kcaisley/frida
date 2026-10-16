"""Latch testbench and named TSMC65 Spectre simulation targets."""

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

from .subckt import CASES, Latch, LatchNets, LatchParams, Style


def latch_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in LatchNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class LatchTbParams:
    """Parameters which determine the generated latch testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    latch = h.Param(dtype=LatchParams, desc="Latch parameters", default=LatchParams())
    cload = h.Param(dtype=h.Prefixed, desc="Load capacitance on q and qb", default=2 * f)
    clock_period_s = h.Param(dtype=h.Scalar, desc="Clock period", default=2e-9)
    data_period_s = h.Param(dtype=h.Scalar, desc="Data (and SR set) period", default=5.2e-9)
    reset_time_s = h.Param(dtype=h.Scalar, desc="Reset (rst) pulse length at the start", default=0.5e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Rise and fall time of every source", default=50e-12)


def _validate_latch_tb_params(params: LatchTbParams) -> None:
    values = (
        params.vdd,
        params.cload,
        params.clock_period_s,
        params.data_period_s,
        params.reset_time_s,
        params.transition_time_s,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("latch testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0:
        raise ValueError("latch supply and load must be positive")
    edge = 2 * float(params.transition_time_s)
    if float(params.transition_time_s) <= 0 or min(float(params.clock_period_s), float(params.data_period_s)) <= edge:
        raise ValueError("latch periods must exceed both transitions, which must be positive")
    if float(params.reset_time_s) < 0:
        raise ValueError("latch reset time must be non-negative")


@h.generator
def LatchTb(params: LatchTbParams) -> h.Module:
    """Generate a latch testbench: complementary clocks, data slower than the clock, an initial
    reset pulse, and set and reset pulses for an SR latch."""

    _validate_latch_tb_params(params)

    LatchTb, connections = testbench_from_ports(
        "LatchTb", {net.name: net for net in LatchNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vdd, vss = params.vdd, LatchTb.vss
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    clock, data = float(params.clock_period_s), float(params.data_period_s)
    LatchTb.vvdd = Vdc(dc=vdd)(p=LatchTb.vdd, n=vss)
    LatchTb.vclk = Vpulse(v1=0.0, v2=vdd, period=clock, width=clock / 2, delay=clock / 2, **edge)(p=LatchTb.clk, n=vss)
    LatchTb.vclkb = Vpulse(v1=vdd, v2=0.0, period=clock, width=clock / 2, delay=clock / 2, **edge)(
        p=LatchTb.clkb, n=vss
    )
    LatchTb.vd = Vpulse(v1=0.0, v2=vdd, period=data, width=data / 2, delay=data / 4, **edge)(p=LatchTb.d, n=vss)
    LatchTb.vrst = Vpulse(v1=vdd, v2=0.0, period=1.0, width=0.5, delay=params.reset_time_s, **edge)(
        p=LatchTb.rst, n=vss
    )
    # set and reset pulses, a quarter period each and half a period apart (active low for a NAND latch)
    active, idle = (0.0, vdd) if params.latch.style == Style.SR_NAND else (vdd, 0.0)
    for name, net, delay in (("vs", LatchTb.s, data / 4), ("vr", LatchTb.r, 3 * data / 4)):
        LatchTb.add(
            Vpulse(v1=idle, v2=active, period=data, width=data / 4, delay=delay, **edge)(p=net, n=vss), name=name
        )
    LatchTb.cloadq = C(c=params.cload)(p=LatchTb.q, n=vss)
    LatchTb.cloadqb = C(c=params.cload)(p=LatchTb.qb, n=vss)
    LatchTb.dut = Latch(params.latch)(**connections)
    return LatchTb


def _transient(run_dir: Path, params: LatchTbParams, tstop: float, check: bool) -> Path:
    """Run one latch testbench transient in TSMC65 (``check``: one tenth of it with Spectre's checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = LatchTb(params)
    h.pdk.compile(tb)
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([raw for raw in latch_signal_names() if raw != "time"]),
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


def div2_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the divide-by-two flip-flop for eight clock periods after its reset."""

    params = LatchTbParams(latch=CASES["div2"])
    return _transient(run_dir, params, 8 * float(params.clock_period_s) + float(params.reset_time_s), check)


def flop_rst_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the flip-flop with reset over three data periods."""

    params = LatchTbParams(latch=CASES["flop_rst"])
    return _transient(run_dir, params, 3 * float(params.data_period_s), check)


def sr_nand_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the NAND SR latch over three set and reset periods."""

    params = LatchTbParams(latch=CASES["sr_nand"])
    return _transient(run_dir, params, 3 * float(params.data_period_s), check)


def main() -> None:
    """Create one output directory and run one named latch target."""

    targets = {target.__name__: target for target in (div2_transient, flop_rst_transient, sr_nand_transient)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available latch simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "latch"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
