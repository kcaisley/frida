# Plan: Mixed-Signal Co-Simulation (v2)

Uses Cadence Xcelium (digital) + Spectre (analog) via AMS Designer for
mixed-signal co-simulation, driven by cocotb/basil scan code.

## Pre-implementation questions

These need to be resolved before proceeding with the steps below.

### 1. cocotb + Xcelium AMS compatibility

cocotb can initialize inside Xcelium AMS (with `-iusldno` and `PYGPI_PYTHON_BIN`),
and can drive signals. However, A2D connect module outputs don't propagate to
VPI-visible `wire` signals — digital outputs read as constant 0 from cocotb,
despite working correctly in standalone `xrun` with `$monitor`.

- Is this a cocotb VPI polling issue (needs explicit `await` for AMS sync)?
- Does Xcelium AMS support `cbValueChange` callbacks on connect module outputs?
- Should we use `wreal` outputs instead of `wire` and read via `vpiRealNet`?
- Is there a Cadence support note about VPI + AMS interop?

### 2. wreal vs real for analog signals

Xcelium emits `$var wreal` in VCD files, which is a Cadence extension that
`bspwave` and other open tools can't parse. Using standard `real` instead
of `wreal` in the testbench would avoid this entirely.

Key questions (require Xcelium docs research):
- Do AMS connect modules insert correctly when a `real` variable (not `wreal`
  net) is connected to a SPICE instance `inout` port?
- The Cadence `sv_real` sample (p.20 of `top.sv`) showed `real vco_vin`
  connected to a `wreal` VCO port — but does it work when there is no
  intermediate `wreal` port, i.e. `real` directly to SPICE `inout`?
- The docs (p.431) say "if the net of built-in nettype is a singular net
  then the data type of the variable or expression must be a singular real"
  for port connections — does this mean `real` works at the AMS boundary?
- Does `real` support multiple drivers (needed for bidirectional SPICE ports)?
  `wreal` has resolution functions; `real` is single-driver.
- If `real` works: does cocotb read it via `vpiRealVar` (same as for Icarus)?
- Relevant Xcelium docs to check: `wreal.pdf`, `vpiref.pdf`, `svsim.pdf`,
  `ams_dms_simug.pdf` chapters on "Real Number Modeling" and
  "Wreal Interaction with Built-In Real Nettypes"

### 3. SPICE netlist format for Spectre's parser

HDL21's ngspice netlister produces files that Spectre can't always parse:
missing title line, `mm` instance prefix, `+` continuation lines, quoted
parameters, hashed subcircuit names.

- Should we fix this in HDL21/vlsirtools (add a Spectre-compatible SPICE mode)?
- Or post-process in `flow netlist` with a `fix_spice_for_spectre()` function?
- Or generate Spectre-native netlists (`.scs`) directly? The `--scope dut -f spectre`
  already works, but the full testbench (`--scope sim`) only works for Spectre format.

### 4. Connect module configuration for supplies

We tested two approaches for VDD/VSS:
- Pass through `wreal` + connect modules with `rout=0` (simpler, no `ignore`)
- Disconnect from Verilog (`.vdd(), .vss()`) + Spectre `vsource` (FAQ recommended)

Both approaches compiled and ran, but the comparator output didn't toggle in
either case (turned out to be a circuit bug in the reset device gate signal,
now fixed).

- With the circuit bug fixed, does `rout=0` on connect modules work correctly
  for VDD/VSS? (Need to re-test with the fixed comparator.)
- If not, do we need `porttype=name ignore="vdd vss"` + Spectre `vsource`?
  (This requires explicit `portmap`, preventing auto-generation.)

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
- `gtkwave` — reads `.vcd` only (no `.raw` or SST2 support in GTK4 version)

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

## Step 4: Verilog testbench with wreal signals

The testbench uses `wreal` for analog signals at the AMS boundary. Xcelium's
AMS connect modules (UCM) automatically convert between `wreal` and Spectre
`electrical` at SPICE instance ports.

```verilog
`timescale 1ns/1ps

module tb;
    // Clock (must be wire for SPICE inout port connection)
    reg clk_reg;
    wire clk, clkb;
    assign clk = clk_reg;
    assign clkb = ~clk_reg;

    initial begin
        clk_reg = 0;
        forever #5 clk_reg = ~clk_reg;
    end

    // Analog signals as wreal (AMS connect modules handle conversion)
    wreal inp, inn;
    wreal vdd, vss;

    assign inp = 0.605;
    assign inn = 0.595;
    assign vdd = 1.2;
    assign vss = 0.0;

    // Digital outputs (A2D connect module converts analog → digital)
    wire outp, outn;

    // SPICE instance — module name matches .subckt name in .sp file
    comp i_comp (
        .inp(inp), .inn(inn),
        .outp(outp), .outn(outn),
        .clk(clk), .clkb(clkb),
        .vdd(vdd), .vss(vss)
    );

    // VCD dump (use $var real for bspwave compat, not $var wreal)
    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, tb);
    end

    initial begin
        #340;
        $finish;
    end
endmodule
```

**Signal type rules**:
- `wreal` for analog values (inp, inn, vdd, vss) — connect modules bridge
  to Spectre electrical domain
- `wire` for digital outputs (outp, outn) — A2D connect module thresholds
  the analog voltage to digital 0/1
- `reg` cannot connect directly to SPICE `inout` ports — use `wire` with
  `assign` from `reg`

**VCD note**: Xcelium emits `$var wreal` which bspwave can't parse. Fix with:
```bash
sed 's/\$var wreal/$var real/g' waves.vcd > waves_fixed.vcd
```

---

## Step 5: Running the simulation (without cocotb)

For block-level characterization, run Xcelium AMS directly without cocotb.
The Verilog testbench contains inline stimulus.

```bash
source ~/asiclab/eda/local/scripts/cadence_2024-25.sh

xrun -ams \
    tb.v \
    comp.sp \
    amscontrol.scs \
    -timescale 1ns/1ps \
    -ams_ucm \
    -access +rwc \
    -input "@run; exit"
```

This produces:
- `comp.raw` — nutascii analog waveforms (all internal SPICE nodes)
- `waves.vcd` — digital waveforms (all Verilog signals including wreal)

For native SimVision viewing with unified analog+digital, use SHM probing:
```bash
xrun -ams \
    tb.v comp.sp amscontrol.scs \
    -timescale 1ns/1ps -ams_ucm -access +rwc \
    -input '@database -open waves -into waves.shm -default; \
            probe -create -database waves tb.* -depth all; \
            run; exit'
```

---

## Step 6: Post-simulation analysis in Python

Parse `.raw` and `.vcd` files into numpy arrays for analysis and plotting.

```python
import numpy as np
from spyci.spyci import load_raw
from vcdvcd import VCDVCD

# --- Analog data (internal SPICE nodes) ---
# Note: spyci may not parse Spectre's nutascii header directly.
# Use the manual parser for Spectre-flavored nutascii:

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

raw = parse_spectre_nutascii("comp.raw")
time = raw["time"]
vlatch_p = raw["tb.i_comp.latch_p"]

# --- Digital data (Verilog signals) ---
vcd = VCDVCD("waves.vcd")
clk_transitions = vcd["tb.clk"].tv       # list of (time_ps, "0"/"1")
outp_transitions = vcd["tb.outp"].tv
```

---

## Step 7: cocotb + Xcelium AMS integration (for scan-based tests)

cocotb can drive Xcelium AMS, but requires careful environment setup.
The key flags discovered through testing:

```python
import subprocess, os, sys, sysconfig

def run_xcelium_ams_with_cocotb(
    sources, spice_files, ams_control, test_module, top_level="tb"
):
    """Launch Xcelium AMS with cocotb VPI loaded."""
    import cocotb_tools.config
    vpi_lib = cocotb_tools.config.lib_name_path("vpi", "xcelium")
    python_lib_dir = sysconfig.get_config_var("LIBDIR")

    cmd = [
        "xrun", "-ams",
        *sources,
        *spice_files,
        ams_control,
        "-timescale", "1ns/1ps",
        "-ams_ucm",
        "-iusldno",              # prevent Xcelium from overriding LD_LIBRARY_PATH
        "-access", "+rwc",
        "-loadvpisim", f"{vpi_lib}:vlog_startup_routines_bootstrap",
        "-input", "@run; exit;",
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
        "PYTHONPATH": f".:{env.get('PYTHONPATH', '')}",
    })

    subprocess.run(cmd, env=env, check=True)
```

**Critical flags**:
- `-iusldno` — prevents Xcelium AMS from modifying `LD_LIBRARY_PATH`
  (which breaks cocotb's embedded Python)
- `-loadvpisim` (not `-loadvpi`) — loads VPI in simulation phase only
- `PYGPI_PYTHON_BIN` — tells cocotb which Python interpreter to embed
- Do NOT set `PYTHONHOME` — conflicts with Xcelium's environment

**Known issue**: cocotb initializes successfully and can drive signals, but
the A2D connect module outputs may not propagate correctly to VPI-visible
`wire` signals. The comparator output reads as constant 0. This needs
further investigation — the circuit works correctly without cocotb
(pure `xrun` with `$monitor` shows correct transitions).

**Workaround for now**: Use cocotb only for integration tests where you
read digital signals at the FPGA FIFO level (same as hardware). For
block-level analog characterization, use standalone `xrun` (Step 5)
and parse the `.raw` + `.vcd` files (Step 6).

---

## Step 8: HDL21 scope=cosim netlist generation

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

## Step 9: Scan definitions (shared between sim and measure)

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

## Step 10: Basil contributions (for integration test path)

If cocotb + Xcelium AMS compatibility is resolved:

**`libs/basil/basil/utils/sim/runner.py`** — modern cocotb runner wrapper:
```python
from cocotb_tools.runner import get_runner

def cocotb_run(sim="xcelium", sources=(), top_level="tb",
               test_module="basil.utils.sim.Test",
               includes=(), sim_args=(), extra_env=None):
    runner = get_runner(sim)
    runner.build(sources=[str(s) for s in sources],
                 hdl_toplevel=top_level,
                 includes=[str(i) for i in includes], always=True)
    runner.test(hdl_toplevel=top_level, test_module=test_module,
                test_args=list(sim_args), extra_env=extra_env or {})
```

Note: cocotb's Xcelium runner splits build/test into two `xrun` invocations,
but AMS needs everything in one pass. May need to bypass the runner and
call `xrun` directly (as in Step 7).

**`libs/basil/basil/TL/SerialSim.py`** — new TL for mocking instruments.
**`libs/basil/basil/utils/sim/AnalogDriver.py`** — SIMULATION_MODULE for
driving `wreal` ports. (Same concept as v1 plan, but drives `wreal` in
Xcelium instead of `real` in Icarus via spicebind.)

---

## Step 11: Output format strategy

| Format | Analog internals | Digital signals | wreal values | Viewer |
|--------|-----------------|-----------------|--------------|--------|
| nutascii `.raw` | Yes | No | At boundary | SimVision (translate), bspwave, Python (`spyci`) |
| `.vcd` | No | Yes | Yes (`$var wreal`) | SimVision (translate), bspwave (needs `wreal`→`real` sed), Python (`vcdvcd`) |
| SST2 `.shm` | Yes (with probe) | Yes | Yes | SimVision (native) |

**Recommended approach**:
- Use **VCD + nutascii** for Python-parseable output and open-tool viewing
- Use **SHM probing** when you need unified analog+digital in SimVision
- Post-process VCD with `sed 's/\$var wreal/\$var real/g'` for bspwave

---

## Step 12: Open issues

1. **cocotb + Xcelium AMS output reading**: cocotb can drive signals but
   A2D connect module outputs don't propagate to VPI-visible wires
   correctly. Digital outputs read as constant 0 from cocotb, despite
   working correctly in standalone xrun. Needs investigation.

2. **cocotb runner + AMS**: cocotb's Xcelium runner splits build/test,
   but AMS requires single-step `xrun`. Need to either bypass the runner
   or contribute AMS support to cocotb.

3. **SPICE netlist format**: HDL21's ngspice netlister output needs
   post-processing for Spectre compatibility. Should be integrated into
   `flow netlist` or a new Spectre-compatible netlister added to vlsirtools.

4. **VCD wreal compatibility**: Xcelium emits `$var wreal` which is
   non-standard. Need automated post-processing or a fix in Xcelium
   dump configuration.

---

## File summary

| File | Action |
|------|--------|
| `pyproject.toml` | Add `spyci`, `vcdvcd` deps; remove `spicebind` |
| `flow/circuit/netlist.py` | Add `fix_spice_for_spectre()`, `generate_ams_control()` |
| `flow/cli.py` | Add `--scope cosim` (generates .scs + fixed .sp) |
| `flow/comp/subckt.py` | Already fixed: reset device gate, output buffer refactor, MosType |
| `flow/scans/__init__.py` | ScanBase class + scan registry |
| `flow/scans/simulate.py` | Xcelium AMS launcher (replaces spicebind/Icarus) |
| `flow/scans/measure.py` | Hardware Dut(map_fpga.yaml) setup |
| `flow/scans/host.py` | Frida class (moved from daq/host/) |
| `flow/scans/map_sim.yaml` | Basil config with SiSim + SerialSim |
| `flow/scans/map_fpga.yaml` | Basil config for hardware |
| `design/daq/daq_tb.v` | Xcelium AMS testbench (wreal signals, no bus bridge) |
| `libs/basil/basil/utils/sim/runner.py` | Modern cocotb runner (xcelium) |
| `libs/basil/basil/TL/SerialSim.py` | New basil TL for instrument mocking |
| `libs/basil/basil/utils/sim/AnalogDriver.py` | SIMULATION_MODULE for wreal |
| `docs/xcelium_simvision_format_support.md` | Format support reference |
| `docs/tnoise.md` | Transient noise analysis reference |
