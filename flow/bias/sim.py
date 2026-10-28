"""Cascode bias generator testbench and named Spectre simulation targets, in every PDK.

The testbench follows the current source's: the reference current
flows into ``vbn`` from a supply of its own, and the four gate voltages bias two cascoded test
mirrors, copies of the generator's NMOS and PMOS mirror devices and cascodes, whose outputs are
held by sources and swept across the supply (Spectre's DC sweep): their currents over the output
voltage give the mirrors' accuracy, output resistance and compliance, the generator's purpose.
The PMOS test mirror draws from a supply of its own, so the generator's supply current is its own.
"""

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
from flow.circuit.devices import mos as _mos
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Bias, BiasNets, BiasParams


def bias_signal_names() -> dict[str, str]:
    """Derive simulator saves and names from the block's net bundle: the generator's voltages,
    the test mirrors' inner nodes and output currents, and the supply current."""
    names = {}
    for net in BiasNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
    names.update(
        {
            "xtop.tn": "tn",
            "xtop.tp": "tp",
            "xtop.outn": "outn",
            "xtop.outp": "outp",
            "xtop.voutn:p": "i(outn)",
            "xtop.voutp:p": "i(outp)",
            "xtop.vvdd:p": "i(vdd)",
        }
    )
    return names


@h.paramclass
class BiasTbParams:
    """Parameters which determine the generated cascode bias testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    bias = h.Param(dtype=BiasParams, desc="Generator parameters", default=BiasParams())
    iref = h.Param(dtype=h.Scalar, desc="Reference current into vbn (A)", default=10e-6)
    vout_step_v = h.Param(dtype=float, desc="Test mirrors' output sweep step, from 0 to vdd", default=0.025)


def _validate_bias_tb_params(params: BiasTbParams) -> None:
    values = (params.vdd, params.iref, params.vout_step_v)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("cascode bias testbench values must be finite")
    if min(float(params.vdd), float(params.iref), params.vout_step_v) <= 0:
        raise ValueError("cascode bias supply, reference current, and sweep step must be positive")


@h.generator
def BiasTb(params: BiasTbParams) -> h.Module:
    """Generate the cascode bias testbench: the reference current into vbn, and a cascoded NMOS and
    PMOS test mirror on the four gates, their outputs held at mid-supply by the swept sources."""

    _validate_bias_tb_params(params)

    BiasTb, connections = testbench_from_ports(
        "BiasTb", {net.name: net for net in BiasNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    bias, vss, vdd = params.bias, BiasTb.vss, float(params.vdd)
    BiasTb.vvdd = Vdc(dc=vdd)(p=BiasTb.vdd, n=vss)
    # the reference current and the PMOS test mirror draw from a supply of their own
    BiasTb.vddb = h.Signal()
    BiasTb.vvddb = Vdc(dc=vdd)(p=BiasTb.vddb, n=vss)
    BiasTb.iref = Idc(dc=params.iref)(p=BiasTb.vddb, n=BiasTb.vbn)
    BiasTb.tn, BiasTb.tp, BiasTb.outn, BiasTb.outp = (h.Signal() for _ in range(4))
    nmos = {"tp": MosType.NMOS, "vth": bias.vth, "w": bias.n_w}
    pmos = {"tp": MosType.PMOS, "vth": bias.vth, "w": bias.p_w}
    BiasTb.mtn = _mos(**nmos, l=bias.n_l)(d=BiasTb.tn, g=BiasTb.vbn, s=vss, b=vss)
    BiasTb.mtn_cas = _mos(**nmos, l=bias.cas_l)(d=BiasTb.outn, g=BiasTb.vcasn, s=BiasTb.tn, b=vss)
    BiasTb.mtp = _mos(**pmos, l=bias.p_l)(d=BiasTb.tp, g=BiasTb.vbp, s=BiasTb.vddb, b=BiasTb.vddb)
    BiasTb.mtp_cas = _mos(**pmos, l=bias.cas_l)(d=BiasTb.outp, g=BiasTb.vcasp, s=BiasTb.tp, b=BiasTb.vddb)
    BiasTb.voutn = Vdc(dc=vdd / 2)(p=BiasTb.outn, n=vss)
    BiasTb.voutp = Vdc(dc=vdd / 2)(p=BiasTb.outp, n=vss)
    BiasTb.dut = Bias(bias)(**connections)
    return BiasTb


def _run_bias_sim(run_dir: Path, params: BiasTbParams, *, check: bool = False) -> Path:
    """Run the operating point and both test mirrors' output sweeps of one generator in its PDK
    and return the raw file (``check``: the operating point alone, with Spectre's static checks)."""

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = BiasTb(params)
    h.pdk.compile(tb)
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save(list(bias_signal_names())),
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
        # VLSIR writes a DC sweep over a netlist parameter only: each output source's own dc here,
        # the other output held at mid-supply
        stop, step = float(params.vdd), params.vout_step_v
        attrs.append(
            h.Literal(
                f"sweep_n dc dev=xtop.voutn param=dc start=0 stop={stop:g} step={step:g}\n"
                f"sweep_p dc dev=xtop.voutp param=dc start=0 stop={stop:g} step={step:g}"
            )
        )
    # the simulator's error holds its simulation, which cannot cross back from a worker process:
    # raise it as text
    try:
        hs.Sim(tb=tb, attrs=attrs).run(
            SimOptions(
                simulator=SupportedSimulators.SPECTRE,
                # the campaign reads the raw file itself: an operating point and two DC sweeps
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


# The characterization, in every PDK about its own core supply: each generator over the reference
# current (1 to 50 µA) at the core supply, and over the supply (75 to 108 %) at 10 µA; the test
# mirrors' outputs swept from ground to the supply in 48 steps.
IREF_SWEEP_A = (1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6)
SUPPLY_SWEEP = (9 / 12, 10 / 12, 11 / 12, 1.0, 13 / 12)
NOMINAL_IREF_A = 10e-6


def bias_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every generator over the reference current and the supply in every PDK: 11 runs each.

    Each point writes ``<pdk>/<case>/<iref|supply>/<point>/result.h5`` (a ``MeasBias``). ``check``
    runs the nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from vlsirtools.spice.spectre import parse_nutbin

    from flow.analysis.types import MeasInfo
    from flow.bias.analysis import MeasBias
    from flow.comp.layout import PDKS

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        points = [("iref", supply, iref) for iref in IREF_SWEEP_A]
        points += [("supply", round(step * supply, 4), NOMINAL_IREF_A) for step in SUPPLY_SWEEP]
        if check:
            points = [("iref", supply, NOMINAL_IREF_A)]
        for case, bias in CASES.items():
            for sweep, vdd, iref in points:
                jobs[f"{pdk}/{case}/{sweep}/vdd{round(vdd * 1e3)}_iref{round(iref * 1e9)}na"] = BiasTbParams(
                    pdk=pdk, bias=bias, vdd=vdd, iref=iref, vout_step_v=round(vdd / 48, 6)
                )
    names = bias_signal_names()
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_bias_sim, run_dir / name, params, check=check): (name, params)
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
                        analyses = parse_nutbin(stream)
                    op = {
                        names[key]: float(np.real(value[0]))
                        for key, value in analyses["op"].data.items()
                        if key in names
                    }
                    sweep_n, sweep_p = analyses["sweep_n"].data, analyses["sweep_p"].data
                    # a source's current flows into its positive pin: the NMOS mirror's out of its
                    # source, the PMOS one's into its source
                    measurement = MeasBias(
                        group=None,
                        index=None,
                        dut=params.bias,
                        info=MeasInfo(
                            backend="spice",
                            timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                            instruments={"simulator": "Spectre"},
                            readbacks={
                                "pdk": name.split("/")[0],
                                "case": name.split("/")[1],
                                "sweep": name.split("/")[2],
                                "raw_file": raw_path.name,
                                **{f"op_{key}_v": value for key, value in op.items() if not key.startswith("i(")},
                                "op_supply_current_a": -op["i(vdd)"],
                            },
                        ),
                        param=params,
                        vout_v=np.real(np.asarray(sweep_n["xtop.outn"])).astype(np.float64),
                        n_current_a=np.abs(np.real(np.asarray(sweep_n["xtop.voutn:p"]))).astype(np.float64),
                        p_current_a=np.abs(np.real(np.asarray(sweep_p["xtop.voutp:p"]))).astype(np.float64),
                    )
                    write_measurement(raw_path.parent / "result.h5", measurement)
                except Exception as error:  # noqa: BLE001 - report every independent point failure
                    failures[name] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} cascode bias points failed; see {failure_path}")
    return run_dir
