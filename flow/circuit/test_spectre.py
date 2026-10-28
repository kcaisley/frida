"""Opt-in diagnostics: reuse runner recipes, not separate testbench definitions.

Allow roughly one hour for the full suite on asiclab003 (host/load dependent).
Run it occasionally or after broad simulation-flow changes, not after every edit.
For routine changes, select affected blocks/experiments with pytest's -k option,
for example: uv run pytest -m spectre -k 'adc-frida2_sequence'.
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
        ("adc", "hdl21_sample_rate"),
        ("adc", "hdl21_transfer_curve"),
        ("adc", "frida1_sequence"),
        ("adc", "frida1_sample_rate"),
        ("adc", "frida1_transfer_curve"),
        ("adc", "frida1_supply_noise"),
        ("adc", "frida2_sequence"),
        ("cdac.caparray", "frida1_transfer_curve"),
        ("cdac.caparray", "caparray_characterization"),
        ("delay", "delay_characterization"),
        ("latch", "latch_characterization"),
        ("ota", "ota_characterization"),
        ("follower", "follower_characterization"),
        ("moscap", "moscap_characterization"),
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
    assert {"din", "dout", "clk", "clk_b"} <= set(meas.v) and "vdd" in meas.i
    assert 50 < samp.analyze_track([meas]).on_resistance_ohm[0] < 2000


@pytest.mark.spectre
def test_varying_mom_capacitors_draw_pelgroms_mismatch_and_one_gradient_a_run(diagnostic_root):
    """Spectre's Monte Carlo of the varying FMOM leaf (``flow.momcap.subckt``), read back as one
    measurement (``flow.pipeline.read``): equal capacitors draw independently at Pelgrom's sigma,
    a larger one at its smaller relative sigma, and one away from the origin adds the gradient."""

    from types import SimpleNamespace

    import hdl21 as h
    import hdl21.sim as hs
    import numpy as np
    from hdl21.primitives import Vdc
    from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

    from flow import pipeline
    from flow.momcap.subckt import MomCap, MomCapParams, variation

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
