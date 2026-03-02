# CLI Migration Plan

## Goal

Separate the **flow runner** (variant sweeps, netlist generation, simulation,
layout generation) from **tests** (unit/integration assertions that verify
correctness with a single default input).

- `flow` CLI (`flow/cli.py`) — runs design flows with variant sweeps.
- `uv run pytest` — fast, no-flags-needed correctness checks.

After migration:

```
flow primitive --cell mosfet --tech ihp130 --mode max --visual
flow netlist --cell samp --tech ihp130 --mode max
flow simulate --cell comp --simulator spectre --sim-server jupiter
```

```
uv run pytest          # ~70+ tests, all pass, no flags needed
```

---

## Task Checklist

### Phase 1: Create CLI

- [ ] Create `flow/cli.py` with argparse
  - [ ] `netlist` subcommand (--cell, --tech, --mode, --fmt, --montecarlo, --outdir)
  - [ ] `simulate` subcommand (--cell, --tech, --mode, --simulator, --sim-server, --montecarlo, --outdir),
        including simulator availability check (host allow-list + binary probe) and `print_netlist_summary`
  - [ ] `primitive` subcommand (--cell, --tech, --mode, --visual, --outdir)
  - [ ] Variant sweep logic for each cell lives directly in `cli.py` (translated from current test_*_flow functions)
- [ ] Add `[project.scripts] flow = "flow.cli:main"` to `pyproject.toml`
- [ ] Run `uv sync` so the `flow` entry point is installed

### Phase 2: Simplify test functions

Test functions stay in their current files but are simplified to test a single
default input — no sweep loops, no CLI fixtures.

- [ ] `test_samp_flow` → `test_samp`: call `Samp(SampParams())`, assert module created
- [ ] `test_comp_flow` → `test_comp`: call `Comp(CompParams())`, assert module created
- [ ] `test_cdac_flow` → `test_cdac`: call `Cdac(CdacParams())`, assert valid, check weights
- [ ] `test_adc_flow` → `test_adc`: call `Adc(AdcParams())`, assert module created
- [ ] `test_mosfet` in `mosfet.py`: simplify to single `MosfetParams()`, assert layout valid
- [ ] `test_momcap` in `momcap.py`: simplify to single `MomcapParams()`, assert layout valid
- [ ] `test_serialize` in `serialize.py`: change `outdir` fixture to `tmp_path`
- [ ] Remove `@pytest.mark.usefixtures("check_simulator_avail")` from all tests
- [ ] Remove all fixture parameters (`flow`, `mode`, `montecarlo`, `verbose`,
      `tech`, `simulator`, `netlist_fmt`, `sim_options`, `sim_server`) from test signatures

### Phase 3: Simplify conftest.py

- [ ] Remove `pytest_addoption` (all CLI options: --flow, --mode, --montecarlo,
      --simulator, --fmt, --clean, --visual, --sim-server, --outdir)
- [ ] Remove flow fixtures: `flow`, `mode`, `montecarlo`, `visual`, `sim_options`,
      `simulator`, `netlist_fmt`, `sim_server`, `check_simulator_avail`, `verbose`
- [ ] Remove `print_summary_if_verbose`
- [ ] Remove `resolve_outdir`, `clean_outdir`
- [ ] Move `SIM_HOSTS`, `SIMULATOR_BINARIES`, and simulator availability check
      logic to `cli.py` (the `simulate` subcommand needs these)
- [ ] Keep `set_pdk()`, `_resolve_pdk_module()`, `_reset_generator_caches()`,
      `_PDK_PACKAGES`, `list_pdks()`
- [ ] Keep `pytest_configure` — just calls `set_pdk("ihp130")`
- [ ] Keep `tech` fixture — returns `"ihp130"` (no CLI option)
- [ ] Keep or add `outdir` fixture backed by pytest's `tmp_path`

### Phase 4: Clean up pyproject.toml

- [ ] Keep `mosfet.py`, `momcap.py`, `serialize.py` in `python_files`
      (they still contain inline test functions that pytest needs to discover)
- [ ] Remove `layout.py` from `python_files` (no longer contains tests)
- [ ] Remove `addopts = ["-k", "not test_plot"]` once `test_plot.py` is fixed
      (optional, can keep for now)

---

## File-by-file change summary

### New files

| File | Lines | Purpose |
|------|-------|---------|
| `flow/cli.py` | ~250 | argparse CLI with variant sweep logic from current test_*_flow functions |

### Modified files

| File | Remove | Add | What changes |
|------|--------|-----|--------------|
| `flow/conftest.py` | ~200 | ~40 | Strip all CLI options and flow fixtures |
| `flow/samp/test_samp.py` | ~80 | ~8 | Replace `test_samp_flow` with single-input `test_samp` |
| `flow/comp/test_comp.py` | ~110 | ~8 | Replace `test_comp_flow` with single-input `test_comp` |
| `flow/cdac/test_cdac.py` | ~90 | ~8 | Replace `test_cdac_flow` with single-input `test_cdac` |
| `flow/adc/test_adc.py` | ~80 | ~8 | Replace `test_adc_flow` with single-input `test_adc` |
| `flow/layout/mosfet.py` | ~55 | ~12 | Replace sweep `test_mosfet` with single-input smoke test |
| `flow/layout/momcap.py` | ~50 | ~12 | Replace sweep `test_momcap` with single-input smoke test |
| `flow/layout/serialize.py` | ~2 | ~2 | Change `outdir` fixture to `tmp_path` |
| `pyproject.toml` | ~1 | ~3 | Add `[project.scripts]` |

### Untouched files

All pure unit tests stay exactly as they are:
- `flow/flow/test_measure.py` (~40 tests)
- `flow/flow/test_netlist.py` (~4 tests)
- `flow/flow/test_params.py` (~1 test)
- `flow/flow/test_plot.py` (~23 tests, skipped for now)
- `flow/layout/tech.py` (inline `test_rule_deck`, `test_remap_layers`)
- `pdk/test_supply_rails.py` (~3 tests)

All generator functions, testbench generators, `sim_input()` functions, flow
helpers, PDK code — untouched.

### Estimated totals

- ~665 lines removed
- ~310 lines added
- Net: **~355 lines removed**

---

## CLI API

### `flow primitive`

```
flow primitive --cell mosfet
flow primitive --cell mosfet --tech tsmc65 --mode max --visual
flow primitive --cell momcap --tech ihp130 --outdir scratch/layout
```

| Flag | Default | Choices |
|------|---------|---------|
| `--cell` | required | `mosfet`, `momcap` |
| `--tech` | `ihp130` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` |
| `--mode` | `min` | `min`, `max` |
| `--visual` | off | flag |
| `--outdir` | `scratch` | path |

### `flow netlist`

```
flow netlist --cell samp
flow netlist --cell comp --tech tsmc28 --mode max --fmt ngspice
flow netlist --cell adc --montecarlo
```

| Flag | Default | Choices |
|------|---------|---------|
| `--cell` | required | `samp`, `comp`, `cdac`, `adc` |
| `--tech` | `ihp130` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` |
| `--mode` | `min` | `min`, `max` |
| `--fmt` | `spectre` | `spectre`, `ngspice`, `yaml`, `verilog` |
| `--montecarlo` | off | flag |
| `--outdir` | `scratch` | path |

### `flow simulate`

```
flow simulate --cell samp
flow simulate --cell comp --simulator spectre --sim-server jupiter
```

| Flag | Default | Choices |
|------|---------|---------|
| `--cell` | required | `samp`, `comp`, `cdac`, `adc` |
| `--tech` | `ihp130` | `ihp130`, `tsmc65`, `tsmc28`, `tower180` |
| `--mode` | `min` | `min`, `max` |
| `--simulator` | `spectre` | `spectre`, `ngspice`, `xyce` |
| `--sim-server` | none | `host[:port]` |
| `--montecarlo` | off | flag |
| `--outdir` | `scratch` | path |

---

## Design decisions

### Variant sweep logic lives in cli.py

The sweep loops currently in `test_samp_flow`, `test_comp_flow`, etc. are
translated directly into `cli.py` subcommand handlers. Each handler defines its
own variant list and calls the existing `run_netlist_variants()` /
`run_simulations()` helpers. This keeps variant definitions discoverable in one
file and out of tests.

Example — samp netlist handler in `cli.py`:

```python
def _netlist_samp(args):
    from flow.samp.samp import Samp, SampParams
    from flow.samp.test_samp import SampTb, SampTbParams, sim_input
    from flow.flow import run_netlist_variants, select_variants, ...

    variants = [
        SampParams(switch_type=st, w=w, l=l, vth=vth)
        for st in SwitchType
        for vth in [MosVth.LOW, MosVth.STD]
        for w in [2, 5, 10, 20, 40]
        for l in [1]
    ]
    variants = select_variants(variants, args.mode)

    def build_sim(p):
        tb_params = SampTbParams(samp=p)
        return SampTb(tb_params), sim_input(tb_params)

    def build_dut(p):
        return Samp(p)

    run_netlist_variants("samp", variants, build_sim, args.outdir, ...)
```

Example — mosfet primitive handler in `cli.py`:

```python
def _primitive_mosfet(args):
    from flow.layout.mosfet import mosfet, MosfetParams
    from flow.layout.dsl import L
    from flow.layout.tech import remap_layers
    from flow.layout.serialize import export_layout

    pdk_module = import_module(f"pdk.{args.tech}.layout")
    tech_map = pdk_module.layer_map()

    if args.mode == "min":
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
        layout = mosfet(params, args.tech)
        remap_layers(layout, tech_map)
        artifacts = export_layout(layout, out_dir=args.outdir, stem=..., ...)
```

### What simplified tests look like

Tests stay in their current files. They test a single default input with no
fixtures from conftest (except `tmp_path` where needed).

```python
# flow/samp/test_samp.py
def test_samp():
    """Verify sampler generator produces a valid module."""
    m = Samp(SampParams())
    assert m is not None
    assert hasattr(m, "din")
    assert hasattr(m, "dout")
```

```python
# flow/layout/mosfet.py (inline, stays in place)
def test_mosfet(tmp_path):
    """Verify mosfet generator produces valid layout."""
    from .tech import remap_layers, load_layer_map
    from .serialize import export_layout

    layout = mosfet(MosfetParams(), "ihp130")
    remap_layers(layout, load_layer_map("ihp130"))
    artifacts = export_layout(layout, out_dir=tmp_path, stem="smoke")
    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()
```

```python
# flow/layout/momcap.py (inline, stays in place)
def test_momcap(tmp_path):
    """Verify momcap generator produces valid layout."""
    from .tech import remap_layers, load_layer_map
    from .serialize import export_layout

    layout = momcap(MomcapParams(), "ihp130")
    remap_layers(layout, load_layer_map("ihp130"))
    artifacts = export_layout(layout, out_dir=tmp_path, stem="smoke")
    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()
```

### What conftest.py becomes

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

def set_pdk(name: str) -> ModuleType:
    pkg = import_module(_PDK_PACKAGES[name])
    pdk_module = pkg.pdk_logic
    h.pdk.set_default(pdk_module)
    return pdk_module

def pytest_configure(config):
    set_pdk("ihp130")

@pytest.fixture
def tech() -> str:
    return "ihp130"
```

---

## Migration order

Each phase is independently committable and testable. Phases 1 and 2 can be
done in parallel since they don't conflict.

1. Create `flow/cli.py` + `pyproject.toml` entry point → `flow --help` works
2. Simplify test functions → `uv run pytest` still passes, faster
3. Strip `conftest.py` → cleaner, no unused fixtures
4. Clean up `pyproject.toml`
