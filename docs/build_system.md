# Build system notes

- Linting
- Formatting
- Source file management
- Build target file grouping
- Yosys synthesis
- Verilator simulation
- Icarus simulation
- OpenROAD place and route with standard and customized scripts
- cocotb testbenches
- HDL21 SPICE netlist generation
- HDL21-generated SPICE testbench simulation

## Current SiliconCompiler structure

FRIDA should use SiliconCompiler as the build-system source of truth wherever the task fits SiliconCompiler's model. The project schema should own source files, filesets, PDK selection, flows, job names, build directories, metrics, manifests, and generated artifacts. Custom Python should be limited to functionality SiliconCompiler does not provide directly, such as HDL21 analog netlist generation, SPICE result parsing, and FRIDA-specific analog spec checks.

The current SPI migration is the reference pattern for unit-level digital blocks:

| File | Design variant | Intended entry points |
|---|---|---|
| `flow/sc/spi.py` | behavioral `design/hdl/spi.v` implementation | `sim`, `syn`, `asic` |
| `flow/sc/frida_spi.py` | explicit generated flip-flop / `OPENROAD_*` implementation in `design/hdl/frida_spi.v` | `sim`, `syn`, `asic` |

Use SiliconCompiler's `smake` app for selecting these entry points. `smake` is the installed SiliconCompiler make-like command runner; it discovers public functions in a Python file and exposes them as target subcommands. This is a better fit than parsing ad-hoc positional modes in each file. In this SiliconCompiler version, `smake` selects files with `--file`; if FRIDA wants dotted module names such as `flow.sc.spi sim`, add only a thin package wrapper that resolves the module to a file and then delegates to `smake`, rather than replacing SiliconCompiler's target-discovery model.

```sh
uv run smake --file flow/sc/spi.py sim
uv run smake --file flow/sc/spi.py syn
uv run smake --file flow/sc/spi.py asic

uv run smake --file flow/sc/frida_spi.py sim
uv run smake --file flow/sc/frida_spi.py syn
uv run smake --file flow/sc/frida_spi.py asic
```

Public functions are selectable targets. Private helpers and project classes are implementation details:

```python
__scdefault = "sim"

class SpiDesign(Design):
    ...

class SpiSimProject(Sim):
    ...

class SpiIhp130Project(ASIC):
    ...


def sim(jobname: str = "sim", remote: bool = False) -> None:
    ...


def syn(jobname: str = "ihp130", remote: bool = False) -> None:
    ...


def asic(jobname: str = "ihp130", remote: bool = False, screenshot: bool = True) -> None:
    ...
```

This gives the desired integration behavior: one file can define many named simulations or builds, but only the selected target runs. For example, future blocks can add `sim_reset`, `sim_randomized`, `sim_post_synth`, `syn`, `asic`, or `analog_characterize` functions without forcing all of them to execute.

The underlying SiliconCompiler projects still follow the schema model. The selected function constructs a `Design` plus a `Sim` or `ASIC` project, adds the required filesets, sets the flow, runs, summarizes, and writes normal `.pkg.json` manifests and `reports/metrics.json` files under `build/<design>/<jobname>/<step>/<index>/`.

Current SPI fileset convention:

| Fileset | Used by | Contents |
|---|---|---|
| `rtl` | synthesis / ASIC | DUT RTL only, with top module `spi_register`; for `frida_spi`, this includes the selected PDK wrapper provider `cells_ihp_sg13g2.v` |
| `rtl.sim` | cocotb simulation / lint | DUT plus Verilog testbench wrapper; for `frida_spi`, this includes technology-independent `cells_behavioral.v` |
| `sdc` | synthesis / ASIC | timing constraints in `design/constraints/spi_register.sdc` |
| `testbench.cocotb` | simulation | Python cocotb tests |

Current SPI validation status:

- `sim` passes cocotb unit tests for both the behavioral and explicit-cell SPI implementations.
- `syn` passes IHP130 Yosys/OpenSTA synthesis for both implementations.
- `asic` runs IHP130 OpenROAD through detailed route for both implementations and generates report images under `reports/images/`.
- The installed IHP130 target currently fails in the optional metal-fill/GDS tail, so the SPI `asic` target intentionally stops at `route.detailed`. This is a local target limitation, not an RTL limitation.
- These runs validate pre-synthesis behavior and buildability. They do not yet prove synthesized-netlist or post-route functional equivalence.

Recommended next integration step: add post-synthesis gate-level simulation targets for both SPI implementations. Those targets should reuse the existing cocotb tests against the synthesized netlists:

```text
build/spi/ihp130/synthesis/0/outputs/spi_register.vg
build/frida_spi/ihp130/synthesis/0/outputs/spi_register.vg
```

After that, use the same pattern for the next digital block: one `flow/sc/<block>.py` file, public `smake` target functions for each simulation/build configuration, schema-backed filesets, and custom tasks only where SiliconCompiler has no built-in support.

## Linting and formatting

SiliconCompiler has a specialized `Lint` project class. [project.py#L1462](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/project.py#L1462)

SiliconCompiler has a predefined `LintFlow`. [lintflow.py#L8](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/flows/lintflow.py#L8)

`LintFlow` supports `slang` and `verilator`. [lintflow.py#L14](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/flows/lintflow.py#L14)

`LintFlow(tool="verilator")` creates a Verilator lint node. [lintflow.py#L36](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/flows/lintflow.py#L36)

The Verilator lint task adds `--lint-only` and `--no-timing`. [verilator/lint.py#L8](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/verilator/lint.py#L8)

The Verilator driver always enables SystemVerilog parsing with `-sv`. [verilator/__init__.py#L81](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/verilator/__init__.py#L81)

The Verilator driver records warnings and errors as metrics. [verilator/__init__.py#L38](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/verilator/__init__.py#L38)

The Verilator driver consumes filesets, include directories, defines, parameters, command files, Verilog, and SystemVerilog sources from the project schema. [verilator/__init__.py#L59](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/verilator/__init__.py#L59), [verilator/__init__.py#L103](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/verilator/__init__.py#L103), [verilator/__init__.py#L138](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/verilator/__init__.py#L138)

SiliconCompiler documentation includes `LintFlow` as a predefined flow. [flows.rst#L49](file:///home/kcaisley/libs/siliconcompiler/docs/reference_manual/predef_modules/flows.rst#L49)

SiliconCompiler examples run linting with `Lint()` and `LintFlow()`. [picorv32/make.py#L83](file:///home/kcaisley/libs/siliconcompiler/docs/user_guide/tutorials/examples/picorv32/make.py#L83)

SiliconCompiler tests verify that Verilator lintflow reports zero errors and zero warnings on a passing design. [test_verilator.py#L171](file:///home/kcaisley/libs/siliconcompiler/tests/tools/test_verilator.py#L171)

No built-in SiliconCompiler Verible tool task was found under `siliconcompiler/tools`. Verible is present as install support and as SiliconCompiler’s own repository CI lint/format tool. [lint.yml#L40](file:///home/kcaisley/libs/siliconcompiler/.github/workflows/lint.yml#L40), [_tools.json#L136](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/toolscripts/_tools.json#L136)

SiliconCompiler’s own repository checks Verible formatting by running `verible-verilog-format --inplace` and then requiring a clean git diff. [format_verilog.sh#L28](file:///home/kcaisley/libs/siliconcompiler/.github/workflows/bin/format_verilog.sh#L28), [lint.yml#L45](file:///home/kcaisley/libs/siliconcompiler/.github/workflows/lint.yml#L45)

SiliconCompiler’s own repository runs Verible lint directly in CI with `verible-verilog-lint --rules_config`. [lint.yml#L52](file:///home/kcaisley/libs/siliconcompiler/.github/workflows/lint.yml#L52)

Finding: Verilator lint is first-class in SiliconCompiler. Verible lint/format is not first-class in the checked source tree; it would need direct CI commands or a small custom SiliconCompiler task.

FRIDA should aim for 100% passing Verilator and Verible checks by separating ordinary digital RTL from AMS-only support files, rather than by adding broad lint waivers. Verilator/Verible should lint the synthesizable digital files and lint-compatible stubs; Xcelium-only probe modules and simulator-specific AMS glue should live in separate filesets and should not be included in the Verilator lint flow.

Digital RTL style:

- Keep structural Verilog modules in the current `wire`/`reg` style unless there is a concrete reason to modernize them to SystemVerilog. For example, `adc_digital.v` is mostly module instantiation and continuous assignment, so `wire` is appropriate for ports, internal interconnect, and assigned nets. [adc_digital.v#L3](file:///home/kcaisley/frida/design/hdl/adc_digital.v#L3), [adc_digital.v#L60](file:///home/kcaisley/frida/design/hdl/adc_digital.v#L60), [adc_digital.v#L145](file:///home/kcaisley/frida/design/hdl/adc_digital.v#L145)
- Use `reg` or, in `.sv` files, `logic` for procedurally assigned state. Do not convert all `wire`s to `logic` by default.
- For structural outputs driven by instantiated cells, prefer `wire` over `reg`/`logic`. For example, `salogic.v` currently declares `dac_state_p`/`dac_state_n` as `output reg`, but those signals are driven by instantiated `OPENROAD_DFFE` outputs, so `output wire` is the clearer lint/synthesis-friendly style. [salogic.v#L26](file:///home/kcaisley/frida/design/hdl/salogic.v#L26), [salogic.v#L69](file:///home/kcaisley/frida/design/hdl/salogic.v#L69)
- Prefer explicit per-port declarations instead of relying on inherited direction/type across comma-separated names. This makes Verible formatting and human review easier.

AMS/cosimulation style:

- Use `real` variables for cocotb-visible analog stimulus values in the testbench.
- Use `wreal` nets for analog-valued signals that must propagate through Verilog hierarchy to a Spectre electrical/SPICE boundary.
- Bridge cocotb-driven `real` variables to `wreal` nets with continuous assignments: `real vin_p_val; wreal vin_p; assign vin_p = vin_p_val;`.
- Keep `wreal`-bearing wrappers/stubs small and Verilog-compatible: use `wire`/`reg`, not SystemVerilog `logic`, in files that must also pass Verilator lint. In local tests, Verilator accepted `wreal` only when VAMS keyword mode was enabled, and that mode did not recognize `logic`. [cosim_wreal_ports.sv#L2](file:///home/kcaisley/frida/build/cosim_lint/cosim_wreal_ports.sv#L2), [cosim_wreal_ports.sv#L10](file:///home/kcaisley/frida/build/cosim_lint/cosim_wreal_ports.sv#L10)
- Xcelium enables `wreal` with `xrun -ams`; Verilator lint needs VAMS keyword mode for `wreal`. Use guarded VAMS keyword directives in lint-compatible AMS stubs if the file is parsed by Verilator, but do not include those directives in Xcelium mode.
- Cadence-only analog probe system tasks, such as `$cds_analog_is_valid` and `$cds_get_analog_value`, are not Verilator-compatible. Put those probes in an Xcelium-only fileset rather than adding lint ignores. [cosim_xcelium_probe.sv#L8](file:///home/kcaisley/frida/build/cosim_lint/cosim_xcelium_probe.sv#L8)
- The current `adc_stub.v` already demonstrates the intended branch structure: wire-only ports for `COCOTBEXT_AMS`, `real` ports for `SPICEBIND`, and `wreal` ports for Xcelium AMS. [adc_stub.v#L34](file:///home/kcaisley/frida/design/hdl/adc_stub.v#L34), [adc_stub.v#L40](file:///home/kcaisley/frida/design/hdl/adc_stub.v#L40), [adc_stub.v#L44](file:///home/kcaisley/frida/design/hdl/adc_stub.v#L44)

Local lint experiments were run in `build/cosim_lint/`:

- `cosim_wire_only.sv`: plain `wire`/`reg` stub style passed Verilator and Verible. [cosim_wire_only.sv#L1](file:///home/kcaisley/frida/build/cosim_lint/cosim_wire_only.sv#L1)
- `cosim_real_ports.sv`: `real` ports passed Verilator and Verible. [cosim_real_ports.sv#L1](file:///home/kcaisley/frida/build/cosim_lint/cosim_real_ports.sv#L1)
- `cosim_wreal_ports.sv`: `wreal` ports passed Verilator when guarded with VAMS keyword mode and written without `logic`; Verible also accepted it. [cosim_wreal_ports.sv#L1](file:///home/kcaisley/frida/build/cosim_lint/cosim_wreal_ports.sv#L1)
- `cosim_xcelium_probe.sv`: Verible accepted the Cadence probe syntax, but Verilator rejected the Cadence system tasks. This confirms those modules should be excluded from Verilator lint filesets. [cosim_xcelium_probe.sv#L1](file:///home/kcaisley/frida/build/cosim_lint/cosim_xcelium_probe.sv#L1)

HDL cleanup plan for Xcelium/Spectre cosimulation:

- Treat `design/hdl/` cleanup as a staged migration. First get the existing ADC, SPI, and top-level RTL parseable and simulatable with Xcelium, Spectre/AMS, Yosys, and OpenROAD without intentionally changing behavior. Then add cocotb or simulator-level regression tests. Only after that baseline exists should the source RTL be rewritten to remove explicit implementation-cell instantiations.
- Delete the obsolete single-channel integration path before building new regressions: `frida_core_1chan.v` and `tb_integration.v`. The latter is tied to the old `frida_core_1chan` wrapper and older open-source co-simulation assumptions. [frida_core_1chan.v#L19](file:///home/kcaisley/frida/design/hdl/frida_core_1chan.v#L19), [tb_integration.v#L1](file:///home/kcaisley/frida/design/hdl/tb_integration.v#L1), [tb_integration.v#L152](file:///home/kcaisley/frida/design/hdl/tb_integration.v#L152)
- Do not include both PDK-specific `cells_*` files in the same HDL compilation. They define the same `OPENROAD_*` module names and are mutually exclusive providers. More importantly, they instantiate PDK standard cells directly, which makes them poor behavioral simulation inputs and fragile for Xcelium/Yosys/OpenROAD frontend parsing. [cells_tsmc65.v#L1](file:///home/kcaisley/frida/design/hdl/cells_tsmc65.v#L1), [cells_ihp_sg13g2.v#L1](file:///home/kcaisley/frida/design/hdl/cells_ihp_sg13g2.v#L1)
- Use `cells_behavioral.v` as the technology-independent behavioral provider for the current `OPENROAD_*` primitives. It should model only the current wrapper interfaces: `OPENROAD_DFFE`, `OPENROAD_DFFER`, `OPENROAD_CLKXOR`, `OPENROAD_CLKBUF`, `OPENROAD_CLKINV`, and `OPENROAD_CTRLGATE`. This file is for lint, RTL simulation, Xcelium digital-side compilation, and early Yosys parsing; it is not the final physical implementation library.
- The behavioral models should be simple Verilog, not SystemVerilog-only: continuous assigns for buffer/inverter/xor; `always @(posedge C)` for enabled flops; `always @(posedge C or negedge R)` for active-low reset flops; and a conservative functional clock-gate model such as `assign GCK = CK & E`. The clock-gate model is only a functional approximation, not a latch-based glitch-free signoff model.
- Current explicit `OPENROAD_*` users are the cleanup targets: `capdriver.v` uses `OPENROAD_CLKXOR`, `clkgate.v` uses `OPENROAD_CTRLGATE`, `salogic.v` uses `OPENROAD_DFFE`, `sampdriver.v` uses `OPENROAD_CLKBUF`/`OPENROAD_CLKINV`, and `frida_spi.v` uses `OPENROAD_DFFER`/`OPENROAD_CLKINV`. [capdriver.v#L28](file:///home/kcaisley/frida/design/hdl/capdriver.v#L28), [clkgate.v#L33](file:///home/kcaisley/frida/design/hdl/clkgate.v#L33), [salogic.v#L72](file:///home/kcaisley/frida/design/hdl/salogic.v#L72), [sampdriver.v#L17](file:///home/kcaisley/frida/design/hdl/sampdriver.v#L17), [frida_spi.v#L33](file:///home/kcaisley/frida/design/hdl/frida_spi.v#L33)
- After the baseline simulations pass, eliminate these explicit `OPENROAD_*` instantiations from maintained RTL where possible: replace clock buffers/inverters/xors with assigns, replace enabled flops with normal procedural RTL, and leave actual clock-gating/mapping to synthesis or a dedicated technology-mapping step. This should be done with regression tests in place so functional changes are visible.
- Fileset rule: every compilation should include exactly one implementation of the `OPENROAD_*` wrappers. Use the behavioral provider for lint, cocotb/digital simulation, Xcelium AMS compilation, and frontend parse checks. Use PDK/stdcells only in synthesis, place-and-route, or post-layout/netlist contexts where the selected technology library is also present.

Recommended fileset policy:

| Fileset | Contents | Verilator lint | Verible lint/format |
|---|---|---:|---:|
| `rtl` | Synthesizable digital RTL, no Cadence-only tasks, no obsolete `frida_core_1chan`/`tb_integration` path | Yes | Yes |
| `rtl.behavioral_cells` | Technology-independent behavioral definitions for `OPENROAD_*` wrappers; include exactly one provider per compile | Yes | Yes |
| `rtl.blackbox` | Lint-compatible analog macro stubs using `wire`/`reg`/optional `wreal` | Yes, if VAMS-safe | Yes |
| `rtl.pdk_cells` | PDK-specific standard-cell wrappers or simulation libraries for selected technology only | No, unless standalone lintable | Optional syntax check only |
| `ams.xcelium` | Xcelium AMS wrappers, `$cds_get_analog_value` probes, AMS-only testbench glue | No | Optional syntax check only |
| `testbench.cocotb` | Python cocotb tests | No | No |

Formatting plan:

- Use `verible-verilog-format` for Verilog/SystemVerilog RTL and lint-compatible stubs.
- Keep generated HDL or simulator-specific wrappers in generated/build directories unless they are intentionally maintained source files.
- Require a clean diff after formatting in CI, following SiliconCompiler’s own repository pattern. [format_verilog.sh#L28](file:///home/kcaisley/libs/siliconcompiler/.github/workflows/bin/format_verilog.sh#L28)

# Netlist generation (on top of Hdl21 and vlsirtools) 
SiliconCompiler owns orchestration, paths, PDK selection, build directories, job names, dependencies, and artifacts. HDL21/vlsirtools owns circuit elaboration and netlist emission.

So instead of `flow/cli.py` deciding `--out build`, `--tech ihp130`, `--fmt spectre`, etc., those become SiliconCompiler project/flow/task settings. Your HDL21 code should only be called from inside SC tasks.

Concretely, I would migrate responsibilities like this:

| Current custom runner responsibility | Move to SiliconCompiler? | How |
|---|---:|---|
| Build directory / output root | Yes | `project.option.set_builddir(...)`; SC default is `build` and structure is `<builddir>/<design>/<jobname>/<step>/<index>` [option.py#L549](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/schema_support/option.py#L549) |
| Job naming | Yes | `project.option.set_jobname(...)`; default `job0` [option.py#L565](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/schema_support/option.py#L565) |
| Target PDK selection | Mostly yes | `project.set_pdk(...)` for SC; HDL21 task reads SC PDK name and calls `flow.pdks.set_pdk(...)` internally |
| Source-file registration | Yes | `Design.set_dataroot`, filesets, `design.add_file(...)` [pathschema.py#L313](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/schema_support/pathschema.py#L313), [design.py#L87](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/design.py#L87) |
| Build graph | Yes | `Flowgraph.node(...)`, `Flowgraph.edge(...)` |
| Output directories and forwarding | Yes | Task `outputs/` directories are forwarded to downstream `inputs/` directories [schedulernode.py#L692](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/scheduler/schedulernode.py#L692) |
| Netlist variant generation | HDL21-native, triggered by SC | Custom `FridaHdl21NetlistTask` calls your existing HDL21/vlsirtools code |
| Netlist naming inside a generated bundle | Mostly HDL21/FRIDA | Your `params_to_filename` logic can remain, or be simplified to emit an indexed manifest |
| OA→CDL / CDL→SP / cleanup | SC task wrapper around current functions | Existing functions in `flow/util/netlist.py` stay, but CLI dispatch goes away |
| `flow/cli.py` argument parsing | Delete/reduce heavily | Replaced by SC project setup scripts / manifests / flowgraph |

The important architectural move is: **do not pass `outdir` around from your own CLI anymore.** Inside a SiliconCompiler task, the current working directory is already the node work directory. The task should write to:

```text
outputs/
```

and downstream tasks will receive those artifacts in:

```text
inputs/
```

So your HDL21 netlist task should write something like:

```text
outputs/
  netlists/
    manifest.json
    spectre/
      comp/
      samp/
      cdac/
    ngspice/
      comp/
      samp/
      cdac/
    verilog/
      comp.v
      samp.v
```

Declare only the directory as the task output:

```python
self.add_output_file("netlists")
```

This avoids declaring hundreds of dynamic files individually. That matters because SiliconCompiler validates task outputs against declared outputs [schedulernode.py#L1281](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/scheduler/schedulernode.py#L1281). A declared directory is the right abstraction for “many generated netlists.”

Your current CLI dispatch logic in `flow/cli.py` is exactly the kind of thing I’d delete: it parses `--tech`, `--fmt`, `--scope`, `--out`, then calls `mod.run_netlist(...)` [flow/cli.py#L62](file:///home/kcaisley/frida/flow/cli.py#L62), [flow/cli.py#L332](file:///home/kcaisley/frida/flow/cli.py#L332). In SC, those become task parameters and output directories managed by SC.

Your HDL21 netlist internals can stay. For example, `run_netlist_variants()` already does the HDL21/vlsirtools-native work: selects variants, checks the active HDL21 PDK, compiles the design, and writes netlists [flow/circuit/netlist.py#L163](file:///home/kcaisley/frida/flow/circuit/netlist.py#L163). That should be called by an SC task, not by a custom CLI.

I would structure the replacement like this:

```python
from siliconcompiler import Task


class FridaHdl21NetlistTask(Task):
    def __init__(self):
        super().__init__()
        self.add_parameter("formats", "[str]", "Netlist formats to generate", defvalue=["spectre"])
        self.add_parameter("mode", "<min,max>", "Variant generation mode", defvalue="max")
        self.add_parameter("scope", "<dut,stim,full>", "Netlist scope", defvalue="dut")

    def tool(self):
        return "frida"

    def task(self):
        return "hdl21_netlist"

    def setup(self):
        super().setup()
        self.set_threads(1)

        # One output directory containing many generated netlists.
        self.add_output_file("netlists")

        self.add_required_key("asic", "pdk")
        self.add_required_key("var", "formats")
        self.add_required_key("var", "mode")
        self.add_required_key("var", "scope")

    def run(self):
        from pathlib import Path
        import json

        from flow.pdks import set_pdk
        from flow.comp.testbench import run_netlist as comp_netlist
        from flow.samp.testbench import run_netlist as samp_netlist

        tech = self.project.get("asic", "pdk")
        formats = self.get("var", "formats")
        mode = self.get("var", "mode")
        scope = self.get("var", "scope")

        # Bridge SC PDK selection into HDL21 PDK selection.
        set_pdk(tech)

        outroot = Path("outputs") / "netlists"
        outroot.mkdir(parents=True, exist_ok=True)

        blocks = {
            "comp": comp_netlist,
            "samp": samp_netlist,
        }

        manifest = {
            "tech": tech,
            "mode": mode,
            "scope": scope,
            "formats": formats,
            "blocks": {},
        }

        for fmt in formats:
            for block, runner in blocks.items():
                block_out = outroot / fmt / block
                block_out.mkdir(parents=True, exist_ok=True)

                runner(
                    tech=tech,
                    mode=mode,
                    montecarlo=False,
                    fmt=fmt,
                    scope=scope,
                    outdir=block_out,
                    verbose=False,
                )

                manifest["blocks"].setdefault(block, []).extend(
                    str(p.relative_to(outroot)) for p in block_out.iterdir() if p.is_file()
                )

        (outroot / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return 0
```

Then `frida1` setup becomes a SiliconCompiler project description, not a custom command-line runner:

```python
from siliconcompiler import ASIC, Design, Flowgraph

design = Design("frida1")
design.set_dataroot("frida", __file__)

with design.active_fileset("rtl"):
    design.set_topmodule("frida1")
    design.add_file("design/rtl/frida1.sv", dataroot="frida")

with design.active_fileset("hdl21"):
    design.add_file("flow/comp/subckt.py", dataroot="frida", filetype="python")
    design.add_file("flow/comp/testbench.py", dataroot="frida", filetype="python")
    design.add_file("flow/samp/subckt.py", dataroot="frida", filetype="python")
    design.add_file("flow/samp/testbench.py", dataroot="frida", filetype="python")
    design.add_file("flow/circuit/netlist.py", dataroot="frida", filetype="python")
    design.add_file("flow/circuit/sim.py", dataroot="frida", filetype="python")

project = ASIC(design)
project.add_fileset(["rtl", "hdl21"])
project.option.set_builddir("build")
project.option.set_jobname("frida1_ihp130")
project.set_pdk("ihp130")

flow = Flowgraph("frida1")
flow.node("analog.netlist", FridaHdl21NetlistTask())
flow.node("analog.convert", FridaNetlistConvertTask())
flow.node("analog.sim", FridaAnalogSimTask())
flow.edge("analog.netlist", "analog.convert")
flow.edge("analog.convert", "analog.sim")

project.set_flow(flow)
project.run()
```

For `flow/util/netlist.py`, I would keep the pure conversion functions but remove the CLI role. The functions `oa_to_cdl`, `cdl_to_sp`, and `clean_cdl` are good reusable task bodies [flow/util/netlist.py#L55](file:///home/kcaisley/frida/flow/util/netlist.py#L55), [flow/util/netlist.py#L94](file:///home/kcaisley/frida/flow/util/netlist.py#L94), [flow/util/netlist.py#L127](file:///home/kcaisley/frida/flow/util/netlist.py#L127). Wrap them in SC tasks:

```text
oa.netlist      -> outputs/<cell>.cdl
cdl.clean       -> outputs/<cell>.sp
hdl21.netlist   -> outputs/netlists/
analog.sim      -> outputs/results/
```

That replaces the `flow convert ...` branch in `flow/cli.py` [flow/cli.py#L105](file:///home/kcaisley/frida/flow/cli.py#L105) with real build-graph nodes.

The one custom bridge I would keep is very small:

```python
def activate_hdl21_pdk_from_sc(project):
    from flow.pdks import set_pdk
    return set_pdk(project.get("asic", "pdk"))
```

Longer term, `flow/pdks.py` can shrink too. Right now it owns PDK registry and HDL21 activation [flow/pdks.py#L15](file:///home/kcaisley/frida/flow/pdks.py#L15), [flow/pdks.py#L39](file:///home/kcaisley/frida/flow/pdks.py#L39). Ideally SC owns the registry, and `flow.pdks` only maps SC PDK names to HDL21 modules/cache resets.

So I’d aim for this final separation:

```text
frida/flow/
  hdl21 generators      keep
  circuit/netlist.py    keep but no CLI assumptions
  util/netlist.py       keep pure functions; wrap in SC tasks
  cli.py               delete or reduce to compatibility shim

frida/flow/sc/
  targets.py            project setup: frida1_ihp130(), frida1_tsmc65()
  flows.py              Flowgraph definitions
  tasks/
    hdl21_netlist.py
    netlist_convert.py
    spectre_sim.py
    ngspice_sim.py
    oa_to_cdl.py
```

That gives you what you want: SiliconCompiler becomes the build system, while HDL21/vlsirtools remains the circuit generator. You do not manually run HDL21, and you do not check generated SPICE into Git.

# Cosimulation and testbenching

SiliconCompiler’s “happy path” for simulation-based verification is much stronger on the digital/cocotb side than on the SPICE/Xyce side.

For digital simulation, SiliconCompiler’s intended path is `Sim()` + `DVFlow`. `DVFlow` explicitly supports plain Icarus, plain Verilator, Icarus+cocotb, Verilator+cocotb, Xyce, and xdm→Xyce [dvflow.py#L27](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/flows/dvflow.py#L27). For cocotb, the path is fairly complete:

1. Register RTL and cocotb Python filesets.
2. Use `DVFlow(tool="icarus-cocotb")` or `DVFlow(tool="verilator-cocotb")`.
3. Cocotb drives stimulus and performs assertions in Python.
4. Cocotb writes `outputs/results.xml`.
5. SiliconCompiler parses that xUnit XML and records failures as the `errors` metric.

The bundled adder example is exactly this. It registers `rtl`, `testbench.cocotb`, and simulator command-file filesets [adder_cocotb/make.py#L35](file:///home/kcaisley/libs/siliconcompiler/examples/adder_cocotb/make.py#L35), then uses `DVFlow(tool="icarus-cocotb")` [adder_cocotb/make.py#L80](file:///home/kcaisley/libs/siliconcompiler/examples/adder_cocotb/make.py#L80) or `DVFlow(tool="verilator-cocotb")` [adder_cocotb/make.py#L138](file:///home/kcaisley/libs/siliconcompiler/examples/adder_cocotb/make.py#L138). The testbench is normal cocotb with Python `assert`s [cocotb_adder.py#L9](file:///home/kcaisley/libs/siliconcompiler/examples/adder_cocotb/cocotb_adder.py#L9).

SiliconCompiler’s cocotb task sets `COCOTB_RESULTS_FILE=outputs/results.xml` [cocotb_task.py#L194](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/_common/cocotb/cocotb_task.py#L194), declares `results.xml` as an output [cocotb_task.py#L210](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/_common/cocotb/cocotb_task.py#L210), parses the XML [cocotb_task.py#L250](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/_common/cocotb/cocotb_task.py#L250), and records failures/errors as SC’s `errors` metric [cocotb_task.py#L275](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/_common/cocotb/cocotb_task.py#L275). That is a real verification loop, not just “ran a simulator.”

Plain digital simulation is less rich but still conventional. The non-cocotb path compiles to a simulator executable/image and then runs it. Icarus produces a `.vvp` output [icarus/compile.py#L70](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/icarus/compile.py#L70), and `ExecInputTask` simply executes the previous node’s single output [exec_input.py#L10](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/execute/exec_input.py#L10). In that mode the testbench itself needs to be self-checking — e.g. `$fatal`, nonzero exit, or simulator-detectable errors. The heartbeat example has a plain Verilog testbench, but it is mostly stimulus/finish/monitor rather than a self-checking verification test [heartbeat/testbench.v#L18](file:///home/kcaisley/libs/siliconcompiler/examples/heartbeat/testbench.v#L18).

For Xyce, the situation is much thinner. `DVFlow(tool="xyce")` exists [dvflow.py#L70](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/flows/dvflow.py#L70), and `DVFlow(tool="xdm-xyce")` can first convert through XDM [dvflow.py#L73](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/flows/dvflow.py#L73). The Xyce task runs `Xyce`, recognizes warnings/errors via log regexes [xyce/simulate.py#L53](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/xyce/simulate.py#L53), accepts `.xyce`, `.cir`, or registered SPICE files [xyce/simulate.py#L64](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/xyce/simulate.py#L64), and can write a `.raw` trace if tracing is enabled [xyce/simulate.py#L73](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/xyce/simulate.py#L73). But I do **not** see a built-in Xyce result-evaluation layer comparable to cocotb’s `results.xml` parsing.

So for SPICE/Xyce, SiliconCompiler’s built-in happy path is basically:

```text
SPICE/Xyce input → run Xyce → collect log errors/warnings → optionally collect raw waveform
```

It is **not**:

```text
SPICE sim → parse waveforms → compute offset/noise/settling/ENOB → assert specs → report xUnit-like test result
```

That latter piece would be yours to add as a custom task.

This maps very naturally to what FRIDA already has. Your measurement layer already separates waveform extraction from numpy-based measurement functions [measure.py#L1](file:///home/kcaisley/frida/flow/circuit/measure.py#L1). You already have functions for settling, delay, average power, offset, charge injection, etc. [measure.py#L306](file:///home/kcaisley/frida/flow/circuit/measure.py#L306). That is basically the analog equivalent of a cocotb checker, but post-simulation instead of live over VPI.

I would make FRIDA’s analog “happy path” in SC look like this:

```text
hdl21.netlist
    ↓
spice.simulate
    ↓
analog.measure
    ↓
analog.verify
```

Where:

- `hdl21.netlist` generates DUT/testbench netlists.
- `spice.simulate` runs Spectre/ngspice/Xyce/vlsirtools and emits waveform/results files.
- `analog.measure` reads results, computes metrics, writes `outputs/measurements.json`.
- `analog.verify` checks those metrics against spec thresholds and records `errors=0` or `errors>0`.

SiliconCompiler’s metric system is the right integration point. It has standard metrics like `errors`, `warnings`, runtime, memory [metric.py#L34](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/schema_support/metric.py#L34), and ASIC metrics like power, area, timing, DRCs, etc. [asic metrics#L84](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/metrics/asic.py#L84). Tasks record metrics with `record_metric` [tool.py#L2172](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tool.py#L2172). Flowgraph nodes can have goals such as `errors == 0` [flowgraph.py#L1716](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/flowgraph.py#L1716), and the docs describe goals as hard pass/fail constraints [metrics.rst#L19](file:///home/kcaisley/libs/siliconcompiler/docs/development_guide/metrics.rst#L19).

There is also a built-in `verify` task that asserts metric predicates like `errors==0` [verify.py#L9](file:///home/kcaisley/libs/siliconcompiler/siliconcompiler/tools/builtin/verify.py#L9). That could be used after a custom measurement task, though for analog specs you may want a FRIDA-specific verify task that can report richer failures, e.g. `comp_offset_mV > 2.5`, `samp_settling_ns > 5`, etc.

On your cosimulation thought: yes, cocotb + digital simulator + ngspice/Xyce co-simulation is possible in principle, but I would not consider it the SiliconCompiler happy path. It would be a custom mixed-signal verification environment. It makes sense when digital stimulus must interact dynamically with transistor-level analog state during the same simulated timebase. But it is a heavier dependency and you’d own a lot of glue.

For FRIDA, I’d separate the problem by abstraction level:

1. **Analog block characterization:** SPICE testbench + Python post-processing. This is the cleanest path for comparator offset, CDAC settling, sampler charge injection, power, Monte Carlo, etc.
2. **Digital control verification:** cocotb with Verilator/Icarus. Use behavioral models or sampled traces for analog-facing signals.
3. **Mixed-signal system verification:** preferably digital simulator + behavioral/RNM analog models first. Use cocotb to drive sequences and check functional behavior.
4. **Full transistor-level mixed-signal co-sim:** only for selected signoff scenarios where interaction effects matter enough to justify the complexity.

So I would not try to force Xyce/ngspice into a cocotb-like live stimulus/checker model unless you really need dynamic co-simulation. The happier SC-aligned path is: **run SPICE as a task, parse waveforms in a following Python task, record metrics/errors, and let SC summarize/verify those metrics.**
