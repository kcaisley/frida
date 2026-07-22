## SiliconCompiler Workflows

Use SiliconCompiler as the source of truth for digital build orchestration whenever possible: filesets, flows, PDK selection, job names, build directories, metrics, manifests, and generated artifacts should live in the SC schema. Add custom tasks only where SC does not provide the needed behavior, such as HDL21 analog netlist generation or FRIDA-specific analog measurement checks.

For unit-level digital targets, prefer one `flow/sc/<block>.py` file per design variant. Public functions in that file are selectable `smake` targets; private helpers and project classes are implementation details.

Current SPI examples:

```bash
uv run smake -f flow/sc/spi.py sim
uv run smake -f flow/sc/spi.py syn
uv run smake -f flow/sc/spi.py asic

uv run smake -f flow/sc/frida_spi.py sim
uv run smake -f flow/sc/frida_spi.py syn
uv run smake -f flow/sc/frida_spi.py asic
```

Direct execution is only the fixed/default path for a file. For example:

```bash
uv run python -m flow.sc.spi
uv run python flow/sc/spi.py
```

currently runs the file's default `sim()` target. Use `smake` when selecting among multiple simulations/builds in the same file.

`smake` in the installed SiliconCompiler version selects files with `-f/--file`; it does not natively accept dotted module names. If dotted names are desired later, add only a thin FRIDA wrapper that resolves a module to a file and delegates to `smake`, rather than replacing SC's target-discovery model.

Generated outputs from SC runs should go under `build/`, which is ignored. Do not commit SC build products, screenshots, VCDs, coverage files, simulator logs, or Python caches.
