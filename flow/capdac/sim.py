"""The capacitive DAC's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The settling testbench is the converter's two sides, two of the array as the PDK draws it
(``netlist``, one side, its requests resolved by ``flow.layout.devices.device.resolve``: each
driver its chain of inverters, each capacitor its MOM unit's capacitances), ``dut_p`` and
``dut_n``: it drives both sides' states, every stage up and back down in its turn
(``TbParams.window_start_s``; the main plates follow the states, the difference plates their
complement), and bleeds both top plates to mid-supply. ``simulate`` runs it in Spectre and leaves
Spectre's raw output on disk: both top plates, the P side's states and main bottom plates, a bit per
stage, the P side's difference bottom plates, and the supply's current (``vvdd``, the drivers'
and the reference's: the bench's supply is both), every ``TbParams.waveform_sample_interval_s``,
Spectre's step bounded to it, in classic Spectre (marked ``Accuracy.SMALL_DIFFERENCE``: half a
14-bit LSB on a step of up to a volt), at the run's process corner and temperature.

A Monte Carlo run (``TbParams.mc_runs``) holds the plates alone, each stage's main and difference
plates of each side at their design values (``TbParams.main_f``, ``diff_f``), each top plate bled to
ground: each run's operating point with every plate's probe (``flow.layout.devices.momcap``: its
drawn value in fF), Spectre's runs a plot each. Without the drivers it is linear, solved at once in
every PDK. The run sets the plates' mismatch (``flow.layout.devices.momcap.netlist.variation``);
the plates stand at the origin, so the process gradient has nothing to act on until the layout
places them.
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import R, Vdc, Vpulse

from flow.circuit import spectre
from flow.circuit.ports import testbench_from_ports
from flow.layout.devices.device import resolve
from flow.layout.devices.momcap.netlist import mom_cap, variation

from .params import TbParams, WeightImpl
from .subckt import netlist


def testbench(tb: TbParams) -> h.Module:
    """The testbench of one run: the drawn array twice, the converter's sides (``dut_p``,
    ``dut_n``; they share only the supply), each stage's P state up and its N state down a window
    into its turn and back the window after, both top plates bled to mid-supply; a Monte Carlo
    run's, the design's plates alone, each top plate bled to ground."""

    if tb.mc_runs:
        plates = h.Module(name="CapdacPlates")
        plates.vss = h.Port()
        for side in ("p", "n"):
            top = plates.add(h.Signal(), name=f"vdac_{side}")
            plates.add(R(r=tb.bleed_ohm)(p=top, n=plates.vss), name=f"rbleed_{side}")
            for kind, values in (("main", tb.main_f), ("diff", tb.diff_f)):
                for stage, plate in enumerate(values):
                    if plate > 0:
                        leaf = mom_cap(float(plate), varies=True)
                        plates.add(leaf(PLUS=plates.vss, MINUS=top, BULK=plates.vss), name=f"c{kind}_{side}_{stage}")
        bench = h.Module(name="CapdacPlatesTb")
        bench.vss = h.Port()
        bench.dut = plates(vss=bench.vss)
        return bench

    # the array as the PDK draws it: its requests' views, its devices the PDK's (a capacitor below
    # the PDK's smallest drawn at that, as the layout draws it; the analysis measures what it gives)
    h.pdk.set_default(importlib.import_module(f"pdk.{tb.pdk}").pdk_logic)
    dut = netlist(tb.params)
    resolve(dut, tb.pdk)
    # side p on the block's own nets, renamed; side n on its own states, sensed plates and top plate
    # (a side's difference drivers' states, ``dac_state_diff``, on its states: no net of their own)
    ports = {name: port for name, port in dut.ports.items() if name != "dac_state_diff"}
    renames = {"dac_state": "dac_state_p", "dac_plate": "dac_plate_p", "vdac": "vdac_p"}
    bench, connections = testbench_from_ports("CapdacTb", ports, renames=renames)
    bench.dac_state_n = h.Signal(width=dut.dac_state.width)
    bench.dac_plate_n = h.Signal(width=dut.dac_plate.width)
    bench.vdac_n = h.Signal()
    vss, vdd, edge = bench.vss, tb.vdd, tb.transition_time_s
    # not in the reference texts: the bench's sources, ideal: the supply (the DAC's reference) and
    # the top plates' bleed to mid-supply through 1 TOhm, a DC path far slower than any window
    bench.vcm = h.Signal()
    bench.vvdd = Vdc(dc=vdd)(p=bench.vdd, n=vss)
    bench.vvcm = Vdc(dc=vdd / 2)(p=bench.vcm, n=vss)
    for side in ("p", "n"):
        bench.add(R(r=tb.bleed_ohm)(p=getattr(bench, f"vdac_{side}"), n=bench.vcm), name=f"rbleed_{side}")
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
    far = "dac_state_diff" in dut.ports
    bench.dut_p = dut(**{**connections, **({"dac_state_diff": bench.dac_state_p} if far else {})})
    bench.dut_n = dut(
        **{
            **connections,
            "dac_state": bench.dac_state_n,
            "dac_plate": bench.dac_plate_n,
            "vdac": bench.vdac_n,
            **({"dac_state_diff": bench.dac_state_n} if far else {}),
        }
    )
    return bench


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir``: its raw output, in nutbin, on disk.

    The settling run saves both top plates (``vdac_p``, ``vdac_n``), the P side's states
    (``dac_state_p_<stage>``), main and difference bottom plates (within its side,
    ``dut_p.main_<stage>``, ``dut_p.diff_<stage>``) and sensed plates (``dac_plate_p_<stage>``), and
    the supply's current (``vvdd``), strobed every ``tb.waveform_sample_interval_s``, the step
    bounded to it, at the run's tolerances, corner and temperature, in classic Spectre. A Monte
    Carlo run (``tb.mc_runs``): every plate's probe at each run's operating point, from
    ``tb.mc_seed``.
    """

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    if tb.mc_runs:
        # every plate's drawn value, each run's operating point
        saves = [
            f"xtop.dut.c{kind}_{side}_{stage}.drawn"
            for side in ("p", "n")
            for kind, plates in (("main", tb.main_f), ("diff", tb.diff_f))
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
        difference = tb.params.weight_impl is WeightImpl.DIFFERENCE_CAPS
        saves = [
            "xtop.vdac_p",
            "xtop.vdac_n",
            "xtop.vvdd:p",
            *(f"xtop.dac_state_p_{stage}" for stage in range(tb.stages)),
            *(f"xtop.dut_p.main_{stage}" for stage in range(tb.stages)),
            *(f"xtop.dut_p.diff_{stage}" for stage in range(tb.stages) if difference),
            *(f"xtop.dac_plate_p_{stage}" for stage in range(tb.stages)),
        ]
        interval = tb.waveform_sample_interval_s
        analysis = hs.Tran(
            tstop=tb.stop_s,
            name="tran",
            options={
                "strobeperiod": interval,
                "maxstep": interval,
                "strobeoutput": "strobeonly",
                "errpreset": "moderate",
            },
        )
    attrs = [
        *spectre.includes(install, tb.corner, stdcells=True),
        *spectre.options(tb.temperature_c),
        hs.Options(name="reltol", value=tb.reltol),
        hs.Options(name="vabstol", value=tb.vabstol),
        hs.Options(name="iabstol", value=tb.iabstol),
        *variation(pelgrom=tb.pelgrom),
        hs.Save(saves),
        analysis,
    ]
    # the settling's half LSB is a small difference of large steps: classic Spectre, marked so
    accuracy = None if tb.mc_runs else spectre.Accuracy.SMALL_DIFFERENCE
    spectre.run(bench, attrs, run_dir, fast=False, accuracy=accuracy)
    return run_dir / "netlist.raw"
