# HDL21 Implementation Comparison

Comparing three implementation approaches: dict-based (`blocks/samp.py`), Python-class (`samp_python.py`), and HDL21 (`alt/samp.py`).

## 1. Topology Selection (`switch_type`)

| Feature | blocks/samp.py | samp_python.py | alt/samp.py |
|---------|----------------|----------------|-------------|
| Definition | `"topo_params": {"switch_type": ["nmos", "pmos", "tgate"]}` | `class SwitchType(Enum)` | `class SwitchType(Enum)` in `common/params.py` |
| Selection | `gen_topo_subckt(switch_type: str)` function | `if self.switch_type == SwitchType.NMOS` in `schematic()` | `if p.switch_type == SwitchType.NMOS` in generator |

**blocks/samp.py (dict-based):**
```python
def gen_topo_subckt(switch_type: str) -> tuple[dict, dict]:
    if switch_type == "nmos":
        instances["MN"] = {"dev": "nmos", "pins": {"d": "out", "g": "clk", ...}}
```

**samp_python.py (class-based):**
```python
def schematic(self, io, cell: CellBuilder):
    if self.switch_type == SwitchType.NMOS:
        mn = cell.instantiate(Nfet(self.w, self.l, self.vth))
        cell.connect(io.dout, mn.d)
```

**alt/samp.py (HDL21):**
```python
if p.switch_type == SwitchType.NMOS:
    Samp.mn = Nfet(w=p.w, l=p.l)(d=Samp.dout, g=Samp.clk, s=Samp.din, b=Samp.vss)
```

---

## 2. Port/IO Definition

| Feature | blocks/samp.py | samp_python.py | alt/samp.py |
|---------|----------------|----------------|-------------|
| Syntax | `ports = {"in": "I", "out": "O", ...}` | `class SampIo(Io): din = Input()` | `din = h.Input(desc="...")` inside `@h.module` |
| Direction encoding | Strings: `"I"`, `"O"`, `"B"` | Classes: `Input()`, `Output()`, `InOut()` | HDL21 types: `h.Input()`, `h.Output()`, `h.Port()` |

**blocks/samp.py:**
```python
ports = {"in": "I", "out": "O", "clk": "I", "clk_b": "I", "vdd": "B", "vss": "B"}
```

**samp_python.py:**
```python
class SampIo(Io):
    din = Input()
    dout = Output()
    clk = Input()
    clk_b = Input()
    vdd = InOut()
    vss = InOut()
```

**alt/samp.py:**
```python
@h.module
class Samp:
    din = h.Input(desc="Data input")
    dout = h.Output(desc="Data output")
    clk = h.Input(desc="Clock (active high)")
    clk_b = h.Input(desc="Clock complement (active low)")
    vdd = h.Port(desc="Supply")
    vss = h.Port(desc="Ground")
```

---

## 3. Device Parameters (w, l, vth)

| Feature | blocks/samp.py | samp_python.py | alt/samp.py |
|---------|----------------|----------------|-------------|
| Where defined | `inst_params` list with sweep values | `@dataclass` fields | `@h.paramclass` with `h.Param` |
| Units | Implicit (microns assumed) | Implicit integers | Explicit: `1 * µ`, `60 * n` |
| Defaults | In `inst_params` fallback | `vth: Vth = Vth.LVT` | `default=1 * µ` |

**blocks/samp.py:**
```python
"inst_params": [
    {"instances": {"nmos": ["MN"], "pmos": ["MP"]}, "w": [5, 10, 20, 40], "l": [1, 2]},
    {"instances": {"nmos": "all", "pmos": "all"}, "type": "lvt", "w": 1, "l": 1, "nf": 1},
]
```

**samp_python.py:**
```python
@dataclass
class Samp:
    switch_type: SwitchType
    w: int
    l: int
    vth: Vth = Vth.LVT
```

**alt/samp.py:**
```python
@h.paramclass
class SampParams:
    switch_type = h.Param(dtype=SwitchType, desc="Switch topology", default=SwitchType.NMOS)
    w = h.Param(dtype=h.Scalar, desc="Device width", default=1 * µ)
    l = h.Param(dtype=h.Scalar, desc="Device length", default=60 * n)
    vth = h.Param(dtype=Vth, desc="Threshold voltage flavor", default=Vth.LVT)
```

---

## 4. Device Instantiation & Connection

| Feature | blocks/samp.py | samp_python.py | alt/samp.py |
|---------|----------------|----------------|-------------|
| Instantiation | Dict: `{"dev": "nmos", "pins": {...}}` | `cell.instantiate(Nfet(...))` | `Nfet(w=p.w, l=p.l)(...)` |
| Connection | Implicit via pin dict | Explicit `cell.connect()` | Inline: `d=Samp.dout, g=Samp.clk` |
| PDK binding | Deferred to `flow/` | Via `flow.pdk` imports | Via `get_pdk()` |

**blocks/samp.py:**
```python
instances["MN"] = {
    "dev": "nmos",
    "pins": {"d": "out", "g": "clk", "s": "in", "b": "vss"},
}
```

**samp_python.py:**
```python
mn = cell.instantiate(Nfet(self.w, self.l, self.vth))
cell.connect(io.dout, mn.d)
cell.connect(io.clk, mn.g)
cell.connect(io.din, mn.s)
cell.connect(io.vss, mn.b)
```

**alt/samp.py:**
```python
Nfet = pdk.NmosLvt if p.vth == Vth.LVT else pdk.Nmos
Samp.mn = Nfet(w=p.w, l=p.l)(d=Samp.dout, g=Samp.clk, s=Samp.din, b=Samp.vss)
```

---

## 5. Variant Generation (Sweeps)

| Feature | blocks/samp.py | samp_python.py | alt/samp.py |
|---------|----------------|----------------|-------------|
| Mechanism | `topo_params × inst_params` Cartesian product | Explicit list comprehension | `samp_variants()` function |
| Where | Processed by `flow/` framework | Module-level `variants = [...]` | Callable with configurable defaults |

**blocks/samp.py:**
```python
"topo_params": {"switch_type": ["nmos", "pmos", "tgate"]},
"inst_params": [
    {"instances": {"nmos": ["MN"]}, "w": [5, 10, 20, 40], "l": [1, 2]},
]
# Framework expands: 3 types × 4 widths × 2 lengths = 24 variants
```

**samp_python.py:**
```python
variants = [
    Samp(switch_type, w, l, vth)
    for switch_type in SwitchType
    for w in [5, 10, 20, 40]
    for l in [1, 2]
    for vth in Vth
]  # 3 × 4 × 2 × 2 = 48 variants
```

**alt/samp.py:**
```python
def samp_variants(
    w_list: list = None,  # default: [5*µ, 10*µ, 20*µ, 40*µ]
    l_list: list = None,  # default: [60*n, 120*n]
    switch_types: list = None,  # default: all
    vth_list: list = None,  # default: all
) -> list:
    return [
        SampParams(switch_type=st, w=w, l=l, vth=vth)
        for st in switch_types
        for w in w_list
        for l in l_list
        for vth in vth_list
    ]
```

---

## 6. Testbench

**samp_python.py:**
```python
cell.instantiate(self.dut, din=din, dout=dout, clk=clk, ...)
```

**alt/samp.py (in tests/test_samp.py):**
```python
@h.generator
def SampTb(params: SampTbParams) -> h.Module:
    tb = h.sim.tb("SampTb")
    tb.vclk = Vpulse(v1=0*m, v2=supply.VDD, period=100*n, width=50*n, ...)(p=tb.clk, n=tb.VSS)
    tb.dut = Samp(params.samp)(din=tb.din, dout=tb.dout, clk=tb.clk, ...)
    return tb
```

---

## 7. Project Structure Options

**Current structure (separate test files):**
```
alt/
├── samp.py
├── comp.py
├── cdac.py
└── tests/
    ├── test_samp.py   # SampTb + sweeps + measures
    ├── test_comp.py   # CompTb + MC + sweeps
    └── test_cdac.py   # CdacTb + code sweeps
```

**Alternative (testbenches with blocks):**
```
alt/
├── samp.py            # Samp + SampTb + SampTbParams
├── comp.py            # Comp + CompTb + CompTbParams
├── cdac.py            # Cdac + CdacTb + CdacTbParams
└── tests/
    └── test_all.py    # Just test functions, imports from above
```

The USBphy project uses the second pattern — testbenches live alongside their DUTs. This makes sense because:

1. **Tight coupling** — `CompTb` instantiates `Comp`, `CompTbParams` contains `CompParams`
2. **Same import context** — Both need the same PDK, params, prefixes
3. **Single source of truth** — When you change `Comp`, the testbench is right there

---

## Summary: Key Differences

| Aspect | Dict-based | Python-class | HDL21 |
|--------|------------|--------------|-------|
| Type safety | None (strings) | Enums, dataclass | Enums, `@h.paramclass` |
| Units | Implicit | Implicit | Explicit prefixes |
| PDK binding | Deferred | Import-time | Runtime `get_pdk()` |
| Netlist generation | Custom `flow/` code | Custom framework | Built-in `h.netlist()` |
| Simulation | PyOPUS integration | Framework abstraction | `vlsirtools.spice.sim()` |

The HDL21 approach gives us type safety, explicit units, and a real circuit IR (VLSIR protobuf) that can target multiple simulators.
