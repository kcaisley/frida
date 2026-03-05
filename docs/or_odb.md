# OpenROAD-Driven Python

This document explains how to drive OpenROAD from Python — the execution model,
the two APIs available, and the practical patterns used in FRIDA's layout flow.

---

## Execution model

OpenROAD is a C++ application with an embedded Python interpreter. There is no
pip-installable package; Python runs *inside* OpenROAD, not the other way around.

```
openroad -exit -python flow/comp/layout.py comp ihp130
```

`-python` starts OpenROAD with the Python interpreter instead of the default TCL
interpreter. `-exit` ensures OpenROAD exits after the script finishes rather than
dropping into an interactive prompt. Arguments after the script path are forwarded
to `sys.argv`.

Inside the script, `sys.argv[0]` is the script path, `sys.argv[1]` onward are the
arguments passed from the CLI — in the FRIDA flow, `cell` and `tech`.

```python
# flow/comp/layout.py
import sys
cell = sys.argv[1]   # "comp"
tech = sys.argv[2]   # "ihp130"
```

This is wired up in [flow/cli.py#L143](file:///home/kcaisley/frida/flow/cli.py#L143)
via `_run_layout`.

---

## Two APIs

Inside a `-python` session, two modules are available:

### `openroad` — high-level design API

Wraps the major flow stages as Python objects. Used to load files and run
placement and routing stages.

```python
from openroad import Tech, Design

tech = Tech()
tech.readLef("sg13g2_tech.lef")
tech.readLef("sg13g2_macros.lef")

design = Design(tech)
design.readVerilog("comp.v")
design.link("Comp")
```

For commands that don't have a dedicated Python method, use `evalTclString` to
call the underlying TCL command on the live in-memory database:

```python
design.evalTclString('initialize_floorplan -die_area "0 0 35 35" -core_area "1 1 34 34" -site unit')
design.evalTclString("global_route -allow_congestion -verbose")
design.evalTclString("detailed_route")
design.evalTclString("write_def comp_placed_routed.def")
```

This is not a subprocess call — it calls the TCL interpreter embedded in the same
process, operating on the same in-memory database. There is no serialisation cost.

### `odb` — low-level database API

Direct access to the OpenDB C++ objects via SWIG bindings. Used for reading and
writing the design database at the object level: instances, nets, routing guides,
wires.

```python
import odb

db    = openroad.get_db()
chip  = db.getChip()
block = chip.getBlock()

# Place and lock an instance
inst = block.findInst("mtail")
inst.setLocation(14480, 1000)          # coordinates in database units (nm)
inst.setPlacementStatus("LOCKED")

# Iterate nets
for net in block.getNets():
    print(net.getName())
```

The database unit is **nanometres**. A coordinate in microns must be multiplied
by 1000 to convert to database units.

---

## Why Python over pure TCL

The Python API exposes more of the C++ surface than TCL does. TCL wraps a
fixed set of commands; Python binds all public C++ methods via SWIG. This matters
for:

- **Direct ODB manipulation** — placing instances, creating/deleting routing
  guides, inspecting wire geometry. All of this is only practical via `odb`.
- **Geometric computation** — mirroring guide coordinates for symmetric routing
  requires arithmetic that is cumbersome in TCL and natural in Python.
- **Integration with the rest of FRIDA** — constraint objects, PDK lookups, and
  output path handling are all Python. Keeping the layout script in Python means
  no context switch.

See [docs/or_analog.md](file:///home/kcaisley/frida/docs/or_analog.md) for a
detailed comparison of Python vs TCL coverage and a summary of what OpenROAD
does and does not support natively for analog flows.

---

## Symmetric routing workaround

OpenROAD has no native symmetric routing. The workaround is to route one net,
extract its guides, mirror the coordinates about the symmetry axis, and apply
the mirrored guides to the paired net before re-routing.

```python
import odb

SYM_AXIS_DBU = 17500   # 17.5 um * 1000

def mirror_x(coord, axis):
    return 2 * axis - coord

block  = openroad.get_db().getChip().getBlock()
net_a  = block.findNet("outp_int")
net_b  = block.findNet("outn_int")

# Remove existing guides on net_b
for guide in list(net_b.getGuides()):
    odb.dbGuide.destroy(guide)

# Mirror net_a's guides onto net_b
for guide in net_a.getGuides():
    box   = guide.getBox()
    layer = guide.getLayer()
    new_xlo = mirror_x(box.xMax(), SYM_AXIS_DBU)
    new_xhi = mirror_x(box.xMin(), SYM_AXIS_DBU)
    odb.dbGuide.create(net_b, layer,
        odb.Rect(new_xlo, box.yMin(), new_xhi, box.yMax()))
```

After mirroring, run `detailed_route` again via `evalTclString` so the router
uses the constrained guides for `net_b`.

---

## NDR and net weights

Non-default routing rules (`add_ndr` / `assign_ndr`) require a liberty file to
be loaded because OpenROAD's constraint infrastructure was built around timing-
driven digital flows. Without a liberty file the timing graph is uninitialised
and these commands fail silently or error out.

For analog flows without liberty files, apply width and spacing constraints
directly via ODB instead of using NDR commands.

Net weights (for influencing global placement and routing congestion) are not
exposed as plain TCL commands. They must be set via the Replace (global placer)
Python API:

```python
replace = design.getReplace()
replace.setInitialPlaceNetWeightScale(scale)
```

---

## Typical script structure

```python
import sys
from pathlib import Path
from openroad import Tech, Design
import openroad
import odb

cell = sys.argv[1]
tech = sys.argv[2]

script_dir = Path(__file__).parent

# 1. Load tech and design
t = Tech()
t.readLef(str(script_dir / f"{tech}_tech.lef"))
t.readLef(str(script_dir / f"{tech}_macros.lef"))

d = Design(t)
d.readVerilog(str(script_dir / f"{cell}.v"))
d.link(cell.capitalize())

# 2. Floorplan and tracks (TCL commands without Python equivalents)
d.evalTclString('initialize_floorplan -die_area "0 0 35 35" -core_area "1 1 34 34" -site unit')
d.evalTclString("make_tracks Metal1 -x_offset 0 -x_pitch 0.42 -y_offset 0 -y_pitch 0.42")

# 3. Pin placement
d.evalTclString("place_pins -hor_layers Metal3 -ver_layers Metal2")

# 4. Manual instance placement via ODB
block = openroad.get_db().getChip().getBlock()
for name, x_um, y_um in PLACEMENTS:
    inst = block.findInst(name)
    inst.setLocation(int(x_um * 1000), int(y_um * 1000))
    inst.setPlacementStatus("LOCKED")

# 5. Routing
d.evalTclString("set_routing_layers -signal Metal1-Metal5")
d.evalTclString("global_route -allow_congestion -verbose")

# 6. Symmetric guide mirroring (if needed)
# ... mirror_guides() ...

# 7. Detail routing and output
d.evalTclString("detailed_route")
d.evalTclString(f"write_def {script_dir}/{cell}_placed_routed.def")
```

---

## Further reading

- [docs/or_analog.md](file:///home/kcaisley/frida/docs/or_analog.md) — placement
  status options, routing guide API, symmetric routing workaround detail,
  Python vs TCL feature comparison table
- [docs/man_openroad.md](file:///home/kcaisley/frida/docs/man_openroad.md) — full
  TCL command reference for OpenROAD
- OpenROAD ODB unit tests: `src/odb/test/unitTestsPython/` in the OpenROAD source
  tree — the most complete examples of the `odb` Python API
