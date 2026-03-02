# CLI Migration Plan

## Goal

Separate the **flow runner** (variant sweeps, netlist generation, simulation,
layout generation) from **tests** (unit/integration assertions that verify
correctness with a single default input).

- `flow` CLI (`flow/cli.py`) — thin dispatcher that parses args and calls
  per-module `run_netlist()` / `run_simulate()` / `run_layout()` functions.
- `uv run pytest` — fast, no-flags-needed correctness checks.

After migration:

```
flow primitive -c mosfet -t ihp130 -m max -v
flow netlist -c samp -t ihp130 -m max
flow simulate -c comp -s spectre --host jupiter
```

```
uv run pytest          # ~70+ tests, all pass, no flags needed
```

---

## Architecture

### Module-oriented structure

Each **block** directory contains files named by **what they do**. The
directory name provides the block identity, so function names are generic
(`run_netlist`, `run_simulate`, `run_layout`).

| File | Contains | Example |
|------|----------|---------|
| `subckt.py` | DUT generator + params (the thing you're designing) | `Samp`, `SampParams` |
| `testbench.py` | Testbench, sim_input, variant sweep runners | `SampTb`, `run_netlist()`, `run_simulate()` |
| `primitive.py` | Layout generator + params + layout runner | `mosfet()`, `MosfetParams`, `run_layout()` |
| `test.py` | Smoke test (single default input) | `test_samp()` |

### Runners live inside each module

Each module's `testbench.py` (or `primitive.py` for layout) owns its variant
sweep logic and all domain-specific enums. The CLI never imports enums like
`L.MosType`, `SwitchType`, `PreampDiffpair`, etc. — those stay internal to the
module that uses them.

### CLI is a thin dispatcher

`flow/cli.py` (~80 lines) parses arguments, calls `set_pdk()`, and dispatches
to the appropriate module's runner via lazy import. It can use dynamic import
since cell names match directory names (`flow.{cell}.testbench`).

### Dependency tree controlled by CLI

The CLI decides ordering (primitives before layout, netlisting before
simulation). Each module's `run_*()` function just does its job without
knowing about the broader dependency chain.

---

## Directory structure after migration

```
flow/
├── cli.py                      # ~80 lines, thin argparse dispatcher
├── conftest.py                 # ~30 lines, set_pdk + tech fixture
├── __init__.py
│
├── circuit/                    # shared circuit infrastructure (renamed from flow/)
│   ├── __init__.py
│   ├── netlist.py
│   ├── sim.py
│   ├── measure.py
│   ├── params.py
│   ├── plot.py
│   ├── spice_server.py
│   ├── test_measure.py         # unit tests (unchanged)
│   ├── test_netlist.py
│   ├── test_params.py
│   └── test_plot.py
│
├── layout/                     # shared layout infrastructure (unchanged)
│   ├── __init__.py
│   ├── dsl.py
│   ├── tech.py
│   ├── serialize.py
│   └── image.py
│
├── samp/
│   ├── __init__.py
│   ├── subckt.py               # SampParams, Samp generator
│   ├── testbench.py            # SampTb, sim_input, run_netlist(), run_simulate()
│   └── test.py                 # smoke test
│
├── comp/
│   ├── __init__.py
│   ├── subckt.py               # CompParams, Comp generator
│   ├── testbench.py            # CompTb, sim_input, run_netlist(), run_simulate()
│   └── test.py                 # smoke test
│
├── cdac/
│   ├── __init__.py
│   ├── subckt.py               # CdacParams, Cdac generator
│   ├── testbench.py            # CdacTb, sim_input, run_netlist(), run_simulate()
│   └── test.py                 # smoke test
│
├── adc/
│   ├── __init__.py
│   ├── subckt.py               # AdcParams, Adc generator
│   ├── testbench.py            # AdcTb, sim_input, run_netlist(), run_simulate()
│   └── test.py                 # smoke test
│
├── mosfet/
│   ├── __init__.py
│   ├── primitive.py            # MosfetParams, mosfet generator, run_layout()
│   └── test.py                 # smoke test
│
└── momcap/
    ├── __init__.py
    ├── primitive.py            # MomcapParams, momcap generator, run_layout()
    └── test.py                 # smoke test
```

---

## File rename mapping

```
BEFORE                              AFTER
──────                              ─────
flow/samp/samp.py                   flow/samp/subckt.py
flow/samp/test_samp.py              flow/samp/testbench.py
(new)                               flow/samp/test.py

flow/comp/comp.py                   flow/comp/subckt.py
flow/comp/test_comp.py              flow/comp/testbench.py
(new)                               flow/comp/test.py

flow/cdac/cdac.py                   flow/cdac/subckt.py
flow/cdac/test_cdac.py              flow/cdac/testbench.py
(new)                               flow/cdac/test.py

flow/adc/adc.py                     flow/adc/subckt.py
flow/adc/test_adc.py                flow/adc/testbench.py
(new)                               flow/adc/test.py

flow/layout/mosfet.py               flow/mosfet/primitive.py
(new)                               flow/mosfet/test.py

flow/layout/momcap.py               flow/momcap/primitive.py
(new)                               flow/momcap/test.py
```

---

## Task Checklist

### Phase 1: Restructure modules + create runners

Rename files, move sweep logic from `test_*_flow` functions into `run_*()`
functions, extract smoke tests into `test.py` files.

- [x] Rename `flow/samp/samp.py` → `flow/samp/subckt.py`
- [x] Rename `flow/samp/test_samp.py` → `flow/samp/testbench.py`
  - [x] Update internal import: `from .subckt import Samp, SampParams`
  - [x] Extract sweep logic from `test_samp_flow` into `run_netlist()` and `run_simulate()`
  - [x] Extract `_build_variants()` helper (shared by both runners)
  - [x] Remove `test_samp_flow` function
- [x] Create `flow/samp/test.py` with smoke test `test_samp()`
- [x] Update `flow/samp/__init__.py` imports (`from .subckt import ...`, `from .testbench import ...`)

- [x] Rename `flow/comp/comp.py` → `flow/comp/subckt.py`
- [x] Rename `flow/comp/test_comp.py` → `flow/comp/testbench.py`
  - [x] Update internal import: `from .subckt import Comp, CompParams, is_valid_comp_params`
  - [x] Extract sweep logic from `test_comp_flow` into `run_netlist()` and `run_simulate()`
  - [x] Remove `test_comp_flow` function
- [x] Create `flow/comp/test.py` with smoke test `test_comp()`
- [x] Update `flow/comp/__init__.py` imports

- [x] Rename `flow/cdac/cdac.py` → `flow/cdac/subckt.py`
- [x] Rename `flow/cdac/test_cdac.py` → `flow/cdac/testbench.py`
  - [x] Update internal import: `from .subckt import Cdac, CdacParams, ...`
  - [x] Extract sweep logic from `test_cdac_flow` into `run_netlist()` and `run_simulate()`
  - [x] Keep `test_cdac_weights` — move to `flow/cdac/test.py`
  - [x] Remove `test_cdac_flow` function
- [x] Create `flow/cdac/test.py` with `test_cdac()` smoke test and `test_cdac_weights()`
- [x] Update `flow/cdac/__init__.py` imports

- [x] Rename `flow/adc/adc.py` → `flow/adc/subckt.py`
- [x] Rename `flow/adc/test_adc.py` → `flow/adc/testbench.py`
  - [x] Update internal import: `from .subckt import Adc, AdcParams, get_adc_weights`
  - [x] Extract sweep logic from `test_adc_flow` into `run_netlist()` and `run_simulate()`
  - [x] Keep `test_adc_weights` — move to `flow/adc/test.py`
  - [x] Remove `test_adc_flow` function
- [x] Create `flow/adc/test.py` with `test_adc()` smoke test and `test_adc_weights()`
- [x] Update `flow/adc/__init__.py` imports

- [x] Move `flow/layout/mosfet.py` → `flow/mosfet/primitive.py`
  - [x] Update imports to reference `flow.layout.dsl`, `flow.layout.tech`, etc.
  - [x] Extract sweep logic from `test_mosfet` into `run_layout()`
  - [x] Remove `test_mosfet` function
- [x] Create `flow/mosfet/__init__.py`
- [x] Create `flow/mosfet/test.py` with smoke test `test_mosfet()`

- [x] Move `flow/layout/momcap.py` → `flow/momcap/primitive.py`
  - [x] Update imports to reference `flow.layout.dsl`, `flow.layout.tech`, etc.
  - [x] Extract sweep logic from `test_momcap` into `run_layout()`
  - [x] Remove `test_momcap` function
- [x] Create `flow/momcap/__init__.py`
- [x] Create `flow/momcap/test.py` with smoke test `test_momcap()`

- [x] Update `flow/layout/__init__.py` to remove mosfet/momcap re-exports
      (they now live in `flow.mosfet` and `flow.momcap`)

- [x] Update cross-module imports that reference old paths
  - [x] `flow/adc/subckt.py`: uses `..samp`, `..comp`, `..cdac` (package-level, already correct)
  - [x] `flow/conftest.py`: `_reset_generator_caches` imports updated to `.subckt`/`.testbench`
  - [x] No PDK or external code imported from `flow.layout.mosfet` or `flow.layout.momcap`
  - [x] `flow/circuit/test_netlist.py`: updated `..samp.samp` → `..samp.subckt`
  - [x] `flow/circuit/netlist.py`: updated docstring example `flow.comp.comp` → `flow.comp.subckt`

### Phase 2: Create CLI

- [x] Create `flow/cli.py` with argparse — thin dispatcher
  - [x] `primitive` subcommand (-c/--cell, -t/--tech, -m/--mode, -v/--visual, -o/--out)
  - [x] `netlist` subcommand (-c/--cell, -t/--tech, -m/--mode, -f/--fmt, --montecarlo, -o/--out)
  - [x] `simulate` subcommand (-c/--cell, -t/--tech, -m/--mode, -s/--simulator, --host, --montecarlo, -o/--out)
  - [x] Simulator availability check (`_check_simulator`) with `SIM_HOSTS` and `SIMULATOR_BINARIES`
  - [x] `argcomplete.autocomplete(parser)` for tab completion
- [x] Add `[project.scripts] flow = "flow.cli:main"` to `pyproject.toml`
- [x] Run `uv sync` so the `flow` entry point is installed

### Phase 3: Simplify conftest.py

- [x] Remove `pytest_addoption` (all CLI options: --flow, --mode, --montecarlo,
      --simulator, --fmt, --clean, --visual, --sim-server, --outdir)
- [x] Remove flow fixtures: `flow`, `mode`, `montecarlo`, `visual`, `sim_options`,
      `simulator`, `netlist_fmt`, `sim_server`, `check_simulator_avail`, `verbose`
- [x] Remove `print_summary_if_verbose`
- [x] Remove `resolve_outdir`, `clean_outdir`
- [x] Move `SIM_HOSTS`, `SIMULATOR_BINARIES`, and simulator availability check
      logic to `cli.py` (the `simulate` subcommand needs these)
- [x] Keep `set_pdk()`, `_resolve_pdk_module()`, `_reset_generator_caches()`,
      `_PDK_PACKAGES`, `list_pdks()`
- [x] Keep `pytest_configure` — just calls `set_pdk("ihp130")`
- [x] Keep `tech` fixture — returns `"ihp130"` (no CLI option)
- [x] Tests use pytest's built-in `tmp_path` instead of custom `outdir` fixture

### Phase 4: Clean up pyproject.toml

- [x] Update `python_files` for new test file locations (`test.py` files in
      block directories, `serialize.py` in layout)
- [x] Remove `mosfet.py`, `momcap.py` from `python_files`
      (no longer contain tests; `layout.py` kept — pdk/*/layout.py still has inline tests)
- [ ] Remove `addopts = ["-k", "not test_plot"]` once `test_plot.py` is fixed
      (optional, can keep for now)

---

## What the runners look like

### Runner in `flow/samp/testbench.py`

Variant sweep logic stays co-located with the testbench. All domain-specific
enums (`SwitchType`, `MosVth`) are used internally — never exposed to the CLI.

```python
# flow/samp/testbench.py

from pathlib import Path
from hdl21.primitives import MosVth

from .subckt import Samp, SampParams
from ..circuit import (
    SwitchType, select_variants, run_netlist_variants,
    run_simulations, get_param_axes, print_netlist_summary,
    wrap_monte_carlo,
)

# ... SampTb, SampTbParams, sim_input (unchanged) ...

def _build_variants():
    """Build the full sampler variant list."""
    return [
        SampParams(switch_type=st, w=w, l=l, vth=vth)
        for st in SwitchType
        for vth in [MosVth.LOW, MosVth.STD]
        for w in [2, 5, 10, 20, 40]
        for l in [1]
    ]


def run_netlist(tech: str, mode: str, montecarlo: bool,
                fmt: str, outdir: Path, verbose: bool = False) -> None:
    """Run sampler netlist generation."""
    variants = select_variants(_build_variants(), mode)

    def build_sim(p):
        tb_params = SampTbParams(samp=p)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return SampTb(tb_params), sim

    def build_dut(p):
        return Samp(p)

    wall_time = run_netlist_variants(
        "samp", variants, build_sim, outdir,
        simulator=fmt, netlist_fmt=fmt, build_dut=build_dut,
    )
    if verbose:
        print_netlist_summary(
            block="samp", pdk_name=tech, count=len(variants),
            param_axes=get_param_axes(variants),
            wall_time=wall_time, outdir=str(outdir),
        )


def run_simulate(tech: str, mode: str, montecarlo: bool,
                 simulator: str, sim_options, sim_server,
                 outdir: Path, verbose: bool = False) -> None:
    """Run sampler simulation."""
    variants = select_variants(_build_variants(), mode)

    def build_sim(p):
        tb_params = SampTbParams(samp=p)
        sim = sim_input(tb_params)
        if montecarlo:
            wrap_monte_carlo(sim)
        return SampTb(tb_params), sim

    wall_time, sims = run_netlist_variants(
        "samp", variants, build_sim, outdir,
        return_sims=True, simulator=simulator,
    )
    run_simulations(sims, sim_options, sim_server=sim_server)
```

### Runner in `flow/mosfet/primitive.py`

Layout enums (`L.MosType`, `L.MosVth`, `L.SourceTie`) stay internal to the
primitive module.

```python
# flow/mosfet/primitive.py

from pathlib import Path
import klayout.db as kdb
from ..layout.dsl import L, load_generic_layers
from ..layout.tech import load_dbu, load_rules_deck, remap_layers
from ..layout.serialize import export_layout
from ..layout.image import gds_to_png_with_pdk_style

# ... MosfetParams, mosfet generator (unchanged) ...

def run_layout(tech: str, mode: str, visual: bool, outdir: Path) -> None:
    """Run mosfet layout sweep."""
    from importlib import import_module

    pdk_module = import_module(f"pdk.{tech}.layout")
    tech_map = pdk_module.layer_map()

    if mode == "min":
        variants = [MosfetParams()]
    else:
        variants = [
            MosfetParams(
                mosfet_type=tp, mosfet_vth=vth, track_count=tracks,
                fing_count=fingers, wf_mult=wf, lf_mult=lf,
                source_tie=tie, powerrail_mult=pr,
            )
            for tp in (L.MosType.NMOS, L.MosType.PMOS)
            for vth in (L.MosVth.LOW, L.MosVth.REGULAR, L.MosVth.HIGH)
            for tracks in (9, 12)
            for fingers in (2, 4, 8)
            for wf in (1, 2, 3)
            for lf in (1, 2)
            for tie in (L.SourceTie.OFF, L.SourceTie.ON)
            for pr in (2, 3)
        ]

    for params in variants:
        layout = mosfet(params, tech)
        remap_layers(layout, tech_map)
        stem = (
            f"mos_t{params.mosfet_type.name.lower()}_"
            f"v{params.mosfet_vth.name.lower()}_"
            f"nf{params.fing_count}_w{params.wf_mult}_l{params.lf_mult}_"
            f"s{params.source_tie.name.lower()}_pr{params.powerrail_mult}"
        )
        artifacts = export_layout(
            layout=layout, out_dir=outdir, stem=stem,
            domain=f"frida.layout.{tech}", write_debug_gds=visual,
        )
        if visual and artifacts.gds is not None:
            gds_to_png_with_pdk_style(artifacts.gds, tech=tech, out_dir=outdir)
```

### Runner in `flow/comp/testbench.py`

All comparator-specific enums stay internal.

```python
# flow/comp/testbench.py

from pathlib import Path
from .subckt import Comp, CompParams, is_valid_comp_params
from ..circuit import (
    CompStages, LatchPwrgateCtl, LatchPwrgateNode,
    LatchRstExternCtl, LatchRstInternCtl, PreampBias, PreampDiffpair,
    select_variants, run_netlist_variants, run_simulations,
    get_param_axes, print_netlist_summary, wrap_monte_carlo,
)

# ... CompTb, CompTbParams, sim_input (unchanged) ...

def _build_variants():
    """Build the full comparator variant list."""
    preamp_diffpairs = list(PreampDiffpair)
    preamp_biases = list(PreampBias)
    comp_stages_list = list(CompStages)
    diffpair_w_list = [40, 80]

    variants = []
    for preamp_diffpair in preamp_diffpairs:
        for preamp_bias in preamp_biases:
            for comp_stages in comp_stages_list:
                for diffpair_w in diffpair_w_list:
                    if comp_stages == CompStages.SINGLE_STAGE:
                        params = CompParams(
                            preamp_diffpair=preamp_diffpair,
                            preamp_bias=preamp_bias,
                            comp_stages=comp_stages,
                            latch_pwrgate_ctl=LatchPwrgateCtl.CLOCKED,
                            latch_pwrgate_node=LatchPwrgateNode.EXTERNAL,
                            latch_rst_extern_ctl=LatchRstExternCtl.CLOCKED,
                            latch_rst_intern_ctl=LatchRstInternCtl.CLOCKED,
                            diffpair_w=diffpair_w,
                        )
                        if is_valid_comp_params(params):
                            variants.append(params)
                    else:
                        for latch_pwrgate_node in LatchPwrgateNode:
                            rst_extern = (
                                LatchRstExternCtl.NO_RESET
                                if latch_pwrgate_node == LatchPwrgateNode.INTERNAL
                                else LatchRstExternCtl.CLOCKED
                            )
                            params = CompParams(
                                preamp_diffpair=preamp_diffpair,
                                preamp_bias=preamp_bias,
                                comp_stages=comp_stages,
                                latch_pwrgate_ctl=LatchPwrgateCtl.CLOCKED,
                                latch_pwrgate_node=latch_pwrgate_node,
                                latch_rst_extern_ctl=rst_extern,
                                latch_rst_intern_ctl=LatchRstInternCtl.CLOCKED,
                                diffpair_w=diffpair_w,
                            )
                            if is_valid_comp_params(params):
                                variants.append(params)
    return variants


def run_netlist(tech: str, mode: str, montecarlo: bool,
                fmt: str, outdir: Path, verbose: bool = False) -> None:
    """Run comparator netlist generation."""
    variants = select_variants(_build_variants(), mode)
    # ... same pattern as samp ...


def run_simulate(tech: str, mode: str, montecarlo: bool,
                 simulator: str, sim_options, sim_server,
                 outdir: Path, verbose: bool = False) -> None:
    """Run comparator simulation."""
    # ... same pattern as samp ...
```

---

## What the CLI looks like

```python
# flow/cli.py — thin dispatcher (~80 lines)

import argparse
from pathlib import Path

try:
    import argcomplete
    HAS_ARGCOMPLETE = True
except ImportError:
    HAS_ARGCOMPLETE = False

from .conftest import set_pdk, list_pdks
# Note: circuit infrastructure accessed via flow.circuit (e.g. flow.circuit.sim)


def main():
    parser = argparse.ArgumentParser(prog="flow", description="FRIDA design flow runner")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── primitive ─────────────────────────────────────────
    p = sub.add_parser("primitive", help="Generate layout primitives")
    p.add_argument("-c", "--cell", required=True, choices=["mosfet", "momcap"])
    p.add_argument("-t", "--tech", default="ihp130", choices=list_pdks())
    p.add_argument("-m", "--mode", default="min", choices=["min", "max"])
    p.add_argument("-v", "--visual", action="store_true")
    p.add_argument("-o", "--out", default="scratch", type=Path)

    # ── netlist ───────────────────────────────────────────
    p = sub.add_parser("netlist", help="Generate netlists")
    p.add_argument("-c", "--cell", required=True, choices=["samp", "comp", "cdac", "adc"])
    p.add_argument("-t", "--tech", default="ihp130", choices=list_pdks())
    p.add_argument("-m", "--mode", default="min", choices=["min", "max"])
    p.add_argument("-f", "--fmt", default="spectre",
                   choices=["spectre", "ngspice", "yaml", "verilog"])
    p.add_argument("--montecarlo", action="store_true")
    p.add_argument("-o", "--out", default="scratch", type=Path)

    # ── simulate ──────────────────────────────────────────
    p = sub.add_parser("simulate", help="Run simulations")
    p.add_argument("-c", "--cell", required=True, choices=["samp", "comp", "cdac", "adc"])
    p.add_argument("-t", "--tech", default="ihp130", choices=list_pdks())
    p.add_argument("-m", "--mode", default="min", choices=["min", "max"])
    p.add_argument("-s", "--simulator", default="spectre",
                   choices=["spectre", "ngspice", "xyce"])
    p.add_argument("--host", default=None)
    p.add_argument("--montecarlo", action="store_true")
    p.add_argument("-o", "--out", default="scratch", type=Path)

    if HAS_ARGCOMPLETE:
        argcomplete.autocomplete(parser)

    args = parser.parse_args()
    set_pdk(args.tech)
    args.out.mkdir(parents=True, exist_ok=True)

    if args.command == "primitive":
        _run_primitive(args)
    elif args.command == "netlist":
        _run_netlist(args)
    elif args.command == "simulate":
        _run_simulate(args)


def _run_primitive(args):
    from importlib import import_module
    mod = import_module(f"flow.{args.cell}.primitive")
    mod.run_layout(tech=args.tech, mode=args.mode,
                   visual=args.visual, outdir=args.out)


def _run_netlist(args):
    from importlib import import_module
    mod = import_module(f"flow.{args.cell}.testbench")
    mod.run_netlist(tech=args.tech, mode=args.mode,
                    montecarlo=args.montecarlo, fmt=args.fmt,
                    outdir=args.out, verbose=True)


def _run_simulate(args):
    _check_simulator(args.simulator, args.host)
    from importlib import import_module
    mod = import_module(f"flow.{args.cell}.testbench")
    mod.run_simulate(tech=args.tech, mode=args.mode,
                     montecarlo=args.montecarlo, simulator=args.simulator,
                     sim_options=_make_sim_options(args),
                     sim_server=args.host, outdir=args.out, verbose=True)


def _check_simulator(simulator, host):
    import shutil, socket
    if host:
        return
    SIM_HOSTS = {"jupiter", "juno", "asiclab003"}
    SIMULATOR_BINARIES = {
        "spectre": ("spectre",),
        "ngspice": ("ngspice",),
        "xyce": ("Xyce", "xyce"),
    }
    hostname = socket.gethostname().split(".")[0].lower()
    if hostname not in SIM_HOSTS:
        hosts = ", ".join(sorted(SIM_HOSTS))
        raise SystemExit(
            f"Simulator unavailable: host '{hostname}' not in allow-list ({hosts})"
        )
    binaries = SIMULATOR_BINARIES[simulator]
    if not any(shutil.which(b) for b in binaries):
        raise SystemExit(f"Simulator binary '{simulator}' not found on PATH")


def _make_sim_options(args):
    from vlsirtools.spice import SupportedSimulators
    from .circuit.sim import get_sim_options
    sim = SupportedSimulators(args.simulator)
    return get_sim_options(rundir=args.out, simulator=sim)


if __name__ == "__main__":
    main()
```

---

## What smoke tests look like

Tests live in `test.py` inside each block directory. They test a single default
input with no fixtures from conftest (except `tmp_path` where needed).

```python
# flow/samp/test.py
from .subckt import Samp, SampParams

def test_samp():
    """Verify sampler generator produces a valid module."""
    m = Samp(SampParams())
    assert m is not None
    assert hasattr(m, "din")
    assert hasattr(m, "dout")
```

```python
# flow/comp/test.py
from .subckt import Comp, CompParams

def test_comp():
    """Verify comparator generator produces a valid module."""
    m = Comp(CompParams())
    assert m is not None
```

```python
# flow/cdac/test.py
import numpy as np
from .subckt import Cdac, CdacParams, get_cdac_weights

def test_cdac():
    """Verify CDAC generator produces a valid module."""
    m = Cdac(CdacParams())
    assert m is not None

def test_cdac_weights():
    """Test weight calculation for different strategies."""
    from ..circuit.params import RedunStrat
    params = CdacParams(n_dac=8, n_extra=0, redun_strat=RedunStrat.RDX2)
    weights = get_cdac_weights(params)
    assert len(weights) == 8
```

```python
# flow/adc/test.py
import numpy as np
from .subckt import Adc, AdcParams, get_adc_weights

def test_adc():
    """Verify ADC generator produces a valid module."""
    m = Adc(AdcParams())
    assert m is not None

def test_adc_weights():
    """Test ADC weight calculation."""
    params = AdcParams()
    weights = get_adc_weights(params)
    assert len(weights) == 16
    expected = np.array([768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1])
    np.testing.assert_array_equal(weights, expected)
```

```python
# flow/mosfet/test.py
def test_mosfet(tmp_path):
    """Verify mosfet generator produces valid layout."""
    from .primitive import mosfet, MosfetParams
    from ..layout.tech import remap_layers, load_layer_map
    from ..layout.serialize import export_layout

    layout = mosfet(MosfetParams(), "ihp130")
    remap_layers(layout, load_layer_map("ihp130"))
    artifacts = export_layout(layout, out_dir=tmp_path, stem="smoke",
                              domain="frida.layout.ihp130")
    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()
```

```python
# flow/momcap/test.py
def test_momcap(tmp_path):
    """Verify momcap generator produces valid layout."""
    from .primitive import momcap, MomcapParams
    from ..layout.tech import remap_layers, load_layer_map
    from ..layout.serialize import export_layout

    layout = momcap(MomcapParams(), "ihp130")
    remap_layers(layout, load_layer_map("ihp130"))
    artifacts = export_layout(layout, out_dir=tmp_path, stem="smoke",
                              domain="frida.layout.ihp130")
    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()
```

---

## What conftest.py becomes

```python
"""Pytest configuration for FRIDA tests."""

from importlib import import_module
from types import ModuleType

import hdl21 as h
import pytest

_PDK_PACKAGES = {
    "ihp130": "pdk.ihp130",
    "tsmc65": "pdk.tsmc65",
    "tsmc28": "pdk.tsmc28",
    "tower180": "pdk.tower180",
}

def list_pdks() -> list[str]:
    return list(_PDK_PACKAGES.keys())

def _resolve_pdk_module(name: str) -> ModuleType:
    if name not in _PDK_PACKAGES:
        available = ", ".join(list_pdks())
        raise ValueError(f"Unknown PDK '{name}'. Available: {available}")
    pkg = import_module(_PDK_PACKAGES[name])
    pdk_module = getattr(pkg, "pdk_logic", None)
    if pdk_module is None:
        raise RuntimeError(f"PDK package '{_PDK_PACKAGES[name]}' has no `pdk_logic`")
    return pdk_module

def _reset_generator_caches() -> None:
    try:
        from flow.samp.subckt import Samp
        from flow.samp.testbench import SampTb
        Samp.Cache.reset()
        SampTb.Cache.reset()
    except (ImportError, AttributeError):
        pass
    try:
        from flow.comp.subckt import Comp
        from flow.comp.testbench import CompTb
        Comp.Cache.reset()
        CompTb.Cache.reset()
    except (ImportError, AttributeError):
        pass
    try:
        from flow.cdac.subckt import Cdac
        from flow.cdac.testbench import CdacTb
        Cdac.Cache.reset()
        CdacTb.Cache.reset()
    except (ImportError, AttributeError):
        pass

def set_pdk(name: str) -> ModuleType:
    pdk_module = _resolve_pdk_module(name)
    h.pdk.set_default(pdk_module)
    _reset_generator_caches()
    return pdk_module

def pytest_configure(config):
    set_pdk("ihp130")

@pytest.fixture
def tech() -> str:
    return "ihp130"
```

---

## What `__init__.py` files become

```python
# flow/samp/__init__.py
from .subckt import Samp, SampParams
from .testbench import SampTb, SampTbParams, sim_input

__all__ = ["Samp", "SampParams", "SampTb", "SampTbParams", "sim_input"]
```

```python
# flow/comp/__init__.py
from .subckt import Comp, CompParams, is_valid_comp_params
from .testbench import CompTb, CompTbParams, sim_input

__all__ = ["Comp", "CompParams", "is_valid_comp_params",
           "CompTb", "CompTbParams", "sim_input"]
```

```python
# flow/mosfet/__init__.py
from .primitive import MosfetParams, mosfet

__all__ = ["MosfetParams", "mosfet"]
```

```python
# flow/momcap/__init__.py
from .primitive import MomcapParams, momcap

__all__ = ["MomcapParams", "momcap"]
```

```python
# flow/layout/__init__.py  (updated: remove mosfet/momcap re-exports)
from .dsl import (L, GenericLayers, MetalDraw, MosType, MosVth, Param,
                  SourceTie, generator, load_generic_layers, paramclass)
from .image import gds_to_png_with_pdk_style
from .serialize import (ExportArtifacts, TechArtifacts, export_layout,
                        layout_to_vlsir_raw, read_technology_proto,
                        vlsir_raw_to_disk, write_technology_proto)
from .tech import (LayerInfoData, LayerInfoMap, NewLayerRules, NewRuleDeck,
                   RelativeRules, load_dbu, load_layer_map,
                   load_rules_deck, remap_layers)
```

---

## File-by-file change summary

### New files

| File | Lines | Purpose |
|------|-------|---------|
| `flow/cli.py` | ~80 | Thin argparse dispatcher to per-module runners |
| `flow/samp/test.py` | ~10 | Smoke test for sampler |
| `flow/comp/test.py` | ~8 | Smoke test for comparator |
| `flow/cdac/test.py` | ~15 | Smoke test + weight test for CDAC |
| `flow/adc/test.py` | ~15 | Smoke test + weight test for ADC |
| `flow/mosfet/__init__.py` | ~5 | Package init |
| `flow/mosfet/test.py` | ~15 | Smoke test for mosfet layout |
| `flow/momcap/__init__.py` | ~5 | Package init |
| `flow/momcap/test.py` | ~15 | Smoke test for momcap layout |

### Renamed + modified files

| Before | After | What changes |
|--------|-------|--------------|
| `flow/samp/samp.py` | `flow/samp/subckt.py` | Rename only |
| `flow/samp/test_samp.py` | `flow/samp/testbench.py` | Remove `test_samp_flow`, add `run_netlist()`, `run_simulate()`, update import to `.subckt` |
| `flow/comp/comp.py` | `flow/comp/subckt.py` | Rename only |
| `flow/comp/test_comp.py` | `flow/comp/testbench.py` | Remove `test_comp_flow`, add `run_netlist()`, `run_simulate()`, update import to `.subckt` |
| `flow/cdac/cdac.py` | `flow/cdac/subckt.py` | Rename only |
| `flow/cdac/test_cdac.py` | `flow/cdac/testbench.py` | Remove `test_cdac_flow`, `test_cdac_weights`, add `run_netlist()`, `run_simulate()`, update import to `.subckt` |
| `flow/adc/adc.py` | `flow/adc/subckt.py` | Rename only |
| `flow/adc/test_adc.py` | `flow/adc/testbench.py` | Remove `test_adc_flow`, `test_adc_weights`, add `run_netlist()`, `run_simulate()`, update import to `.subckt` |
| `flow/layout/mosfet.py` | `flow/mosfet/primitive.py` | Remove `test_mosfet`, add `run_layout()`, update imports |
| `flow/layout/momcap.py` | `flow/momcap/primitive.py` | Remove `test_momcap`, add `run_layout()`, update imports |

### Modified files (in place)

| File | What changes |
|------|--------------|
| `flow/conftest.py` | Strip all CLI options and flow fixtures (~200 lines removed, ~40 remain) |
| `flow/samp/__init__.py` | Update imports: `.subckt`, `.testbench` |
| `flow/comp/__init__.py` | Update imports: `.subckt`, `.testbench` |
| `flow/cdac/__init__.py` | Update imports: `.subckt`, `.testbench` |
| `flow/adc/__init__.py` | Update imports: `.subckt`, `.testbench` |
| `flow/layout/__init__.py` | Remove mosfet/momcap re-exports |
| `pyproject.toml` | Add `[project.scripts]`, update `python_files` |

### Untouched files

All pure unit tests stay exactly as they are:
- `flow/circuit/test_measure.py` (~40 tests)
- `flow/circuit/test_netlist.py` (~4 tests)
- `flow/circuit/test_params.py` (~1 test)
- `flow/circuit/test_plot.py` (~23 tests, skipped for now)
- `flow/layout/tech.py` (inline `test_rule_deck`, `test_remap_layers`)
- `flow/layout/serialize.py` (inline `test_serialize`)
- `pdk/test_supply_rails.py` (~3 tests)

All shared infrastructure — `flow/circuit/*.py`, `flow/layout/dsl.py`,
`flow/layout/tech.py`, `flow/layout/serialize.py`, `flow/layout/image.py`,
PDK code — untouched.

---

## CLI API

### `flow primitive`

```
flow primitive -c mosfet
flow primitive -c mosfet -t tsmc65 -m max -v
flow primitive -c momcap -t ihp130 -o scratch/layout
```

| Short | Long | Default | Choices |
|-------|------|---------|---------|
| `-c` | `--cell` | required | `mosfet`, `momcap` |
| `-t` | `--tech` | `ihp130` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` |
| `-m` | `--mode` | `min` | `min`, `max` |
| `-v` | `--visual` | off | flag |
| `-o` | `--out` | `scratch` | path |

### `flow netlist`

```
flow netlist -c samp
flow netlist -c comp -t tsmc28 -m max -f ngspice
flow netlist -c adc --montecarlo
```

| Short | Long | Default | Choices |
|-------|------|---------|---------|
| `-c` | `--cell` | required | `samp`, `comp`, `cdac`, `adc` |
| `-t` | `--tech` | `ihp130` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` |
| `-m` | `--mode` | `min` | `min`, `max` |
| `-f` | `--fmt` | `spectre` | `spectre`, `ngspice`, `yaml`, `verilog` |
| | `--montecarlo` | off | flag |
| `-o` | `--out` | `scratch` | path |

### `flow simulate`

```
flow simulate -c samp
flow simulate -c comp -s spectre --host jupiter
```

| Short | Long | Default | Choices |
|-------|------|---------|---------|
| `-c` | `--cell` | required | `samp`, `comp`, `cdac`, `adc` |
| `-t` | `--tech` | `ihp130` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` |
| `-m` | `--mode` | `min` | `min`, `max` |
| `-s` | `--simulator` | `spectre` | `spectre`, `ngspice`, `xyce` |
| | `--host` | none | `host[:port]` |
| | `--montecarlo` | off | flag |
| `-o` | `--out` | `scratch` | path |

---

## Design decisions

### Runners live in each module, not in cli.py

Each `testbench.py` (or `primitive.py`) owns its variant sweep logic and all
domain-specific enums. The CLI never imports enums like `L.MosType`,
`SwitchType`, `PreampDiffpair`, etc.

| Aspect | Runners in modules (chosen) | Everything in cli.py (rejected) |
|--------|----------------------------|--------------------------------|
| Where enums are used | Each module uses its own enums internally | cli.py imports every enum from every module |
| cli.py size | ~80 lines, pure argparse + dispatch | ~250 lines, knows every sweep loop |
| Adding a new cell | Add `run_*()` to the new module, add 2 lines to cli.py | Edit cli.py sweep logic + choices |
| Where sweep knowledge lives | Co-located with the generator/testbench | Centralized in cli.py |
| CLI's job | Parse args + dispatch + check simulators | Parse args + run sweeps + check simulators |

### Files named by role, not by block

Since the directory provides block identity, files use generic role names:

- `subckt.py` — the device under test (SPICE naming convention)
- `testbench.py` — wraps the DUT for simulation
- `primitive.py` — layout generator for physical cells
- `test.py` — pytest smoke test

This means function names are also generic: `run_netlist()`, `run_simulate()`,
`run_layout()`. The call site reads naturally:
`from flow.comp.testbench import run_netlist`.

### Smoke tests are separate files

Tests are extracted from `testbench.py` / `primitive.py` into dedicated
`test.py` files. This means testbench modules contain zero pytest functions,
so pytest discovery is clean, and the test/runner boundary is unambiguous.

---

## Migration order

Each phase is independently committable and testable.

1. **Restructure modules** — rename files, move sweep logic into runners,
   create smoke tests, update `__init__.py` files → `uv run pytest` still
   passes
2. **Create CLI** — `flow/cli.py` + `pyproject.toml` entry point →
   `flow --help` works, `flow netlist -c samp` runs
3. **Simplify conftest.py** — strip CLI options and flow fixtures → cleaner,
   no unused fixtures
4. **Clean up pyproject.toml** — update `python_files`, remove stale entries