# Plan: Mixed-Signal Co-Simulation (v2)

Uses Cadence Xcelium (digital) + Spectre (analog) via AMS Designer for
mixed-signal co-simulation, driven by cocotb/basil scan code.

## Pre-implementation questions (resolved)

Researched via Xcelium 25.09 docs (`wreal.pdf`, `vpiref.pdf`,
`ams_dms_simug.pdf`, `ams_dms_simkpns.pdf`) and cocotb source code.

### 1. cocotb + Xcelium AMS compatibility

**Resolved.** VPI is a digital-only interface. Analog signals need HDL bridges.

- `vpiref.pdf` p.14: analog nets appear as `vpiNet` with
  `vpiDomain == vpiContinuous`. Applying VPI routines to them "can produce
  incorrect results or even crash."
- `vpiref.pdf` p.120: the only AMS VPI extension is `vpiDomain` (from
  `vpi_ams.h`) — for *filtering out* analog objects, not interacting with them.
- `cbValueChange` is not guaranteed for analog-domain signals — the callback
  mechanism is tied to the digital event-driven kernel; analog changes happen
  in continuous-time via the Spectre solver.
- `ams_dms_simug.pdf` p.332-333: all digital objects in AMS designs default
  to no VPI access — must use `-access +rwc`.
- `ams_dms_simkpns.pdf` CCR 13907/7827: auto-inserted connect modules are
  opaque to probing and the Tcl `drivers` command.

**This explains the "A2D output reads constant 0" bug**: the A2D connect
module output is in the analog domain from VPI's perspective, so
`cbValueChange` never fires.

**Solution**: Use the `$cds_get_analog_value` HDL probe pattern from cocotb's
own `mixed_signal` example (see Step 4b). cocotb drives/reads `real` variables,
not wreal nets or connect-module outputs directly.

### 2. wreal vs real for analog signals

**Resolved.** `wreal` is mandatory at the AMS boundary. `real` cannot be
used there.

- `wreal.pdf` p.59-60: SV `real` variables have "No support for inout ports",
  "No discipline association", "Limited connectivity to analog models", and
  "forbids multiple drivers." Connect modules only insert between *nets* of
  different disciplines — `real` is a variable, not a net.
- `ams_dms_simug.pdf` p.189 (explicit warning): "Connection between the
  `wreal` nettype and the `real` nettype is not supported."
- Architecture must be: cocotb → `real` var → `assign` → `wreal` net →
  connect module → `electrical` (SPICE). Cannot skip the `wreal` step.

**VCD compatibility**: instead of post-processing with `sed`, declare `real`
mirror variables in the testbench and use selective `$dumpvars` to exclude
`wreal` nets entirely. The VCD then contains only `$var real` entries, which
gtkwave and bspwave both understand natively (see Step 4).

### 3. SPICE netlist format for Spectre's parser

Post-process with `fix_spice_for_spectre()` in `flow netlist` (see Step 2).

### 4. Connect module configuration for supplies

**Resolved.** `rout=0` works but must be per-net, not global.

- `ams_dms_simug.pdf` p.93/98: `rout=0` creates an ideal voltage source
  (zero impedance). But with UCM, setting `rout=0` globally **disables
  bidirectional signal operation for ALL connect modules** in the scope.
  Use per-net targeting: `ie net=top.i1.i2.vdd rout=0`.
- `ams_dms_simug.pdf` p.80: `porttype=name ignore="vdd vss"` disconnects
  those ports from the digital domain entirely — the SPICE subcircuit's
  VDD/VSS pins stay in the analog domain, powered by Spectre `vsource`.
- `ams_dms_simkpns.pdf` CCR 115386: supply/ground sensitivity doesn't work
  in default discipline resolution mode — use `-detailed` instead.

**Plan**: re-test with `rout=0` on specific supply nets now that the circuit
bug is fixed. Fall back to `ignore` + Spectre `vsource` if needed.

---

## Step 1: Dependencies and tooling

**Python packages** (already added to `pyproject.toml`):
```toml
dependencies = [
    ...
    "cocotb",
    "cocotb-bus",
    "spyci",       # parse nutascii .raw files
    "vcdvcd",      # parse .vcd files
]
```

**Cadence tools** (sourced via `~/asiclab/eda/local/scripts/cadence_2024-25.sh`):
- `xrun` (Xcelium 24.03) — digital simulation + AMS elaboration
- `spectre` (Spectre 24.10) — analog solver
- `simvision` — waveform viewer (SST2/SHM native)

**Open-source viewers**:
- `bspwave` — reads `.vcd` (with `$var real`, not `$var wreal`) and nutascii `.raw`
- `gtkwave` — reads `.vcd` with `$var real` (no `$var wreal`, no `.raw` or SST2)

---

## Step 2: SPICE netlist format fixes for Spectre compatibility

HDL21's ngspice netlister produces SPICE that Spectre's parser can't always
read. The generated `.sp` files need post-processing:

1. **Title line**: First line must be a comment (SPICE convention — first line
   is always treated as title, even if it looks like a `.subckt`)
2. **Continuation lines**: Join `\n+ ` into single lines (Spectre's parser
   is stricter than ngspice about `+` continuation)
3. **Instance prefixes**: MOSFET instances must start with `M` (not `mm` as
   HDL21 generates)
4. **Quoted parameters**: Remove single quotes from values (`w='4.8u'` → `w=4.8u`)
5. **Subcircuit naming**: Use simple names (e.g. `comp`) not hashed names
   (`Comp_a427ac9f7a74...`)

Post-processing script (or integrate into `flow netlist`):
```python
def fix_spice_for_spectre(inpath: Path, outpath: Path, subckt_name: str):
    """Post-process HDL21 ngspice netlist for Spectre AMS compatibility."""
    with open(inpath) as f:
        text = f.read()

    # Join continuation lines
    text = re.sub(r'\n\+ ', ' ', text)

    # Extract just the .SUBCKT ... .ENDS block
    match = re.search(r'(\.SUBCKT\s.*?\.ENDS)', text, re.DOTALL)
    subckt = match.group(1)

    # Rename subcircuit
    subckt = re.sub(r'\.SUBCKT\s+\S+', f'.subckt {subckt_name}', subckt, count=1)
    subckt = subckt.replace('.ENDS', '.ends')

    # Fix instance prefixes: mm -> M
    subckt = re.sub(r'^mm', 'M', subckt, flags=re.MULTILINE)

    # Remove quotes from parameter values
    subckt = subckt.replace("'", "")

    # Write with title comment
    with open(outpath, 'w') as f:
        f.write(f"* {subckt_name} subcircuit\n")
        f.write(subckt + "\n")
```

**Verify:** Generated `.sp` file passes `xrun -ams` elaboration without parse errors.

---

## Step 3: AMS control file (.scs)

The `.scs` file configures the Spectre analog solver and defines the
analog/digital boundary. It is passed as a regular source file to `xrun`.

```spectre
// amscontrol.scs — passed as source file to xrun (name is arbitrary)
simulator lang=spectre

// PDK models
include "/eda/kits/TSMC/65LP/.../toplevel.scs" section=tt_lib
include "/eda/kits/TSMC/65LP/.../toplevel.scs" section=pre_simu

// Analog output format (nutascii for Python parsing)
saveOpt options save=allpub rawfmt=nutascii
save tb.i_comp.* depth=3

// Transient analysis
tran tran stop=340n

// AMS boundary configuration
amsd {
    config cell=comp use=spice    // implicit portmap — no Verilog stub needed
    ie vsup=1.2 rout=0            // connect module config: ideal voltage source
}
```

Key points:
- **No Verilog stub needed**: `config cell=comp use=spice` triggers implicit
  portmap. Xcelium auto-generates port bindings from the SPICE subcircuit.
- **`rout=0`**: Makes connect modules act as ideal voltage sources (zero
  impedance) so VDD/VSS can pass through without IR drop.
- **`rawfmt=nutascii`**: Produces `.raw` file parseable by `spyci` and
  viewable in SimVision (via auto-translation to SST2).
- **Alternative**: Use `rawfmt=sst2` for native SimVision viewing, or add
  SHM probing via Tcl input for unified analog+digital in one database.

---

## Phase 1: Prototype verification (scratch/test* directories)

Work backward-to-forward, verifying each layer of the system before adding
the next. All prototype work lives in `scratch/test*/` directories.

---

### Step 4: Fix comparator netlist generator (`scratch/test1`)

Fix the HDL21 comparator netlist generator so it produces correct SPICE.
Verify by generating both the DUT subcircuit and a SPICE testbench, then
running a standalone Spectre simulation.

1. Fix `flow netlist --scope dut` to produce a clean `.subckt` (Step 2 fixes)
2. Fix `flow netlist --scope sim` to produce a self-contained SPICE testbench
   (Vpwl/Vpulse sources, transient analysis, PDK model includes)
3. Run `spectre comp_sim.sp` and verify the comparator toggles correctly
4. Parse the `.raw` output to confirm expected waveforms

**Pass criterion**: standalone Spectre simulation shows correct comparator
switching with the fixed netlist. No Xcelium or Verilog involved yet.

---

### Step 5: Xcelium + Spectre AMS with Verilog testbench (`scratch/test2`)

Replace the SPICE test signal generation with a Verilog testbench. The
Verilog testbench drives analog inputs via `real` variables → `wreal` nets,
and the `.scs` control file handles the AMS boundary.

**Testbench pattern** — `real` variables drive `wreal` nets at the boundary:
```verilog
`timescale 1ns/1ps

module tb;
    reg clk_reg;
    wire clk, clkb;
    assign clk = clk_reg;
    assign clkb = ~clk_reg;

    initial begin
        clk_reg = 0;
        forever #5 clk_reg = ~clk_reg;
    end

    // Real variables (cocotb-accessible, VCD-compatible)
    real inp_val, inn_val, vdd_val, vss_val;

    // Wreal nets at AMS boundary (connect modules insert here)
    wreal inp, inn, vdd, vss;
    assign inp = inp_val;
    assign inn = inn_val;
    assign vdd = vdd_val;
    assign vss = vss_val;

    // Real mirrors for VCD logging (no wreal in VCD)
    real inp_r, inn_r, vdd_r, vss_r;
    always @(inp) inp_r = inp;
    always @(inn) inn_r = inn;
    always @(vdd) vdd_r = vdd;
    always @(vss) vss_r = vss;

    // Digital outputs
    wire outp, outn;

    // SPICE instance
    comp i_comp (
        .inp(inp), .inn(inn),
        .outp(outp), .outn(outn),
        .clk(clk), .clkb(clkb),
        .vdd(vdd), .vss(vss)
    );

    // Inline stimulus (replaced by cocotb in Step 7)
    initial begin
        vdd_val = 1.2; vss_val = 0.0;
        inp_val = 0.605; inn_val = 0.595;
    end

    // Selective VCD dump — only real mirrors + digital (no wreal)
    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, clk_reg, clk, clkb, outp, outn,
                  inp_r, inn_r, vdd_r, vss_r);
    end

    initial begin
        #340;
        $finish;
    end
endmodule
```

**Signal type chain**: cocotb/Verilog → `real` var → `assign` → `wreal` net
→ connect module → `electrical` (SPICE).

**Run command**:
```bash
xrun -ams tb.v comp.sp amscontrol.scs \
    -timescale 1ns/1ps -ams_ucm -access +rwc \
    -input "@run; exit"
```

**Verify**:
- `waves.vcd` contains only `$var real` entries (no `$var wreal`) — open in
  gtkwave or bspwave to confirm
- `comp.raw` (nutascii) contains internal SPICE node waveforms
- Comparator output toggles correctly
- VDD/VSS reach the SPICE subcircuit correctly — resolve `rout=0` per-net
  vs `ignore` + Spectre `vsource` (see Q4)

**Pass criterion**: same comparator behavior as Step 4, but driven from
Verilog. VCD files readable by gtkwave and bspwave without post-processing.

---

### Step 6: Add analog probes for internal signals (`scratch/test3`)

Same configuration as Step 5, but add `$cds_get_analog_value` probes to
expose internal comparator signals as `real` variables in the VCD.

**Probe module** (Cadence-specific, reusable across designs):
```verilog
module analog_probe();
    var string node_to_probe = "<unassigned>";

    // Voltage probe — toggled to capture a reading
    logic probe_voltage_toggle = 0;
    real voltage;

    always @(probe_voltage_toggle) begin
        if ($cds_analog_is_valid(node_to_probe, "potential")) begin
            voltage = $cds_get_analog_value(node_to_probe, "potential");
        end else begin
            voltage = 1.234567;
            $display("%m: Warning: node_to_probe=%s is not valid", node_to_probe);
        end
    end

    // Current probe (same pattern)
    logic probe_current_toggle = 0;
    real current;

    always @(probe_current_toggle) begin
        if ($cds_analog_is_valid(node_to_probe, "flow")) begin
            current = $cds_get_analog_value(node_to_probe, "flow");
        end else begin
            current = 1.234567;
            $display("%m: Warning: node_to_probe=%s is not valid for current",
                     node_to_probe);
        end
    end
endmodule
```

**Testbench additions** (add to `tb` module from Step 5):
```verilog
// Instantiate the probe
analog_probe i_analog_probe ();

// Periodic sampling of an internal node (for VCD logging without cocotb)
real latch_p_r;
initial begin
    i_analog_probe.node_to_probe = "tb.i_comp.latch_p";
    forever begin
        #1;  // sample every 1ns
        i_analog_probe.probe_voltage_toggle = ~i_analog_probe.probe_voltage_toggle;
        #0;  // let the always block execute
        latch_p_r = i_analog_probe.voltage;
    end
end
```

Add `latch_p_r` (and any other probed signals) to the `$dumpvars` list.

**Verify**:
- Internal SPICE node values appear as `$var real` traces in the VCD
- Values match what the `.raw` file shows for the same nodes
- Probe works for multiple nodes by changing `node_to_probe` string

**Pass criterion**: internal analog signals visible in gtkwave/bspwave
via VCD, matching the nutascii `.raw` data.

---

### Step 7: cocotb-driven stimulus (`scratch/test4`)

Remove the inline Verilog stimulus and drive everything from a cocotb test.
Use cocotb's Python runner in direct mode (no pytest).

#### 7a. Python runner approach (primary)

The runner's `Xcelium` class splits into `xrun -elaborate` (build) then
`xrun -R` (test). AMS flags go in `build_args` so they're present during
elaboration; the `-R` step runs from the elaborated snapshot.

```python
# flow/scans/simulate.py
from pathlib import Path
from cocotb_tools.runner import get_runner

def run_ams_cocotb(
    sources: list[Path],
    spice_files: list[Path],
    ams_control: Path,
    test_module: str,
    top_level: str = "tb",
    sim_build: Path = Path("sim_build"),
):
    """Launch Xcelium AMS co-simulation with cocotb via the Python runner."""
    runner = get_runner("xcelium")

    # AMS flags go in build_args (present during -elaborate step)
    ams_build_args = [
        "-discipline", "logic",
        "-amsconnrules", "ConnRules_full_fast",
        "-iusldno",
        str(ams_control),          # .scs file as positional arg
        *[str(f) for f in spice_files],
    ]

    runner.build(
        sources=[str(s) for s in sources],
        hdl_toplevel=top_level,
        build_dir=str(sim_build),
        build_args=ams_build_args,
        always=True,
    )

    runner.test(
        hdl_toplevel=top_level,
        test_module=test_module,
        test_dir=str(sim_build),
        waves=True,
    )
```

**cocotb test with direct invocation**:
```python
import cocotb
from cocotb.triggers import Timer

async def probe_voltage(dut, node_path):
    """Read voltage of any internal analog node via the HDL probe."""
    dut.i_analog_probe.node_to_probe.value = node_path
    dut.i_analog_probe.probe_voltage_toggle.value = \
        ~dut.i_analog_probe.probe_voltage_toggle.value
    await Timer(1, units="ps")
    return float(dut.i_analog_probe.voltage.value)

@cocotb.test()
async def test_comp_threshold(dut):
    """Drive comparator from cocotb and verify output."""
    dut.vdd_val.value = 1.2
    dut.vss_val.value = 0.0
    dut.inp_val.value = 0.605
    dut.inn_val.value = 0.595
    await Timer(340, units="ns")

    # Read internal node via probe
    vlatch = await probe_voltage(dut, "tb.i_comp.latch_p")
    assert dut.outp.value == 1

if __name__ == "__main__":
    from flow.scans.simulate import run_ams_cocotb
    from pathlib import Path

    run_ams_cocotb(
        sources=[Path("tb.v"), Path("analog_probe.v")],
        spice_files=[Path("comp.sp")],
        ams_control=Path("amscontrol.scs"),
        test_module=__name__,
    )
```

The testbench Verilog is the same as Step 5/6 but with the `initial` stimulus
block removed — cocotb sets `inp_val`, `inn_val`, `vdd_val`, `vss_val` at
runtime.

#### 7b. Single-pass fallback (if two-step fails for AMS)

cocotb's Makefile flow uses a single `xrun` call (no `-elaborate`/`-R` split),
which is proven to work for AMS (the `mixed_signal` regulator example). If the
Python runner's two-step flow doesn't handle AMS correctly (e.g. if the Spectre
transient analysis isn't captured in the elaborate snapshot), fall back to a
thin wrapper that mimics the Makefile's single-pass invocation:

```python
# flow/scans/simulate.py (fallback)
import subprocess, os, sys, sysconfig

def run_ams_cocotb_singlepass(
    sources: list[Path],
    spice_files: list[Path],
    ams_control: Path,
    test_module: str,
    top_level: str = "tb",
):
    """Single-pass xrun with cocotb VPI — mimics Makefile.xcelium."""
    import cocotb_tools.config
    vpi_lib = cocotb_tools.config.lib_name_path("vpi", "xcelium")
    python_lib_dir = sysconfig.get_config_var("LIBDIR")

    cmd = [
        "xrun",
        *[str(s) for s in sources],
        *[str(f) for f in spice_files],
        str(ams_control),
        "-timescale", "1ns/1ps",
        "-discipline", "logic",
        "-amsconnrules", "ConnRules_full_fast",
        "-iusldno",
        "-access", "+rwc",
        "-loadvpisim", f"{vpi_lib}:vlog_startup_routines_bootstrap",
        "-licqueue",
    ]

    env = os.environ.copy()
    env.update({
        "COCOTB_TEST_MODULES": test_module,
        "COCOTB_TOPLEVEL": top_level,
        "MODULE": test_module,
        "TOPLEVEL": top_level,
        "TOPLEVEL_LANG": "verilog",
        "PYGPI_PYTHON_BIN": sys.executable,
        "LD_LIBRARY_PATH": f"{python_lib_dir}:{env.get('LD_LIBRARY_PATH', '')}",
    })

    subprocess.run(cmd, env=env, check=True)
```

#### Notes

**Critical flags**:
- `-iusldno` — prevents Xcelium from overriding `LD_LIBRARY_PATH`
  (which breaks cocotb's embedded Python)
- `-discipline logic` — sets default discipline for unresolved nets
- `-amsconnrules ConnRules_full_fast` — enables E2R/R2E/Bidir connect modules
- `PYGPI_PYTHON_BIN` — tells cocotb which Python interpreter to embed
- Do NOT set `PYTHONHOME` — conflicts with Xcelium's environment

**Pass criterion**: cocotb drives all stimulus, reads outputs and internal
nodes. Same waveform results as Steps 5/6 but with no inline Verilog
stimulus. Runs via `python test_comp.py` (direct) or `uv run flow simulate`.

---

## Phase 2: Integration (after prototyping is proven)

Steps below build on the verified prototype from Phase 1. File locations
move from `scratch/test*/` to `flow/` and `design/` as appropriate.

---

### Step 8: HDL21 scope=cosim netlist generation

Add `--scope cosim` to `flow netlist` to generate AMS-ready files.
For Xcelium AMS, this means:

| Scope | Produces | Purpose |
|-------|----------|---------|
| `dut` | `comp.sp` | Subcircuit only |
| `sim` | `comp.sp` + `tb_comp.sp` | Self-contained SPICE (Vpwl/Vpulse sources) |
| `cosim` | `comp.sp` + `amscontrol.scs` | AMS co-sim (amsd block + model includes) |

**No Verilog stub** — Xcelium auto-generates from the SPICE subcircuit.
**No `Vexternal`** — connect modules handle domain crossing.

The `cosim` scope generates the `.scs` AMS control file:
```python
def generate_ams_control(
    subckt_name: str,
    pdk_model_path: str,
    pdk_corner: str,
    tran_stop: str,
    output_path: Path,
    save_depth: int = 3,
):
    lines = [
        f"// AMS control file for {subckt_name}",
        "simulator lang=spectre",
        "",
        f'include "{pdk_model_path}" section={pdk_corner}',
        "",
        "saveOpt options save=allpub rawfmt=nutascii",
        f"save tb.i_{subckt_name}.* depth={save_depth}",
        "",
        f"tran tran stop={tran_stop}",
        "",
        "amsd {",
        f"    config cell={subckt_name} use=spice",
        "    ie vsup=1.2 rout=0",
        "}",
    ]
    output_path.write_text("\n".join(lines) + "\n")
```

Also applies `fix_spice_for_spectre()` from Step 2 to the generated `.sp`.

---

### Step 9: Post-simulation analysis in Python

Parse `.raw` and `.vcd` files into numpy arrays for analysis and plotting.

```python
import numpy as np
from vcdvcd import VCDVCD

def parse_spectre_nutascii(path):
    """Parse Spectre nutascii .raw file into dict of numpy arrays."""
    with open(path) as f:
        text = f.read()
    header, data_text = text.split('Values:\n', 1)

    var_names = ['time']
    for line in header.split('\n'):
        parts = [p for p in line.strip().split('\t') if p]
        if len(parts) >= 3 and parts[0].isdigit():
            var_names.append(parts[1])

    n_vars = len(var_names)
    all_values = []
    for line in data_text.strip().split('\n'):
        for p in line.strip().split():
            try:
                all_values.append(float(p))
            except ValueError:
                pass

    stride = n_vars + 1  # +1 for point index
    n_pts = len(all_values) // stride
    data = np.zeros((n_pts, n_vars))
    for i in range(n_pts):
        data[i, :] = all_values[i * stride + 1 : i * stride + 1 + n_vars]

    return {name: data[:, j] for j, name in enumerate(var_names)}
```

---

### Step 10: Scan definitions (shared between sim and measure)

Scans define stimulus and collection, agnostic of sim vs hardware:

```python
class ScanBase:
    scan_id = None
    def configure(self, frida, daq, **kwargs):
        raise NotImplementedError
    def run(self, frida, daq, **kwargs):
        raise NotImplementedError
```

For integration tests (full FPGA + chip + analog):
- Scan code calls `daq["awg"].set_voltage_high(0.6)` to set stimulus
- Calls `frida.run_conversions()` to trigger and read back
- Same code for hardware (SiTcp + Serial) and simulation (SiSim + SerialSim)

For block-level characterization (standalone Xcelium AMS):
- Generate Verilog testbench with inline stimulus (PWL or stepping)
- Run `xrun -ams` without cocotb
- Parse `.raw` and `.vcd` offline

---

### Step 11: Basil contributions (for integration test path)

The `flow simulate` CLI (Step 7) handles cocotb + Xcelium AMS launching
directly. Basil contributions are needed only for integration tests that
use the full FPGA + chip + analog path via SiSim/SerialSim.

**`libs/basil/basil/TL/SerialSim.py`** — new TL for mocking instruments.
**`libs/basil/basil/utils/sim/AnalogDriver.py`** — SIMULATION_MODULE for
driving `wreal` ports via `real` variables (see Step 5 signal chain).

---

## Output format strategy

| Format | Analog internals | Digital signals | Boundary analog | Viewer |
|--------|-----------------|-----------------|-----------------|--------|
| nutascii `.raw` | Yes | No | At boundary | SimVision, bspwave, Python |
| `.vcd` (with `real` mirrors) | No | Yes | Yes (`$var real`) | gtkwave, bspwave, Python (`vcdvcd`) |
| SST2 `.shm` | Yes (with probe) | Yes | Yes | SimVision (native) |

**Recommended approach**:
- Use **VCD + nutascii** for Python-parseable output and open-tool viewing
- Testbench mirrors `wreal` → `real` with selective `$dumpvars` (Step 5),
  so VCD contains only standard `$var real` — no `sed` post-processing needed
- Use **SHM probing** when you need unified analog+digital in SimVision

---

## Open issues

1. ~~**cocotb + Xcelium AMS output reading**~~: **Resolved.** VPI is
   digital-only; analog signals need HDL bridges. Use `real` mirror
   variables for boundary signals (Step 5) and `analog_probe` with
   `$cds_get_analog_value` for internal nodes (Step 6).

2. **cocotb Python runner + AMS**: The runner's two-step flow
   (`xrun -elaborate` then `xrun -R`) is unproven for AMS. Try with
   AMS flags in `build_args` first (Step 7a). If it fails, use the
   single-pass fallback (Step 7b) which mirrors the proven Makefile flow.

3. **SPICE netlist format**: HDL21's ngspice netlister output needs
   post-processing for Spectre compatibility. Integrate
   `fix_spice_for_spectre()` into `flow netlist` (Step 2).

4. ~~**VCD wreal compatibility**~~: **Resolved.** Mirror `wreal` → `real`
   in testbench with selective `$dumpvars` (Step 5). VCD contains only
   standard `$var real` entries — compatible with gtkwave, bspwave, and
   `vcdvcd` without post-processing.

5. **Supply connect module re-test**: Re-test `rout=0` on per-net basis
   with the fixed comparator circuit. Fall back to `ignore` + Spectre
   `vsource` if needed (see Q4 above).

---

## File summary

| File | Action |
|------|--------|
| `pyproject.toml` | Add `spyci`, `vcdvcd` deps; remove `spicebind` |
| `flow/circuit/netlist.py` | Add `fix_spice_for_spectre()`, `generate_ams_control()` |
| `flow/cli.py` | Add `--scope cosim` (generates .scs + fixed .sp) |
| `flow/comp/subckt.py` | Already fixed: reset device gate, output buffer refactor, MosType |
| `flow/scans/__init__.py` | ScanBase class + scan registry |
| `flow/scans/simulate.py` | Xcelium AMS launcher via cocotb runner |
| `flow/scans/measure.py` | Hardware Dut(map_fpga.yaml) setup |
| `flow/scans/host.py` | Frida class (moved from daq/host/) |
| `flow/scans/map_sim.yaml` | Basil config with SiSim + SerialSim |
| `flow/scans/map_fpga.yaml` | Basil config for hardware |
| `scratch/test*/` | Prototype testbenches, probes, cocotb tests |
| `libs/basil/basil/TL/SerialSim.py` | New basil TL for instrument mocking |
| `libs/basil/basil/utils/sim/AnalogDriver.py` | SIMULATION_MODULE for wreal |
