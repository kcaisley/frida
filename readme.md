# FRIDA: Fast Radiation Imaging Digitizer Array

> [!WARNING]
> This project is currently under very active development, and is subject to change.

Frame-based radiation detectors with integrating front-ends are especially well-suited for applications like electron microscopy and X-ray imaging, where hit rates are high, spatial resolution should be maximized with simple pixels, and energy resolution is needed, but particles need not be individually discriminated in time, space, or spectrum. In an experimental setting, fast frame rates allow for real-time in-situ observations. Potential subjects include rapid chemical processes, molecular dynamics of proteins, crystal nucleation and growth, material phase transitions, thermal conductivity, charge transfer, and mechanical strain.

This project pursues the possibility of a single-reticle array larger than 1 Mpixel with a continuous frame rate surpassing 100,000 fps. For the conjunction of these two specifications to be met, one must have a compact and power-efficient bank of column-parallel data converters, which at 10–12 bit resolution churn out data at a rate in excess of 1000 Gbps. To fit within the constraints of a chip bottom, the converter fabric must respect a restricted metric of 1 W/cm² while exceeding a 5 ksps/µm² sampling rate density. Successive-approximation ADCs are identified as the optimal choice, and various topologies and techniques will be analyzed to meet our goals.

![](docs/images/arch.png)

Seen below is the initial prototype, designed in 65nm and measuring 1x1 mm. On the prototype are 16 ADCs, each measuring 60x60um. The tapeout was submitted in Oct 2025, and will be tested upon arrival this Spring 2026.

![FRIDA Top Level](docs/images/frida_top.png)

## Setup

The FRIDA analog design flow uses a Python-based netlist generation system that creates parameterized subcircuits and testbenches, runs SPICE simulations, and analyzes results.

Run `make setup` to check dependencies and install missing packages.

This project is a "workspace", and relies on a mixture of tools (mostly open, some commercial) which don't all have a decent Python interfance. Therefore 'make' fufills the needs better than a `requirements.txt` or `pyproject.toml` file.

## Flow commands

Generate parameterized subcircuit netlists from block definitions:

```bash
make subckt cell=<cellname> [debug=1]
```

Input: Block definition in `blocks/[cell].py` containing:
- `subckt` struct with topology parameters, device parameters, and sweep specifications
- Optional `generate_topology()` function for dynamic topologies

Output: `results/[cell]/subckt/`
- `[cell]_[tech]_[hash].sp` - SPICE subcircuit netlists
- `[cell]_[tech]_[hash].json` - Netlist metadata
- `files.json` - File tracking database

Process:
- Topology Expansion: `expand_topo_params()` creates cartesian product of `topo_params`, calls `generate_topology()` to compute ports/devices
- Device Parameter Expansion:** `expand_dev_params()` creates cartesian product of tech, inst_params, dev_params
- Maps generic device types to technology-specific models
- Writes SPICE and JSON files, updates db.json

Generate testbenches that reference the subcircuit variants:

```bash
make tb cell=<cellname> [debug=1]
```

Input: Block definition `blocks/[cell].py` containing:
- `tb` struct with testbench devices, analyses, corner/temp sweeps, and optional `topo_params`
- Optional `generate_tb_topology()` function for dynamic testbenches

Output: `results/[cell]/tb/`
- `[cell]_[tech]_[hash]_[corner]_[temp].sp` - SPICE testbench netlists
- `[cell]_[tech]_[hash]_[corner]_[temp].json` - Testbench metadata

Process:
- Reads `files.json` to find all generated subcircuits
- For each subcircuit, generates testbenches across corner × temp combinations
- Matches testbench topology to subcircuit using `topo_params`
- Auto-adds includes (from files.json paths), libs, options, save statements
- Updates files.json with testbench paths

## Netlist Structs

The netlist schema provides a way to describe many different combinations of subcircuits and testbenches withou having to write procedural code.

Here is an example subcircuit netlist struct:

```python
subckt = {
    "cellname": "comp",                    # Cell name
    "ports": {},                           # Port definitions (or empty for dynamic)
    "devices": {},                         # Device instances (or empty for dynamic)
    "tech": ["tsmc65", "tsmc28"],          # Technologies to generate
    "topo_params": {                       # Topology parameters (optional)
        "param_A": [val1, val2],           # Cartesian product in Stage 1
    },
    "dev_params": {                        # Device defaults (applied last)
        "nmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
        "pmos": {"type": "lvt", "w": 1, "l": 1, "nf": 1},
    },
    "inst_params": [                       # Instance overrides (applied before dev_params)
        {"devices": ["MN1", "MN2"], "w": [20, 40], "l": [1, 2]},
    ]
}
```

To generate the ports and devices list based on topology paramters, we can write a function called `generate_topology()`:

```python
def generate_topology(**topo_params) -> tuple[dict, dict]:
    """Generate (ports, devices) for given topo_param combination."""
    # Compute ports and devices based on topo_params
    return ports, devices
```

Device parameters are applied in **priority order** (later values override earlier):

1. Topology-set values, from `generate_topology()` using `topo_params`, are never overwritten
2. `inst_params`, are applied to specific device instances
3. `dev_params` - are applied last as defaults to all devices of matching type

All list-valued parameters create cartesian products. For example `tech: ["tsmc65", "tsmc28"]` × `dev_params.nmos.w: [1, 2]` yeilds 4 variants.

To simulate a circuit, you also can (and should!) create a corresponding tesbench netlist struct, with it's generation function:

```python
tb = {
    "devices": {                           # Testbench devices (or empty for dynamic)
        'Vvdd': {'dev': 'vsource', ...},
        'Xdut': {'dev': 'cellname', ...}   # References subcircuit
    },
    "corner": ["tt", "ss", "ff"],          # Process corners
    "temp": [27, -40, 125],                # Temperatures
    "topo_params": {                       # For matching with subcircuits (optional)
        "switch_type": ["nmos", "pmos"]
    },
}

def generate_tb_topology(**topo_params) -> tuple[dict, dict]:
    """Generate testbench devices for given topo_param combination."""
    return {}, devices  # Ports always empty for top-level TB
```

## Output files and their management

The output of each flow step writes to a subdirectory inside `/results`:

```
results/
└── [cell]/
    ├── files.json             # File tracking database
    ├── subckt/
    │   ├── *.sp               # SPICE subcircuits
    │   └── *.json             # Subcircuit metadata
    └── tb/
        ├── *.sp               # SPICE testbenches
        └── *.json             # Testbench metadata
```

Furthermore, each cell has a `results/[cell]/files.json` automatically written and update to track all generated files. Here's a single entry:

```json
[
  {
    "cellname": "samp",
    "cfgname": "samp_nmos_tsmc65_dfe2429be6c3",
    "subckt_json": "subckt/samp_nmos_tsmc65_dfe2429be6c3.json",
    "subckt_spice": "subckt/samp_nmos_tsmc65_dfe2429be6c3.sp",
    "subckt_children": [],
    "tb_json": ["tb/samp_nmos_tsmc65_dfe2429be6c3_tt_27.json"],
    "tb_spice": ["tb/samp_nmos_tsmc65_dfe2429be6c3_tt_27.sp"],
    "sim_raw": [],
    "meas_db": null,
    "plot_img": []
  }
  // plus many more
]
```

Subsequent flow steps read files.json to find exact file paths without inferring from filenames. For example, testbench generation reads `subckt_spice` to add `.include` statements.

## Simulation Flow

Run Spectre simulations (automatically uses remote server if local host lacks Spectre):

```bash
make sim cell=<cellname> mode=<dryrun|single|all> [tech=<tech>] [debug=1]
```

- `mode=dryrun` - Show simulation plan only
- `mode=single` - Run first testbench only (for debugging)
- `mode=all` - Run all testbenches

```mermaid
flowchart LR
    A[tb/*.sp] --> B[simulate.py]
    B --> C{local Spectre?}
    C -->|yes| D[run locally]
    C -->|no| E[rsync to remote]
    E --> F[run on juno]
    F --> G[rsync back]
    D & G --> H[sim/*.raw]
```

## Measurement Flow

Extract measurements and generate plots from simulation results:

```bash
make meas cell=<cellname> [tech=<tech>] [corner=<corner>] [temp=<temp>] [no_plot=1] [debug=1]
```

```mermaid
flowchart LR
    A[sim/*.raw] --> B[measure.py]
    B --> C[eval expressions]
    C --> D[meas/*.json]
    C --> E[plot/*.pdf]
```

## Full Flow

Run the complete flow (subckt → tb → sim → meas) in one command:

```bash
make all cell=<cellname> [mode=single|all] [debug=1]
```

Defaults to `mode=single` for quick iteration.

## Clean Targets

```bash
make clean_subckt cell=<cellname>   # Remove subcircuit outputs
make clean_tb cell=<cellname>       # Remove testbench outputs
make clean_sim cell=<cellname>      # Remove simulation outputs
make clean_meas cell=<cellname>     # Remove measurement outputs
make clean_plot cell=<cellname>     # Remove plot outputs
make clean_all cell=<cellname>      # Remove all outputs for cell
```

Omit `cell=` to clean all cells.

## Analyses and Measures

Each cell defines its analyses and measures in `blocks/[cell].py`. These are evaluated by PyOPUS PerformanceEvaluator.

### Analyses Configuration

Analyses specify what simulations to run:

```python
analyses = {
    # Standard transient analysis
    "tran": {
        "head": "spectre",
        "modules": ["tb"],
        "command": "tran(stop=5.5e-6)",
        "saves": [
            "v(['in+', 'in-', 'out+', 'out-', 'clk'])",
            "i(['Vvdd'])"
        ]
    },
    # Monte Carlo wrapped transient (uses foundry mismatch models)
    "mc_tran": {
        "head": "spectre",
        "modules": ["tb", "mc"],  # Include MC models from PDK
        "command": "'montecarlo numruns=10 seed=12345 variations=mismatch savefamilyplots=yes { inner_tran tran stop=5.5e-6 }'",
        "saves": [
            "v(['in+', 'in-', 'out+', 'out-', 'clk'])",
            "i(['Vvdd'])"
        ]
    }
}
```

### Measures Configuration

Measures define scalar values extracted from simulation waveforms:

```python
measures = {
    "offset_mV": {
        "analysis": "tran",
        "expression": "m.comp_offset_mV(v, scale, 'in+', 'in-', 'out+', 'out-')",
    },
    "delay_ns": {
        "analysis": "tran",
        "expression": "m.comp_delay_ns(v, scale, 'clk', 'out+', 'out-')",
    },
    "power_uW": {
        "analysis": "tran",
        "expression": "m.avg_power_uW(v, i, scale, 'Vvdd')",
    },
}
```

The expression has access to:
- `v(node)` - Returns voltage waveform array for a node
- `i(source)` - Returns current waveform array for a source
- `scale()` - Returns the time axis array
- `m` - The `flow/expression.py` module with measurement functions
- `np` - NumPy for array operations

Custom measurement functions are defined in `flow/expression.py` and should return a single scalar value.

## Monte Carlo Measurement Extraction

For Monte Carlo simulations, the measurement system automatically handles multiple runs and computes statistics:

```mermaid
flowchart LR
    A[MC raw file] --> B[per-run eval]
    B --> C[N scalar values]
    C --> D[mean/std/min/max]
```

The same measure expressions work unchanged for both deterministic and MC simulations. For MC, the output includes statistics:

```json
{
  "offset_mV": {
    "mean": 0.45,
    "std": 1.2,
    "min": -1.5,
    "max": 2.3,
    "values": [2.3, -1.1, 0.8, ...],
    "numruns": 10
  }
}
```

The MC models (mismatch, process variation) come from the foundry PDK and are automatically included when an analysis specifies `"modules": ["tb", "mc"]`.

## Past Designs vs Current Target

The table below compares previous ADC designs with the current FRIDA target, highlighting improvements in resolution, speed, area, and energy efficiency. Notable advancements include higher conversion rates and lower power consumption per ADC, supporting the project's goal of scalable, high-performance digitizer arrays.

| Design                  | DCD v1      | CoRDIA     | M          | H           | F           |
|-------------------------|-------------|------------|------------|-------------|-------------|
| Design resolution       | 8-bit       | 10-bit     | 8-bit      | 10-bit      | 12-bit      |
| ENOB                    | 8.3         | 8.8        | 8.0        | 9.5 ?       | 11.0 ?      |
| Conversion rate         | 6.25 MHz    | 2.5 MHz    | 4.5 MHz    | 10 MHz      | 10 MHz      |
| Dimensions of one ADC   | 40×55 μm²   | 80×330 μm² | 60×800 μm² | 15×100 μm²  | 50×50 μm²   |
| Area of one ADC         | 0.002 mm²   | 0.026 mm²  | 0.048 mm²  | 0.0015 mm²  | 0.0025 mm²  |
| Power of one ADC        | 960 μW      | 30 μW      | 700 μW     | 100 μW      | 200 μW ?    |
| FOM_csa (conv/sec/area) | 3125 Hz/μm² | 95 Hz/μm²  | 105 Hz/μm² | 5000 Hz/μm² | 5000 Hz/μm² |
| FOM_wal (J/conv-step)   | 487 fJ      | 26 fJ      | 608 fJ     | 14 fJ       | 10 fJ       |

## Additional software

The following are also necessary in `$PATH`, using a mixture of `oss-cad-suite` or `apt` or `dnf` installs from distribution repos:

```bash
which klayout ngspice iverilog vvp verilator yosys gtkwave
```

Ensure `spectre` is installed and available in your `$PATH`. This is the Cadence Spectre simulator, which is used for running simulations. It is available as part of the Cadence Virtuoso suite, which is a commercial EDA tool.

```bash
which spectre
```

I also plan to support `ngspice` version 45+, which when compiled depends on the following packages on Ubuntu 22 LTS:

```bash
sudo apt install bison flex libx11-6 libx11-dev libxaw7 libxaw7-dev libxmu-dev libxext6 libxext-dev libxft2 libxft-dev libfontconfig1 libfontconfig1-dev libxrender1 libxrender-dev libfreetype6 libfreetype-dev libreadline8 libreadline-dev

sudo ./compile_linux.sh
```

For waveform viewing, I've found some success using [`gaw`](https://www.rvq.fr/linux/gaw.php).

When producing raw binary files, ensure `utf_8` encoding is used for the plaintext section.

## Directory Structure

Finally, here's a overview of the project directories at large:

```
├── blocks/             # Cell definitions (subckt + tb + analyses + measures)
│   ├── inv.py
│   ├── nand2.py
│   ├── samp.py
│   ├── comp.py
│   ├── cdac.py
│   └── adc.py
├── flow/               # Flow scripts
│   ├── netlist.py      # Subcircuit and testbench generation
│   ├── simulate.py     # PyOPUS-based Spectre simulation
│   ├── measure.py      # Measurement extraction and plotting
│   ├── expression.py   # Custom measurement functions
│   └── common.py       # Shared utilities and techmap
├── results/            # Generated netlists and simulation data
│   └── [cell]/
│       ├── files.json  # File tracking database
│       ├── subckt/     # Generated subcircuit netlists
│       │   ├── *.sp
│       │   └── *.json
│       ├── tb/         # Generated testbench netlists
│       │   ├── *.sp
│       │   └── *.json
│       ├── sim/        # Simulation outputs (after make sim)
│       │   ├── *.scs   # PyOPUS-generated Spectre input
│       │   ├── *.log   # Simulation log
│       │   ├── *.raw   # Waveform data
│       │   └── *.pkl   # Pickled results
│       ├── meas/       # Measurement results (after make meas)
│       │   └── *.json
│       └── plot/       # Generated plots (after make meas)
│           ├── *.pdf
│           └── *.svg
├── docs/               # Documentation
├── logs/               # Flow execution logs
└── makefile            # Build targets
```
