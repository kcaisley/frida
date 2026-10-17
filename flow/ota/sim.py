"""OTA testbench and named Spectre simulation targets, in every PDK.

The testbench follows Usb2Phy's op-amp benches (``OpAmp5T`` ``Tb``, ``FcascTb``): a balun puts
the input common mode on both inputs and half the AC stimulus on each, with opposite signs; bias
references (a diode-connected copy of the devices each bias drives, fed their current from a
supply of its own, so the amplifier's supply current is its own), fixed cascode biases, and a
load capacitor on each output; an operating point, the AC response and the output noise. A
single-ended amplifier sits open loop at the output its mirror sets. A fully differential one
has no defined output common mode of its own, so its bench adds an ideal common-mode feedback:
the outputs' average, against a target, steers the load bias.
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
from hdl21.primitives import C, Idc, MosType, Vcvs, Vdc
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.analysis.io import write_measurement
from flow.circuit.ports import testbench_from_ports
from flow.comp.subckt import _mos

from .subckt import CASES, Ota, OtaNets, OtaParams, Topology


def ota_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"freq": "freq"}
    for net in OtaNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class OtaTbParams:
    """Parameters which determine the generated OTA testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    ota = h.Param(dtype=OtaParams, desc="Amplifier parameters", default=OtaParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on each output (F)", default=50e-15)
    vcm = h.Param(dtype=h.Scalar, desc="Input common-mode voltage", default=0.6)
    bias_current_a = h.Param(dtype=float, desc="Tail current the bias references set (A)", default=40e-6)
    vcasn = h.Param(dtype=h.Scalar, desc="NMOS cascode bias", default=0.75)
    vcasp = h.Param(dtype=h.Scalar, desc="PMOS cascode bias", default=0.45)
    vocm = h.Param(dtype=h.Scalar, desc="Output common-mode target of a differential output", default=0.6)
    cmfb_gain = h.Param(dtype=float, desc="Common-mode feedback gain onto the load bias (V/V)", default=100.0)
    fstart_hz = h.Param(dtype=float, desc="AC sweep start", default=1e3)
    fstop_hz = h.Param(dtype=float, desc="AC sweep stop", default=1e11)
    points_per_decade = h.Param(dtype=int, desc="AC points per decade", default=20)


def _validate_ota_tb_params(params: OtaTbParams) -> None:
    values = (params.vdd, params.cload, params.vcm, params.vcasn, params.vcasp, params.vocm)
    if not all(math.isfinite(float(value)) for value in (*values, params.cmfb_gain, params.bias_current_a)):
        raise ValueError("OTA testbench values must be finite")
    if min(float(params.vdd), float(params.cload), params.cmfb_gain, params.bias_current_a) <= 0:
        raise ValueError("OTA supply, load, common-mode feedback gain, and bias current must be positive")
    if not all(0 <= float(v) <= float(params.vdd) for v in values[2:]):
        raise ValueError("OTA input, bias, and output common-mode voltages must lie between the rails")
    if not 0 < params.fstart_hz < params.fstop_hz or params.points_per_decade < 1:
        raise ValueError("OTA frequency sweep must rise from a positive start")


@h.generator
def OtaTb(params: OtaTbParams) -> h.Module:
    """Generate the OTA testbench (Usb2Phy ``OpAmp5T`` ``Tb``): a balun on the inputs, biases from
    reference currents, output loads, and for a differential output an ideal common-mode feedback."""

    _validate_ota_tb_params(params)

    OtaTb, connections = testbench_from_ports(
        "OtaTb", {net.name: net for net in OtaNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = OtaTb.vss
    OtaTb.vvdd = Vdc(dc=params.vdd)(p=OtaTb.vdd, n=vss)
    # the balun: the common mode on both inputs, a 1 V differential AC stimulus split between them
    OtaTb.vinp = Vdc(dc=params.vcm, ac=0.5)(p=OtaTb.inp, n=vss)
    OtaTb.vinn = Vdc(dc=params.vcm, ac=-0.5)(p=OtaTb.inn, n=vss)
    for name, value in (("vcasn", params.vcasn), ("vcasp", params.vcasp)):
        OtaTb.add(Vdc(dc=value)(p=getattr(OtaTb, name), n=vss), name=f"v{name}")
    # the bias references, as Usb2Phy's benches bias: each bias a diode-connected copy of the
    # devices it drives, fed their current. An NMOS input's tail (and bottom sources) sit on vbn
    # and carry the bias current, its loads on vbp and half of it each (a folded cascode's top
    # sources one and a half: their fold's half and their bottom source's whole); a PMOS input's
    # tail sits on vbp.
    ota = params.ota
    current = params.bias_current_a
    load_current = 1.5 * current if ota.topology == Topology.FOLDED else current / 2
    if ota.input_xtors == MosType.NMOS:
        (n_w, n_l, n_current), (p_w, p_l, p_current) = (
            (ota.tail_w, ota.tail_l, current),
            (ota.load_w, ota.load_l, load_current),
        )
    else:
        (n_w, n_l, n_current), (p_w, p_l, p_current) = (
            (ota.load_w, ota.load_l, load_current),
            (ota.tail_w, ota.tail_l, current),
        )
    single = ota.topology in (Topology.FIVE_T, Topology.SELF_BIASED)
    # a differential output's load bias is the feedback's starting point; the feedback drives vbp
    vbp_start = OtaTb.vbp if single else OtaTb.add(h.Signal(name="vbp_start"))
    # the references draw from their own supply, so the amplifier's is its own current
    OtaTb.vddb = h.Signal()
    OtaTb.vvddb = Vdc(dc=params.vdd)(p=OtaTb.vddb, n=vss)
    OtaTb.mbn = _mos(tp=MosType.NMOS, vth=ota.vth, w=n_w, l=n_l)(d=OtaTb.vbn, g=OtaTb.vbn, s=vss, b=vss)
    OtaTb.ibn = Idc(dc=n_current)(p=OtaTb.vddb, n=OtaTb.vbn)
    OtaTb.mbp = _mos(tp=MosType.PMOS, vth=ota.vth, w=p_w, l=p_l)(d=vbp_start, g=vbp_start, s=OtaTb.vddb, b=OtaTb.vddb)
    OtaTb.ibp = Idc(dc=p_current)(p=vbp_start, n=vss)
    if not single:
        # ideal common-mode feedback: vbp = its start + gain x (output average - target). A higher
        # load bias lowers one stage's output common mode and, through a second stage, raises it.
        OtaTb.cm_half, OtaTb.cm, OtaTb.vocm = (h.Signal() for _ in range(3))
        OtaTb.ecm_p = Vcvs(gain=0.5)(p=OtaTb.cm_half, n=vss, cp=OtaTb.outp, cn=vss)
        OtaTb.ecm_n = Vcvs(gain=0.5)(p=OtaTb.cm, n=OtaTb.cm_half, cp=OtaTb.outn, cn=vss)
        OtaTb.vvocm = Vdc(dc=params.vocm)(p=OtaTb.vocm, n=vss)
        gain = -params.cmfb_gain if params.ota.two_stage else params.cmfb_gain
        OtaTb.ecmfb = Vcvs(gain=gain)(p=OtaTb.vbp, n=vbp_start, cp=OtaTb.cm, cn=OtaTb.vocm)
    OtaTb.cloadp = C(c=params.cload)(p=OtaTb.outp, n=vss)
    OtaTb.cloadn = C(c=params.cload)(p=OtaTb.outn, n=vss)
    OtaTb.dut = Ota(params.ota)(**connections)
    return OtaTb


def _run_ota_sim(run_dir: Path, params: OtaTbParams, *, check: bool = False) -> Path:
    """Run the operating point, AC response and output noise of one OTA in its PDK and return the
    raw directory (PSF ASCII: VLSIR writes a noise analysis's results so) (``check``: two points a
    decade, with Spectre's static checks)."""

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = OtaTb(params)
    h.pdk.compile(tb)
    # the AC and noise analyses share one sweep (VLSIR's npts: points per decade)
    sweep = hs.LogSweep(start=params.fstart_hz, stop=params.fstop_hz, npts=2 if check else params.points_per_decade)
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in ota_signal_names() if raw != "freq"]),
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
    single = params.ota.topology in (Topology.FIVE_T, Topology.SELF_BIASED)
    attrs += [
        hs.Op(name="op"),
        hs.Ac(sweep=sweep, name="ac"),
        hs.Noise(output=tb.outp if single else (tb.outp, tb.outn), input_source=tb.vinp, sweep=sweep, name="noise"),
    ]
    # the simulator's error holds its simulation, which cannot cross back from a worker process:
    # raise it as text
    try:
        hs.Sim(tb=tb, attrs=attrs).run(
            SimOptions(
                simulator=SupportedSimulators.SPECTRE,
                fmt=ResultFormat.NONE if check else ResultFormat.SIM_DATA,
                rundir=run_dir,
                simulator_args=(
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


# The characterization, in every PDK about its own core supply: the input common mode from a sixth
# to five sixths of it (0.2 to 1.0 V in TSMC65), and the supply (75 to 108 %) with the common modes
# at mid-supply. The cascodes sit an eighth of the supply above (NMOS) and below (PMOS) the
# middle, the tails carry 40 µA.
VCM_SWEEP = tuple((4 + step) / 24 for step in range(17))
SUPPLY_SWEEP = (9 / 12, 10 / 12, 11 / 12, 1.0, 13 / 12)
NOMINAL_VCM = 0.5


def ota_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every OTA over the input common mode and the supply in every PDK: 6 cases, 22 runs each.

    Each point writes ``<pdk>/<case>/<sweep>/<point>/result.h5`` (a ``MeasOta``). ``check`` runs
    the nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from vlsirtools.spice.spectre import parse_psfascii

    from flow.analysis.types import MeasInfo
    from flow.comp.layout import PDKS
    from flow.ota.analysis import MeasOta

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        points = [("vcm", supply, step * supply) for step in VCM_SWEEP]
        points += [("supply", step * supply, NOMINAL_VCM * step * supply) for step in SUPPLY_SWEEP]
        if check:
            points = [("check", supply, NOMINAL_VCM * supply)]
        for case, ota in CASES.items():
            for sweep, vdd, vcm in points:
                jobs[f"{pdk}/{case}/{sweep}/vdd{round(vdd * 1e3)}_vcm{round(vcm * 1e3)}"] = OtaTbParams(
                    pdk=pdk,
                    ota=ota,
                    vdd=round(vdd, 4),
                    vcm=round(vcm, 4),
                    vocm=round(vdd / 2, 4),
                    vcasn=round(5 * vdd / 8, 4),
                    vcasp=round(3 * vdd / 8, 4),
                )
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_ota_sim, run_dir / name, params, check=check): (name, params)
                for name, params in jobs.items()
                if params.pdk == pdk
            }
            for future in as_completed(futures):
                name, params = futures[future]
                try:
                    raw_path = future.result()
                    if check:
                        continue
                    analyses = parse_psfascii(raw_path)
                    op, ac, noise = (analyses[key].data for key in ("op", "ac", "noise"))
                    single = params.ota.topology in (Topology.FIVE_T, Topology.SELF_BIASED)
                    # the differential AC response to the 1 V differential stimulus
                    response = np.asarray(ac["xtop.outp"]) - (0.0 if single else np.asarray(ac["xtop.outn"]))
                    measurement = MeasOta(
                        group=None,
                        index=None,
                        dut=params.ota,
                        info=MeasInfo(
                            backend="spice",
                            timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                            instruments={"simulator": "Spectre"},
                            readbacks={
                                "pdk": name.split("/")[0],
                                "case": name.split("/")[1],
                                "sweep": name.split("/")[2],
                                "nominal": name.split("/")[2] == "vcm"
                                and abs(float(params.vcm) - NOMINAL_VCM * float(params.vdd)) < 1e-3,
                                "raw_file": raw_path.name,
                                "supply_current_convention": "positive_current_draw",
                                "op_supply_current_a": -float(np.real(op["xtop.vvdd:p"][0])),
                                "op_outp_v": float(np.real(op["xtop.outp"][0])),
                                # a single-ended amplifier leaves outn floating: Spectre drops it
                                **({} if single else {"op_outn_v": float(np.real(op["xtop.outn"][0]))}),
                                "op_vbp_v": float(np.real(op["xtop.vbp"][0])),
                            },
                        ),
                        param=params,
                        frequency_hz=np.real(np.asarray(ac["freq"])).astype(np.float64),
                        gain_v_per_v=np.abs(response).astype(np.float64),
                        phase_deg=np.degrees(np.unwrap(np.angle(response))).astype(np.float64),
                        output_noise_v_rthz=np.asarray(noise["out"], dtype=np.float64),
                    )
                    write_measurement(raw_path.parent / "result.h5", measurement)
                except Exception as error:  # noqa: BLE001 - report every independent point failure
                    failures[name] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} OTA points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named OTA target."""

    targets = {target.__name__: target for target in (ota_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available OTA simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "ota"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
