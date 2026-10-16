"""Level shifter testbench and named TSMC65 Spectre simulation targets."""

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

from .subckt import CASES, LvShift, LvShiftNets, LvShiftParams


def lvshift_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in LvShiftNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class LvShiftTbParams:
    """Parameters which determine the generated level shifter testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage (the outputs')", default=1.2)
    vddl = h.Param(dtype=h.Scalar, desc="The inputs' supply", default=0.6)
    lvshift = h.Param(dtype=LvShiftParams, desc="Level shifter parameters", default=LvShiftParams())
    cload = h.Param(dtype=h.Prefixed, desc="Load capacitance on each output", default=2 * f)
    period_s = h.Param(dtype=h.Scalar, desc="Input period", default=4e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Rise and fall time of every source", default=50e-12)


def _validate_lvshift_tb_params(params: LvShiftTbParams) -> None:
    values = (params.vdd, params.cload, params.period_s, params.transition_time_s)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("level shifter testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0:
        raise ValueError("level shifter supply and load must be positive")
    if float(params.transition_time_s) <= 0 or float(params.period_s) <= 2 * float(params.transition_time_s):
        raise ValueError("level shifter period must exceed both transitions, which must be positive")
    if not 0 < float(params.vddl) <= float(params.vdd):
        raise ValueError("level shifter input supply must lie between 0 and vdd")


@h.generator
def LvShiftTb(params: LvShiftTbParams) -> h.Module:
    """Generate a level shifter testbench: complementary input pulses at vddl levels, rst high for the first quarter period, a load on each output and buffered output."""

    _validate_lvshift_tb_params(params)

    LvShiftTb, connections = testbench_from_ports(
        "LvShiftTb", {net.name: net for net in LvShiftNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = LvShiftTb.vss
    vdd, vddl, period = float(params.vdd), float(params.vddl), float(params.period_s)
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    LvShiftTb.vvdd = Vdc(dc=vdd)(p=LvShiftTb.vdd, n=vss)
    LvShiftTb.vvddl = Vdc(dc=vddl)(p=LvShiftTb.vddl, n=vss)
    LvShiftTb.vinp = Vpulse(v1=0.0, v2=vddl, period=period, width=period / 2, delay=period / 2, **edge)(
        p=LvShiftTb.inp, n=vss
    )
    if not params.lvshift.input_inverter:  # the shifter makes inn itself otherwise
        LvShiftTb.vinn = Vpulse(v1=vddl, v2=0.0, period=period, width=period / 2, delay=period / 2, **edge)(
            p=LvShiftTb.inn, n=vss
        )
    LvShiftTb.vrst = Vpulse(v1=vdd, v2=0.0, period=1.0, width=0.5, delay=period / 4, **edge)(p=LvShiftTb.rst, n=vss)
    for name in ("outp", "outn", "bufp", "bufn"):
        LvShiftTb.add(C(c=params.cload)(p=getattr(LvShiftTb, name), n=vss), name=f"c{name}")
    LvShiftTb.dut = LvShift(params.lvshift)(**connections)
    return LvShiftTb


def _transient(run_dir: Path, params: LvShiftTbParams, tstop: float, check: bool) -> Path:
    """Run one level shifter testbench transient in TSMC65 (``check``: one tenth of it with Spectre's checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = LvShiftTb(params)
    h.pdk.compile(tb)
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([raw for raw in lvshift_signal_names() if raw != "time"]),
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


def core_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the cross-coupled core over three input periods."""

    params = LvShiftTbParams(lvshift=CASES["core"])
    return _transient(run_dir, params, 3 * float(params.period_s), check)


def single_rst_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the level shifter with an input inverter and reset over three input periods."""

    params = LvShiftTbParams(lvshift=CASES["single_rst"])
    return _transient(run_dir, params, 3 * float(params.period_s), check)


def main() -> None:
    """Create one output directory and run one named level shifter target."""

    targets = {
        target.__name__: target
        for target in (
            core_transient,
            single_rst_transient,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available level shifter simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "lvshift"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
