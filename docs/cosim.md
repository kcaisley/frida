# Mixed-Signal Co-Simulation Reference

This document describes the two co-simulation stacks available in frida:
an open-source stack (cocotb + Icarus/Verilator + spicebind + ngspice)
and a commercial stack (cocotb + Xcelium + Spectre AMS). Each section
builds from the bottom of the stack (SPICE circuits) upward to the
Python test layer (cocotb).

## Tooling

| Tool | Version tested | Minimum required | Notes |
|---|---|---|---|
| cocotb | 2.0.1 | 2.0 | Runner API moved to `cocotb_tools.runner` |
| spicebind | 0.0.2 | — | Git submodule at `libs/spicebind`, built via `uv sync` (scikit-build-core invokes CMake). May need `CMAKE_ARGS="-DNGSPICE_ROOT=/usr"` if ngspice headers are in a non-standard location |
| Icarus Verilog | 13.0 | 12.0 | v13 has VPI stability fixes. Install from source: `~/asiclab/eda/install_iverilog.sh` |
| Verilator | 5.046 | 5.036 | Minimum 5.036 required by cocotb 2.0. Install from source with `mold` and `libjemalloc-dev` for performance: `~/asiclab/eda/install_verilator.sh` |
| ngspice | 45.2 | — | Needs both the standalone binary and the shared library (`libngspice.so` + `sharedspice.h`). The install script runs two separate configure/build passes (`--with-ngshared`): `~/asiclab/eda/install_ngspice.sh` |
| GTKWave | 4.0.0 | — | Provides `fst2vcd`, `vcd2fst` utilities |
| vcdvcd | 2.6.0 | — | Python VCD parser |
| Xcelium | 24.03 | — | Requires `-ams` flag for `wreal` |
| Spectre | 24.10 | — | Analog solver for Xcelium AMS |

---

## 1. SPICE Subcircuit Layer

The analog design is described as a SPICE subcircuit. Both stacks
consume `.subckt` blocks, but the simulator determines which syntax
flavors and analysis features are available.

| Feature | ngspice | Spectre |
|---|---|---|
| Input format | `.sp` (SPICE3/HSPICE subset) | `.scs` (native) or `.sp` (SPICE compatibility mode) |
| PDK model decks | HSPICE-format `.lib` / `.l` files (reads `.lib 'file' corner` syntax) | Spectre-format `.scs` or HSPICE `.lib` via compatibility parser |
| BSIM models | BSIM3v3 (level 49), BSIM4 (level 14/54), BSIM-SOI, BSIM-CMG | Full BSIM family + proprietary Spectre models |
| Mismatch / Monte Carlo | Manual: add Gaussian offsets to parameters via `.param` + random functions. No built-in Monte Carlo engine | Built-in `.montecarlo` analysis with `mismatch` and `process` blocks |
| Transient noise | Not supported — `.tran` is deterministic | Supported via `tran noise=yes` (transient noise injection) |
| Subcircuit syntax | `.subckt name ports` ... `.ends` | `subckt name (ports)` ... `ends` (native) or `.subckt` (compat) |

**Note on ngspice HSPICE compatibility:** ngspice reads HSPICE-format
model libraries (`.lib` / `.l` files with `section` corners) and supports
most HSPICE MOSFET model levels. However, some HSPICE extensions
(e.g., `$random` in expressions, `.alter`, `.data` sweep tables) are
unsupported. TSMC and other foundry HSPICE decks generally work for
DC/AC/transient but may need minor edits for advanced features.

---

## 2. Analog Wrapper / Control Layer

Above the subcircuit sits a "wrapper" that configures the co-simulation
boundary: how signals enter/exit, how supplies are connected, what
analysis to run, and what to save. This layer differs significantly
between the two stacks.

### spicebind: `.cir` wrapper file

A flat SPICE netlist that declares `external` voltage sources for each
input, instantiates the DUT, and specifies the transient analysis:

```spice
* External sources — driven by Verilog via spicebind VPI
Vinp inp 0 0 external
Vinn inn 0 0 external
Vclk clk 0 0 external

* Fixed supplies (not driven by spicebind)
Vvdd vdd 0 1.2
Vvss vss 0 0

* DUT instantiation
Xdut inp inn outp outn clk vdd vss my_comparator

* Output format
.options filetype=ascii

* Transient analysis
.tran 0.1ns 1

.end
```

Key points:
- Each input port needs a `Vname node 0 0 external` declaration
- Output nodes are read by matching Verilog port names to SPICE node names
- Supplies are typically fixed (`Vvdd vdd 0 1.2`), not `external`, because
  `external` sources start at 0V during SPICE initialization
- `.options filetype=ascii` produces nutascii `.raw` output; omit for binary
- `.tran` step size controls ngspice's internal timestep granularity

### Xcelium AMS: `.scs` control file

A Spectre-language file that configures the AMS boundary, PDK models,
analysis, and signal saving:

```spectre
simulator lang=spectre

// PDK models
include "/path/to/toplevel.scs" section=tt_lib
include "/path/to/toplevel.scs" section=pre_simu

// Signal saving
saveOpt options save=allpub rawfmt=nutascii
save tb.i_comp.* depth=3

// Transient analysis
tran tran stop=340n

// AMS boundary configuration
amsd {
    portmap subckt=comp autobus=yes porttype=name ignore="vdd vss"
    config cell=comp use=spice
    ie vsup=1.2 rout=0
}
```

Key points:
- `simulator lang=spectre` is required at the top
- `amsd {}` block configures the mixed-signal boundary:
  - `config cell=comp use=spice` — tells Xcelium to replace the Verilog
    module `comp` with the SPICE subcircuit
  - `portmap` — controls port name mapping between Verilog and SPICE
  - `ignore="vdd vss"` — excludes supply ports from the digital domain
  - `ie vsup=1.2` — configures connect module supply voltage
  - `rout=0` — makes connect modules act as ideal voltage sources (zero
    impedance). **Caution:** setting `rout=0` globally disables bidirectional
    operation for ALL connect modules. Use per-net targeting for supplies:
    `ie net=tb.i_comp.vdd rout=0`
- Supplies can be driven via Spectre `vsource` using hierarchical paths:
  `Vvdd (tb.i_comp.vdd 0) vsource type=dc dc=1.2`
- `rawfmt=nutascii` for Python-parseable output; `rawfmt=sst2` for
  SimVision-native format

### Output formats

| Format | Producer | gtkwave | bspwave | SimVision | spyci (Python) | vcdvcd (Python) |
|---|---|---|---|---|---|---|
| nutascii `.raw` | ngspice, Spectre | No | Yes | Yes | Yes (numpy 1.x only) | No |
| nutbin `.raw` | ngspice, Spectre | No | Yes | No | No | No |
| psfbin | Spectre | No | No | Yes (via SST2) | No | No |
| psfascii | Spectre | No | No | Yes (via SST2) | No | No |
| SST2 / SHM | Xcelium probes | No | No | Yes (native) | No | No |
| VCD `.vcd` (`$var real`) | Icarus, Verilator | Yes | Yes | No | No | Yes |
| VCD `.vcd` (`$var wreal`) | Xcelium (`$dumpvars` on `wreal` nets) | **Crashes** | No | No | No | Yes |
| FST `.fst` | Icarus (cocotb `waves=True`) | Yes (native) | No | No | No | via `fst2vcd` |

Notes on the spicebind + Icarus waveform output:
- cocotb hard-codes **FST** format for Icarus (not VCD). Set `waves=True`
  on both `runner.build()` and `runner.test()` to enable it.
- VCD dumping via `$dumpvars` is **suppressed** when cocotb's VPI
  controls the simulation alongside spicebind.
- ngspice always produces a `.raw` file (use `.options filetype=ascii`
  for nutascii). This contains the full SPICE-side analog waveforms.
- FST files are readable in Python via `fst2vcd` (ships with GTKWave)
  piped to `vcdvcd`. `spyci` has a numpy 2.0 compatibility bug
  (`np.complex_` removed).

---

## 3. Interconnect and Synchronization

This layer describes how the analog and digital simulation engines
communicate during a co-simulation run.

### spicebind: VPI time-barrier synchronization

spicebind bridges Icarus Verilog and ngspice through VPI callbacks
with a shared time barrier. The synchronization is **event-driven with
redo support**, not a fixed-interval poll:

1. **Event-driven sync:** When a Verilog input signal changes, a
   `cbValueChange` VPI callback fires, triggering a sync with ngspice
   at the current simulation time.

2. **Time barrier:** Both engines publish their current time to a shared
   barrier. Neither advances until the other has caught up. ngspice's
   internal adaptive timestep control determines the SPICE-side step size.

3. **Input transfer (Verilog → SPICE):** Zero-order hold. The `external`
   voltage source is set to the current Verilog port value and held
   constant until the next sync point. No ramping or interpolation.

4. **Output transfer (SPICE → Verilog):** Sample-and-hold. At each
   SPICE end-of-step, the converged node voltage is read and applied to
   the corresponding Verilog output port.

5. **Redo mechanism:** If a Verilog input changes during a SPICE step,
   spicebind signals ngspice to redo the step from the change point with
   the updated input value. This prevents missing fast transients.

6. **Digital thresholds:** Controlled by environment variables:
   - `VCC` (default 1.0V)
   - `LOGIC_THRESHOLD_LOW` (default 0.3 × VCC)
   - `LOGIC_THRESHOLD_HIGH` (default 0.7 × VCC)

**Limitation:** The piecewise-constant input model means fast-changing
analog inputs (e.g., sinusoids) appear as staircases to ngspice. Use
small cocotb `Timer` steps (e.g., 0.5ns) to approximate smooth waveforms.

### Xcelium AMS: connect module discipline resolution

Xcelium + Spectre AMS uses a **tightly coupled** co-simulation where
both solvers share a unified timeline managed by the AMS engine:

1. **Automatic connect module insertion:** At elaboration time, Xcelium
   identifies every boundary where signals cross between disciplines
   (e.g., `logic` ↔ `electrical`, `wreal` ↔ `electrical`) and
   automatically inserts connect modules.

2. **Connect module types:**

   | Module | Direction | Function |
   |---|---|---|
   | R2E | `wreal` → `electrical` | Injects a voltage source: `V_spice = V_wreal` |
   | E2R | `electrical` → `wreal` | Reads node voltage: `V_wreal = V_spice` |
   | L2E | `logic` → `electrical` | Voltage source with rise/fall times |
   | E2L | `electrical` → `logic` | Threshold comparator |
   | Bidir | Bidirectional | Combined R2E + E2R or L2E + E2L |

3. **Connect rules** are specified in the `amsd {}` block via the `ie`
   (interface element) statement, or via `-amsconnrules` on the command
   line. The Universal Connect Module (UCM) is enabled with `-ams_ucm`.

4. **No manual wiring required.** Unlike spicebind, there are no
   `external` source declarations. The AMS engine handles all boundary
   signal injection and sampling automatically.

5. **Tight coupling:** The analog solver (Spectre) and digital solver
   (Xcelium) communicate at every analog timestep, not just at discrete
   sync points. Analog waveforms are continuous, not piecewise-constant.

---

## 4. Verilog Stub Modules

A Verilog stub is an empty module declaration whose ports match the SPICE
subcircuit pins. It tells the digital simulator what the analog block's
interface looks like.

### spicebind: stub required

spicebind discovers ports via VPI iteration over the Verilog module
hierarchy. A stub is mandatory, and it must be instantiated inside a
testbench wrapper:

```systemverilog
// Shell module — body empty, implemented by ngspice
module comp(
    input  real inp,
    input  real inn,
    output real outp,
    output real outn,
    input  wire clk,
    input  wire clkb
);
endmodule

// Testbench wrapper — required for HDL_INSTANCE path
module tb();
    real inp, inn;
    real outp, outn;
    reg clk, clkb;

    comp comp(.inp(inp), .inn(inn), .outp(outp), .outn(outn),
              .clk(clk), .clkb(clkb));
endmodule
```

The `HDL_INSTANCE` environment variable must point to the hierarchical
path of the stub instance (e.g., `tb.comp`), not the top-level module.

### Xcelium AMS: stub optional

With `config cell=comp use=spice` in the `amsd {}` block, Xcelium
auto-generates port bindings from the SPICE subcircuit. No Verilog stub
is needed. A stub is useful when you want to:

- Explicitly control port types (`logic` vs `wreal`)
- Add `(* cds_ams_schematic *)` pragma for schematic-driven flow
- Provide a behavioral fallback model for faster simulation

If a stub is provided, its syntax is identical to the spicebind case
(same port names and types). The `amsd { config cell=comp use=spice }`
directive tells Xcelium to replace the stub's body with the SPICE
implementation at elaboration time.

---

## 5. Top-Level Verilog and Real-Valued Net Types

The top-level testbench must declare signals to connect to the analog
stub's ports. The choice of type (`real`, `wire real`, `wreal`) affects
portability across simulators.

### Signal type comparison

| Type | Standard | Description |
|---|---|---|
| `real` | IEEE 1800 (SV) | 64-bit float **variable**. Single driver only. No inout ports, no X/Z state, no discipline association, no connect module support. |
| `wire real` | Icarus extension | `real`-valued **net**. Non-standard; not IEEE 1800 compliant. |
| `wreal` | Verilog-AMS / Cadence | Real-valued **net type**. Supports continuous assignment, multiple drivers with resolution functions (`wreal1driver`, `wreal4state`, `wrealmin`, `wrealmax`, `wrealsum`, `wrealavg`), connect modules, and discipline resolution. |

### Simulator support

| Type | Icarus Verilog | Verilator | Xcelium |
|---|---|---|---|
| `real` (variable) | Yes | Yes | Yes |
| `wire real` (net) | Yes (extension) | No (rejected per IEEE 1800 §6.7.1) | No (not a recognized type) |
| `wreal` (VAMS net) | Yes | Yes (requires `` `begin_keywords "VAMS-2.3" ``) | Yes (requires `-ams` flag; rejects `` `begin_keywords`` pragma) |

### VPI exposure

| Type | Icarus VPI type | Verilator VPI type | Xcelium VPI type | cocotb `GPI_REAL`? |
|---|---|---|---|---|
| `real` | `vpiRealVar` | `vpiRealVar` | `vpiRealVar` | Yes |
| `wire real` | `vpiRealNet` | N/A | N/A | Yes (Icarus only) |
| `wreal` | `vpiRealNet` | `vpiRealNet` | `vpiNet` (analog domain) | Icarus/Verilator: Yes. Xcelium: **No** |

cocotb's VPI layer maps `vpiRealVar` and `vpiRealNet` to `GPI_REAL` for
read/write via `vpiRealVal` format. However, Xcelium exposes `wreal` as
`vpiNet` with an analog domain attribute (confirmed via `describe`:
`wire(real)`), not as `vpiRealNet`. cocotb does not recognize this as a
real-valued signal — which is why the `$cds_get_analog_value` probe
pattern is necessary for reading analog outputs in Xcelium.

### Enabling `wreal` across simulators

There is no single pragma that enables `wreal` in all three simulators:

| Simulator | How to enable `wreal` |
|---|---|
| Icarus Verilog | Always available (no flag needed) |
| Verilator | `` `begin_keywords "VAMS-2.3" `` pragma in source file |
| Xcelium | `-ams` flag on `xrun` command line (rejects `` `begin_keywords "VAMS-2.3" ``) |

For Icarus/Verilator portability, use the pragma. For Xcelium, use the
flag. A `ifdef` guard can bridge both:

```systemverilog
`ifndef XCELIUM
`begin_keywords "VAMS-2.3"
`endif
```

### VCD compatibility with `wreal`

Xcelium's `$dumpvars` emits `$var wreal 64` in VCD output — a
non-standard type that **crashes gtkwave** and is not recognized by
bspwave. The `vcdvcd` Python library does parse it successfully.

The workaround is to mirror `wreal` nets to `real` variables and use
selective `$dumpvars` to exclude `wreal` signals:

```systemverilog
module tb();
    real inp_val, inn_val;         // Variables (cocotb-driven)
    wreal inp, inn;                // Nets at analog boundary
    assign inp = inp_val;
    assign inn = inn_val;

    wreal outp, outn;              // Analog outputs (wreal net)
    real outp_r, outn_r;           // Real mirrors for VCD
    always @(outp) outp_r = outp;
    always @(outn) outn_r = outn;

    comp comp(.inp(inp), .inn(inn), .outp(outp), .outn(outn), ...);

    // Selective dump — only real mirrors + digital (no wreal)
    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, inp_val, inn_val, outp_r, outn_r, clk);
    end
endmodule
```

---

## 6. cocotb Test Layer

cocotb drives the simulation from Python via VPI. The capabilities and
limitations depend on which simulator and analog engine are in use.

### Driving and reading signals

| Operation | spicebind (ngspice) | Xcelium AMS (Spectre) |
|---|---|---|
| **Drive real/analog inputs** | `dut.inp.value = 0.605` — sets `external` voltage source at next sync point | `dut.inp_val.value = 0.605` — drives `real` variable, which propagates through `assign` to `wreal` net, then through R2E connect module to SPICE |
| **Drive digital inputs** | `dut.clk.value = 1` — maps to VCC via threshold | `dut.clk.value = 1` — digital VPI, L2E connect module at boundary |
| **Drive power supplies** | Fixed in SPICE wrapper (`Vvdd vdd 0 1.2`). Can use `external` but supplies start at 0V during init | Fixed via Spectre `vsource` in `.scs` file, or use `ignore="vdd vss"` in `amsd {}` and drive from `.scs` with hierarchical paths |
| **Read real outputs** | `float(dut.outp.value)` — reads SPICE node voltage sampled at last sync point | Cannot read `wreal` directly via VPI (VPI is digital-only). Must use `$cds_get_analog_value` probe pattern (see below) |
| **Read digital outputs** | `int(dut.outp.value)` — SPICE voltage thresholded to 0/1/x | `int(dut.outp.value)` — standard VPI on digital signals |
| **Read internal SPICE nodes** | Add `output real <nodename>` to Verilog stub (see below) | Add `analog_probe` module to testbench (see below) |

### Observing internal analog nodes

Both stacks can expose internal SPICE nodes as `real` variables readable
by cocotb, without modifying the SPICE netlist. The syntax differs but
the result is identical: `float(dut.<signal>.value)` in Python.

| | spicebind | Xcelium AMS |
|---|---|---|
| Where to declare | Verilog stub module | Testbench (`analog_probe` instance) |
| When nodes are chosen | Compile time (fixed ports) | Runtime (string path from cocotb) |
| cocotb access | `float(dut.vamp.value)` | `float(dut.i_probe.voltage.value)` |

**spicebind** — add an output port to the stub whose name matches the
SPICE node:

```systemverilog
module comp(
    input  real inp, inn,
    output real outp, outn,
    output real vamp,           // internal node exposed as output
    input  wire clk, clkb
);
endmodule
```

**Xcelium AMS** — instantiate a reusable probe module in the testbench
and point it at any node from cocotb at runtime:

```systemverilog
module analog_probe();
    var string node_to_probe = "<unassigned>";
    logic probe_voltage_toggle = 0;
    real voltage;

    always @(probe_voltage_toggle) begin
        if ($cds_analog_is_valid(node_to_probe, "potential"))
            voltage = $cds_get_analog_value(node_to_probe, "potential");
    end
endmodule
```

```python
# From cocotb — probe any internal node by hierarchical path
dut.i_probe.node_to_probe.value = b"tb.i_comp.vamp"
dut.i_probe.probe_voltage_toggle.value = ~dut.i_probe.probe_voltage_toggle.value
await Timer(1, unit="ps")
voltage = float(dut.i_probe.voltage.value)
```

The `.raw` file from ngspice/Spectre also contains all internal node
voltages and branch currents for post-simulation analysis.

### cocotb runner configuration

| Setting | spicebind + Icarus | spicebind + Verilator | Xcelium AMS |
|---|---|---|---|
| Runner | `get_runner("icarus")` | `get_runner("verilator")` | Single `xrun` command (no cocotb runner) |
| VPI module loading | `test_args=["-M", spicebind.get_lib_dir(), "-m", "spicebind_vpi"]` | Not supported (VPI must be linked at compile time) | `-loadvpisim <cocotb_vpi.so>` |
| Waveform output | FST via `waves=True` on both `build()` and `test()` | VCD via `--trace` (cocotb default) | SHM via xrun `-input "probe ..."` or VCD via `$dumpvars` |
| Environment | `SPICE_NETLIST`, `HDL_INSTANCE`, `VCC` | Same (but VPI linking unsolved) | `COCOTB_TEST_MODULES`, `COCOTB_TOPLEVEL`, `PYGPI_PYTHON_BIN` |
| `test_module` syntax | `test_module="test_name"` (cocotb 2.0) | Same | Set via `COCOTB_TEST_MODULES` env var |

### Limitations summary

| Limitation | spicebind | Xcelium AMS |
|---|---|---|
| Analog input waveform | Piecewise constant (staircase) | Continuous (connect module with rise/fall) |
| Output latency | Sample-and-hold at sync points | Continuous (but VPI reads need probe pattern) |
| `cbValueChange` on analog | Works (VPI sees `real` variable changes) | Does not fire for `wreal`/analog signals |
| Internal SPICE node access | `.raw` file only (post-processing) | `$cds_get_analog_value` (runtime) or `.raw` (post) |
| Transient noise | Not supported (ngspice limitation) | Supported (`tran noise=yes`) |
| Monte Carlo | Manual parameter variation only | Built-in `.montecarlo` analysis |
| Verilator support | HDL compiles but VPI module loading unsolved | N/A (Xcelium is its own simulator) |
| License required | No (fully open-source) | Yes (Cadence Xcelium + Spectre) |
