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


def options(temperature_c: float = 25.0) -> list[Any]:
    """The options every run takes: its temperature, the selected signals saved alone, and the
    models' limit checks into a file (``checklimitdest``)."""
    return [
        hs.Options(name="temp", value=temperature_c),
        hs.Options(name="save", value="selected"),
        hs.Options(name="checklimitdest", value="file"),
    ]


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
