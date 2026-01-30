# Plan: Implement Proprietary PDK Support for FRIDA

## Overview

The `/alt` directory has HDL21-based generators with testbenches and pytest integration complete. This plan details adding PDK support for proprietary processes (Tower 180nm, TSMC 65nm, TSMC 28nm).

## Completed Tasks

1. ✅ Rename `calc_weights` → `_calc_weights` and move after main generator
2. ✅ Testbenches consolidated into block files (samp.py, comp.py, cdac.py)
3. ✅ Shared measure module created (alt/measure.py)
4. ✅ pytest-based execution with SimTestMode fixture (alt/conftest.py)
5. ✅ Generic values → PDK-specific only at netlist time

## Current Focus: PDK Implementation

**Target PDKs:**
- `tower180` - Tower Semiconductor 180nm (for lab tape-outs)
- `tsmc65` - TSMC 65nm LP (target production)
- `tsmc28` - TSMC 28nm HPC+ (future target)

**Already Available Upstream (Hdl21/pdks/):**
- IHP SG13G2 130nm BiCMOS - Full implementation with HBTs, resistors, caps
- Sky130 - SkyWater open-source PDK
- ASAP7 - Academic 7nm FinFET
- GF180 - GlobalFoundries 180nm

## Current State

### What's Complete
- **Generators**: samp.py, comp.py, cdac.py with full topology support
- **PDK Abstraction**: base.py + generic.py with device selection
- **Parameters**: common/params.py with all enums, Pvt, SupplyVals
- **Testbenches**: Consolidated into block files with pytest test functions
- **Monte Carlo**: MCConfig and sim_input_with_mc() framework
- **Measure module**: alt/measure.py with extraction functions
- **Pytest config**: alt/conftest.py with SimTestMode fixture

### What's Missing for PDK
- PDK implementations for tower180, tsmc65, tsmc28
- Model file include statements
- PDK-specific device parameter classes
- Supply voltage configurations per process

---

## PDK Target Architecture

```
alt/pdk/
├── __init__.py          # PDK selector: set_pdk(), get_pdk() ✅
├── base.py              # Abstract FridaPdk class ✅
├── generic.py           # Generic PDK (SPICE primitives) ✅
├── tower180.py          # Tower 180nm (NEW)
├── tsmc65.py            # TSMC 65nm LP (NEW)
└── tsmc28.py            # TSMC 28nm HPC+ (NEW)
```

---

## Implementation Steps

### Step 1: Create TSMC65 PDK Plugin

**New File:** `alt/pdk/tsmc65.py`

Create PDK following the IHP pattern from `/home/kcaisley/libs/Hdl21/pdks/IHP/`.

**Device mapping from `flow/common.py` techmap:**
```python
# From techmap["tsmc65"]["devmap"]
"nmos_lvt": {"model": "nch_lvt", "w": 120e-9, "l": 60e-9}
"nmos_svt": {"model": "nch", "w": 120e-9, "l": 60e-9}
"nmos_hvt": {"model": "nch_hvt", "w": 120e-9, "l": 60e-9}
"pmos_lvt": {"model": "pch_lvt", "w": 120e-9, "l": 60e-9}
"pmos_svt": {"model": "pch", "w": 120e-9, "l": 60e-9}
"pmos_hvt": {"model": "pch_hvt", "w": 120e-9, "l": 60e-9}
```

**Model file:**
```
/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs
Sections: tt_lib, ss_lib, ff_lib, sf_lib, fs_lib, mc_lib
```

**Implementation structure:**
```python
# alt/pdk/tsmc65.py

PDK_NAME = "tsmc65"

@h.paramclass
class Tsmc65MosParams:
    """TSMC 65nm MOS parameters."""
    w = h.Param(dtype=h.Scalar, desc="Width", default=120*n)
    l = h.Param(dtype=h.Scalar, desc="Length", default=60*n)
    nf = h.Param(dtype=int, desc="Number of fingers", default=1)
    m = h.Param(dtype=int, desc="Multiplier", default=1)

# ExternalModules for each device flavor
xtors = {
    (h.MosType.NMOS, h.MosVth.LOW): _xtor_module("nch_lvt"),
    (h.MosType.NMOS, h.MosVth.STD): _xtor_module("nch"),
    (h.MosType.NMOS, h.MosVth.HIGH): _xtor_module("nch_hvt"),
    (h.MosType.PMOS, h.MosVth.LOW): _xtor_module("pch_lvt"),
    (h.MosType.PMOS, h.MosVth.STD): _xtor_module("pch"),
    (h.MosType.PMOS, h.MosVth.HIGH): _xtor_module("pch_hvt"),
}

@dataclass
class Install(h.pdk.PdkInstallation):
    """TSMC 65nm installation paths."""
    pdk_path: Path = Path("/eda/kits/TSMC/65LP/2024/V1.7A_1")

    def include(self, corner: h.pdk.Corner) -> h.sim.Lib:
        corner_map = {
            h.pdk.Corner.TYP: "tt_lib",
            h.pdk.Corner.FAST: "ff_lib",
            h.pdk.Corner.SLOW: "ss_lib",
        }
        return h.sim.Lib(
            path=self.pdk_path / "1p9m6x1z1u/models/spectre/toplevel.scs",
            section=corner_map[corner],
        )

class Tsmc65Walker(h.HierarchyWalker):
    """Convert primitives to TSMC65 ExternalModules."""
    # Cache and walker methods per IHP pattern

def compile(src: h.Elaboratables) -> None:
    Tsmc65Walker.walk(src)
```

---

### Step 2: Create TSMC28 PDK Plugin

**New File:** `alt/pdk/tsmc28.py`

**Device mapping from techmap:**
```python
# From techmap["tsmc28"]["devmap"]
"nmos_lvt": {"model": "nch_lvt_mac", "w": 40e-9, "l": 30e-9}
"nmos_svt": {"model": "nch_svt_mac", "w": 40e-9, "l": 30e-9}
"nmos_hvt": {"model": "nch_hvt_mac", "w": 40e-9, "l": 30e-9}
"pmos_lvt": {"model": "pch_lvt_mac", "w": 40e-9, "l": 30e-9}
"pmos_svt": {"model": "pch_svt_mac", "w": 40e-9, "l": 30e-9}
"pmos_hvt": {"model": "pch_hvt_mac", "w": 40e-9, "l": 30e-9}
```

**Model files:**
```
Main: /eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/toplevel.scs
Sections: att_pt, ass_ps, aff_pf, asf_ps, afs_pf, local_mc

Noise (optional): crn28ull_1d8_elk_v1d8_2p2_shrink0d9_embedded_usage.scs
Sections: noise_worst, noise_typical
```

---

### Step 3: Create Tower180 PDK Plugin

**New File:** `alt/pdk/tower180.py`

**Device mapping from techmap:**
```python
# From techmap["tower180"]["devmap"]
"nmos_lvt": {"model": "n18lvt", "w": 220e-9, "l": 180e-9}
"nmos_svt": {"model": "n18", "w": 220e-9, "l": 180e-9}
"nmos_hvt": {"model": "n18hvt", "w": 220e-9, "l": 180e-9}
"pmos_lvt": {"model": "p18lvt", "w": 220e-9, "l": 180e-9}
"pmos_svt": {"model": "p18", "w": 220e-9, "l": 180e-9}
"pmos_hvt": {"model": "p18hvt", "w": 220e-9, "l": 180e-9}
```

**Model files:**
```
FET: /eda/kits/TOWER/ts18is_Rev_6.3.6/HOTCODE/models/ts18sl/v5.6.00/spectre/fet.scs
Sections: NOM, SLOW, FAST, SLOWFAST, FASTSLOW, STAT

Global: /eda/kits/TOWER/ts18is_Rev_6.3.6/HOTCODE/models/ts18sl/v5.6.00/spectre/global.scs
Section: BSIM (always included)
```

---

### Step 4: Update FridaPdk Base Class

**Edit:** `alt/pdk/base.py`

Add abstract methods for model includes:

```python
class FridaPdk(ABC):
    """Abstract base class for FRIDA PDK plugins."""

    # Process parameters
    W_MIN: h.Prefixed  # Minimum transistor width
    L_MIN: h.Prefixed  # Minimum transistor length
    VDD_NOM: h.Prefixed  # Nominal supply voltage

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def Nmos(self) -> h.ExternalModule: ...

    @property
    @abstractmethod
    def NmosLvt(self) -> h.ExternalModule: ...

    @abstractmethod
    def compile(self, src: h.Elaboratables) -> None: ...

    @abstractmethod
    def include_statements(self, corner: Corner) -> List[h.sim.Lib]:
        """Return model includes for simulation at given corner."""
        ...
```

---

### Step 5: Update PDK Registry

**Edit:** `alt/pdk/__init__.py`

```python
from .base import FridaPdk
from .generic import GenericPdk
from .tsmc65 import Tsmc65Pdk  # NEW
from .tsmc28 import Tsmc28Pdk  # NEW
from .tower180 import Tower180Pdk  # NEW

_PDK_REGISTRY = {
    "generic": GenericPdk,
    "tsmc65": Tsmc65Pdk,
    "tsmc28": Tsmc28Pdk,
    "tower180": Tower180Pdk,
}

def set_pdk(name: str) -> None:
    global _active_pdk
    if name not in _PDK_REGISTRY:
        raise ValueError(f"Unknown PDK: {name}. Available: {list(_PDK_REGISTRY.keys())}")
    _active_pdk = _PDK_REGISTRY[name]()
```

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `alt/pdk/tsmc65.py` | Create | TSMC 65nm LP PDK plugin |
| `alt/pdk/tsmc28.py` | Create | TSMC 28nm HPC+ PDK plugin |
| `alt/pdk/tower180.py` | Create | Tower 180nm PDK plugin |
| `alt/pdk/base.py` | Edit | Add include_statements(), W_MIN, L_MIN, VDD_NOM |
| `alt/pdk/__init__.py` | Edit | Register new PDKs |
| `alt/common/params.py` | Edit | Add PDK-specific SupplyVals classes |

---

## PDK File Structure (per PDK)

Each PDK file follows the IHP pattern:

```
alt/pdk/tsmc65.py
├── PDK_NAME constant
├── MosParams paramclass (w, l, nf, m)
├── _xtor_module() factory function
├── xtors dict: (MosType, MosVth) → ExternalModule
├── Install dataclass with include() method
├── Walker(h.HierarchyWalker) class
└── compile() function
```

---

## Reference: techmap from flow/common.py

Source of truth for device names and model paths:

| PDK | VDD | Wmin | Lmin | NMOS LVT | PMOS LVT | Model Path |
|-----|-----|------|------|----------|----------|------------|
| tsmc65 | 1.2V | 120nm | 60nm | nch_lvt | pch_lvt | /eda/kits/TSMC/65LP/.../toplevel.scs |
| tsmc28 | 0.9V | 40nm | 30nm | nch_lvt_mac | pch_lvt_mac | /eda/kits/TSMC/28HPC+/.../toplevel.scs |
| tower180 | 1.8V | 220nm | 180nm | n18lvt | p18lvt | /eda/kits/TOWER/.../fet.scs |

---

## Verification

### 1. PDK Netlist Test (no simulator)
```bash
pytest --simtestmode netlist alt/pdk/test_pdks.py -v
```

### 2. PDK Simulation Test (requires Spectre + models)
```bash
# Single PDK test
pytest --simtestmode min alt/pdk/test_pdks.py::test_tsmc65_compile

# All PDKs
pytest --simtestmode min alt/pdk/test_pdks.py
```

### 3. Block Tests with Specific PDK
```bash
# Test comp with TSMC65
pytest --simtestmode min alt/comp.py::test_comp_sim --pdk tsmc65
```

---

## Reference: IHP PDK Pattern

The IHP implementation in `/home/kcaisley/libs/Hdl21/pdks/IHP/ihp_hdl21/` serves as the template:

**Key files:**
- `pdk_data.py` - Parameter classes, ExternalModule factory functions, port lists
- `pdk_logic.py` - Install class, Walker class, compile() function
- `primitives/prim_dicts.py` - Device dictionaries (xtors, ress, caps, etc.)

**Install class pattern:**
```python
@dataclass
class Install(PdkInstallation):
    pdk_path: Path
    model_lib: Path

    def include(self, corner: h.pdk.Corner) -> h.sim.Lib:
        corner_map = {Corner.TYP: "tt", Corner.FAST: "ff", Corner.SLOW: "ss"}
        return h.sim.Lib(path=self.pdk_path / "models.scs", section=corner_map[corner])
```

**Walker class pattern:**
```python
class PdkWalker(h.HierarchyWalker):
    def __init__(self):
        super().__init__()
        self.mos_modcalls = dict()  # Cache

    def visit_primitive_call(self, call: h.PrimitiveCall) -> h.Instantiable:
        if call.prim is Mos:
            return self.mos_module_call(call.params)
        return call  # Pass through others

    def mos_module_call(self, params) -> h.ExternalModuleCall:
        if params in self.mos_modcalls:
            return self.mos_modcalls[params]
        mod = self.mos_module(params)
        modparams = self.mos_params(params)
        modcall = mod(modparams)
        self.mos_modcalls[params] = modcall
        return modcall
```

---

## Reference: techmap from flow/common.py

The existing `techmap` dict contains all the device info needed:

```python
techmap = {
    "tsmc65": {
        "libs": [{"path": "/eda/kits/TSMC/65LP/.../toplevel.scs",
                  "sections": ["tt_lib", "ss_lib", "ff_lib", ...]}],
        "vdd": 1.2,
        "devmap": {
            "nmos_lvt": {"model": "nch_lvt", "w": 120e-9, "l": 60e-9},
            ...
        },
        "corners": {"tt": "tt_lib", "ss": "ss_lib", "ff": "ff_lib", ...},
    },
    "tsmc28": {...},
    "tower180": {...},
}
```

---

## Reference Documents

- IHP PDK: `/home/kcaisley/libs/Hdl21/pdks/IHP/ihp_hdl21/`
- PdkTemplate: `/home/kcaisley/libs/Hdl21/pdks/PdkTemplate/`
- PR #239: https://github.com/dan-fritchman/Hdl21/pull/239
- techmap: `/home/kcaisley/frida/flow/common.py` lines 20-149
