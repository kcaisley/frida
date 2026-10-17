"""MOS capacitor testbench and named TSMC65 Spectre simulation targets.

The testbench follows BAG's MOS capacitor characterization (``bag3_analog`` ``mos_cap``, the
decap array): the AC stimulus on the capacitor's own net at its DC bias, so the stimulated
source's current is the admittance, whose imaginary part over 2 pi f is the capacitance and whose
real part the loss; an operating point gives the leakage. A decap's bias is its supply, a
two-net capacitor's the gate plate's voltage over the channel plate's.
"""

import argparse
import json
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.primitives import Vdc
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.analysis.io import write_measurement
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Mode, MosCap, MosCapNets, MosCapParams


def moscap_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle: the currents of the
    sources on vdd and on top, from which the capacitance follows."""
    names = {"freq": "freq"}
    for net in MosCapNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class MosCapTbParams:
    """Parameters which determine the generated MOS capacitor testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    moscap = h.Param(dtype=MosCapParams, desc="Capacitor parameters", default=MosCapParams())
    vtop = h.Param(dtype=h.Scalar, desc="Gate-plate DC voltage (two-net capacitor)", default=1.2)
    vbot = h.Param(dtype=h.Scalar, desc="Channel-plate DC voltage (two-net capacitor)", default=0.0)
    fstart_hz = h.Param(dtype=float, desc="AC sweep start", default=1e6)
    fstop_hz = h.Param(dtype=float, desc="AC sweep stop", default=1e11)
    points_per_decade = h.Param(dtype=int, desc="AC points per decade", default=10)


def _validate_moscap_tb_params(params: MosCapTbParams) -> None:
    values = (params.vdd, params.vtop, params.vbot)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("MOS capacitor testbench values must be finite")
    if float(params.vdd) <= 0:
        raise ValueError("MOS capacitor supply must be positive")
    if not all(0 <= float(value) <= float(params.vdd) for value in values[1:]):
        raise ValueError("MOS capacitor plate voltages must lie between the rails")
    if not 0 < params.fstart_hz < params.fstop_hz or params.points_per_decade < 1:
        raise ValueError("MOS capacitor frequency sweep must rise from a positive start")


@h.generator
def MosCapTb(params: MosCapTbParams) -> h.Module:
    """Generate the MOS capacitor testbench: the AC stimulus on vdd (a decap) or on top (a two-net
    capacitor) at its DC level; the stimulated source's current gives the capacitance."""

    _validate_moscap_tb_params(params)

    MosCapTb, connections = testbench_from_ports(
        "MosCapTb", {net.name: net for net in MosCapNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    decap = params.moscap.mode == Mode.DECAP
    vss = MosCapTb.vss
    MosCapTb.vvdd = Vdc(dc=params.vdd, ac=1.0 if decap else 0.0)(p=MosCapTb.vdd, n=vss)
    MosCapTb.vtop = Vdc(dc=params.vtop, ac=0.0 if decap else 1.0)(p=MosCapTb.top, n=vss)
    MosCapTb.vbot = Vdc(dc=params.vbot)(p=MosCapTb.bot, n=vss)
    MosCapTb.dut = MosCap(params.moscap)(**connections)
    return MosCapTb


def _run_moscap_sim(run_dir: Path, params: MosCapTbParams, *, check: bool = False) -> Path:
    """Run the operating point and AC response of one MOS capacitor in TSMC65 and return the raw
    file (``check``: two points a decade, with Spectre's static checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = MosCapTb(params)
    h.pdk.compile(tb)
    decades = math.log10(params.fstop_hz / params.fstart_hz)
    attrs = [
        site.install.include(h.pdk.Corner.TYP),
        site.install.include_pre_simulation(),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in moscap_signal_names() if raw != "freq"]),
    ]
    if check:
        attrs.append(
            h.Literal(
                "check_caps static_capacitor type=distr\n"
                "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top\n"
                "check_highz static_highz node=[*] fanout=gate_has_driver_no_moscap\n"
                "check_dcpath static_dcpath net=[xtop.vdd 0]\n"
                "check_topology static_topology node=[*] pin2gnd=on"
            )
        )
    attrs += [
        hs.Op(name="op"),
        hs.Ac(
            sweep=hs.LogSweep(
                start=params.fstart_hz,
                stop=params.fstop_hz,
                npts=round(decades * (2 if check else params.points_per_decade)) + 1,
            ),
            name="ac",
        ),
    ]
    hs.Sim(tb=tb, attrs=attrs).run(
        SimOptions(
            simulator=SupportedSimulators.SPECTRE,
            # the campaign reads the raw file itself: an operating point and an AC analysis
            fmt=ResultFormat.NONE,
            rundir=run_dir,
            simulator_args=(
                *(() if check else ("-format", "nutbin")),
                "+preset=mx",
                "+mt=1",
                "+lqtimeout",
                "3600",
                "+escchars",
                "+log",
                "spectre.log",
                *(("-ahdllint=warn", "-ahdllint_log", "ahdllint.log") if check else ()),
            ),
        )
    )
    return run_dir / "netlist.raw"


# The characterization: a decap over its supply up to past TSMC65's 1.2 V core, a two-net
# capacitor over the gate plate's voltage relative to the channel plate, both signs.
SUPPLY_SWEEP_V = tuple(round(0.1 * step, 3) for step in range(1, 14))
BIAS_SWEEP_V = tuple(round(0.1 * step, 3) for step in range(-12, 13))
NOMINAL_SUPPLY_V = 1.2


def moscap_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every MOS capacitor over its bias: 13 supplies for a decap, 25 plate biases otherwise.

    Each point writes ``<case>/bias<mV>/result.h5`` (a ``MeasMosCap``). ``check`` runs the
    nominal bias of each case with Spectre's checks instead, writing no measurement.
    """

    from vlsirtools.spice.spectre import parse_nutbin

    from flow.analysis.types import MeasInfo
    from flow.moscap.analysis import MeasMosCap

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for case, moscap in CASES.items():
        decap = moscap.mode == Mode.DECAP
        for bias in (NOMINAL_SUPPLY_V,) if check else SUPPLY_SWEEP_V if decap else BIAS_SWEEP_V:
            # a decap's bias is its supply (its unused plates on vss); a two-net capacitor's the
            # gate plate above the channel plate, either on vss
            params = (
                MosCapTbParams(moscap=moscap, vdd=bias, vtop=0.0)
                if decap
                else MosCapTbParams(moscap=moscap, vtop=max(bias, 0.0), vbot=max(-bias, 0.0))
            )
            jobs[f"{case}/bias{round(bias * 1e3)}"] = params
    failures: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
        futures = {
            executor.submit(_run_moscap_sim, run_dir / name, params, check=check): (name, params)
            for name, params in jobs.items()
        }
        for future in as_completed(futures):
            name, params = futures[future]
            try:
                raw_path = future.result()
                if check:
                    continue
                with raw_path.open("rb") as stream:
                    analyses = parse_nutbin(stream)
                op, ac = analyses["op"].data, analyses["ac"].data
                # the stimulated source's current drawn per volt of AC: the capacitor's admittance
                source = "xtop.vvdd:p" if params.moscap.mode == Mode.DECAP else "xtop.vtop:p"
                admittance = -np.asarray(ac[source])
                measurement = MeasMosCap(
                    group=None,
                    index=None,
                    dut=params.moscap,
                    info=MeasInfo(
                        backend="spice",
                        timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                        instruments={"simulator": "Spectre"},
                        readbacks={
                            "case": name.split("/")[0],
                            "raw_file": raw_path.name,
                            "stimulated_source": source,
                            "bias_mv": int(name.split("/")[1].removeprefix("bias")),
                            "op_leakage_a": -float(np.real(op[source][0])),
                        },
                    ),
                    param=params,
                    frequency_hz=np.real(np.asarray(ac["freq"])).astype(np.float64),
                    conductance_s=np.real(admittance).astype(np.float64),
                    susceptance_s=np.imag(admittance).astype(np.float64),
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
            except Exception as error:  # noqa: BLE001 - report every independent point failure
                failures[name] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} MOS capacitor points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named MOS capacitor target."""

    targets = {target.__name__: target for target in (moscap_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available MOS capacitor simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "moscap"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
