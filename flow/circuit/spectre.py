"""What every block's Spectre run shares (its ``sim.simulate``): the kit's includes in its order,
the simulator options every run takes, the command line and the running itself, its failure
raised as a plain error (a worker process cannot send Spectre's own back).

    attrs = [*includes(install), *options(), hs.Save(...), hs.Tran(...)]
    run(bench, attrs, run_dir)

The options settle what Spectre otherwise warns about in every run: ``checklimitdest`` names
where the models' limit checks (their asserts: a device's safe operating area) go, the run's
log (``file``: spectre.log, which the flow's log reads with the rest), where Spectre's default is
its own database and a warning that none was named.

A run's analyses are its ``attrs``: a transient (``hs.Tran``), the operating point (``hs.Op``;
``options`` runs one already, ``opdc``), the AC response (``hs.Ac``), noise (``hs.Noise``), and,
as literals, what hdl21 has no analysis for: a DC sweep of a source's value
(``h.Literal("<name> dc dev=xtop.v<net> param=dc start=... stop=... step=...")``) and the
transfer functions to an output (``h.Literal("<name> (xtop.<net> 0) xf start=... stop=...
dec=...")``). ``flow.pipeline.read`` reads each by its name. hdl21 simulates nothing for a run
without an analysis of its own, so one whose analyses are all literals (DC sweeps alone) carries
an ``hs.Op`` as well; ``run`` refuses it otherwise.

A run is Spectre X at its fast preset (``FAST``) unless it passes ``fast=False`` (classic Spectre).
Spectre X ignores a transient's ``maxstep`` (SPECTRE-592), and its error control leaves a sine's
harmonics past the third and small differences of large signals wrong, so ``run`` refuses Spectre X
(``FAST``, or any ``+preset`` in ``args``) for a run that needs accuracy: one with a noise
analysis (``hs.Noise``, a noise literal), and one its bench marks with an ``Accuracy`` (noise,
distortion, an S-curve, a small difference, sub-picosecond timing)::

    run(bench, attrs, run_dir, fast=False, accuracy=Accuracy.S_CURVE)

A run left in Spectre X without a mark whose transient has noise or bounds its step (``maxstep``)
runs, with a warning on the flow's log (``caution``) that names it and the remedy: such a run is
what a bench marks, as a comparator's S-curve is.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from enum import Enum, auto
from pathlib import Path
from typing import Any

from hdl21 import Literal
from hdl21 import sim as hs
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.circuit import oppoint

# Spectre's command line after its raw format (``raw_format``): a license waited for up to an
# hour (other runs share the server's), escaped names, its log in spectre.log
ARGS = ("+lqtimeout", "3600", "+escchars", "+log", "spectre.log")
# Spectre X at its mx preset, on this many threads a run (the flow runs many at once)
FAST = ("+preset=mx", "+mt=1")
LOG = logging.getLogger("flow.spectre")


class Accuracy(Enum):
    """Why a run needs classic Spectre's accuracy rather than Spectre X's fast preset (``FAST``), a
    bench's mark on its run (``run(..., accuracy=...)``): the error control of Spectre X's presets
    sets these wrong, and it ignores a transient's ``maxstep``."""

    NOISE = auto()  # noise: transient noise (an AC noise analysis ``run`` finds itself)
    DISTORTION = auto()  # a sine's harmonics past the third, THD, SFDR
    S_CURVE = auto()  # a decision's probability against a small input (a comparator's noise, offset)
    SMALL_DIFFERENCE = auto()  # a small difference of large signals (a pedestal, an offset, a residue)
    TIMING = auto()  # a time measured to below a picosecond (a delay's change, jitter, setup and hold)


def includes(install: Any, corner: Any = None, *, stdcells: bool = False) -> list[Any]:
    """The kit's includes a run takes, in its order: its models at ``corner`` (typical by default),
    then what else its simulations take where it has it (TSMC's pre-simulation settings, its
    standard cells where ``stdcells``, the device names its netlists use: pdk/<name>/hdl21)."""
    import hdl21 as h

    names = ("include_pre_simulation", *(("include_stdcell",) if stdcells else ()), "include_devices")
    return [
        install.include(corner if corner is not None else h.pdk.Corner.TYP),
        *(getattr(install, name)() for name in names if hasattr(install, name)),
    ]


# the operating point's file a run writes (``options(oppoint=True)``): each device's terminals and
# its model's values at the DC solution the run starts from
OPPOINT = "oppoint.txt"


def options(temperature_c: float = 25.0, *, oppoint: bool = True) -> list[Any]:
    """The options every run takes: its temperature, the selected signals saved alone, and the
    models' limit checks into a file (``checklimitdest``); where ``oppoint``, the DC operating
    point before its analyses (``opdc``: the saved signals' in the run's measurement,
    ``sweeps["opdc"]``), each device's into ``OPPOINT`` (its capacitances: ``device_capacitance``)."""
    found = [
        hs.Options(name="temp", value=temperature_c),
        hs.Options(name="save", value="selected"),
        hs.Options(name="checklimitdest", value="file"),
    ]
    if oppoint:
        found += [hs.Literal("opdc dc"), hs.Literal(f'opinfo info what=oppoint where=file file="{OPPOINT}"')]
    return found


_SI = {"a": 1e-18, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0}
# a device's terminal and the self-capacitances (its model's, at the operating point) it puts on
# that terminal's net: the gate's total, the drain's and source's intrinsic and junction ones
_SELF = {"g": ("cgg",), "d": ("cdd", "cjd"), "s": ("css", "cjs")}


def device_capacitance(path: Path) -> dict[str, float]:
    """Each net's capacitance from the devices on it (F), from a run's operating point
    (``OPPOINT``): every transistor's gate (``cgg``), drain (``cdd`` and ``cjd``) and source
    (``css`` and ``cjs``) self-capacitance on its terminal's net, the net named as the DUT names it
    (the testbench's ``xtop.`` and ``xtop.dut.`` left out; ground, ``0``, is ``vss``)."""
    found: dict[str, float] = {}
    for block in path.read_text(errors="replace").split("Instance: ")[1:]:
        nets = {
            term: net or value
            for term, net, value in re.findall(r"^\s+([gdsb]) : (?:V\(([^)]+)\)|val\(([^)]+)\))", block, re.MULTILINE)
        }
        values = {
            name: float(number) * _SI[prefix]
            for name, number, prefix in re.findall(
                r"^\s+(\w+) = (-?[\d.]+(?:e-?\d+)?) ?([afpnum]?)F\b", block, re.MULTILINE
            )
        }
        for term, names in _SELF.items():
            if term not in nets:
                continue
            net = re.sub(r"^xtop\.(dut\.)?", "", nets[term])
            net = "vss" if net == "0" else net
            found[net] = found.get(net, 0.0) + sum(values.get(name, 0.0) for name in names)
    return found


def _analyses(attrs: Iterable[Any]) -> list[Any]:
    """A run's analyses and literals, the inner analyses of any that holds some (a Monte Carlo's,
    a sweep's) among them."""
    found = []
    for attr in attrs:
        found.append(attr)
        if isinstance(getattr(attr, "inner", None), list):
            found += _analyses(attr.inner)
    return found


def _literal(attr: Any, statement: str) -> bool:
    """Whether ``attr`` is a literal with a Spectre analysis statement of the kinds ``statement``
    matches (a regular expression: ``tran``, ``noise|pnoise``): ``<name> [(<nodes>)] <kind> ...``."""
    pattern = rf"^\s*\S+\s+(?:\([^)]*\)\s+)?(?:{statement})\b"
    return isinstance(attr, Literal) and re.search(pattern, attr.text, re.MULTILINE) is not None


def noise_analysis(attrs: Iterable[Any]) -> bool:
    """Whether a run has a noise analysis: an ``hs.Noise``, or a literal one (``<name> [(<nodes>)]
    noise ...``, the periodic and harmonic-balance ones too); one inside another analysis too."""
    return any(
        isinstance(attr, hs.Noise) or _literal(attr, "noise|pnoise|qpnoise|hbnoise") for attr in _analyses(attrs)
    )


def _transient_option(attrs: Iterable[Any], option: str) -> bool:
    """Whether a run's transient sets ``option``: an ``hs.Tran``'s options, or a literal ``tran``
    statement's."""
    return any(
        (isinstance(attr, hs.Tran) and option in attr.options)
        or (_literal(attr, "tran") and re.search(rf"\b{option}\s*=", attr.text) is not None)
        for attr in _analyses(attrs)
    )


def transient_noise(attrs: Iterable[Any]) -> bool:
    """Whether a run's transient has noise (``hs.Tran``'s ``noise``, or its ``noisefmax`` option,
    which turns Spectre's transient noise on; a literal ``tran`` statement's too)."""
    noisy = any(isinstance(attr, hs.Tran) and bool(attr.noise) for attr in _analyses(attrs))
    return noisy or _transient_option(attrs, "noisefmax")


def bounded_step(attrs: Iterable[Any]) -> bool:
    """Whether a run's transient bounds its time step (its ``maxstep`` option, of an ``hs.Tran`` or a
    literal ``tran`` statement), which Spectre X ignores (SPECTRE-592)."""
    return _transient_option(attrs, "maxstep")


def _saves_device_values(attrs: Iterable[Any]) -> bool:
    """Whether a run saves a device's operating-point values (``<device>:vds``, ``:region``:
    ``flow.circuit.oppoint.saves``)."""
    for attr in attrs:
        if isinstance(attr, hs.Save):
            names = attr.targ if isinstance(attr.targ, list) else [attr.targ]
            if any(isinstance(name, str) and name.rpartition(":")[2] in oppoint.VALUES for name in names):
                return True
    return False


def raw_format(attrs: list[Any]) -> str:
    """The format a run's raw output takes (Spectre's ``-format``): nutbin, one file; PSF ASCII, a
    directory with a file an analysis, where the run has a noise analysis (``noise_analysis``),
    which Spectre's nutbin file holds short of the values its header declares, or saves a device's
    operating-point values (``flow.circuit.oppoint.saves``), whose region nutbin writes without a
    unit and whose last analysis it writes with no points where the run has no transient: neither
    parses."""
    return "psfascii" if noise_analysis(attrs) or _saves_device_values(attrs) else "nutbin"


def _preset(fast: bool, args: tuple[str, ...]) -> str | None:
    """The Spectre X preset a run takes: ``FAST``'s where ``fast``, a ``+preset`` among ``args``,
    or None (classic Spectre)."""
    given = next((arg for arg in args if arg.startswith("+preset")), None)
    return given or (FAST[0] if fast else None)


def refusal(
    attrs: list[Any], run_dir: Path, *, fast: bool, args: tuple[str, ...], accuracy: Accuracy | None
) -> str | None:
    """Why ``run`` refuses a run in Spectre X (``fast``, or a ``+preset`` among ``args``) where it
    needs accuracy (its bench's ``Accuracy`` mark, a noise analysis), with the remedy; None where it
    runs."""
    preset = _preset(fast, args)
    if preset is None:
        return None
    reasons = [accuracy.name.lower().replace("_", " ")] if accuracy is not None else []
    reasons += ["a noise analysis"] if noise_analysis(attrs) else []
    if not reasons:
        return None
    remedy = "pass fast=False to flow.circuit.spectre.run (classic Spectre"
    remedy += ', its transient at options={"errpreset": "conservative", ...})'
    remedy += f" and drop {preset} from its args" if preset in args else ""
    return (
        f"the run in {run_dir} needs accuracy ({'; '.join(reasons)}) and is set to run in Spectre X ({preset}), "
        f"whose error control sets noise, distortion past the third harmonic and small differences wrong: {remedy}"
    )


def caution(
    attrs: list[Any], run_dir: Path, *, fast: bool, args: tuple[str, ...], accuracy: Accuracy | None
) -> str | None:
    """What ``run`` warns of a run in Spectre X that its bench left unmarked (no ``accuracy``) whose
    transient has noise or bounds its step (``maxstep``, which Spectre X ignores: SPECTRE-592), with
    the remedy; None where there is nothing to warn of."""
    preset = _preset(fast, args)
    if preset is None or accuracy is not None:
        return None
    found = ["transient noise"] if transient_noise(attrs) else []
    found += ["a transient's maxstep, which Spectre X ignores (SPECTRE-592)"] if bounded_step(attrs) else []
    if not found:
        return None
    return (
        f"the run in {run_dir} has {' and '.join(found)} in Spectre X ({preset}) and no accuracy mark: where "
        "it measures noise, an S-curve, distortion, a small difference or sub-picosecond timing, mark it "
        "(accuracy=flow.circuit.spectre.Accuracy...) and pass fast=False; else drop maxstep and noise"
    )


def run(
    bench: Any,
    attrs: list[Any],
    run_dir: Path,
    *,
    fast: bool = True,
    accuracy: Accuracy | None = None,
    args: tuple[str, ...] = (),
    data=False,
) -> Any:
    """Simulate ``bench`` with ``attrs`` in ``run_dir`` (Spectre's raw output left there,
    ``netlist.raw``, in the format its analyses take, ``raw_format``): Spectre X (``FAST``) unless
    ``fast`` is off, ``args`` after the common command line; its results parsed only where
    ``data``. Spectre's failure raised as a RuntimeError naming the run; a run without an hdl21
    analysis (literals alone), which hdl21 passes over without calling Spectre, refused; a run
    that needs accuracy (``accuracy``, its bench's mark; a noise analysis) refused in Spectre X with
    a ValueError naming it and the remedy (``refusal``); an unmarked one in Spectre X with
    transient noise or a ``maxstep`` warned of (``caution``)."""
    if reason := refusal(attrs, run_dir, fast=fast, args=args, accuracy=accuracy):
        raise ValueError(reason)
    if warning := caution(attrs, run_dir, fast=fast, args=args, accuracy=accuracy):
        LOG.warning(warning)
    if not any(hs.is_analysis(attr) for attr in attrs):
        raise ValueError(
            f"the run in {run_dir} has no hdl21 analysis (hs.Tran, hs.Ac, hs.Noise, hs.Op, hs.MonteCarlo): "
            "hdl21 simulates nothing for analyses written as literals alone; "
            'add hs.Op(name="op") beside them (read as sweeps["op"])'
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    settings = SimOptions(
        simulator=SupportedSimulators.SPECTRE,
        fmt=ResultFormat.SIM_DATA if data else ResultFormat.NONE,
        rundir=run_dir,
        simulator_args=("-format", raw_format(attrs), *ARGS, *(FAST if fast else ()), *args),
    )
    try:
        return hs.Sim(tb=bench, attrs=attrs).run(settings)
    except SimError as error:
        # the simulator's error holds its simulation, which cannot cross back from a worker process
        raise RuntimeError(f"Spectre failed in {run_dir}: {error}") from None


def log_stats(path: Path) -> dict[str, Any]:
    """What a run's log (``spectre.log``) says of it: its circuit (nodes, each primitive's
    instances), its transient's accepted steps, its times (the parse of its netlist and models,
    its transient, its whole run: elapsed seconds) and its peak memory (bytes)."""
    text = path.read_text(errors="replace")
    inventory = text.split("Circuit inventory:", 1)[-1].split("\n\n", 1)[0] if "Circuit inventory:" in text else ""
    counts = {name: int(count) for name, count in re.findall(r"^\s+(\w+) (\d+)\s*$", inventory, re.MULTILINE)}

    def seconds(pattern: str) -> float | None:
        found = re.findall(pattern + r".*?elapsed = ([\d.]+) (\w*s)", text, re.MULTILINE)
        if not found:
            return None
        value, unit = found[-1]
        return float(value) * {"s": 1.0, "ms": 1e-3, "us": 1e-6}.get(unit, 1.0)

    memory = [int(value) for value in re.findall(r"Peak resident memory used = (\d+) Mbytes", text)]
    steps = re.findall(r"Number of accepted tran steps =\s+(\d+)", text)
    return {
        "nodes": counts.pop("nodes", None),
        "primitives": counts,
        "accepted_steps": int(steps[-1]) if steps else None,
        "parse_s": seconds(r"Time for NDB Parsing:"),
        "tran_s": seconds(r"Total time required for tran analysis"),
        "elapsed_s": seconds(r"^Time used:"),
        "memory_b": max(memory) * 2**20 if memory else None,
        "preset": (re.findall(r"Spectre X preset=(\w+) enabled", text) or [None])[-1],
    }
