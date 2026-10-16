"""Clock generator testbench and named TSMC65 Spectre simulation targets."""

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

from .subckt import CASES, Clkgen, ClkgenNets, ClkgenParams


def clkgen_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in ClkgenNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class ClkgenTbParams:
    """Parameters which determine the generated clock generator testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    clkgen = h.Param(dtype=ClkgenParams, desc="Clock generator parameters", default=ClkgenParams())
    cload = h.Param(dtype=h.Prefixed, desc="Load capacitance on each output", default=2 * f)
    period_s = h.Param(dtype=h.Scalar, desc="Clock period", default=1e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Rise and fall time of every source", default=30e-12)


def _validate_clkgen_tb_params(params: ClkgenTbParams) -> None:
    values = (params.vdd, params.cload, params.period_s, params.transition_time_s)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("clock generator testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0:
        raise ValueError("clock generator supply and load must be positive")
    if float(params.transition_time_s) <= 0 or float(params.period_s) <= 2 * float(params.transition_time_s):
        raise ValueError("clock generator period must exceed both transitions, which must be positive")


@h.generator
def ClkgenTb(params: ClkgenTbParams) -> h.Module:
    """Generate a clock generator testbench: complementary clocks, en low for the first two periods then high, a load on each output."""

    _validate_clkgen_tb_params(params)

    ClkgenTb, connections = testbench_from_ports(
        "ClkgenTb", {net.name: net for net in ClkgenNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = ClkgenTb.vss
    vdd, period = float(params.vdd), float(params.period_s)
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    ClkgenTb.vvdd = Vdc(dc=vdd)(p=ClkgenTb.vdd, n=vss)
    ClkgenTb.vclk = Vpulse(v1=0.0, v2=vdd, period=period, width=period / 2, delay=period / 2, **edge)(
        p=ClkgenTb.clk, n=vss
    )
    ClkgenTb.vclkb = Vpulse(v1=vdd, v2=0.0, period=period, width=period / 2, delay=period / 2, **edge)(
        p=ClkgenTb.clkb, n=vss
    )
    # en rises a quarter period into the third clock period, while clk is low
    ClkgenTb.ven = Vpulse(v1=0.0, v2=vdd, period=1.0, width=0.5, delay=2.25 * period, **edge)(p=ClkgenTb.en, n=vss)
    ClkgenTb.cloadp = C(c=params.cload)(p=ClkgenTb.outp, n=vss)
    ClkgenTb.cloadn = C(c=params.cload)(p=ClkgenTb.outn, n=vss)
    ClkgenTb.dut = Clkgen(params.clkgen)(**connections)
    return ClkgenTb


def _transient(run_dir: Path, params: ClkgenTbParams, tstop: float, check: bool) -> Path:
    """Run one clock generator testbench transient in TSMC65 (``check``: one tenth of it with Spectre's checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = ClkgenTb(params)
    h.pdk.compile(tb)
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            site.install.include_stdcell(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([raw for raw in clkgen_signal_names() if raw != "time"]),
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


def gate_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the clock gate over six clock periods (en rises in the third)."""

    params = ClkgenTbParams(clkgen=CASES["gate"])
    return _transient(run_dir, params, 6 * float(params.period_s), check)


def nonoverlap_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the non-overlapping clock generator over five clock periods."""

    params = ClkgenTbParams(clkgen=CASES["nonoverlap"])
    return _transient(run_dir, params, 5 * float(params.period_s), check)


def pulse_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run the rising-edge pulse generator over five clock periods."""

    params = ClkgenTbParams(clkgen=CASES["pulse"])
    return _transient(run_dir, params, 5 * float(params.period_s), check)


def main() -> None:
    """Create one output directory and run one named clock generator target."""

    targets = {
        target.__name__: target
        for target in (
            gate_transient,
            nonoverlap_transient,
            pulse_transient,
        )
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available clock generator simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "clkgen"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
