# Unified Makefile Implementation Plan

## Executive Summary

**FEASIBLE** - Combining the two existing makefiles into a unified root-level Makefile with expanded functionality is not only feasible but highly beneficial. The project already has most required tools and infrastructure in place.

## Current State Analysis

### Existing Assets:
- **hdl/Makefile**: Mature Verilog simulation/synthesis system using iverilog/yosys
- **docs/tex/Makefile**: LaTeX/Pandoc documentation pipeline with custom Lua filters
- **Python ecosystem**: Comprehensive behavioral modeling, SPICE analysis, and layout generation tools
- **Multi-PDK support**: Established tech/ directory with tsmc28, tsmc65, nopdk
- **Output infrastructure**: build/ directory with organized output formats (.raw, .vcd, .pdf, .svg)

### Current Limitations:
- Fragmented workflows requiring manual coordination
- No dependency management between design stages
- Inconsistent file organization
- Manual parameter passing between tools

## Proposed Solution

### 1. Unified Root Makefile Architecture

**Structure inspired by OpenROAD Makefile:**
```makefile
# Configuration via config.mk
include config/config.mk

# Hierarchical includes
include makefiles/specs.mk
include makefiles/layout.mk
include makefiles/simulation.mk
# ... etc
```

**Key Features:**
- **Parameter-driven**: Single config.mk file for design parameters
- **Dependency-aware**: Automatic file dependency tracking
- **Multi-PDK**: Technology-specific configurations
- **Incremental**: Only rebuild what's necessary
- **Parallel-safe**: Multiple targets can run concurrently

### 2. Proposed Directory Structure

```
frida/
├── Makefile                    # Unified root makefile
├── config/
│   ├── config.mk              # Main design parameters
│   ├── tsmc28.mk              # PDK-specific configs
│   ├── tsmc65.mk
│   └── nopdk.mk
├── makefiles/                 # Modular makefile includes
│   ├── specs.mk
│   ├── layout.mk
│   ├── simulation.mk
│   ├── synthesis.mk
│   ├── analysis.mk
│   └── docs.mk
├── specs/                     # Design specifications
│   ├── parameters.yaml
│   ├── constraints.yaml
│   └── generated/            # Generated design params
├── layout/                    # Layout generation
│   ├── scripts/              # KLayout generation scripts
│   ├── generated/            # Generated .gds files
│   └── extracted/            # Extracted netlists
├── netlist/                   # SPICE netlists
│   ├── templates/            # Netlist templates
│   ├── generated/            # Generated netlists
│   └── testbenches/          # SPICE testbenches
├── simulation/               # Simulation outputs
│   ├── spice/                # SPICE .raw files
│   ├── digital/              # Verilog .vcd files
│   └── behavioral/           # Python behavioral .raw
├── synthesis/                # Synthesis outputs
│   ├── netlist/              # Gate-level netlists
│   ├── constraints/          # Timing constraints
│   └── reports/              # Synthesis reports
├── physical/                 # Physical design (OpenROAD)
│   ├── results/              # Final GDS/timing
│   ├── reports/              # PnR reports
│   └── logs/                 # Detailed logs
├── analysis/                 # Analysis results
│   ├── plots/                # Generated plots (.svg/.pdf)
│   ├── data/                 # Processed data
│   └── reports/              # Analysis reports
├── docs/                     # Documentation (kept mostly as-is)
│   ├── generated/            # Auto-generated content
│   ├── templates/            # Markdown templates
│   └── final/                # Combined reports
├── src/                      # Source code (unchanged)
├── hdl/                      # HDL source (unchanged)
└── tech/                     # PDK files (unchanged)
```

### 3. Make Target Implementation

#### `make specs`
**Purpose**: Convert design specifications to design parameters
**Implementation**:
```makefile
specs: specs/generated/design_params.yaml

specs/generated/design_params.yaml: specs/parameters.yaml src/param_generator.py
	@mkdir -p specs/generated
	cd src && python param_generator.py ../specs/parameters.yaml ../specs/generated/design_params.yaml
```

#### `make layout`
**Purpose**: Generate layouts using KLayout
**Implementation**:
```makefile
layout: layout/generated/$(TOP_BLOCK).gds

layout/generated/$(TOP_BLOCK).gds: specs/generated/design_params.yaml src/cdac_layout.py
	@mkdir -p layout/generated
	cd src && python cdac_layout.py ../specs/generated/design_params.yaml ../layout/generated/$(TOP_BLOCK).gds
```

#### `make netlist`
**Purpose**: Generate SPICE netlists using spicelib
**Implementation**:
```makefile
netlist: netlist/generated/$(TOP_BLOCK).sp

netlist/generated/$(TOP_BLOCK).sp: specs/generated/design_params.yaml src/netlist_gen.py
	@mkdir -p netlist/generated
	cd src && python netlist_gen.py ../specs/generated/design_params.yaml ../netlist/generated/$(TOP_BLOCK).sp
```

#### `make spicesim`
**Purpose**: Run SPICE simulations using ngspice
**Implementation**:
```makefile
spicesim: simulation/spice/$(TOP_BLOCK).raw

simulation/spice/$(TOP_BLOCK).raw: netlist/generated/$(TOP_BLOCK).sp netlist/testbenches/$(TOP_BLOCK)_tb.sp
	@mkdir -p simulation/spice
	cd simulation/spice && ngspice -b ../../netlist/testbenches/$(TOP_BLOCK)_tb.sp
```

#### `make digsim`
**Purpose**: Run digital testbenches using iverilog
**Implementation**: (Enhanced version of existing hdl/Makefile)
```makefile
digsim: simulation/digital/$(TOP_BLOCK).vcd

simulation/digital/$(TOP_BLOCK).vcd: hdl/$(TOP_BLOCK).v hdl/$(TOP_BLOCK)_tb.v
	@mkdir -p simulation/digital
	cd hdl && iverilog -o ../simulation/digital/$(TOP_BLOCK)_sim $(TOP_BLOCK).v $(TOP_BLOCK)_tb.v
	cd simulation/digital && ./$(TOP_BLOCK)_sim
```

#### `make bevsim`
**Purpose**: Run Python behavioral simulations
**Implementation**:
```makefile
bevsim: simulation/behavioral/$(TOP_BLOCK).raw

simulation/behavioral/$(TOP_BLOCK).raw: specs/generated/design_params.yaml src/behavioral.py
	@mkdir -p simulation/behavioral
	cd src && python behavioral.py ../specs/generated/design_params.yaml ../simulation/behavioral/$(TOP_BLOCK).raw
```

#### `make synth`
**Purpose**: Technology mapping using yosys/abc
**Implementation**: (Enhanced version of existing hdl/Makefile)
```makefile
synth: synthesis/netlist/$(TOP_BLOCK)_synth.v

synthesis/netlist/$(TOP_BLOCK)_synth.v: hdl/$(TOP_BLOCK).v tech/$(PDK)/synth.ys
	@mkdir -p synthesis/netlist synthesis/reports
	cd synthesis && yosys -s ../tech/$(PDK)/synth.ys
```

#### `make flow`
**Purpose**: OpenROAD flow integration
**Implementation**:
```makefile
flow: physical/results/$(TOP_BLOCK).gds

physical/results/$(TOP_BLOCK).gds: synthesis/netlist/$(TOP_BLOCK)_synth.v
	@mkdir -p physical/results physical/reports physical/logs
	# Integration with OpenROAD-flow-scripts
	cd physical && make -f $(OPENROAD_FLOW)/flow/Makefile DESIGN_CONFIG=../config/openroad_config.mk
```

#### `make analyze`
**Purpose**: Analysis and plotting from .raw files
**Implementation**:
```makefile
analyze: analysis/plots/performance_summary.pdf

analysis/plots/performance_summary.pdf: simulation/spice/$(TOP_BLOCK).raw src/spice.py
	@mkdir -p analysis/plots analysis/data
	cd src && python spice.py ../simulation/spice/$(TOP_BLOCK).raw
```

#### `make docs`
**Purpose**: Generate documentation with embedded analysis
**Implementation**:
```makefile
docs: docs/generated/complete_report.md

docs/generated/complete_report.md: analysis/plots/*.svg docs/templates/report_template.md
	@mkdir -p docs/generated
	# Template processing to embed analysis results
	python scripts/generate_docs.py docs/templates/report_template.md docs/generated/complete_report.md
```

#### `make pdf`
**Purpose**: Generate final PDF report
**Implementation**: (Enhanced version of existing docs/tex/Makefile)
```makefile
pdf: docs/final/complete_report.pdf

docs/final/complete_report.pdf: docs/generated/complete_report.md docs/tex/simple_table.lua
	@mkdir -p docs/final
	cd docs && pandoc generated/complete_report.md -t latex --lua-filter=tex/simple_table.lua -o final/complete_report.tex
	cd docs/final && pdflatex complete_report.tex
```

### 4. Integration Strategy

#### Phase 1: Foundation (Week 1-2)
1. Create unified Makefile structure
2. Migrate existing hdl/Makefile and docs/tex/Makefile functionality
3. Establish directory structure and basic config system
4. Test basic integration with existing workflows

#### Phase 2: Core Functionality (Week 3-4)
1. Implement specs, layout, netlist, spicesim, digsim targets
2. Create parameter passing system via config.mk
3. Establish dependency relationships
4. Basic testing and validation

#### Phase 3: Advanced Features (Week 5-6)
1. Implement bevsim, synth, analyze targets
2. OpenROAD flow integration
3. Documentation pipeline (docs, pdf targets)
4. Multi-PDK configuration system

#### Phase 4: Optimization (Week 7-8)
1. Parallel execution optimization
2. Incremental build improvements
3. Error handling and logging
4. User experience enhancements

### 5. Technical Challenges & Solutions

#### Challenge: Parameter Propagation
**Solution**: YAML-based parameter files with Python parsers, integrated into make dependency system

#### Challenge: Tool Integration
**Solution**: Wrapper scripts in Python that standardize interfaces between different tools (ngspice, yosys, klayout, etc.)

#### Challenge: Multi-PDK Support
**Solution**: Technology-specific .mk includes with PDK-specific paths, tool configurations, and constraints

#### Challenge: OpenROAD Integration
**Solution**: Submodule or git subtree integration with OpenROAD-flow-scripts, custom config files

#### Challenge: Dependency Tracking
**Solution**: Automatic dependency generation using make's built-in dependency tracking and timestamp checking

### 6. Benefits of Unified Approach

1. **Single Command Execution**: `make all` runs complete design flow
2. **Incremental Development**: Only rebuild changed components
3. **Parameter Consistency**: Single source of truth for design parameters
4. **Reproducible Results**: Consistent environment and tool versions
5. **Parallel Execution**: Independent stages can run concurrently
6. **Quality Assurance**: Automatic checks and validations at each stage
7. **Documentation Integration**: Analysis results automatically embedded in reports

### 7. Compatibility Preservation

- Existing source code in src/ and hdl/ unchanged
- Current docs/ structure mostly preserved
- Existing build/ becomes organized into new structure
- All current workflows continue to work via compatibility targets

### 8. Implementation Notes

- **Pipeline Status**: The current Python pipeline is in early development and will undergo significant changes
- **Flexibility**: The Makefile structure should be designed to accommodate evolving Python tool interfaces
- **Incremental Adoption**: Each make target can be implemented independently, allowing gradual migration
- **Tool Wrapping**: Python wrapper scripts will provide consistent interfaces as the underlying tools evolve

This unified Makefile approach will transform the current fragmented development process into a cohesive, automated design flow while preserving all existing functionality and providing significant productivity improvements.

## Next Steps

When ready to implement, start with Phase 1 and work through each target incrementally. The plan provides a roadmap that can be referenced and adapted as the project evolves.