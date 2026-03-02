# Conftest Cleanup Plan

## Problem

`flow/conftest.py` currently holds two unrelated things:

1. **PDK infrastructure** — `set_pdk()`, `list_pdks()`, `_resolve_pdk_module()`,
   `_PDK_PACKAGES`, `_reset_generator_caches()`. These are general-purpose
   functions used by both the CLI (`flow/cli.py`) and pytest. Having the CLI
   import from `conftest.py` is a code smell — conftest is a pytest mechanism,
   not a library module.

2. **Pytest wiring** — `pytest_configure()` hook and the `tech` fixture.

Additionally, the `tech` fixture is dead code (no test uses it), and
`pdk/__init__.py` already has a parallel `_KNOWN_PDKS` tuple that duplicates
the same information as `_PDK_PACKAGES`.

## Current state of `flow/conftest.py` (81 lines)

| Component | Lines | Used by tests? | Used by CLI? | Purpose |
|---|---|---|---|---|
| `_PDK_PACKAGES` | 9–14 | Indirectly (via `set_pdk`) | Yes (`list_pdks`) | Map short names → importable packages |
| `list_pdks()` | 17–19 | No | Yes (argparse choices) | Return PDK name list |
| `_resolve_pdk_module()` | 22–32 | Indirectly (via `set_pdk`) | Indirectly | Import PDK and extract `pdk_logic` |
| `_reset_generator_caches()` | 35–57 | No (defensive only) | No | Clear hdl21 generator caches after PDK switch |
| `set_pdk()` | 65–70 | Indirectly (`pytest_configure`) | Yes | Resolve + set default + reset caches |
| `pytest_configure()` | 73–75 | Yes (4 generator smoke tests need PDK set) | No | Pytest hook |
| `tech` fixture | 78–80 | **No — dead code** | No | Returns `"ihp130"` |

## Call graph analysis

```
cli.py ──→ list_pdks()           (3× for argparse choices)
cli.py ──→ set_pdk()             (1× before dispatch)
conftest.py pytest_configure ──→ set_pdk()

set_pdk()
├── _resolve_pdk_module()   ← only caller
└── _reset_generator_caches()  ← only caller

_resolve_pdk_module()
└── list_pdks()              (1× for error message)
```

`_resolve_pdk_module()` and `_reset_generator_caches()` are private
single-caller helpers — their only caller is `set_pdk()`. They should be
inlined into `set_pdk()` rather than kept as separate functions.

## What breaks if each component is removed

| Component | Tests that break | CLI breaks? | Safe to remove today? |
|---|---|---|---|
| `_PDK_PACKAGES` | 4 generator smoke tests (no PDK → `h.Mos` fails) | Yes | No — move it |
| `list_pdks()` | None | Yes (no choices for `--tech`) | No — move it |
| `_resolve_pdk_module()` | 4 generator smoke tests | Yes | Inline into `set_pdk` |
| `_reset_generator_caches()` | None (only matters for multi-PDK in one process) | No | Inline into `set_pdk` |
| `set_pdk()` | 4 generator smoke tests (via `pytest_configure`) | Yes | No — move it |
| `pytest_configure()` | 4 generator smoke tests | No | No — keep in conftest |
| `tech` fixture | **None** | No | **Yes — delete** |

### Key discovery

All 96 tests pass with a completely empty `conftest.py`. None of the current
tests actually need `set_pdk("ihp130")` to be called. The generators work
fine without a PDK set — hdl21 doesn't need a PDK at generation time, only at
compile time (when converting `h.Mos` to PDK-specific devices). The smoke
tests only call generators; they never netlist or compile. The layout tests
pass the tech name as an explicit string parameter. So both
`pytest_configure` and the `tech` fixture were dead code.

## Proposed changes

### 1. Create `flow/pdks.py` — shared PDK infrastructure

Move all the non-pytest code into a new module that `cli.py` can import.
Inline the two private helpers into `set_pdk()`.

The module exports exactly two public functions:

- `list_pdks()` — returns the list of PDK short names
- `set_pdk(name)` — resolves, sets, and cache-resets in one call

The cache reset keeps an explicit list of `(module_path, class_name)` pairs
rather than scanning with `dir()`:

```python
_CACHED_GENERATORS: list[tuple[str, str]] = [
    ("flow.samp.subckt", "Samp"),
    ("flow.samp.testbench", "SampTb"),
    ("flow.comp.subckt", "Comp"),
    ("flow.comp.testbench", "CompTb"),
    ("flow.cdac.subckt", "Cdac"),
    ("flow.cdac.testbench", "CdacTb"),
]
```

This is clearer and avoids importing names that don't need cache resets.

### 2. Delete `flow/conftest.py` entirely

Since no test depends on `pytest_configure` calling `set_pdk("ihp130")`,
and the `tech` fixture is unused, there is nothing left to keep. The file
is deleted rather than slimmed down.

If a future test needs a PDK set, the author can either call `set_pdk()`
explicitly in their test/fixture, or re-introduce a minimal conftest at
that point.

### 3. Update `flow/cli.py` import

Change:
```python
from .conftest import list_pdks, set_pdk
```
To:
```python
from .pdks import list_pdks, set_pdk
```

### 4. Consider consolidating with `pdk/__init__.py` (future)

`pdk/__init__.py` already has:
- `_KNOWN_PDKS = ("ihp130", "tsmc65", "tsmc28", "tower180")`
- `_resolve_tech_name()` — similar to the resolve logic but different API
- `_install_class()` — imports `pdk.{tech}.pdk_logic`

There's clear duplication. A future cleanup could merge `_PDK_PACKAGES` with
`_KNOWN_PDKS`, but that crosses the `flow/` ↔ `pdk/` package boundary and
may introduce circular imports (flow imports pdk, pdk layout files import
flow.layout). That's a separate investigation — this plan keeps the scope
small by staying within `flow/`.

## Task Checklist

- [x] Create `flow/pdks.py` with `_PDK_PACKAGES`, `list_pdks()`, and
      `set_pdk()` (with resolve + cache reset inlined)
- [x] Update `flow/cli.py`: change `from .conftest import` → `from .pdks import`
- [x] Delete `flow/conftest.py` entirely (no test depends on it)
- [x] Run `uv run pytest` — 96 passed, 23 deselected ✓
- [x] Run `uv run flow netlist -c samp` — works, 10 netlists generated ✓
- [x] Run `uv run ruff check flow/` — clean ✓

## Final file changes

| File | Before | After |
|------|--------|-------|
| `flow/pdks.py` | (new) | ~69 lines |
| `flow/conftest.py` | 81 lines | deleted |
| `flow/cli.py` | 160 lines | 160 lines (1 import line changed) |
| **Net change** | | −12 lines |