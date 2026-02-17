# YAML Netlist Backend (VLSIRTools)

This note tracks the VLSIRTools backend work done for FRIDA netlist export.

## Branch

Implemented in `~/libs/Vlsir` on branch:

- `yaml-netlist`

Base branch used:

- `main`

## Scope

All code changes are in VLSIRTools (not in FRIDA flow code).

## What Was Added

### 1) New GDSFactory-style YAML netlist backend

Added file:

- `~/libs/Vlsir/VlsirTools/vlsirtools/netlist/gdsfactory_yaml.py`

This backend emits recursive hierarchical netlists in the form:

- `{module_name: {instances, placements, ports, nets}}`

Supported content:

- Hierarchical local modules
- External model leaf instances (including transistor model refs)
- Instance parameter serialization, including prefixed values

### 2) Netlist format wiring

Updated files:

- `~/libs/Vlsir/VlsirTools/vlsirtools/netlist/fmt.py`
- `~/libs/Vlsir/VlsirTools/vlsirtools/netlist/__init__.py`

New format key:

- `gdsfactory_yaml`

Accepted aliases:

- `yaml`
- `yml`
- `gdsfactory`
- `gdsfactory-yaml`
- `gdsfactory_yaml`

### 3) Verilog backend compatibility for physical hierarchies

Updated file:

- `~/libs/Vlsir/VlsirTools/vlsirtools/netlist/verilog.py`

Changes:

- Allow `SpiceModelRef` instances as Verilog leaf modules
- Treat undirected (`NONE`) ports as `inout` (for analog-style module ports)
- Keep SPICE builtins rejected for Verilog

## Tests Added / Updated

Updated file:

- `~/libs/Vlsir/VlsirTools/tests/test_vlsirtools.py`

New coverage:

- `test_verilog_netlist_model_ref`
- `test_gdsfactory_yaml_netlist`
- YAML test checks prefixed parameter handling

## Validation Run

Executed:

```bash
.venv/bin/pytest ../libs/Vlsir/VlsirTools/tests/test_vlsirtools.py -k 'netlist' -v
```

Result:

- `6 passed, 9 deselected`

## Usage Examples

From Python:

```python
from io import StringIO
import vlsirtools

# pkg is a vlsir.circuit.Package
out = StringIO()
vlsirtools.netlist(pkg=pkg, dest=out, fmt="yaml")      # alias for gdsfactory_yaml
yaml_netlist = out.getvalue()

out = StringIO()
vlsirtools.netlist(pkg=pkg, dest=out, fmt="verilog")
verilog_netlist = out.getvalue()
```

## Note on DUT-only Hierarchy

For FRIDA usage, pass the DUT package into netlisting (not simulation/testbench `SimInput`).
That yields hierarchical physical-module content only.
