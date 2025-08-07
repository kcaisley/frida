# SPICE Simulation Flow - Lessons Learned

This document captures key lessons learned from setting up SPICE simulations with TSMC 65LP PDK, data extraction with spicelib, and waveform visualization. These notes help avoid common pitfalls and establish reliable workflows.

## SPICE Netlist Setup

### PDK Model Integration

**Correct Approach:**
```spice
* Include TSMC 65LP transistor models for typical corner
.lib "/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/hspice/toplevel.l" tt_lib
```

**Key Lessons:**
1. **Use `.lib` instead of `.include`** for TSMC model files - the toplevel.l file contains library definitions, not direct includes
2. **Specify corner explicitly** (`tt_lib` for typical) - don't rely on defaults
3. **Check PDK directory structure** - TSMC provides multiple model files; toplevel.l is the main entry point
4. **Combine with standard cell models** - both transistor models and digital cell libraries are needed

### Simulation Control and Data Output

**Critical Error - Missing Output Commands:**
Initial attempt failed with "No '.plot', '.print', or '.fourier' lines; no simulations run"

**Correct Setup:**
```spice
* Save output data - ESSENTIAL for post-processing
.save v(a) v(b) v(c) v(y1) v(y2)

* Control section for ngspice - REQUIRED
.control
tran 0.01n 20n
write test_simple_complete.raw
.endc

* Legacy .tran still needed
.tran 0.01n 20n
```

**Key Lessons:**
1. **`.save` directive is mandatory** - specify all signals to be analyzed
2. **`.control` section required for ngspice** - this executes the simulation and writes output
3. **`write` command generates raw file** - essential for Python post-processing
4. **Keep legacy `.tran`** - some SPICE variants still need this outside .control section
5. **Use binary raw format** - much faster than ASCII for large datasets

## spicelib Python API Usage

### Common API Errors and Solutions

**Error 1: Incorrect method names**
```python
# WRONG - get_title() doesn't exist
print(f'Title: {raw_data.get_title()}')

# WRONG - get_data() doesn't exist for traces  
time = raw_data.get_trace('time').get_data()

# CORRECT - use get_wave() for signal data
time = raw_data.get_trace('time').get_wave()
```

**Error 2: Object length assumptions**
```python
# WRONG - RawRead objects don't support len()
print(f'Points: {len(raw_data)} data points')

# CORRECT - get data array first, then check length
time = raw_data.get_trace('time').get_wave()
print(f'Points: {len(time)} data points')
```

**Error 3: Case sensitivity in trace names**
```python
# WRONG - case mismatch
a = raw_data.get_trace('V(a)').get_wave()  # Note capital V

# CORRECT - lowercase from ngspice
a = raw_data.get_trace('v(a)').get_wave()
```

### Correct spicelib Usage Pattern

```python
from spicelib import *

# Read raw file
raw_data = RawRead('/path/to/file.raw')

# Get available traces (debugging)
trace_names = raw_data.get_trace_names()
print(f'Available: {trace_names}')

# Extract signal data
time = raw_data.get_trace('time').get_wave()
voltage = raw_data.get_trace('v(node)').get_wave()

# Data is returned as numpy arrays
print(f'Time range: {time[0]:.2e}s to {time[-1]:.2e}s')
print(f'Voltage range: {voltage.min():.3f}V to {voltage.max():.3f}V')
```

**Key API Lessons:**
1. **Use `get_wave()` not `get_data()`** - this is the correct method for signal arrays
2. **Trace names are case-sensitive** - ngspice typically uses lowercase
3. **Node voltages use `v(node)` format** - not `V(node)` or just `node`
4. **Raw data returns numpy arrays** - can use all numpy operations directly
5. **Check available traces first** - use `get_trace_names()` for debugging

## Matplotlib Integration with PyQt5

### Backend Configuration

**For Static Plots (batch processing):**
```python
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
```

**For Interactive Plots:**
```python
import matplotlib
matplotlib.use('Qt5Agg')  # PyQt5 backend
import matplotlib.pyplot as plt
```

**Key Lessons:**
1. **Set backend before importing pyplot** - order matters
2. **Use 'Agg' for batch/server environments** - no display required
3. **'Qt5Agg' for interactive plots** - requires PyQt5 installation
4. **Handle backend failures gracefully** - fall back to static plots if PyQt5 unavailable

### Waveform Plot Best Practices

```python
# Convert time to readable units
time_ns = time * 1e9

# Use subplots for grouped signals
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

# Proper line styles and colors
ax1.plot(time_ns, signal, 'b-', linewidth=2.5, label='signal_name')

# Add reference levels
ax1.axhline(y=0.6, color='gray', linestyle='--', alpha=0.7, label='Logic Threshold')

# Save high-quality outputs
plt.savefig('output.png', dpi=200, bbox_inches='tight')
plt.savefig('output.pdf', bbox_inches='tight')  # Vector format
```

## Process Integration Workflow

### Complete Flow Summary

1. **Netlist Preparation**
   - Include PDK models with correct `.lib` syntax
   - Add `.save` directives for all signals of interest
   - Use `.control` section with `write` command

2. **Simulation Execution**
   ```bash
   ngspice -b netlist.sp
   ```

3. **Data Analysis**
   ```python
   from spicelib import *
   raw_data = RawRead('file.raw')
   signals = {name: raw_data.get_trace(name).get_wave() for name in trace_names}
   ```

4. **Visualization**
   - Static plots for documentation
   - Interactive plots for debugging
   - Both PNG (raster) and PDF (vector) formats

### Common Troubleshooting

**Simulation Fails to Run:**
- Check for `.save`, `.control`, and `write` commands
- Verify PDK model paths exist
- Ensure proper .lib syntax for model includes

**Python Analysis Fails:**
- Verify raw file was generated
- Check trace names with `get_trace_names()`
- Use `get_wave()` not `get_data()`
- Handle case sensitivity in node names

**Plot Generation Issues:**
- Set matplotlib backend before importing pyplot
- Use 'Agg' backend for headless environments
- Handle PyQt5 dependencies gracefully
- Convert time units for readability (seconds → ns)

## File Organization

```
src/spice/
├── CLAUDE.md              # This documentation
├── analyze_template.py    # Template analysis script
└── plot_template.py       # Template plotting script

hdl/
├── *.sp                   # SPICE netlists
├── *.raw                  # Simulation results
├── analyze_spice.py       # Analysis script
├── plot_waveforms.py      # Plotting script
└── spice_waveforms.*      # Generated plots
```

## Performance Notes

- **Raw file size**: 2104 points × 6 signals ≈ 50KB (manageable)
- **spicelib loading**: Fast for files <1MB, slower for large transient datasets
- **Plot generation**: PNG at 200 DPI takes ~2-3 seconds
- **Interactive plots**: PyQt5 launch time ~5-10 seconds

## Future Improvements

1. **Automated PDK detection** - script to find and validate model paths
2. **Multi-corner analysis** - run tt, ss, ff corners automatically  
3. **Measurement extraction** - automated delay/power/noise measurements
4. **Waveform comparison** - overlay multiple simulation results
5. **Export to WaveVCD** - generate VCD files for digital timing tools

This workflow has been validated with TSMC 65LP PDK and ngspice, providing a reliable foundation for mixed-signal simulation and analysis.