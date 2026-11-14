"""Opt-in diagnostics: reuse runner recipes, not separate testbench definitions.

Allow roughly one hour for the full suite on asiclab003 (host/load dependent).
Run it occasionally or after broad simulation-flow changes, not after every edit.
For routine changes, select affected blocks/experiments with pytest's -k option,
for example: uv run pytest -m spectre -k 'latch'. The ADC's circuit runs are its sweep's
(``python -m flow --block adc --run <name> --to circuit``), its Spectre check its own test.
The short simulated durations do not imply short wall-clock runtimes.
"""

import importlib
import importlib.util
import shutil
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def spectre_installation():
    """Skip absent site installations, never broken inputs or simulator failures."""

    if shutil.which("spectre") is None:
        pytest.skip("Spectre binary is not on PATH; source the Cadence environment")
    spec = importlib.util.find_spec("pdk.tsmc65")
    if spec is None or spec.origin is None:
        pytest.skip("TSMC65 PDK Python package is not installed")
    from pdk.tsmc65.hdl21 import site

    if not site.install.pdk_path.is_dir():
        pytest.skip(f"TSMC65 PDK installation is unavailable: {site.install.pdk_path}")
    # The installation exists: missing configured collateral is an error.
    for path in site.MODEL_FILES:
        if not path.is_file():
            raise FileNotFoundError(path)


@pytest.fixture(scope="module")
def diagnostic_root(spectre_installation):
    root = (
        Path(__file__).resolve().parents[2]
        / "build/diagnostics"
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    )
    root.mkdir(parents=True, exist_ok=False)
    return root


@pytest.mark.spectre
@pytest.mark.parametrize(
    "block,target",
    (
        ("delay", "delay_characterization"),
        ("idac", "idac_characterization"),
        ("cml", "cml_characterization"),
        ("pi", "pi_characterization"),
        ("clkgen", "clkgen_characterization"),
        ("lvshift", "lvshift_characterization"),
        ("ringamp", "ringamp_characterization"),
    ),
    ids=lambda value: value,
)
def test_target_diagnostic(block, target, diagnostic_root):
    # a block's named runs are its sim's
    runner = getattr(importlib.import_module(f"flow.{block}.sim"), target)
    run_dir = diagnostic_root / block / target
    assert runner(run_dir, check=True) == run_dir
    assert list(run_dir.rglob("netlist.scs")), f"no generated decks beneath {run_dir}"
    assert list(run_dir.rglob("spectre.log")), f"no simulator reports beneath {run_dir}"


@pytest.mark.spectre
def test_comp_pipeline_diagnostic(diagnostic_root):
    """The comparator on the pipeline: one short run simulated (``comp.simulate``) and read
    (``flow.pipeline.read``) on Spectre's own steps."""

    from flow import comp, pipeline

    tb = comp.TbParams(pdk="tsmc65", vin_diff_values_v=(-1e-3, 1e-3), conversions=1)
    run_dir = diagnostic_root / "comp" / "pipeline"
    meas = pipeline.read(comp.simulate(tb, run_dir), tb)
    assert list(run_dir.rglob("netlist.scs")) and list(run_dir.rglob("spectre.log"))
    assert {"clk", "outp", "outn", "latch_p", "latch_n"} <= set(meas.v) and "vdd" in meas.i
    assert comp.analyze_decisions(meas).decision.tolist() == [0, 1]


@pytest.mark.spectre
def test_samp_pipeline_diagnostic(diagnostic_root):
    """The sampler on the pipeline: two periods of the FRIDA-1 switch simulated (``samp.simulate``)
    and read (``flow.pipeline.read``), its tracking analysed."""

    from flow import pipeline, samp

    tb = samp.TbParams(pdk="tsmc65", periods=3)
    run_dir = diagnostic_root / "samp" / "pipeline"
    meas = pipeline.read(samp.simulate(tb, run_dir), tb)
    assert list(run_dir.rglob("netlist.scs")) and list(run_dir.rglob("spectre.log"))
    assert {"vin", "vout", "clk", "clk_b"} <= set(meas.v) and "vdd" in meas.i
    assert 50 < samp.analyze_track([meas]).on_resistance_ohm[0] < 2000


@pytest.mark.spectre
@pytest.mark.parametrize("noise", (False, True), ids=("nutbin", "psfascii"))
def test_every_analysis_of_a_run_reads_as_a_sweep(diagnostic_root, noise):
    """An RC low-pass beside a resistor on a supply, simulated by the shared helper
    (``flow.circuit.spectre.run``) and read by the shared reader (``flow.pipeline.read``): its
    operating point, a DC sweep, its AC response and transfer functions, and its transient
    (nutbin) or its noise (PSF ASCII, which a noise analysis takes)."""

    from types import SimpleNamespace

    import hdl21 as h
    import hdl21.sim as hs
    import numpy as np
    from hdl21.primitives import C, R, Vdc

    from flow import pipeline
    from flow.analysis import calc
    from flow.circuit import spectre
    from flow.pipeline import SweepKind

    r, c, r_supply, vdd, temperature_k = 1e3, 1e-12, 1e4, 1.2, 300.0
    bench = h.Module(name="RcTb")
    bench.VSS = h.Port()
    bench.inp, bench.out, bench.vdd = h.Signal(), h.Signal(), h.Signal()
    bench.vinp = Vdc(dc=0.5, ac=1.0)(p=bench.inp, n=bench.VSS)
    bench.vvdd = Vdc(dc=vdd)(p=bench.vdd, n=bench.VSS)
    bench.r = R(r=r)(p=bench.inp, n=bench.out)
    bench.c = C(c=c)(p=bench.out, n=bench.VSS)
    bench.rsupply = R(r=r_supply)(p=bench.vdd, n=bench.VSS)
    sweep = hs.LogSweep(start=1e3, stop=1e11, npts=10)
    attrs = [
        *spectre.options(temperature_k - 273.15),
        hs.Save(["xtop.inp", "xtop.out", "xtop.vinp:p", "xtop.vvdd:p"]),
        hs.Ac(sweep=sweep, name="ac"),
        h.Literal("xf (xtop.out 0) xf start=1e3 stop=1e11 dec=10"),
        h.Literal(f"sweep_vdd dc dev=xtop.vvdd param=dc start=0 stop={vdd:g} step={vdd / 4:g}"),
        hs.Noise(output=bench.out, input_source=bench.vinp, sweep=sweep, name="noise")
        if noise
        else hs.Tran(tstop=20 * r * c, name="tran"),
    ]
    run_dir = diagnostic_root / "sweeps" / ("psfascii" if noise else "nutbin")
    spectre.run(bench, attrs, run_dir)
    raw = run_dir / "netlist.raw"
    assert raw.is_dir() == noise
    meas = pipeline.read(raw, SimpleNamespace(params=None))
    kinds = {"opdc": SweepKind.OP, "ac": SweepKind.AC, "xf": SweepKind.XF, "sweep_vdd": SweepKind.DC}
    expected = kinds | ({"noise": SweepKind.NOISE} if noise else {})
    assert {name: found.kind for name, found in meas.sweeps.items()} == expected
    op, ac, xf, dc = (meas.sweeps[name] for name in kinds)
    # the operating point and the DC sweep: the supply's current as drawn, through its resistor
    assert op.v["out"][0] == pytest.approx(0.5) and op.i["vdd"][0] == pytest.approx(vdd / r_supply)
    np.testing.assert_allclose(dc.x, np.linspace(0, vdd, 5), atol=1e-12)
    np.testing.assert_allclose(dc.i["vdd"], dc.x / r_supply, atol=1e-12)
    # [Razavi-Analog] Eq. (7.17), p. 229: the RC low-pass's transfer function, 1 / (RCs + 1)
    h_ideal = 1 / (1 + 2j * np.pi * ac.x * r * c)
    np.testing.assert_allclose(ac.v["out"], h_ideal, rtol=1e-6)
    # its corner, 1 / (2 pi RC), read between the sweep's points
    assert calc.bandwidth(ac.v["out"], ac.x, 3) == pytest.approx(1 / (2 * np.pi * r * c), rel=1e-2)
    # the output per volt of each source: the input's is the AC response, the supply's nothing
    np.testing.assert_allclose(xf.v["inp"], h_ideal, rtol=1e-6)
    np.testing.assert_allclose(np.abs(xf.v["vdd"]), 0.0, atol=1e-9)
    if noise:
        found = meas.sweeps["noise"]
        # [Razavi-Analog] Eq. (7.19), p. 229: the low-pass's output noise spectrum
        density = 4 * 1.380649e-23 * temperature_k * r / (4 * np.pi**2 * r**2 * c**2 * found.x**2 + 1)
        np.testing.assert_allclose(found.v["out"] ** 2, density, rtol=1e-3)
        np.testing.assert_allclose(found.v["r.total"], density, rtol=1e-3)
        np.testing.assert_allclose(found.v["gain"], np.abs(h_ideal), rtol=1e-6)
        assert meas.time_s.shape == (0,)
    else:
        # the transient beside them, as a run of it alone reads: the input held, the output on it
        assert meas.time_s[-1] == pytest.approx(20 * r * c) and meas.v["out"][-1] == pytest.approx(0.5)
        assert meas.i["vdd"][-1] == pytest.approx(vdd / r_supply)


@pytest.mark.spectre
def test_a_run_of_dc_sweeps_alone_runs_with_an_operating_point(diagnostic_root):
    """Two resistors, each on a source swept by a literal: a run of the literals alone is refused
    (hdl21 would not call Spectre for it); with an operating point of hdl21's (``hs.Op``) it runs
    and reads as the two sweeps and both operating points, and its raw output (the file and the
    directory of the devices' operating points beside it) is discarded whole."""

    from types import SimpleNamespace

    import hdl21 as h
    import hdl21.sim as hs
    import numpy as np
    from hdl21.primitives import R, Vdc

    from flow import pipeline
    from flow.analysis import calc
    from flow.circuit import spectre
    from flow.pipeline import SweepKind

    r_sink, r_source, vdd = 1e3, 2e3, 1.2
    bench = h.Module(name="DcTb")
    bench.VSS = h.Port()
    bench.outn, bench.outp, bench.vdd = h.Signal(), h.Signal(), h.Signal()
    bench.voutn = Vdc(dc=vdd / 2)(p=bench.outn, n=bench.VSS)
    bench.voutp = Vdc(dc=vdd / 2)(p=bench.outp, n=bench.VSS)
    bench.vvdd = Vdc(dc=vdd)(p=bench.vdd, n=bench.VSS)
    # a load sinking from its source, as an NMOS mirror does, and one pushing into its, as a PMOS one
    bench.rsink = R(r=r_sink)(p=bench.outn, n=bench.VSS)
    bench.rsource = R(r=r_source)(p=bench.vdd, n=bench.outp)
    literals = [
        *spectre.options(),
        hs.Save(["xtop.outn", "xtop.outp", "xtop.voutn:p", "xtop.voutp:p", "xtop.vvdd:p"]),
        h.Literal(f"sweep_n dc dev=xtop.voutn param=dc start=0 stop={vdd:g} step={vdd / 4:g}"),
        h.Literal(f"sweep_p dc dev=xtop.voutp param=dc start=0 stop={vdd:g} step={vdd / 4:g}"),
    ]
    run_dir = diagnostic_root / "sweeps" / "dc"
    with pytest.raises(ValueError, match="has no hdl21 analysis"):
        spectre.run(bench, literals, run_dir)
    spectre.run(bench, [*literals, hs.Op(name="op")], run_dir)
    raw = run_dir / "netlist.raw"
    assert raw.is_file() and (run_dir / "netlist.raw.psf").is_dir()
    meas = pipeline.read(raw, SimpleNamespace(params=None))
    assert meas.time_s.shape == (0,)
    assert {name: found.kind for name, found in meas.sweeps.items()} == {
        "opdc": SweepKind.OP,
        "op": SweepKind.OP,
        "sweep_n": SweepKind.DC,
        "sweep_p": SweepKind.DC,
    }
    op, sweep_n, sweep_p = (meas.sweeps[name] for name in ("op", "sweep_n", "sweep_p"))
    assert op.v["outn"][0] == pytest.approx(vdd / 2) and op.i["outn"][0] == pytest.approx(vdd / 2 / r_sink)
    assert op.i["vdd"][0] == pytest.approx(vdd / 2 / r_source)
    np.testing.assert_allclose(sweep_n.x, np.linspace(0, vdd, 5), atol=1e-12)
    np.testing.assert_allclose(sweep_n.v["outn"], sweep_n.x, atol=1e-12)
    # a source's current is positive as drawn from it: what the sinking load takes, and the
    # negative of what the sourcing one pushes into its source
    np.testing.assert_allclose(sweep_n.i["outn"], sweep_n.x / r_sink, atol=1e-12)
    np.testing.assert_allclose(sweep_p.i["outp"], -(vdd - sweep_p.x) / r_source, atol=1e-12)
    # the resistance seen at either output is the slope of its source's current as drawn, positive
    # for both; the range a current holds over takes the sourcing one's negated (its magnitude)
    np.testing.assert_allclose(1 / calc.deriv(sweep_n.i["outn"], sweep_n.x), r_sink, rtol=1e-9)
    np.testing.assert_allclose(1 / calc.deriv(sweep_p.i["outp"], sweep_p.x), r_source, rtol=1e-9)
    assert np.isnan(calc.compliance_range(sweep_p.i["outp"], sweep_p.x, at=vdd / 2, tolerance=0.6)).all()
    assert calc.compliance_range(-sweep_p.i["outp"], sweep_p.x, at=vdd / 2, tolerance=0.6) == pytest.approx(
        (vdd / 4, 3 * vdd / 4)
    )
    pipeline.discard(raw)
    assert not raw.exists() and not (run_dir / "netlist.raw.psf").exists()


@pytest.mark.spectre
def test_varying_mom_capacitors_draw_pelgroms_mismatch_and_one_gradient_a_run(diagnostic_root):
    """Spectre's Monte Carlo of the varying FMOM leaf (``flow.layout.devices.momcap.netlist``), read back as one
    measurement (``flow.pipeline.read``): equal capacitors draw independently at Pelgrom's sigma,
    a larger one at its smaller relative sigma, and one away from the origin adds the gradient."""

    from types import SimpleNamespace

    import hdl21 as h
    import hdl21.sim as hs
    import numpy as np
    from hdl21.primitives import Vdc
    from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

    from flow import pipeline
    from flow.layout.devices.momcap.netlist import MomCap, MomCapParams, variation

    leaves = {"a": (100e-15, 0.0), "b": (100e-15, 0.0), "c": (400e-15, 50.0)}
    bench = h.Module(name="MomCapMonteCarlo")
    bench.VSS = h.Port()
    bench.top, bench.bottom = h.Signal(), h.Signal()
    bench.vtop = Vdc(dc=0.0)(p=bench.top, n=bench.VSS)
    bench.vbottom = Vdc(dc=0.0)(p=bench.bottom, n=bench.VSS)
    for name, (c, x) in leaves.items():
        leaf = MomCap(MomCapParams(c=c, varies=True, x_um=x))
        bench.add(leaf(PLUS=bench.top, MINUS=bench.bottom, BULK=bench.VSS), name=f"c{name}")
    runs = 400
    attrs = [
        *variation(pelgrom=0.01, gradient_per_um=1e-4),
        hs.Save([f"xtop.c{name}.drawn" for name in leaves]),
        hs.MonteCarlo(inner=[hs.Op(name="op")], npts=runs, seed=12345, name="mc", options={"savefamilyplots": "yes"}),
    ]
    run_dir = diagnostic_root / "momcap_monte_carlo"
    hs.Sim(tb=bench, attrs=attrs).run(
        SimOptions(
            simulator=SupportedSimulators.SPECTRE,
            fmt=ResultFormat.NONE,
            rundir=run_dir,
            simulator_args=("-format", "nutbin", "+escchars", "+log", "spectre.log"),
        )
    )
    meas = pipeline.read(run_dir / "netlist.raw", SimpleNamespace(params=None, mc_seed=12345))
    assert meas.info.readbacks["runs"] == runs
    drawn = {name: meas.v[f"c{name}.drawn"] * 1e-15 for name in leaves}
    relative = {name: float(np.std(values) / np.mean(values)) for name, values in drawn.items()}
    # 1 %.sqrt(fF) over sqrt(100 fF): 0.1 %; the 400 fF one at 0.05 % and the gradient's 0.5 % at 50 um
    # in a random direction (rms 0.5 % / sqrt(2))
    assert relative["a"] == pytest.approx(1e-3, rel=0.15) and relative["b"] == pytest.approx(1e-3, rel=0.15)
    assert relative["c"] == pytest.approx(np.hypot(5e-4, 5e-3 / np.sqrt(2)), rel=0.15)
    assert abs(np.corrcoef(drawn["a"], drawn["b"])[0, 1]) < 0.2
