"""OTA testbench and named TSMC65 Spectre simulation targets.

The testbench follows Usb2Phy's op-amp benches (``OpAmp5T`` ``Tb``, ``FcascTb``): a balun puts
the input common mode on both inputs and half the AC stimulus on each, with opposite signs; fixed
bias voltages and a load capacitor on each output; an operating point and the AC response. A
single-ended amplifier sits open loop at the output its mirror sets. A fully differential one
has no defined output common mode of its own, so its bench adds an ideal common-mode feedback:
the outputs' average, against a target, steers the load bias.
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
from hdl21.primitives import C, Vcvs, Vdc
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.analysis.io import write_measurement
from flow.circuit.ports import testbench_from_ports

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

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    ota = h.Param(dtype=OtaParams, desc="Amplifier parameters", default=OtaParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on each output (F)", default=50e-15)
    vcm = h.Param(dtype=h.Scalar, desc="Input common-mode voltage", default=0.6)
    vbn = h.Param(dtype=h.Scalar, desc="NMOS current-source bias", default=0.55)
    vbp = h.Param(
        dtype=h.Scalar, desc="PMOS current-source bias (a differential output: its starting point)", default=0.65
    )
    vcasn = h.Param(dtype=h.Scalar, desc="NMOS cascode bias", default=0.75)
    vcasp = h.Param(dtype=h.Scalar, desc="PMOS cascode bias", default=0.45)
    vocm = h.Param(dtype=h.Scalar, desc="Output common-mode target of a differential output", default=0.6)
    cmfb_gain = h.Param(dtype=float, desc="Common-mode feedback gain onto the load bias (V/V)", default=100.0)
    fstart_hz = h.Param(dtype=float, desc="AC sweep start", default=1e3)
    fstop_hz = h.Param(dtype=float, desc="AC sweep stop", default=1e11)
    points_per_decade = h.Param(dtype=int, desc="AC points per decade", default=20)


def _validate_ota_tb_params(params: OtaTbParams) -> None:
    values = (params.vdd, params.cload, params.vcm, params.vbn, params.vbp, params.vcasn, params.vcasp, params.vocm)
    if not all(math.isfinite(float(value)) for value in (*values, params.cmfb_gain)):
        raise ValueError("OTA testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0 or params.cmfb_gain <= 0:
        raise ValueError("OTA supply, load, and common-mode feedback gain must be positive")
    if not all(0 <= float(v) <= float(params.vdd) for v in values[2:]):
        raise ValueError("OTA input, bias, and output common-mode voltages must lie between the rails")
    if not 0 < params.fstart_hz < params.fstop_hz or params.points_per_decade < 1:
        raise ValueError("OTA frequency sweep must rise from a positive start")


@h.generator
def OtaTb(params: OtaTbParams) -> h.Module:
    """Generate the OTA testbench (Usb2Phy ``OpAmp5T`` ``Tb``): a balun on the inputs, fixed
    biases, output loads, and for a differential output an ideal common-mode feedback."""

    _validate_ota_tb_params(params)

    OtaTb, connections = testbench_from_ports(
        "OtaTb", {net.name: net for net in OtaNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = OtaTb.vss
    OtaTb.vvdd = Vdc(dc=params.vdd)(p=OtaTb.vdd, n=vss)
    # the balun: the common mode on both inputs, a 1 V differential AC stimulus split between them
    OtaTb.vinp = Vdc(dc=params.vcm, ac=0.5)(p=OtaTb.inp, n=vss)
    OtaTb.vinn = Vdc(dc=params.vcm, ac=-0.5)(p=OtaTb.inn, n=vss)
    for name, value in (("vbn", params.vbn), ("vcasn", params.vcasn), ("vcasp", params.vcasp)):
        OtaTb.add(Vdc(dc=value)(p=getattr(OtaTb, name), n=vss), name=f"v{name}")
    if params.ota.topology in (Topology.FIVE_T, Topology.SELF_BIASED):
        OtaTb.vvbp = Vdc(dc=params.vbp)(p=OtaTb.vbp, n=vss)
    else:
        # ideal common-mode feedback: vbp = its start + gain x (output average - target). A higher
        # load bias lowers one stage's output common mode and, through a second stage, raises it.
        OtaTb.cm_half, OtaTb.cm, OtaTb.vbp_start, OtaTb.vocm = (h.Signal() for _ in range(4))
        OtaTb.ecm_p = Vcvs(gain=0.5)(p=OtaTb.cm_half, n=vss, cp=OtaTb.outp, cn=vss)
        OtaTb.ecm_n = Vcvs(gain=0.5)(p=OtaTb.cm, n=OtaTb.cm_half, cp=OtaTb.outn, cn=vss)
        OtaTb.vvocm = Vdc(dc=params.vocm)(p=OtaTb.vocm, n=vss)
        OtaTb.vvbp = Vdc(dc=params.vbp)(p=OtaTb.vbp_start, n=vss)
        gain = -params.cmfb_gain if params.ota.two_stage else params.cmfb_gain
        OtaTb.ecmfb = Vcvs(gain=gain)(p=OtaTb.vbp, n=OtaTb.vbp_start, cp=OtaTb.cm, cn=OtaTb.vocm)
    OtaTb.cloadp = C(c=params.cload)(p=OtaTb.outp, n=vss)
    OtaTb.cloadn = C(c=params.cload)(p=OtaTb.outn, n=vss)
    OtaTb.dut = Ota(params.ota)(**connections)
    return OtaTb


def _run_ota_sim(run_dir: Path, params: OtaTbParams, *, check: bool = False) -> Path:
    """Run the operating point and AC response of one OTA in TSMC65 and return the raw file
    (``check``: two points a decade, with Spectre's static checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = OtaTb(params)
    h.pdk.compile(tb)
    decades = math.log10(params.fstop_hz / params.fstart_hz)
    sweep = hs.LogSweep(
        start=params.fstart_hz,
        stop=params.fstop_hz,
        npts=round(decades * (2 if check else params.points_per_decade)) + 1,
    )
    attrs = [
        site.install.include(h.pdk.Corner.TYP),
        site.install.include_pre_simulation(),
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
    attrs += [
        hs.Op(name="op"),
        hs.Ac(sweep=sweep, name="ac"),
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


# The characterization: the input common mode across the rails at TSMC65's 1.2 V core supply, and
# the supply with every bias held from its own rail and the common modes at mid-supply.
VCM_SWEEP_V = tuple(round(0.2 + 0.05 * step, 3) for step in range(17))
SUPPLY_SWEEP_V = (0.9, 1.0, 1.1, 1.2, 1.3)
NOMINAL_SUPPLY_V = 1.2
NOMINAL_VCM_V = 0.6


def ota_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every OTA over the input common mode and the supply: 6 cases, 22 runs each.

    Each point writes ``<case>/<sweep>/<point>/result.h5`` (a ``MeasOta``). ``check`` runs the
    nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from vlsirtools.spice.spectre import parse_nutbin

    from flow.analysis.types import MeasInfo
    from flow.ota.analysis import MeasOta

    run_dir.mkdir(parents=True, exist_ok=True)
    nominal = OtaTbParams()
    jobs = {}
    for case, ota in CASES.items():
        for vcm in (NOMINAL_VCM_V,) if check else VCM_SWEEP_V:
            jobs[f"{case}/vcm/vcm{round(vcm * 1e3)}"] = OtaTbParams(ota=ota, vcm=vcm)
        for vdd in () if check else SUPPLY_SWEEP_V:
            # the PMOS biases keep their gate drive from vdd, the common modes stay at mid-supply
            jobs[f"{case}/supply/vdd{round(vdd * 1e3)}"] = OtaTbParams(
                ota=ota,
                vdd=vdd,
                vcm=vdd / 2,
                vocm=vdd / 2,
                vbp=vdd - (NOMINAL_SUPPLY_V - float(nominal.vbp)),
                vcasp=vdd - (NOMINAL_SUPPLY_V - float(nominal.vcasp)),
            )
    failures: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
        futures = {
            executor.submit(_run_ota_sim, run_dir / name, params, check=check): (name, params)
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
                            "case": name.split("/")[0],
                            "sweep": name.split("/")[1],
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
