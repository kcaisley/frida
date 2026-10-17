"""Current source testbench and named TSMC65 Spectre simulation targets.

The testbench follows Usb2Phy's ``IdacSweepTb``: an operating point of the unit with its bias a
voltage or, with a diode, a reference current, here with out and dump held by sources whose
currents are the unit's and the output's voltage swept (Spectre's DC sweep), so one run gives the
whole output characteristic: the current, its output resistance, and its compliance.
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
from hdl21.primitives import Idc, MosType, Vdc
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.analysis.io import write_measurement
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Idac, IdacNets, IdacParams, Switch


def idac_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle: the voltages of the
    ports and the currents of the sources holding out and dump."""
    names = {}
    for net in IdacNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
    names.update({"xtop.vout:p": "i(out)", "xtop.vdump:p": "i(dump)", "xtop.vvdd:p": "i(vdd)"})
    return names


@h.paramclass
class IdacTbParams:
    """Parameters which determine the generated current source testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    idac = h.Param(dtype=IdacParams, desc="Current source parameters", default=IdacParams())
    vout = h.Param(dtype=h.Scalar, desc="Voltage held on out and dump (the sweep's operating point)", default=0.6)
    vbias = h.Param(dtype=h.Scalar, desc="Current source gate voltage (no diode)", default=0.5)
    iref = h.Param(dtype=h.Scalar, desc="Reference current into vbias (with a diode, A)", default=10e-6)
    vcas = h.Param(dtype=h.Scalar, desc="Cascode gate voltage", default=0.8)
    en = h.Param(dtype=bool, desc="en high (enb low)", default=True)
    vout_step_v = h.Param(dtype=float, desc="Output voltage sweep step, from 0 to vdd", default=0.025)


def _validate_idac_tb_params(params: IdacTbParams) -> None:
    values = (params.vdd, params.vout, params.vbias, params.iref, params.vcas, params.vout_step_v)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("current source testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.iref) <= 0 or params.vout_step_v <= 0:
        raise ValueError("current source supply, reference current, and sweep step must be positive")
    if not all(0 <= float(value) <= float(params.vdd) for value in (params.vout, params.vbias, params.vcas)):
        raise ValueError("current source output, bias, and cascode voltages must lie between the rails")


@h.generator
def IdacTb(params: IdacTbParams) -> h.Module:
    """Generate the current source testbench (Usb2Phy ``IdacSweepTb``): out and dump held by
    sources (their currents are the unit's), the bias a voltage or, with a diode, a reference
    current into vbias."""

    _validate_idac_tb_params(params)

    IdacTb, connections = testbench_from_ports(
        "IdacTb", {net.name: net for net in IdacNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss, vdd = IdacTb.vss, float(params.vdd)
    IdacTb.vvdd = Vdc(dc=vdd)(p=IdacTb.vdd, n=vss)
    IdacTb.vout = Vdc(dc=params.vout)(p=IdacTb.out, n=vss)
    IdacTb.vdump = Vdc(dc=params.vout)(p=IdacTb.dump, n=vss)
    IdacTb.ven = Vdc(dc=vdd if params.en else 0.0)(p=IdacTb.en, n=vss)
    IdacTb.venb = Vdc(dc=0.0 if params.en else vdd)(p=IdacTb.enb, n=vss)
    IdacTb.vvcas = Vdc(dc=params.vcas)(p=IdacTb.vcas, n=vss)
    if params.idac.diode:  # a PMOS reference draws its current out of vbias, an NMOS one takes it in
        pmos = params.idac.source_xtors == MosType.PMOS
        IdacTb.iref = Idc(dc=params.iref)(p=IdacTb.vbias if pmos else IdacTb.vdd, n=vss if pmos else IdacTb.vbias)
    else:
        IdacTb.vvbias = Vdc(dc=params.vbias)(p=IdacTb.vbias, n=vss)
    IdacTb.dut = Idac(params.idac)(**connections)
    return IdacTb


def _run_idac_sim(run_dir: Path, params: IdacTbParams, *, check: bool = False) -> Path:
    """Run the operating point and the output voltage sweep of one unit in TSMC65 and return the
    raw file (``check``: the operating point alone, with Spectre's static checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = IdacTb(params)
    h.pdk.compile(tb)
    attrs = [
        site.install.include(h.pdk.Corner.TYP),
        site.install.include_pre_simulation(),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save(list(idac_signal_names())),
    ]
    if check:
        attrs.append(
            h.Literal(
                "check_caps static_capacitor type=distr\n"
                "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top "
                "gate2power=on gate2ground=on\n"
                "check_highz static_highz node=[*] fanout=gate_has_driver_no_moscap\n"
                "check_dcpath static_dcpath net=[xtop.vdd 0]\n"
                "check_topology static_topology node=[*] pin2gnd=on"
            )
        )
    attrs.append(hs.Op(name="op"))
    if not check:
        # VLSIR writes a DC sweep over a netlist parameter only: the out source's own dc here
        attrs.append(
            h.Literal(
                f"sweep_vout dc dev=xtop.vout param=dc start=0 stop={float(params.vdd):g} step={params.vout_step_v:g}"
            )
        )
    hs.Sim(tb=tb, attrs=attrs).run(
        SimOptions(
            simulator=SupportedSimulators.SPECTRE,
            # the campaign reads the raw file itself: an operating point and a DC sweep
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


# The characterization: each unit on and, where it switches, off, at its nominal bias and over
# its bias: the gate drive (vbias for an NMOS source, vdd minus vbias for a PMOS one), or a
# diode reference's current. A PMOS cascode's gate is held as far below vdd as an NMOS one above vss.
NOMINAL_SUPPLY_V = 1.2
NOMINAL_VOUT_V = 0.6
GATE_DRIVE_SWEEP_V = tuple(round(0.35 + 0.05 * step, 3) for step in range(11))
IREF_SWEEP_A = (1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6)
NOMINAL_GATE_DRIVE_V = 0.5
NOMINAL_IREF_A = 10e-6
CASCODE_GATE_DRIVE_V = 0.8


def idac_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every unit's output sweep over its bias and enable state (about 80 runs).

    Each point writes ``<case>/<on|off>/<bias>/result.h5`` (a ``MeasIdac``). ``check`` runs the
    nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from vlsirtools.spice.spectre import parse_nutbin

    from flow.analysis.types import MeasInfo
    from flow.idac.analysis import MeasIdac

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for case, idac in CASES.items():
        pmos = idac.source_xtors == MosType.PMOS
        vcas = NOMINAL_SUPPLY_V - CASCODE_GATE_DRIVE_V if pmos else CASCODE_GATE_DRIVE_V
        states = (True,) if check or idac.switch == Switch.NONE else (True, False)
        if idac.diode:
            irefs = (NOMINAL_IREF_A,) if check else IREF_SWEEP_A
            biases = {f"iref{round(iref * 1e9)}na": {"iref": iref} for iref in irefs}
        else:
            drives = (NOMINAL_GATE_DRIVE_V,) if check else GATE_DRIVE_SWEEP_V
            biases = {
                f"drive{round(drive * 1e3)}mv": {"vbias": NOMINAL_SUPPLY_V - drive if pmos else drive}
                for drive in drives
            }
        for en in states:
            for bias, values in biases.items():
                jobs[f"{case}/{'on' if en else 'off'}/{bias}"] = IdacTbParams(idac=idac, en=en, vcas=vcas, **values)
    names = idac_signal_names()
    failures: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
        futures = {
            executor.submit(_run_idac_sim, run_dir / name, params, check=check): (name, params)
            for name, params in jobs.items()
        }
        for future in as_completed(futures):
            name, params = futures[future]
            try:
                raw_path = future.result()
                if check:
                    continue
                with raw_path.open("rb") as stream:
                    sweep = parse_nutbin(stream)["sweep_vout"].data
                # every current as drawn out of its source: positive into the unit's pin
                measurement = MeasIdac(
                    group=None,
                    index=None,
                    dut=params.idac,
                    info=MeasInfo(
                        backend="spice",
                        timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                        instruments={"simulator": "Spectre"},
                        readbacks={
                            "case": name.split("/")[0],
                            "bias": name.split("/")[2],
                            "raw_file": raw_path.name,
                            "signal_map_json": json.dumps(names, sort_keys=True),
                            "current_convention": "positive_into_the_unit",
                        },
                    ),
                    param=params,
                    vout_v=np.real(np.asarray(sweep["xtop.out"])).astype(np.float64),
                    out_current_a=-np.real(np.asarray(sweep["xtop.vout:p"])).astype(np.float64),
                    dump_current_a=-np.real(np.asarray(sweep["xtop.vdump:p"])).astype(np.float64),
                    supply_current_a=-np.real(np.asarray(sweep["xtop.vvdd:p"])).astype(np.float64),
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
            except Exception as error:  # noqa: BLE001 - report every independent point failure
                failures[name] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} current source points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named current source target."""

    targets = {target.__name__: target for target in (idac_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available current source simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "idac"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
