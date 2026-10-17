"""Current source testbench and named Spectre simulation targets, in every PDK.

The testbench follows Usb2Phy's ``IdacSweepTb``: an operating point of the unit biased by a
reference current (into its own diode or a diode-connected copy of its source device, from a
supply of its own), here with out and dump held by sources whose
currents are the unit's and the output's voltage swept (Spectre's DC sweep), so one run gives the
whole output characteristic: the current, its output resistance, and its compliance.
"""

import argparse
import importlib
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
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.analysis.io import write_measurement
from flow.circuit.ports import testbench_from_ports
from flow.comp.subckt import _mos

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

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    idac = h.Param(dtype=IdacParams, desc="Current source parameters", default=IdacParams())
    vout = h.Param(dtype=h.Scalar, desc="Voltage held on out and dump (the sweep's operating point)", default=0.6)
    iref = h.Param(dtype=h.Scalar, desc="Reference current into vbias (A)", default=10e-6)
    vcas = h.Param(dtype=h.Scalar, desc="Cascode gate voltage", default=0.8)
    en = h.Param(dtype=bool, desc="en high (enb low)", default=True)
    vout_step_v = h.Param(dtype=float, desc="Output voltage sweep step, from 0 to vdd", default=0.025)


def _validate_idac_tb_params(params: IdacTbParams) -> None:
    values = (params.vdd, params.vout, params.iref, params.vcas, params.vout_step_v)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("current source testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.iref) <= 0 or params.vout_step_v <= 0:
        raise ValueError("current source supply, reference current, and sweep step must be positive")
    if not all(0 <= float(value) <= float(params.vdd) for value in (params.vout, params.vcas)):
        raise ValueError("current source output and cascode voltages must lie between the rails")


@h.generator
def IdacTb(params: IdacTbParams) -> h.Module:
    """Generate the current source testbench (Usb2Phy ``IdacSweepTb``): out and dump held by
    sources (their currents are the unit's), and a reference current into vbias, taken by the
    unit's own diode or, without one, by a diode-connected copy of its source device."""

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
    # a PMOS reference draws its current out of vbias, an NMOS one takes it in
    idac = params.idac
    pmos = idac.source_xtors == MosType.PMOS
    # the reference draws from its own supply, so the unit's is its own current (a unit's own diode
    # sits on the unit's)
    IdacTb.vddb = h.Signal()
    IdacTb.vvddb = Vdc(dc=vdd)(p=IdacTb.vddb, n=vss)
    IdacTb.iref = Idc(dc=params.iref)(p=IdacTb.vbias if pmos else IdacTb.vddb, n=vss if pmos else IdacTb.vbias)
    if not idac.diode:
        rail = IdacTb.vddb if pmos else vss
        IdacTb.mref = _mos(tp=idac.source_xtors, vth=idac.vth, w=idac.src_w, l=idac.src_l)(
            d=IdacTb.vbias, g=IdacTb.vbias, s=rail, b=rail
        )
    IdacTb.dut = Idac(params.idac)(**connections)
    return IdacTb


def _run_idac_sim(run_dir: Path, params: IdacTbParams, *, check: bool = False) -> Path:
    """Run the operating point and the output voltage sweep of one unit in its PDK and return the
    raw file (``check``: the operating point alone, with Spectre's static checks)."""

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = IdacTb(params)
    h.pdk.compile(tb)
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
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
    # the simulator's error holds its simulation, which cannot cross back from a worker process:
    # raise it as text
    try:
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
    except SimError as error:
        raise RuntimeError(f"Spectre failed in {run_dir}: {error}") from None
    return run_dir / "netlist.raw"


# The characterization, in every PDK at its own core supply: each unit on and, where it switches,
# off, over the reference current; its output swept across the supply about mid-supply. An NMOS
# cascode's gate sits two thirds of the supply above vss, a PMOS one as far below vdd.
IREF_SWEEP_A = (1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6)
NOMINAL_IREF_A = 10e-6


def idac_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every unit's output sweep over its reference current and enable state in every PDK (about 40 runs each).

    Each point writes ``<pdk>/<case>/<on|off>/iref<nA>na/result.h5`` (a ``MeasIdac``). ``check``
    runs the nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from vlsirtools.spice.spectre import parse_nutbin

    from flow.analysis.types import MeasInfo
    from flow.comp.layout import PDKS
    from flow.idac.analysis import MeasIdac

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        for case, idac in CASES.items():
            vcas = supply / 3 if idac.source_xtors == MosType.PMOS else 2 * supply / 3
            states = (True,) if check or idac.switch == Switch.NONE else (True, False)
            for en in states:
                for iref in (NOMINAL_IREF_A,) if check else IREF_SWEEP_A:
                    jobs[f"{pdk}/{case}/{'on' if en else 'off'}/iref{round(iref * 1e9)}na"] = IdacTbParams(
                        pdk=pdk,
                        idac=idac,
                        vdd=supply,
                        vout=round(supply / 2, 4),
                        vout_step_v=round(supply / 48, 6),
                        en=en,
                        vcas=round(vcas, 4),
                        iref=iref,
                    )
    names = idac_signal_names()
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_idac_sim, run_dir / name, params, check=check): (name, params)
                for name, params in jobs.items()
                if params.pdk == pdk
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
                                "pdk": name.split("/")[0],
                                "case": name.split("/")[1],
                                "bias": name.split("/")[3],
                                "nominal": float(params.iref) == NOMINAL_IREF_A,
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
                        vbias_v=np.real(np.asarray(sweep["xtop.vbias"])).astype(np.float64),
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
