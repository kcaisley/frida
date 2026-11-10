"""What every block's Spectre run shares (its ``sim.simulate``): the kit's includes in its order,
the simulator options every run takes, the command line and the running itself, its failure
raised as a plain error (a worker process cannot send Spectre's own back).

    attrs = [*includes(install), *options(), hs.Save(...), hs.Tran(...)]
    run(bench, attrs, run_dir)

The options settle what Spectre otherwise warns about in every run: ``checklimitdest`` names
where the models' limit checks (their asserts: a device's safe operating area) go, the run's
log (``file``: spectre.log, which the flow's log reads with the rest), where Spectre's default is
its own database and a warning that none was named.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from hdl21 import sim as hs
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

# Spectre's command line: nutbin output, a license waited for up to an hour (other runs share the
# server's), escaped names, its log in spectre.log
ARGS = ("-format", "nutbin", "+lqtimeout", "3600", "+escchars", "+log", "spectre.log")
# Spectre X at its mx preset, on this many threads a run (the flow runs many at once)
FAST = ("+preset=mx", "+mt=1")


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
    point before its analyses, each device's into ``OPPOINT`` (its capacitances: ``device_capacitance``)."""
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


def run(
    bench: Any, attrs: list[Any], run_dir: Path, *, fast: bool = True, args: tuple[str, ...] = (), data=False
) -> Any:
    """Simulate ``bench`` with ``attrs`` in ``run_dir`` (Spectre's raw output left there,
    ``netlist.raw``): Spectre X (``FAST``) unless ``fast`` is off, ``args`` after the common
    command line; its results parsed only where ``data``. Spectre's failure raised as a
    RuntimeError naming the run."""
    run_dir.mkdir(parents=True, exist_ok=True)
    settings = SimOptions(
        simulator=SupportedSimulators.SPECTRE,
        fmt=ResultFormat.SIM_DATA if data else ResultFormat.NONE,
        rundir=run_dir,
        simulator_args=(*ARGS, *(FAST if fast else ()), *args),
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
