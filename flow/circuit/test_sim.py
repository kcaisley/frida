"""PDK-independent runner contracts and diagnostic prerequisite handling."""

import importlib
import importlib.util
import inspect
import logging
import sys
from types import SimpleNamespace

import pytest

from . import test_spectre


def test_the_adcs_circuit_runs_are_its_sweeps():
    # the ADC's circuit simulator's runs are its sweep's runs at the circuit level: it has no targets
    runs = importlib.import_module("flow.adc.runs")
    assert "level" in inspect.signature(runs.testbenches).parameters
    assert importlib.util.find_spec("flow.adc.targets") is None
    for stage in ("sim", "runs"):
        source = importlib.import_module(f"flow.adc.{stage}")
        assert not hasattr(source, "main")
        assert "netlist_only" not in inspect.getsource(source)
        assert not any(name.startswith("frida65") for name in vars(source))


def test_missing_spectre_skips_before_pdk_import(monkeypatch):
    monkeypatch.setattr(test_spectre.shutil, "which", lambda _: None)
    monkeypatch.setattr(
        test_spectre.importlib.util, "find_spec", lambda _: pytest.fail("PDK imported before binary check")
    )
    with pytest.raises(pytest.skip.Exception, match="Spectre binary"):
        inspect.unwrap(test_spectre.spectre_installation)()


@pytest.mark.parametrize("spec", (None, SimpleNamespace(origin=None)))
def test_missing_pdk_package_skips(spec, monkeypatch):
    monkeypatch.setattr(test_spectre.shutil, "which", lambda _: "/mock/spectre")
    monkeypatch.setattr(test_spectre.importlib.util, "find_spec", lambda _: spec)
    with pytest.raises(pytest.skip.Exception, match="PDK Python package"):
        inspect.unwrap(test_spectre.spectre_installation)()


def test_missing_installation_skips_but_missing_collateral_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(test_spectre.shutil, "which", lambda _: "/mock/spectre")
    monkeypatch.setattr(test_spectre.importlib.util, "find_spec", lambda _: SimpleNamespace(origin="site.py"))
    site = SimpleNamespace(install=SimpleNamespace(pdk_path=tmp_path / "missing"), MODEL_FILES=(tmp_path / "model",))
    monkeypatch.setitem(sys.modules, "pdk.tsmc65.hdl21", SimpleNamespace(site=site))
    with pytest.raises(pytest.skip.Exception, match="installation is unavailable"):
        inspect.unwrap(test_spectre.spectre_installation)()
    site.install.pdk_path = tmp_path
    with pytest.raises(FileNotFoundError):
        inspect.unwrap(test_spectre.spectre_installation)()


def test_spectre_marker_is_opt_in():
    import subprocess

    for selection, expected in (([], "20 deselected"), (["-m", "spectre"], "20 tests collected")):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", str(test_spectre.__file__), *selection],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == (0 if selection else 5), result.stdout + result.stderr
        assert expected in result.stdout


def test_a_runs_operating_point_gives_each_nets_device_capacitance(tmp_path) -> None:
    """Spectre's operating point (``OPPOINT``) as each net's device capacitance: a gate's total, a
    drain's and source's intrinsic and junction ones, the testbench's prefixes left out, ground as vss."""
    from flow.circuit.spectre import device_capacitance

    path = tmp_path / "oppoint.txt"
    path.write_text(
        "Instance: xtop.dut.MN of Samp\nModel: nch\nPrimitive: bsim4\n"
        "          d : V(xtop.vout) = 541 mV\n          g : V(xtop.clk) = 0 V\n"
        "          s : V(xtop.dut.mid) = 550 mV\n          b : val(0) = 0 \n"
        "        cjd = 800 aF\n        cjs = 976.224 aF\n        cgg = 2.5 fF\n"
        "        cgd = -1.1 fF\n        cdd = 1.1 fF\n        cds = -525.08e-24 F\n        css = 1 fF\n"
    )
    found = device_capacitance(path)
    assert set(found) == {"vout", "clk", "mid"}
    assert abs(found["clk"] - 2.5e-15) < 1e-20 and abs(found["vout"] - 1.9e-15) < 1e-20
    assert abs(found["mid"] - 1.976224e-15) < 1e-20


def test_a_noise_literal_or_a_swept_noise_analysis_writes_psf_ascii() -> None:
    """A literal noise statement and a noise analysis inside another (a sweep's) write PSF ASCII as
    an ``hs.Noise`` does; a literal that is no noise analysis leaves nutbin."""
    import hdl21 as h
    import hdl21.sim as hs

    from flow.circuit import spectre

    op = hs.Op(name="op")
    assert spectre.raw_format([op, h.Literal("xn (xtop.out 0) noise start=1e3 stop=1e9 dec=5")]) == "psfascii"
    assert spectre.raw_format([op, h.Literal("sweep_n dc dev=xtop.vn param=dc start=0 stop=1 step=0.5")]) == "nutbin"
    swept = hs.SweepAnalysis(
        inner=[hs.Noise(output="xtop.out", input_source="xtop.vinp", sweep=hs.LogSweep(start=1e3, stop=1e9, npts=5))],
        var="temp",
        sweep=hs.PointSweep(points=[0, 50]),
    )
    assert spectre.raw_format([swept]) == "psfascii"


@pytest.mark.parametrize(("noise", "expected"), [(False, "nutbin"), (True, "psfascii")])
def test_a_run_writes_nutbin_or_psf_ascii_where_it_has_a_noise_analysis(monkeypatch, tmp_path, noise, expected) -> None:
    """Spectre's raw format first on its command line, by the run's analyses: PSF ASCII (a file an
    analysis, which ``flow.pipeline.read`` reads as a directory) where one is a noise analysis."""
    import hdl21 as h
    import hdl21.sim as hs

    from flow.circuit import spectre

    bench = h.Module(name="Bench")
    bench.VSS = h.Port()
    bench.out, bench.inp = h.Signal(), h.Signal()
    bench.vinp = h.primitives.Vdc(dc=0.5, ac=1.0)(p=bench.inp, n=bench.VSS)
    sweep = hs.LogSweep(start=1e3, stop=1e9, npts=5)
    attrs = [hs.Op(name="op"), hs.Ac(sweep=sweep, name="ac")]
    if noise:
        attrs.append(hs.Noise(output=bench.out, input_source=bench.vinp, sweep=sweep, name="noise"))
    assert spectre.raw_format(attrs) == expected
    captured = {}
    monkeypatch.setattr(
        hs, "Sim", lambda **kwargs: SimpleNamespace(run=lambda options: captured.update(kwargs, options=options))
    )
    # a noise analysis runs in classic Spectre alone (``spectre.refusal``)
    spectre.run(bench, attrs, tmp_path / "run", fast=not noise)
    arguments = captured["options"].simulator_args
    assert arguments[:2] == ("-format", expected) and arguments.count("-format") == 1
    assert "+escchars" in arguments and captured["attrs"] is attrs
    assert ({"+preset=mx", "+mt=1"} <= set(arguments)) is not noise


def test_a_run_of_literals_alone_is_refused(monkeypatch, tmp_path) -> None:
    """hdl21 calls no simulator for a run without an analysis of its own, and the flow's operating
    point, a DC sweep and the transfer functions are literals: ``run`` refuses such a run by its
    directory, naming the operating point that makes it one, and runs it with that."""
    import hdl21 as h
    import hdl21.sim as hs

    from flow.circuit import spectre

    bench = h.Module(name="Bench")
    bench.VSS = h.Port()
    literals = [
        *spectre.options(),
        hs.Save(["xtop.outn", "xtop.voutn:p"]),
        h.Literal("sweep_n dc dev=xtop.voutn param=dc start=0 stop=1.2 step=0.3"),
    ]
    monkeypatch.setattr(hs, "Sim", lambda **kwargs: pytest.fail("a run without an analysis reached hdl21"))
    with pytest.raises(ValueError, match=r'run_n has no hdl21 analysis .* add hs\.Op\(name="op"\)'):
        spectre.run(bench, literals, tmp_path / "run_n")
    assert not (tmp_path / "run_n").exists()
    ran = []
    monkeypatch.setattr(hs, "Sim", lambda **kwargs: SimpleNamespace(run=lambda options: ran.append(kwargs["attrs"])))
    spectre.run(bench, [*literals, hs.Op(name="op")], tmp_path / "run_n")
    assert len(ran) == 1


def _accuracy_bench():
    """A bench of one source and a resistor, for the runs ``spectre.run`` refuses."""
    import hdl21 as h

    bench = h.Module(name="Bench")
    bench.VSS = h.Port()
    bench.out, bench.inp = h.Signal(), h.Signal()
    bench.vinp = h.primitives.Vdc(dc=0.5, ac=1.0)(p=bench.inp, n=bench.VSS)
    bench.r = h.primitives.R(r=1e3)(p=bench.inp, n=bench.out)
    return bench


@pytest.mark.parametrize(
    ("analysis", "accuracy", "reason"),
    [
        ("noise", None, "a noise analysis"),
        ("noise literal", None, "a noise analysis"),
        ("pnoise literal", None, "a noise analysis"),
        ("monte carlo noise", None, "a noise analysis"),
        ("swept noise", None, "a noise analysis"),
        ("transient noise", "NOISE", "noise"),
        ("tran", "DISTORTION", "distortion"),
        ("tran", "S_CURVE", "s curve"),
        ("tran", "SMALL_DIFFERENCE", "small difference"),
        ("tran", "TIMING", "timing"),
        ("maxstep", "TIMING", "timing"),
    ],
)
def test_a_run_that_needs_accuracy_is_refused_in_spectre_x(
    monkeypatch, tmp_path, caplog, analysis, accuracy, reason
) -> None:
    """A run with a noise analysis (AC, a literal's, a periodic one's, inside a Monte Carlo or a
    sweep) and one
    its bench marks with an ``Accuracy``: refused in Spectre X (the default, or a preset among its
    arguments) by a ValueError naming the run, why and the remedy, before Spectre is called; run in
    classic Spectre (``fast=False``), without a warning."""
    import hdl21 as h
    import hdl21.sim as hs

    from flow.circuit import spectre

    bench = _accuracy_bench()
    sweep = hs.LogSweep(start=1e3, stop=1e9, npts=5)
    found = {
        "noise": [hs.Noise(output=bench.out, input_source=bench.vinp, sweep=sweep, name="noise")],
        "noise literal": [hs.Op(name="op"), h.Literal("xn (xtop.out 0) noise start=1e3 stop=1e9 dec=5")],
        "pnoise literal": [hs.Op(name="op"), h.Literal("pn (xtop.out 0) pnoise start=1e3 stop=1e9")],
        "monte carlo noise": [
            hs.MonteCarlo(inner=[hs.Noise(output=bench.out, input_source=bench.vinp, sweep=sweep)], npts=3)
        ],
        "swept noise": [
            hs.SweepAnalysis(
                inner=[hs.Noise(output=bench.out, input_source=bench.vinp, sweep=sweep)],
                var="temp",
                sweep=hs.PointSweep(points=[0, 50]),
            )
        ],
        "transient noise": [hs.Tran(tstop=1e-9, name="tran", noise=True)],
        "maxstep": [hs.Tran(tstop=1e-9, name="tran", options={"maxstep": 1e-12})],
        "tran": [hs.Tran(tstop=1e-9, name="tran")],
    }[analysis]
    attrs = [*spectre.options(), *found]
    mark = None if accuracy is None else spectre.Accuracy[accuracy]
    monkeypatch.setattr(hs, "Sim", lambda **kwargs: pytest.fail("a refused run reached hdl21"))
    for fast, args in ((True, ()), (False, ("+preset=cx",)), (True, ("+preset=ax",))):
        with pytest.raises(ValueError, match=rf"the run in \S*run_a needs accuracy \(.*{reason}.*fast=False"):
            spectre.run(bench, attrs, tmp_path / "run_a", fast=fast, accuracy=mark, args=args)
    assert not (tmp_path / "run_a").exists()
    ran = []
    monkeypatch.setattr(hs, "Sim", lambda **kwargs: SimpleNamespace(run=lambda options: ran.append(options)))
    caplog.set_level(logging.WARNING, logger="flow.spectre")
    spectre.run(bench, attrs, tmp_path / "run_a", fast=False, accuracy=mark)
    assert len(ran) == 1 and not any(arg.startswith("+preset") for arg in ran[0].simulator_args)
    assert not _warned(caplog)


def _warned(caplog) -> list[str]:
    """What ``flow.spectre`` warned of since the last clear, and clear it."""
    found = [record.getMessage() for record in caplog.records if record.name == "flow.spectre"]
    caplog.clear()
    return found


@pytest.mark.parametrize(
    ("options", "noise", "words"),
    [
        ({"maxstep": 1e-12}, False, "a transient's maxstep, which Spectre X ignores (SPECTRE-592)"),
        ({}, True, "transient noise"),
        ({"noisefmax": "25G"}, False, "transient noise"),
        ({"maxstep": 1e-12, "noisefmax": "25G"}, True, "transient noise and a transient's maxstep"),
    ],
)
def test_an_unmarked_transient_with_noise_or_a_bounded_step_is_warned_of_in_spectre_x(
    monkeypatch, tmp_path, caplog, options, noise, words
) -> None:
    """A transient with noise or a maxstep, left in Spectre X without a mark: it runs, and the flow's
    log warns of it, naming the run, what it has and the remedy; marked, it is refused instead
    (``test_a_run_that_needs_accuracy_is_refused_in_spectre_x``); in classic Spectre nothing is
    said."""
    import hdl21.sim as hs

    from flow.circuit import spectre

    bench = _accuracy_bench()
    attrs = [*spectre.options(), hs.Tran(tstop=1e-9, name="tran", noise=noise, options=options)]
    ran = []
    monkeypatch.setattr(hs, "Sim", lambda **kwargs: SimpleNamespace(run=lambda options: ran.append(options)))
    caplog.set_level(logging.WARNING, logger="flow.spectre")
    spectre.run(bench, attrs, tmp_path / "run_w")
    warned = _warned(caplog)
    assert "+preset=mx" in ran[0].simulator_args
    assert len(warned) == 1 and f"the run in {tmp_path / 'run_w'} has {words}" in warned[0]
    assert "Spectre X (+preset=mx) and no accuracy mark" in warned[0] and "pass fast=False" in warned[0]
    spectre.run(bench, attrs, tmp_path / "run_w", fast=False)
    assert not _warned(caplog) and len(ran) == 2
    marked = spectre.Accuracy.S_CURVE
    assert spectre.caution(attrs, tmp_path, fast=True, args=(), accuracy=marked) is None


@pytest.mark.parametrize(
    ("statement", "words"),
    [
        ("tr tran stop=1n maxstep=1p", "a transient's maxstep"),
        ("tr tran stop=1n noisefmax=25G noiseseed=1", "transient noise"),
    ],
)
def test_a_literal_transient_with_noise_or_a_bounded_step_is_warned_of_too(tmp_path, statement, words) -> None:
    """A transient written as a literal statement is found as an ``hs.Tran`` is; a literal that is
    no transient, though it names the options, is not."""
    import hdl21 as h
    import hdl21.sim as hs

    from flow.circuit import spectre

    attrs = [hs.Op(name="op"), h.Literal(statement)]
    assert words in spectre.caution(attrs, tmp_path, fast=True, args=(), accuracy=None)
    other = [hs.Op(name="op"), h.Literal("xf (xtop.out 0) xf start=1 stop=1G maxstep=1p noisefmax=25G")]
    assert spectre.caution(other, tmp_path, fast=True, args=(), accuracy=None) is None


def test_a_run_that_needs_no_accuracy_runs_in_spectre_x(monkeypatch, tmp_path, caplog) -> None:
    """A transient that leaves Spectre X its own steps, an AC response and the operating point run
    at its preset without a word; a preset given in the arguments is the one the refusal names,
    with dropping it as the remedy."""
    import hdl21.sim as hs

    from flow.circuit import spectre

    bench = _accuracy_bench()
    sweep = hs.LogSweep(start=1e3, stop=1e9, npts=5)
    attrs = [*spectre.options(), hs.Tran(tstop=1e-9, name="tran", options={"strobeperiod": 1e-12}), hs.Ac(sweep=sweep)]
    ran = []
    monkeypatch.setattr(hs, "Sim", lambda **kwargs: SimpleNamespace(run=lambda options: ran.append(options)))
    caplog.set_level(logging.WARNING, logger="flow.spectre")
    spectre.run(bench, attrs, tmp_path / "run_x")
    assert "+preset=mx" in ran[0].simulator_args and not _warned(caplog)
    for fast in (True, False):
        assert spectre.refusal(attrs, tmp_path, fast=fast, args=(), accuracy=None) is None
        assert spectre.caution(attrs, tmp_path, fast=fast, args=(), accuracy=None) is None
    named = spectre.refusal(attrs, tmp_path, fast=False, args=("+preset=cx",), accuracy=spectre.Accuracy.TIMING)
    assert "Spectre X (+preset=cx)" in named and "drop +preset=cx from its args" in named
    default = spectre.refusal(attrs, tmp_path, fast=True, args=(), accuracy=spectre.Accuracy.TIMING)
    assert "Spectre X (+preset=mx)" in default and "drop" not in default
