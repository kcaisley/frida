"""The CDAC's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The testbench drives both sides' states, every stage up and back down in its turn
(``TbParams.window_start_s``) (the main plates follow the states, the difference plates their
complement), and bleeds both top plates to mid-supply. ``simulate`` runs it in Spectre and leaves Spectre's raw output on disk:
the nets ``Nets`` marks to save (both top plates, the P side's states and main bottom plates, a
bit per stage), every ``TbParams.waveform_sample_interval_s``, Spectre's step bounded to it; or,
for a Monte Carlo run (``TbParams.mc_runs``), each run's operating point with every plate's probe
(``flow.momcap``: its drawn value in fF), Spectre's runs a plot each. A Monte Carlo run's testbench
holds the plates alone, as the netlist names and places them: its operating point reads nothing
else, and without the drivers it is linear, solved at once in every PDK (with them, each run
re-evaluates the drivers' models and, in some PDKs, converges only by gmin stepping: minutes a
condition). Every run sets the plates' variation (``flow.momcap.subckt.variation``), none where the
testbench gives none.
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import R, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.circuit.ports import testbench_from_ports
from flow.momcap.subckt import mom_cap, variation

from .params import BLEED_OHM, ERRPRESET, TOLERANCES, TbParams
from .subckt import Nets, netlist


def testbench(tb: TbParams) -> h.Module:
    """The CDAC testbench of one run: each stage's P state up and its N state down a window into its
    turn and back the window after, both top plates bled to mid-supply; a Monte Carlo run's, the
    plates alone, each top plate bled to ground."""

    if tb.mc_runs:
        dac = tb.params.dac
        plates = h.Module(name="CdacPlates")
        plates.vss = h.Port()
        for side in ("p", "n"):
            top = plates.add(h.Signal(), name=f"vdac_{side}")
            plates.add(R(r=BLEED_OHM)(p=top, n=plates.vss), name=f"rbleed_{side}")
            for kind, values in (("main", dac.main_f), ("diff", dac.diff_f)):
                placed = getattr(dac, f"{kind}_{side}_um")
                for stage, plate in enumerate(values):
                    if plate > 0:
                        x_um, y_um = placed[stage] if placed else (0.0, 0.0)
                        leaf = mom_cap(plate, varies=True, x_um=x_um, y_um=y_um)
                        plates.add(leaf(PLUS=plates.vss, MINUS=top, BULK=plates.vss), name=f"c{kind}_{side}_{stage}")
        bench = h.Module(name="CdacPlatesTb")
        bench.vss = h.Port()
        bench.dut = plates(vss=bench.vss)
        return bench

    dut = netlist(tb.params)
    bench, connections = testbench_from_ports("CdacTb", dut.ports)
    vss, vdd, edge = bench.vss, tb.vdd, tb.transition_time_s
    bench.vcm = h.Signal()
    bench.vvdd_dac = Vdc(dc=vdd)(p=bench.vdd_dac, n=vss)
    bench.vvcm = Vdc(dc=vdd / 2)(p=bench.vcm, n=vss)
    for side in ("p", "n"):
        bench.add(R(r=BLEED_OHM)(p=getattr(bench, f"vdac_{side}"), n=bench.vcm), name=f"rbleed_{side}")
    for stage in range(tb.stages):
        pulse = {
            "delay": tb.window_start_s(stage, rising=True),
            "rise": edge,
            "fall": edge,
            "width": tb.window_s - edge,
            "period": 2 * tb.stop_s,
        }
        bench.add(Vpulse(v1=0.0, v2=vdd, **pulse)(p=bench.dac_state_p[stage], n=vss), name=f"vstate_p_{stage}")
        bench.add(Vpulse(v1=vdd, v2=0.0, **pulse)(p=bench.dac_state_n[stage], n=vss), name=f"vstate_n_{stage}")
    bench.dut = dut(**connections)
    return bench


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir``: its raw output, in nutbin, on disk.

    The settling run: the nets ``Nets`` marks to save, a bit a stage where they have one; the output
    strobed every ``tb.waveform_sample_interval_s``, the step bounded to it, at the tolerances
    ``TOLERANCES``. A Monte Carlo run (``tb.mc_runs``): every plate's probe at each run's operating
    point, from ``tb.mc_seed``.
    """

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    dac = tb.params.dac
    if tb.mc_runs:
        # every plate's drawn value, each run's operating point
        saves = [
            f"xtop.dut.c{kind}_{side}_{stage}.drawn"
            for side in ("p", "n")
            for kind, plates in (("main", dac.main_f), ("diff", dac.diff_f))
            for stage, plate in enumerate(plates)
            if plate > 0
        ]
        analysis = hs.MonteCarlo(
            inner=[hs.Op(name="op")],
            npts=tb.mc_runs,
            seed=tb.mc_seed,
            name="mc",
            options={"savefamilyplots": "yes"},
        )
    else:
        saved = [net for net in Nets.signals.values() if net.props.get("save")]
        saves = [f"xtop.{net.name}" for net in saved if not net.props.get("stages")] + [
            f"xtop.{net.name}_{stage}" for stage in range(tb.stages) for net in saved if net.props.get("stages")
        ]
        interval = tb.waveform_sample_interval_s
        analysis = hs.Tran(
            tstop=tb.stop_s,
            name="tran",
            options={
                "strobeperiod": interval,
                "maxstep": interval,
                "strobeoutput": "strobeonly",
                "errpreset": ERRPRESET,
            },
        )
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings, its
        # standard cells (the drivers), the device names its netlists use (pdk/<name>/hdl21)
        *(
            getattr(install, name)()
            for name in ("include_pre_simulation", "include_stdcell", "include_devices")
            if hasattr(install, name)
        ),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        *(hs.Options(name=name, value=value) for name, value in TOLERANCES.items()),
        *variation(pelgrom=tb.pelgrom, gradient_per_um=tb.gradient_per_um),
        hs.Save(saves),
        analysis,
    ]
    try:
        hs.Sim(tb=bench, attrs=attrs).run(
            SimOptions(
                simulator=SupportedSimulators.SPECTRE,
                fmt=ResultFormat.NONE,
                rundir=run_dir,
                # wait up to an hour for a license: other runs share the server's
                simulator_args=("-format", "nutbin", "+lqtimeout", "3600", "+escchars", "+log", "spectre.log"),
            )
        )
    except SimError as error:
        # the simulator's error holds its simulation, which cannot cross back from a worker process
        raise RuntimeError(f"Spectre failed in {run_dir}: {error}") from None
    return run_dir / "netlist.raw"
