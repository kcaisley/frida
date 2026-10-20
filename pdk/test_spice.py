"""Every device and standard cell a PDK's hdl21 package wraps loads in Spectre and ngspice.

One netlist per PDK instances each device of its ``hdl21/primitives/prim_dicts.py`` (a MOS at its
default length and its narrowest finger the row cells place) and each cell of its library
(``hdl21/cells.py``), every pin on a net of its own, after what its ``Install.simulation_includes``
gives the simulator. The run has no analysis: reading the model decks and resolving every instance
is the check. A device the decks do not define, a binned model with no bin for the size, a cell the
library's netlist lacks or defines with other pins: each is an error. Spectre stops after
elaborating the circuit; ngspice (HSPICE compatibility, ``ngbehavior=hsa``) quits from a control
block once it has read it, and exits 1 on any such error.

What a site's decks cannot simulate is the PDK's to declare, with the reason: a device or the cell
library (``"cells"``) in ``Install.UNMODELED[simulator]``, which the netlist leaves out, or a whole
simulator, whose ``simulation_includes`` raises ``NotImplementedError`` (the run skips).

The netlists build without the kits; the runs need the site's kits under /eda/kits, and Spectre:

    uv run pytest pdk/test_spice.py -m site_pdk
"""

from __future__ import annotations

import io
import shutil
import subprocess
from importlib import import_module
from pathlib import Path

import hdl21 as h
import pytest
from hdl21 import sim as hs
from vlsirtools.netlist.spectre import SpectreNetlister
from vlsirtools.netlist.spice import NgspiceNetlister

from flow.circuit.cells import library_module

ROOT = Path(__file__).resolve().parents[1]
PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")
SIMULATORS = ("spectre", "ngspice")
CADENCE = "/eda/local/scripts/cadence_2024-25.sh"


def devices(pdk: str) -> dict[str, h.ExternalModule]:
    """Every device module the PDK's package wraps, by name."""

    prim = import_module(f"pdk.{pdk}.hdl21.primitives.prim_dicts")
    found = {}
    for value in vars(prim).values():
        if isinstance(value, dict):
            found.update({m.name: m for m in value.values() if isinstance(m, h.ExternalModule)})
    return dict(sorted(found.items()))


def everything(pdk: str, simulator: str | None = None) -> h.Module:
    """One instance of each device and each library cell; leaves out what ``simulator``'s decks
    do not model at this site."""

    prim = import_module(f"pdk.{pdk}.hdl21.primitives.prim_dicts")
    logic = import_module(f"pdk.{pdk}.hdl21.pdk_logic")
    cells = import_module(f"pdk.{pdk}.hdl21.cells")
    skip = logic.Install.UNMODELED.get(simulator, {}) if simulator else {}
    sizes = getattr(prim, "default_xtor_size", {})
    units = getattr(logic, "MOS_FINGER_MIN_UNITS", 1)

    module = h.Module(name=f"{pdk}_everything")
    module.VSS = h.Port()
    for i, (name, device) in enumerate(devices(pdk).items()):
        if name in skip:
            continue
        params = device.paramtype()
        if name in sizes:  # a MOS: the narrowest finger the row cells place
            width, length = sizes[name]
            params = device.paramtype(w=width * units, l=length)
        nets = {port.name: module.add(h.Signal(), name=f"d{i}_{port.name}") for port in device.port_list}
        module.add(device(params)(**nets), name=f"x{name}")
    for i, name in enumerate(() if "cells" in skip else cells.CELLS):
        cell = library_module(cells, name)
        nets = {port.name: module.add(h.Signal(), name=f"c{i}_{port.name}") for port in cell.port_list}
        module.add(cell()(**nets), name=f"x{name}")
    return module


def netlist(pdk: str, simulator: str) -> str:
    install = import_module(f"pdk.{pdk}.hdl21.site").install
    attrs = install.simulation_includes(h.pdk.Corner.TYP, simulator)
    if simulator == "ngspice":
        attrs = [*attrs, hs.Literal(".control\nquit 0\n.endc")]
    inp = hs.to_proto(hs.Sim(tb=everything(pdk, simulator), attrs=attrs))
    out = io.StringIO()
    (SpectreNetlister if simulator == "spectre" else NgspiceNetlister)(out).write_sim_input(inp)
    return out.getvalue()


@pytest.mark.parametrize("pdk", PDKS)
def test_every_device_and_cell_netlists(pdk: str) -> None:
    """The package's devices and cells instance and netlist in both formats."""

    pytest.importorskip(f"pdk.{pdk}.hdl21.cells")
    module = everything(pdk)
    for fmt in ("spectre", "spice"):
        out = io.StringIO()
        h.netlist(module, out, fmt=fmt)
        assert out.getvalue()
    logic = import_module(f"pdk.{pdk}.hdl21.pdk_logic")
    for simulator, reasons in logic.Install.UNMODELED.items():
        assert simulator in SIMULATORS
        assert set(reasons) <= {*devices(pdk), "cells"}, f"{pdk} declares unmodeled devices it does not wrap"
        assert all(isinstance(reason, str) and reason for reason in reasons.values()), "each needs its reason"


@pytest.mark.site_pdk
@pytest.mark.parametrize("simulator", SIMULATORS)
@pytest.mark.parametrize("pdk", PDKS)
def test_every_device_and_cell_loads(pdk: str, simulator: str) -> None:
    site = import_module(f"pdk.{pdk}.hdl21.site")
    if not site.install.pdk_path.is_dir():
        pytest.skip(f"{pdk}'s kit is not at {site.install.pdk_path}")
    if simulator == "spectre" and not Path(CADENCE).is_file():
        pytest.skip(f"no Cadence environment ({CADENCE})")
    if simulator == "ngspice" and shutil.which("ngspice") is None:
        pytest.skip("ngspice is not on the PATH")
    try:
        site.install.simulation_includes(h.pdk.Corner.TYP, simulator)
    except NotImplementedError as reason:
        pytest.skip(f"{pdk} in {simulator}: {reason}")

    run_dir = ROOT / "build/test_spice" / pdk / simulator
    run_dir.mkdir(parents=True, exist_ok=True)
    if simulator == "spectre":
        (run_dir / "netlist.scs").write_text(netlist(pdk, simulator))
        command = f"source {CADENCE} >/dev/null 2>&1; spectre -64 +escchars +log spectre.log netlist.scs"
        run = subprocess.run(
            ["bash", "-c", command], cwd=run_dir, capture_output=True, text=True, timeout=1200, check=False
        )
        log = (run_dir / "spectre.log").read_text(errors="replace")
        errors = [line for line in log.splitlines() if "ERROR" in line]
    else:
        (run_dir / "netlist.sp").write_text(netlist(pdk, simulator))
        command = ["ngspice", "--no-spiceinit", "-D", "ngbehavior=hsa", "-b", "netlist.sp"]
        run = subprocess.run(command, cwd=run_dir, capture_output=True, text=True, timeout=1200, check=False)
        log = run.stdout + run.stderr
        (run_dir / "ngspice.log").write_text(log)
        lines = log.splitlines()
        errors = [line for i, line in enumerate(lines) for line in lines[i : i + 3] if "rror" in lines[i]]
    assert run.returncode == 0 and not errors, f"{pdk} in {simulator} ({run_dir}):\n" + "\n".join(errors[:40])
