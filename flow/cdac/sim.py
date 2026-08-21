"""CDAC testbench and named TSMC65 Spectre simulation targets."""

import argparse
from datetime import datetime
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import f, p
from hdl21.primitives import C, Vdc, Vpwl
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.pdks import set_pdk
from pdk import site

from .subckt import Cdac, CdacParams


@h.paramclass
class CdacTbParams:
    """Parameters which determine the generated CDAC testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    cdac = h.Param(dtype=CdacParams, desc="CDAC parameters", default=CdacParams())
    code_dwell_s = h.Param(dtype=h.Scalar, desc="Time held at each input code", default=200e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Input-code transition time", default=100e-12)


@h.generator
def CdacTb(params: CdacTbParams) -> h.Module:
    """Generate a complete code-ramp CDAC testbench."""

    if float(params.code_dwell_s) <= 0.0 or float(params.transition_time_s) <= 0.0:
        raise ValueError("CDAC dwell and transition times must be positive")
    n_bits = params.cdac.n_dac + params.cdac.n_extra

    @h.module
    class CdacTb:
        vss = h.Port(desc="Simulator ground")
        vdd, top = h.Signals(2)
        dac_bits = h.Signal(width=n_bits)

    CdacTb.vvdd = Vdc(dc=params.vdd)(p=CdacTb.vdd, n=CdacTb.vss)
    CdacTb.cload = C(c=100 * f)(p=CdacTb.top, n=CdacTb.vss)
    CdacTb.dut = Cdac(params.cdac)(top=CdacTb.top, dac=CdacTb.dac_bits, vdd=CdacTb.vdd, vss=CdacTb.vss)
    bit_values: list[list[h.Scalar]] = [[] for _ in range(n_bits)]
    for code in range(2**params.cdac.n_dac):
        for bit in range(n_bits):
            bit_values[bit].append(params.vdd if (code >> bit) & 1 else 0.0)
    for bit, values in enumerate(bit_values):
        setattr(
            CdacTb,
            f"vdac_{bit}",
            Vpwl(
                wave=h.Pwl.steps(
                    values=values,
                    dwell=params.code_dwell_s + params.transition_time_s,
                    transition=params.transition_time_s,
                    transition_at="end",
                )
            )(p=CdacTb.dac_bits[bit], n=CdacTb.vss),
        )
    return CdacTb


def frida65_baseline_check(run_dir: Path) -> Path:
    """Run one short, noise-free CDAC transient with Spectre circuit checks."""

    params = CdacTbParams()
    set_pdk("tsmc65")
    tb = CdacTb(params)
    h.pdk.compile(tb)
    assert site.tsmc65.install is not None
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.tsmc65.install.include(h.pdk.Corner.TYP),
            site.tsmc65.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([tb.top, tb.dac_bits, "xtop.vvdd:p"]),
            h.Literal(
                "check_caps static_capacitor type=distr\n"
                "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top "
                "gate2power=on gate2ground=on\n"
                "check_highz static_highz node=[*] fanout=gate_has_driver_no_moscap\n"
                "check_dcpath static_dcpath net=[xtop.vdd 0]\n"
                "check_topology static_topology node=[*] pin2gnd=on\n"
                "check_nodecap dyn_nodecap node=[xtop.top] time=[100n 200n]"
            ),
            hs.Tran(
                tstop=params.code_dwell_s + params.transition_time_s,
                name="tran",
                options={"strobeperiod": 100 * p, "strobeoutput": "strobeonly"},
            ),
        ],
    )
    simulation.run(
        SimOptions(
            simulator=SupportedSimulators.SPECTRE,
            fmt=ResultFormat.NONE,
            rundir=run_dir,
            simulator_args=(
                "+preset=mx",
                "+mt=4",
                "+lqtimeout",
                "3600",
                "+escchars",
                "+log",
                "spectre.log",
                "-ahdllint=warn",
                "-ahdllint_log",
                "ahdllint.log",
            ),
        )
    )
    return run_dir


def frida65_baseline_transient(run_dir: Path) -> Path:
    """Run the complete fabricated-size CDAC code ramp."""

    params = CdacTbParams()
    set_pdk("tsmc65")
    tb = CdacTb(params)
    h.pdk.compile(tb)
    assert site.tsmc65.install is not None
    n_codes = 2**params.cdac.n_dac
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.tsmc65.install.include(h.pdk.Corner.TYP),
            site.tsmc65.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([tb.top, tb.dac_bits, "xtop.vvdd:p"]),
            hs.Tran(
                tstop=n_codes * params.code_dwell_s + (n_codes - 1) * params.transition_time_s,
                name="tran",
                options={"strobeperiod": 100 * p, "strobeoutput": "strobeonly"},
            ),
        ],
    )
    simulation.run(
        SimOptions(
            simulator=SupportedSimulators.SPECTRE,
            fmt=ResultFormat.SIM_DATA,
            rundir=run_dir,
            simulator_args=(
                "+preset=mx",
                "+mt=4",
                "+lqtimeout",
                "3600",
                "+escchars",
                "+log",
                "spectre.log",
            ),
        )
    )
    return run_dir


def main() -> None:
    """Create one output directory and run one named CDAC target."""

    targets = {target.__name__: target for target in (frida65_baseline_check, frida65_baseline_transient)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available CDAC simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "cdac"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
