"""Delay line and ring oscillator testbench and named TSMC65 Spectre simulation targets."""

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

from .subckt import CASES, Delay, DelayNets, DelayParams


def delay_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in DelayNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class DelayTbParams:
    """Parameters which determine the generated delay line or ring testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    delay = h.Param(dtype=DelayParams, desc="Delay line or ring parameters", default=DelayParams())
    cload = h.Param(dtype=h.Prefixed, desc="Load capacitance on each output", default=2 * f)
    vbn = h.Param(dtype=h.Scalar, desc="Starving NMOS bias", default=0.7)
    vbp = h.Param(dtype=h.Scalar, desc="Starving PMOS bias", default=0.5)
    vctrl = h.Param(dtype=h.Scalar, desc="Shared tail bias", default=0.8)
    vinj = h.Param(dtype=h.Scalar, desc="Injection input level", default=0.0)
    period_s = h.Param(dtype=h.Scalar, desc="Input period (a chain)", default=4e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Input and enable rise and fall time", default=50e-12)
    enable_delay_s = h.Param(dtype=h.Scalar, desc="Time before en rises (a ring)", default=1e-9)


def _validate_delay_tb_params(params: DelayTbParams) -> None:
    values = (
        params.vdd,
        params.cload,
        params.vbn,
        params.vbp,
        params.vctrl,
        params.vinj,
        params.period_s,
        params.transition_time_s,
        params.enable_delay_s,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("delay testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0:
        raise ValueError("delay supply and load must be positive")
    if float(params.period_s) <= 2 * float(params.transition_time_s) or float(params.transition_time_s) <= 0:
        raise ValueError("delay input period must exceed both transitions, which must be positive")
    if float(params.enable_delay_s) < 0:
        raise ValueError("delay enable time must be non-negative")


@h.generator
def DelayTb(params: DelayTbParams) -> h.Module:
    """Generate a delay line (complementary input pulses) or ring (enable step) testbench."""

    _validate_delay_tb_params(params)

    DelayTb, connections = testbench_from_ports(
        "DelayTb", {net.name: net for net in DelayNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vdd, vss = params.vdd, DelayTb.vss
    DelayTb.vvdd = Vdc(dc=vdd)(p=DelayTb.vdd, n=vss)
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    half = float(params.period_s) / 2
    DelayTb.vinp = Vpulse(v1=0.0, v2=vdd, period=params.period_s, width=half, delay=half / 2, **edge)(
        p=DelayTb.inp, n=vss
    )
    DelayTb.vinn = Vpulse(v1=vdd, v2=0.0, period=params.period_s, width=half, delay=half / 2, **edge)(
        p=DelayTb.inn, n=vss
    )
    # en rises once and stays high: one pulse longer than any run
    DelayTb.ven = Vpulse(v1=0.0, v2=vdd, period=1.0, width=0.5, delay=params.enable_delay_s, **edge)(
        p=DelayTb.en, n=vss
    )
    DelayTb.vinj = Vdc(dc=params.vinj)(p=DelayTb.inj, n=vss)
    DelayTb.vvbn = Vdc(dc=params.vbn)(p=DelayTb.vbn, n=vss)
    DelayTb.vvbp = Vdc(dc=params.vbp)(p=DelayTb.vbp, n=vss)
    DelayTb.vvctrl = Vdc(dc=params.vctrl)(p=DelayTb.vctrl, n=vss)
    DelayTb.cloadp = C(c=params.cload)(p=DelayTb.outp, n=vss)
    DelayTb.cloadn = C(c=params.cload)(p=DelayTb.outn, n=vss)
    DelayTb.dut = Delay(params.delay)(**connections)
    return DelayTb


def _transient(run_dir: Path, params: DelayTbParams, tstop: float, check: bool) -> Path:
    """Run one delay testbench transient in TSMC65 (``check``: one tenth of it with Spectre's checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = DelayTb(params)
    h.pdk.compile(tb)
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([raw for raw in delay_signal_names() if raw != "time"]),
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


def chain4_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run three input periods through the four-stage inverter delay line."""

    params = DelayTbParams(delay=CASES["chain4"])
    return _transient(run_dir, params, 3 * float(params.period_s), check)


def ring5_starved_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the current-starved five-stage ring for 20 ns after its enable."""

    params = DelayTbParams(delay=CASES["ring5_starved"])
    return _transient(run_dir, params, float(params.enable_delay_s) + 20e-9, check)


def ring5_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the five-stage inverter ring for 10 ns after its enable."""

    params = DelayTbParams(delay=CASES["ring5"])
    return _transient(run_dir, params, float(params.enable_delay_s) + 10e-9, check)


def ring4_coupled_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the four-stage coupled ring for 10 ns after its enable."""

    params = DelayTbParams(delay=CASES["ring4_coupled"])
    return _transient(run_dir, params, float(params.enable_delay_s) + 10e-9, check)


def main() -> None:
    """Create one output directory and run one named delay line or ring target."""

    targets = {
        target.__name__: target
        for target in (chain4_transient, ring4_coupled_transient, ring5_starved_transient, ring5_transient)
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available delay line and ring simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "delay"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
