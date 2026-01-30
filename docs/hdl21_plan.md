# Plan: Bring alt/ to Feature Parity with blocks/flow

## Completed Tasks (All Done!)

- [x] Rename `calc_weights` → `_calc_weights` and move after main generator (cdac.py)
- [x] Create shared measure module (alt/measure.py)
- [x] Create pytest conftest.py with SimTestMode fixture (alt/conftest.py)
- [x] Move sim_options.py to common/ (alt/common/sim_options.py)
- [x] Consolidate testbench into samp.py (SampTb, SampTbParams, sim_input, test functions)
- [x] Consolidate testbench into comp.py (CompTb, CompTbParams, MCConfig, sim_input, sim_input_with_mc, test functions)
- [x] Consolidate testbench into cdac.py (CdacTb, CdacTbParams, sim_input, sim_input_tran, test functions)
- [x] Archive tests/ to throwaway/tests_archive/
- [x] Update alt/__init__.py exports (testbenches, measure functions, SimTestMode)
- [x] Fix Literal naming issue (use `_` for hs.Literal in @hs.sim decorators)

## Overview

The `/alt` directory has HDL21-based generators for samp, comp, and cdac with comprehensive topology support. This plan details the remaining work to achieve feature parity with the original `/blocks` + `/flow` methodology.

## User Requests (5 Items)

1. ✅ Rename `calc_weights` → `_calc_weights` and move after main generator
2. ✅ Put testbenches in same file as DUT (consolidate tests/ into block files) - samp.py, comp.py done
3. ✅ Separate simulation definition from post-processing (create shared measure module)
4. ✅ pytest-based execution (USBphy pattern - simtestmode fixture, no custom CLI)
5. ✅ Verify generic values → PDK-specific only at netlist time (already works this way)

## Current State

### What's Complete
- **Generators**: samp.py, comp.py, cdac.py with full topology support
- **PDK Abstraction**: base.py + generic.py with device selection
- **Parameters**: common/params.py with all enums, Pvt, SupplyVals
- **Testbenches**: tests/test_*.py with parameterized testbenches
- **Monte Carlo**: MCConfig and sim_input_with_mc() framework

### What's Missing
- Testbenches scattered in tests/ instead of with DUT
- No shared measure/expression module (each test file has stubs)
- No CLI entry point for running simulations
- Measurement extraction functions return NaN (placeholders)
- No actual simulator execution (all commented out)

---

## Target Architecture

```
alt/
├── __init__.py              # Package exports
├── conftest.py              # pytest config + SimTestMode fixture (NEW)
├── samp.py                  # Sampler: generator + testbench + test_* functions
├── comp.py                  # Comparator: generator + testbench + test_* functions
├── cdac.py                  # CDAC: generator + testbench + test_* functions
├── adc.py                   # ADC: hierarchical generator + testbench (NEW)
├── measure.py               # Shared measurement/expression functions (NEW)
├── sim.py                   # Simulation infrastructure (existing)
├── common/
│   ├── __init__.py
│   ├── params.py            # Shared params, enums, Pvt
│   └── sim_options.py       # Spectre config (move from tests/)
├── pdk/
│   ├── __init__.py          # PDK selector: set_pdk(), get_pdk()
│   ├── base.py              # Abstract FridaPdk with W_UNIT, L_UNIT, VDD_NOM
│   ├── generic.py           # Generic PDK (no scaling, pass-through)
│   ├── tsmc65.py            # TSMC 65nm: scaling + SupplyVals (NEW)
│   ├── sky130.py            # SkyWater 130nm (NEW)
│   └── tsmc28.py            # TSMC 28nm (NEW)
└── tests/                   # Archive to throwaway/
```

---

## Implementation Steps

### Step 1: Rename _calc_weights in cdac.py

**File:** `alt/cdac.py`

Move `calc_weights()` after the `Cdac` generator and rename to `_calc_weights()`:
- Update all internal calls: `calc_weights` → `_calc_weights`
- Functions affected: `is_valid_cdac_params()`, `get_cdac_weights()`
- Keep public wrappers `get_cdac_weights()` and `get_cdac_n_bits()` as API

---

### Step 2: Create Shared Measure Module

**New File:** `alt/measure.py`

Extract measurement functions from flow/expression.py, adapted for HDL21 SimResult:

```python
"""Shared measurement functions for FRIDA HDL21 generators."""
import numpy as np
from typing import Dict, Any, List, Tuple
import hdl21.sim as hs

# =============================================================================
# Waveform Helpers
# =============================================================================

def _find_crossings(signal: np.ndarray, time: np.ndarray,
                    threshold: float, rising: bool = True) -> List[float]:
    """Find interpolated crossing times."""
    ...

def _get_waveform(result: hs.SimResult, name: str) -> np.ndarray:
    """Extract waveform from SimResult."""
    return result.an[0].data[name]

def _get_time(result: hs.SimResult) -> np.ndarray:
    """Extract time array from SimResult."""
    return result.an[0].data["time"]

# =============================================================================
# Comparator Measurements
# =============================================================================

def comp_offset_mV(result: hs.SimResult, inp: str, inn: str,
                   outp: str, outn: str) -> float:
    """Extract input-referred offset from S-curve data."""
    ...

def comp_noise_sigma_mV(result: hs.SimResult, inp: str, inn: str,
                        outp: str, outn: str) -> float:
    """Extract input-referred noise sigma from S-curve width."""
    ...

def comp_delay_ns(result: hs.SimResult, clk: str, outp: str, outn: str) -> float:
    """Extract decision delay (clk edge to output crossing)."""
    ...

def comp_settling_ns(result: hs.SimResult, outp: str, outn: str,
                     tol: float = 0.01) -> float:
    """Extract settling time to within tolerance of final value."""
    ...

def comp_power_uW(result: hs.SimResult, vdd_src: str = "vvdd") -> float:
    """Extract average power consumption."""
    ...

# =============================================================================
# CDAC/ADC Measurements
# =============================================================================

def compute_inl_dnl(results: List[hs.SimResult], n_bits: int) -> Dict[str, Any]:
    """Compute INL/DNL from code sweep results."""
    ...

# =============================================================================
# Monte Carlo Statistics
# =============================================================================

def mc_statistics(values: List[float]) -> Dict[str, float]:
    """Compute mean, std, min, max from MC results."""
    return {
        "mean": np.mean(values),
        "std": np.std(values),
        "min": np.min(values),
        "max": np.max(values),
        "n": len(values),
    }
```

---

### Step 3: Consolidate Testbenches into Block Files

Move testbench generators from `tests/test_*.py` into their respective block files.

**Pattern for each block file:**

```python
# alt/samp.py

# =============================================================================
# GENERATOR (existing)
# =============================================================================

@h.paramclass
class SampParams:
    ...

@h.generator
def Samp(p: SampParams) -> h.Module:
    ...

def samp_variants(...) -> List[SampParams]:
    ...

# =============================================================================
# TESTBENCH (move from tests/test_samp.py)
# =============================================================================

@h.paramclass
class SampTbParams:
    pvt = h.Param(dtype=Pvt, desc="PVT conditions", default=Pvt())
    samp = h.Param(dtype=SampParams, desc="Sampler params", default=SampParams())

@h.generator
def SampTb(params: SampTbParams) -> h.Module:
    """Sampler testbench."""
    ...

def sim_input(params: SampTbParams) -> hs.Sim:
    """Create transient simulation for sampler characterization."""
    ...

# =============================================================================
# PYTEST TEST FUNCTIONS
# =============================================================================

def test_samp_netlist(simtestmode: SimTestMode):
    """Test sampler netlist generation."""
    ...

def test_samp_sim(simtestmode: SimTestMode):
    """Test sampler simulation."""
    ...
```

---

### Step 4: Use pytest-Based Test Execution (USBphy Pattern)

Instead of custom CLI in each file, use **pytest** with a `simtestmode` fixture:

**New File:** `alt/conftest.py`
```python
"""Pytest configuration for FRIDA HDL21 tests."""
import pytest
from enum import Enum

class SimTestMode(Enum):
    # Schematic/Simulation stages
    NETLIST = "netlist"  # HDL21 netlist only (no simulator needed)
    MIN = "min"          # One setting, one corner
    TYP = "typ"          # One corner, many settings
    MAX = "max"          # Full PVT sweep
    # Physical design stages (future)
    LAYOUT = "layout"    # gdsfactory layout generation
    DRC = "drc"          # KLayout DRC checks
    LVS = "lvs"          # Layout vs Schematic
    PNR = "pnr"          # OpenROAD place & route

def pytest_addoption(parser):
    parser.addoption(
        "--simtestmode",
        action="store",
        default="netlist",
        choices=[m.value for m in SimTestMode],
        help="Simulation/flow test mode",
    )

@pytest.fixture
def simtestmode(request) -> SimTestMode:
    """Get simulation test mode from command line."""
    mode_str = request.config.getoption("--simtestmode")
    return SimTestMode(mode_str)
```

**Test functions in block files:**
```python
# In alt/samp.py

def test_samp_netlist(simtestmode: SimTestMode):
    """Test sampler netlist generation."""
    if simtestmode == SimTestMode.NETLIST:
        for params in samp_variants():
            mod = Samp(params)
            h.netlist(mod, dest=io.StringIO())
        print(f"Generated {len(list(samp_variants()))} sampler netlists")

def test_samp_sim(simtestmode: SimTestMode):
    """Test sampler simulation."""
    if simtestmode == SimTestMode.NETLIST:
        # Just verify testbench netlist
        tb = SampTb(SampTbParams())
        h.netlist(tb, dest=io.StringIO())
    elif simtestmode == SimTestMode.MIN:
        # Run one quick simulation
        result = sim_input(SampTbParams()).run(sim_options)
        settling = extract_settling_ns(result)
        print(f"Settling time: {settling:.2f} ns")
    elif simtestmode in (SimTestMode.TYP, SimTestMode.MAX):
        # Run parameter sweep
        results = run_switch_type_sweep()
        for (st, vth), settling in results:
            print(f"{st.name}/{vth.name}: {settling:.2f} ns")
```

**Usage:**
```bash
# Netlist-only (fast, no Spectre needed)
pytest --simtestmode netlist alt/

# Quick sanity check (one sim)
pytest --simtestmode min alt/samp.py

# Full sweep (slow, needs Spectre)
pytest -n auto --simtestmode max alt/

# Run specific test
pytest --simtestmode typ alt/comp.py::test_comp_scurve
```

**Benefits over custom CLI:**
- Standard pytest discovery and execution
- Parallel execution with `pytest-xdist` (`-n auto`)
- Fixtures for shared setup (sim_options, PDK)
- Integrates with CI/CD pipelines
- No boilerplate argparse code in each file

---

### Step 5: Move sim_options.py

**Move:** `alt/tests/sim_options.py` → `alt/common/sim_options.py`

Update imports in block files accordingly.

---

### Step 6: Implement Actual Measurement Functions

Complete the placeholder implementations in `alt/measure.py`:

**Priority 1 - Comparator:**
- `comp_offset_mV()` - S-curve zero-crossing
- `comp_delay_ns()` - Clock-to-output delay
- `comp_settling_ns()` - Output settling time

**Priority 2 - CDAC:**
- `compute_inl_dnl()` - Linearity metrics from code sweep

**Priority 3 - Power/Statistics:**
- `comp_power_uW()` - Average supply current × voltage
- `mc_statistics()` - Already implemented in sim.py, move to measure.py

---

## Files to Modify

| File | Action | Description |
|------|--------|-------------|
| `alt/cdac.py` | Edit | Rename `calc_weights` → `_calc_weights`, move after Cdac |
| `alt/conftest.py` | Create | pytest config + extended SimTestMode fixture |
| `alt/measure.py` | Create | Shared measurement functions |
| `alt/samp.py` | Edit | Add testbench + test_* functions from tests/test_samp.py |
| `alt/comp.py` | Edit | Add testbench + test_* functions from tests/test_comp.py |
| `alt/cdac.py` | Edit | Add testbench + test_* functions from tests/test_cdac.py |
| `alt/adc.py` | Create | Hierarchical ADC with nested params (from throwaway/adc_procedural.py) |
| `alt/common/sim_options.py` | Move | From tests/sim_options.py |
| `alt/pdk/base.py` | Edit | Add W_UNIT, L_UNIT, VDD_NOM abstract properties |
| `alt/pdk/generic.py` | Edit | Implement pass-through (no scaling) |
| `alt/pdk/tsmc65.py` | Create | TSMC65 PDK with scaling + walker |
| `alt/pdk/sky130.py` | Create | Sky130 PDK with scaling + walker |
| `alt/pdk/__init__.py` | Edit | Add set_pdk(), get_pdk() functions |
| `alt/common/params.py` | Edit | Make SupplyVals a base class for PDK subclasses |
| `alt/tests/` | Archive | Move to throwaway/, keep as reference |
| `alt/__init__.py` | Edit | Update exports |

---

## Verification

### 1. Netlist Generation (no Spectre needed)
```bash
pytest --simtestmode netlist alt/
```

### 2. Single Block Test
```bash
pytest --simtestmode netlist alt/samp.py -v
pytest --simtestmode netlist alt/comp.py -v
pytest --simtestmode netlist alt/cdac.py -v
```

### 3. Quick Simulation Test (requires Spectre)
```bash
pytest --simtestmode min alt/samp.py::test_samp_sim
```

### 4. Full Sweep (parallel, requires Spectre)
```bash
pytest -n auto --simtestmode max alt/
```

### 5. Measure Module Unit Test
```bash
pytest alt/measure.py -v
```

---

## PDK Architecture with Dimension Scaling

### Generic Multipliers → Physical Dimensions

Generators use **generic multipliers** (w=4, l=2), PDK walkers convert to physical dimensions:

```python
# alt/pdk/base.py
from abc import ABC, abstractmethod

class FridaPdk(ABC):
    """Abstract base class for FRIDA PDK plugins."""

    # Dimension scaling - override in subclasses
    W_UNIT: h.Prefixed  # Minimum/unit width
    L_UNIT: h.Prefixed  # Minimum/unit length

    # Supply voltage - override in subclasses
    VDD_NOM: h.Prefixed  # Nominal supply voltage

    @property
    @abstractmethod
    def Nmos(self) -> h.ExternalModule: ...

    @property
    @abstractmethod
    def Pmos(self) -> h.ExternalModule: ...

    @abstractmethod
    def compile(self, src: h.Elaboratables) -> None:
        """Compile generic primitives to PDK-specific modules."""
        ...

    @abstractmethod
    def supply_vals(self, corner: Corner) -> "SupplyVals":
        """Get supply voltages for a corner."""
        ...
```

### PDK-Specific Implementations

```python
# alt/pdk/tsmc65.py
class Tsmc65Pdk(FridaPdk):
    W_UNIT = 420 * n      # 420nm minimum width
    L_UNIT = 60 * n       # 60nm minimum length
    VDD_NOM = 1200 * m    # 1.2V nominal

    # Supply voltage corners (±10%)
    class SupplyVals(SupplyVals):
        VDD_VALS: ClassVar[List] = [1080*m, 1200*m, 1320*m]

    # Device modules
    Nmos = h.ExternalModule(
        domain="tsmc65", name="nch_lvt",
        port_list=[...], paramtype=Tsmc65MosParams,
    )

    def compile(self, src):
        return Tsmc65Walker.walk(src)


# alt/pdk/sky130.py
class Sky130Pdk(FridaPdk):
    W_UNIT = 840 * n      # 840nm minimum width
    L_UNIT = 150 * n      # 150nm minimum length
    VDD_NOM = 1800 * m    # 1.8V nominal

    class SupplyVals(SupplyVals):
        VDD_VALS: ClassVar[List] = [1620*m, 1800*m, 1980*m]


# alt/pdk/tsmc28.py
class Tsmc28Pdk(FridaPdk):
    W_UNIT = 280 * n      # 280nm minimum width
    L_UNIT = 28 * n       # 28nm minimum length
    VDD_NOM = 900 * m     # 0.9V nominal

    class SupplyVals(SupplyVals):
        VDD_VALS: ClassVar[List] = [810*m, 900*m, 990*m]
```

### PDK Walker for Dimension Scaling

```python
# alt/pdk/tsmc65.py
class Tsmc65Walker(h.HierarchyWalker):
    """Convert generic primitives to TSMC65-specific modules with scaling."""

    def mos_params(self, params: PrimMosParams) -> Tsmc65MosParams:
        # Scale generic multipliers to physical dimensions
        w = (params.w or 1) * Tsmc65Pdk.W_UNIT
        l = (params.l or 1) * Tsmc65Pdk.L_UNIT
        return Tsmc65MosParams(w=w, l=l, m=params.mult or 1, nf=params.nf or 1)
```

### Usage in Generators

```python
# alt/comp.py - technology-independent
@h.generator
def Comp(p: CompParams) -> h.Module:
    pdk = get_pdk()

    # Generic multipliers - PDK scales to physical
    diff_n = pdk.Nmos(w=8, l=2)   # 8× min width, 2× min length
    load_p = pdk.Pmos(w=4, l=1)   # 4× min width, 1× min length
    ...
```

### PDK Selection at Runtime

```python
# alt/pdk/__init__.py
_current_pdk: Optional[FridaPdk] = None

def set_pdk(name: str):
    global _current_pdk
    pdks = {
        "generic": GenericPdk,
        "tsmc65": Tsmc65Pdk,
        "sky130": Sky130Pdk,
        "tsmc28": Tsmc28Pdk,
    }
    _current_pdk = pdks[name]()

def get_pdk() -> FridaPdk:
    return _current_pdk or GenericPdk()
```

---

## Hierarchical Design with Nested Parameters

### Pattern: Compose Child Paramclasses

For complex blocks like ADC that contain multiple child blocks (Samp, Comp, Cdac):

```python
# alt/adc.py

@h.paramclass
class AdcParams:
    # Top-level topology
    n_cycles = h.Param(dtype=int, desc="SAR cycles", default=12)
    n_adc = h.Param(dtype=int, desc="ADC resolution", default=10)

    # Child block params as nested paramclasses
    samp_p = h.Param(dtype=SampParams, desc="Sampler+ params", default=SampParams())
    samp_n = h.Param(dtype=SampParams, desc="Sampler- params", default=SampParams())
    comp = h.Param(dtype=CompParams, desc="Comparator params", default=CompParams())
    cdac = h.Param(dtype=CdacParams, desc="CDAC params", default=CdacParams())

@h.generator
def Adc(p: AdcParams) -> h.Module:
    # Derive child params from parent topology
    n_dac = p.n_adc - 1
    n_extra = p.n_cycles - p.n_adc
    cdac_p = dataclasses.replace(p.cdac, n_dac=n_dac, n_extra=n_extra)

    @h.module
    class Adc:
        ...
        samp_pos = Samp(p.samp_p)(din=vinp, ...)
        comp = Comp(p.comp)(inp=vdac_p, ...)
        cdac_pos = Cdac(cdac_p)(top=vdac_p, ...)
    return Adc
```

### Access/Modify Nested Params at Top Level

```python
from dataclasses import replace

# Create ADC with custom nested params
adc_params = AdcParams(
    n_adc=12,
    n_cycles=14,
    comp=CompParams(stages=CompStages.DOUBLE, diffpair_w=8),
    samp_p=SampParams(switch_type=SwitchType.TGATE, w=4),
)

# Modify just one nested param
variant = replace(adc_params, comp=replace(adc_params.comp, diffpair_w=16))
```

### Managing Parameter Explosion

**Strategy: Define sweep functions at multiple granularities**

```python
# alt/adc.py

def adc_variants_quick() -> List[AdcParams]:
    """Quick sweep - key architectural choices only."""
    variants = []
    for n_adc in [8, 10, 12]:
        for comp_stages in CompStages:
            variants.append(AdcParams(
                n_adc=n_adc,
                n_cycles=n_adc + 2,
                comp=CompParams(stages=comp_stages),
                # Everything else: defaults
            ))
    return variants  # ~6 variants

def adc_variants_full() -> List[AdcParams]:
    """Full sweep - all combinations (expensive!)."""
    variants = []
    for n_adc in [8, 10, 12, 14]:
        for comp_params in comp_variants():      # ~112 combinations
            for samp_params in samp_variants():  # ~6 combinations
                for cdac_params in cdac_variants():  # ~20 combinations
                    # This explodes: 4 × 112 × 6 × 20 = 53,760 variants
                    ...
    return variants

def adc_variants_targeted() -> List[AdcParams]:
    """Targeted sweep - sweep one dimension, fix others."""
    base = AdcParams(n_adc=12, n_cycles=14)

    # Sweep comp while fixing everything else
    return [
        replace(base, comp=cp)
        for cp in comp_variants()
    ]
```

### Test Functions with Hierarchical Params

```python
def test_adc_netlist(simtestmode: SimTestMode):
    if simtestmode == SimTestMode.NETLIST:
        # Quick: only key variants
        for p in adc_variants_quick():
            h.netlist(Adc(p), dest=io.StringIO())

def test_adc_sim(simtestmode: SimTestMode):
    if simtestmode == SimTestMode.MIN:
        # Single point
        result = run_adc_sim(AdcParams())
    elif simtestmode == SimTestMode.TYP:
        # Targeted sweep
        for p in adc_variants_targeted():
            run_adc_sim(p)
    elif simtestmode == SimTestMode.MAX:
        # Full sweep (parallel)
        results = h.sim.run([sim_input(p) for p in adc_variants_full()], opts)
```

---

## Monte Carlo Support

### HDL21 Native Monte Carlo

HDL21 has built-in Monte Carlo analysis:

```python
@hs.sim
class CompMcSim:
    tb = CompTb(params)
    mc = hs.MonteCarlo(
        inner=[hs.Tran(tstop=500*n)],
        npts=100,  # 100 MC runs
    )
```

### Limitation: MonteResult Not Implemented

**Critical:** `vlsirtools.MonteResult` raises `NotImplementedError`. Results must be accessed via:
1. Raw simulator output files (`.raw`, `.psf`)
2. Custom parsing of simulator logs
3. Extending vlsirtools (see below)

### Post-Processing Helper

The `mc_statistics()` function computes statistics from extracted values:

```python
def mc_statistics(values: List[float]) -> Dict[str, float]:
    """Compute mean, std, min, max from MC results."""
    return {
        "mean": np.mean(values),
        "std": np.std(values),
        "min": np.min(values),
        "max": np.max(values),
        "n": len(values),
    }
```

---

## Repos to Fork for vlsirtools Fix

To implement `MonteResult` parsing, you need to fork:

### 1. VLSIR (Protocol Definitions)
```
Repo: https://github.com/Vlsir/Vlsir
Path: /home/kcaisley/libs/Vlsir/
Key files:
  - vlsir/spice.proto          # Protobuf definitions for MonteInput/MonteResult
  - VlsirTools/vlsirtools/spice/sim_data.py  # MonteResult class (NOT IMPLEMENTED)
```

### 2. HDL21 (Python Interface)
```
Repo: https://github.com/dan-fritchman/Hdl21
Path: /home/kcaisley/libs/Hdl21/
Key files:
  - hdl21/sim/data.py          # MonteCarlo analysis definition
  - hdl21/sim/proto.py         # export_monte() serialization
```

### What Needs Implementing

In `VlsirTools/vlsirtools/spice/sim_data.py`:

```python
@dataclass
class MonteResult:
    """Monte Carlo simulation results."""
    vlsir_type: ClassVar[AnalysisType] = AnalysisType.MONTE

    # Currently raises NotImplementedError
    # Need to implement:
    inner_results: List[AnalysisResult]  # Results from each MC run

    @classmethod
    def from_raw(cls, raw_data, inner_analyses) -> "MonteResult":
        """Parse simulator output into structured results."""
        # Simulator-specific parsing (Spectre PSF, ngspice raw, etc.)
        ...
```

### Fork Strategy

1. Fork `Vlsir/Vlsir` → your GitHub
2. Implement `MonteResult` parsing for Spectre (your primary simulator)
3. Install from your fork: `pip install git+https://github.com/youruser/Vlsir.git#subdirectory=VlsirTools`
4. Optionally submit PR upstream

---

## Development Setup

### Forked Repos (editable installs)

```bash
# Clone forks
cd /home/kcaisley/libs
git clone https://github.com/kcaisley/Vlsir.git
git clone https://github.com/kcaisley/Hdl21.git

# Install in editable mode
cd /home/kcaisley/frida
uv pip install -e /home/kcaisley/libs/Vlsir/bindings/python \
               -e /home/kcaisley/libs/Vlsir/VlsirTools \
               -e /home/kcaisley/libs/Hdl21
```

---

## Known Limitations

### Remote Simulation Execution

HDL21/vlsirtools do **not** support remote simulation execution. Options:
1. Use PyOPUS separately for MPI-based remote execution
2. Write a thin SSH wrapper that copies netlists to remote machine
3. Use job scheduler (Slurm, LSF) integration

This is not addressed in this plan - simulations assumed to run locally or via external infrastructure.

### gdsfactory Integration

No automatic schematic→layout generation. The LVS flow uses gplugins/vlsir for **layout→netlist extraction** (verification), not layout generation.

---

## Reference Documents

- `comparison.md` - Comparison of dict-based, Python-class, and HDL21 approaches
- USBphy patterns: `/home/kcaisley/libs/Usb2Phy/Usb2PhyAna/usb2phyana/`
- HDL21 sample PDK: `/home/kcaisley/libs/Hdl21/hdl21/pdk/sample_pdk/pdk.py`
