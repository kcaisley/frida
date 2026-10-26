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
        ("caparray", "frida1_transfer_curve"),
        ("caparray", "caparray_characterization"),
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
