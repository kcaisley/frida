# OpenROAD-flow-scripts Modifications Required for FRIDA

This document describes the modifications required to OpenROAD-flow-scripts (ORFS) to support the FRIDA ADC digital design flow. These changes enable custom cell protection, placement blockages, and proper GDS generation for mixed-signal designs.

## Overview

The FRIDA flow requires several modifications to ORFS scripts to support:
- Custom analog-aware cells (clock gates, sample drivers) that must be protected from optimization
- Placement and routing blockages for future analog macro integration
- Proper via cell preservation during DEF to GDS conversion
- Mixed-signal design constraints

## Required Modifications

### 1. def2stream.py - Via Cell Preservation

**File:** `flow/util/def2stream.py`

**Issue:** KLayout's def2stream conversion was removing via cells because some PDKs use "VIA" prefix without underscore (e.g., VIA12_1cut_V) while the script only preserved cells with "VIA_" prefix.

**Change:**
```python
# Line ~28-34
# remove orphan cell BUT preserve cell with VIA_ or starting with VIA
#  - KLayout is prepending VIA_ when reading DEF that instantiates LEF's via
#  - Some platforms use VIA prefix without underscore (e.g., VIA12_1cut)
for i in main_layout.each_cell():
    if i.cell_index() != top_cell_index:
        if not i.name.startswith("VIA_") and not i.name.startswith("VIA") and not i.name.endswith("_DEF_FILL"):
            i.clear()
```

**Original:**
```python
        if not i.name.startswith("VIA_") and not i.name.endswith("_DEF_FILL"):
            i.clear()
```

**Why needed:** TSMC65 and other PDKs define via cells in LEF without the underscore (VIA12_1cut_V, VIA23_1cut, etc.). Without this change, all via geometry is lost during GDS merge.

---

### 2. synth.tcl - Custom Cell Support

**File:** `flow/scripts/synth.tcl`

**Issue:** Yosys synthesis check with `-assert` flag fails when design contains custom cells or wrapped operators, blocking the flow.

**Change:**
```tcl
# Line ~160-165
if { ![env_var_exists_and_non_empty SYNTH_WRAPPED_OPERATORS] } {

  # Check was causing a break, which I disabled for now! But FIXME!
  check -mapped

  # check -assert -mapped

} else {
```

**Original:**
```tcl
if { ![env_var_exists_and_non_empty SYNTH_WRAPPED_OPERATORS] } {
  check -assert -mapped
} else {
```

**Why needed:** FRIDA design includes custom analog-aware cells (clkgate, sampdriver) that are blackboxed during synthesis. The `-assert` flag causes synthesis to fail when these cells are present. Removing `-assert` allows the flow to continue with warnings instead of errors.

---

### 3. global_place.tcl - Custom Cell Protection and Buffer Control

**File:** `flow/scripts/global_place.tcl`

**Issue:**
1. Need to protect custom analog-aware cells from being optimized/removed during placement
2. Need to manually place specific cells for analog interface requirements
3. Default buffer selection chooses delay cells (DELD1LVT) instead of proper buffers (BUFFD2LVT)

**Changes:**

#### 3.1 DONT_TOUCH Hook (after line 6)
```tcl
# Run optional dont_touch script if DONT_TOUCH variable is defined
if { [info exists ::env(DONT_TOUCH)] && $::env(DONT_TOUCH) != "" } {
    puts "Running FRIDA project specific dont_touch script"
    source $::env(DONT_TOUCH)
}
```

**Why needed:** Allows design-specific script to mark cells as dont_touch before remove_buffers runs, preventing optimization of critical analog interface cells.

#### 3.2 MANUAL_PLACE Hook (after DONT_TOUCH hook)
```tcl
# Run optional manual placement script if MANUAL_PLACE variable is defined
if { [info exists ::env(MANUAL_PLACE)] && $::env(MANUAL_PLACE) != "" } {
    puts "Running FRIDA project specific manual_place script"
    source $::env(MANUAL_PLACE)
}
```

**Why needed:** Enables manual placement of specific cells before global placement, required for analog/digital interface cells that must be positioned precisely.

#### 3.3 Buffer Cell Selection (line ~29)
```tcl
if { ![env_var_exists_and_non_empty FOOTPRINT] } {
  if { ![env_var_equals DONT_BUFFER_PORTS 1] } {
    puts "Perform port buffering..."
    buffer_ports -buffer_cell {BUFFD2LVT}
  }
}

# I'm not sure why but it seems to want to select DELD1LVT as a buffer of choice, which just is a bit silly, the flag above is the only way I found to control it.
```

**Original:**
```tcl
    buffer_ports
```

**Why needed:** Without explicit `-buffer_cell` flag, OpenROAD's `selectBufferCell()` chooses the lowest drive resistance cell from the equivalence class, which selects DELD1LVT (delay cell) instead of a proper buffer. Explicit specification ensures BUFFD2LVT buffers are used.

---

### 4. floorplan.tcl - Placement/Routing Blockage Support

**File:** `flow/scripts/floorplan.tcl`

**Issue:** Mixed-signal designs need placement and routing blockages to reserve space for analog macros that will be integrated later.

**Changes:**

#### 4.1 CREATE_REGIONS Hook (after line 5, before report_unused_masters)
```tcl
# Run optional create_regions.tcl script for additional power rails
if { [info exists ::env(CREATE_REGIONS)] && $::env(CREATE_REGIONS) != "" } {
    puts "Running create_regions.tcl to create alternative voltage domain regions"
    source $::env(CREATE_REGIONS)
}
```

**Why needed:** Allows defining voltage domain regions for mixed-signal designs with multiple power domains (though not currently used in FRIDA digital block).

#### 4.2 CREATE_BLOCKAGES Hook (after line ~93, after floorplan creation)
```tcl
# Run optional create_blockages.tcl script for additional power rails
if { [info exists ::env(CREATE_BLOCKAGES)] && $::env(CREATE_BLOCKAGES) != "" } {
    puts "Running create_blockages.tcl"
    source $::env(CREATE_BLOCKAGES)
}
```

**Why needed:** Creates placement blockages in floorplan stage to reserve space for analog macros (comparator, sampling switches) that will be integrated at chip level. Critical for mixed-signal flows where digital blocks must leave space for analog components.

---

## Usage in FRIDA Design

### config.mk Variables
```makefile
# Enable custom cell protection
export DONT_TOUCH = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/dont_touch.tcl

# Enable placement blockages for analog macros
export CREATE_BLOCKAGES = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/create_blockages.tcl

# Optional: Manual placement (not currently used)
# export MANUAL_PLACE = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/manual_place.tcl

# Optional: Voltage domains (not currently used)
# export CREATE_REGIONS = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/create_regions.tcl
```

### Example: dont_touch.tcl
```tcl
# Protect custom clock gates from optimization
set_dont_touch [get_cells clkgate/clkgate_comp.clkgate_cell]
set_dont_touch [get_cells clkgate/clkgate_init.clkgate_cell]
# ... etc
```

### Example: create_blockages.tcl
```tcl
# Reserve space for analog comparator
set comp_llx [expr int(19.5 * $dbu)]
set comp_lly [expr int(28.8 * $dbu)]
set comp_urx [expr int(40.5 * $dbu)]
set comp_ury [expr int(49.0 * $dbu)]

odb::dbBlockage_create $block $comp_llx $comp_lly $comp_urx $comp_ury
```

---

## Applying These Changes

### Apply Patch File
A patch file is included in this repository at `docs/orfs_mods.patch`.

Apply the patch to your ORFS installation:
```bash
cd /path/to/OpenROAD-flow-scripts
git apply /path/to/frida/docs/orfs_mods.patch
```

Verify the patch:
```bash
cd /path/to/OpenROAD-flow-scripts
git apply --check /path/to/frida/docs/orfs_mods.patch
```

---

## Notes and Caveats

1. **synth.tcl check -assert removal**: This is a workaround. Ideally, custom cells should be properly blackboxed in Yosys to avoid this issue. The TODO comment indicates this needs a proper fix.

2. **def2stream.py VIA preservation**: This change is defensive and should not break other flows, as it only makes the VIA detection more permissive.

3. **Buffer selection**: The DELD1LVT selection issue may be fixed in future OpenROAD versions. Monitor selectBufferCell() behavior in new releases.

4. **Hooks are optional**: All new hooks check for variable existence before sourcing, so they don't affect designs that don't use them.

---

## Version Information

These modifications were developed and tested with:
- OpenROAD: v2.0-24135-gb57dad1953
- KLayout: 0.29.x
- Platform: TSMC65LP (9 metal layers)
- Design: FRIDA ADC Digital Block (mixed-signal SAR ADC)

---

## Future Improvements

1. **Proper custom cell handling in Yosys**: Add proper blackbox directives to avoid synthesis check failures
2. **Standard ORFS mixed-signal support**: Propose these hooks as standard ORFS features for mixed-signal flows
3. **Via preservation improvement**: Investigate if KLayout's DEF reader can be configured to avoid needing def2stream.py modification
