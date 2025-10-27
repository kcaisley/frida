# Portable Inverter Testbench

Multi-technology, multi-simulator CMOS inverter design with support for:
- **Technologies:** TSMC 65nm, TSMC 28nm HPC+
- **Simulators:** Cadence Spectre, Synopsys HSPICE, Solido/AFS
- **Features:** Corner analysis, Monte Carlo, transient noise

## File Structure

```
inverter.sp                    - Technology-independent inverter schematic
tech_wrapper_65nm.sp          - 65nm device mappings and parameters
tech_wrapper_28nm.sp          - 28nm device mappings and parameters
tb_inverter_portable.sp       - Simple testbench
tb_inverter_corners.sp        - Advanced testbench with corners/MC/noise
```

## Quick Start

### Basic Simulation

**65nm with Spectre:**
```bash
spectre +define+TECH_65NM +define+SIM_SPECTRE tb_inverter_portable.sp
```

**28nm with Spectre:**
```bash
spectre +define+TECH_28NM +define+SIM_SPECTRE tb_inverter_portable.sp
```

**65nm with HSPICE:**
```bash
hspice tb_inverter_portable.sp -D TECH_65NM -D SIM_HSPICE
```

**28nm with HSPICE:**
```bash
hspice tb_inverter_portable.sp -D TECH_28NM -D SIM_HSPICE
```

## Advanced Features

### Corner Simulations

Use `tb_inverter_corners.sp` for process corner analysis.

**Available Corners:**
- `CORNER_TT` - Typical-Typical (default)
- `CORNER_SS` - Slow-Slow (worst speed)
- `CORNER_FF` - Fast-Fast (best speed, worst leakage)
- `CORNER_SF` - Slow NMOS, Fast PMOS
- `CORNER_FS` - Fast NMOS, Slow PMOS

**Examples:**

```bash
# 65nm slow corner (Spectre)
spectre +define+TECH_65NM +define+SIM_SPECTRE +define+CORNER_SS \
    -raw sim/inv_65nm_ss tb_inverter_corners.sp

# 28nm fast corner (Spectre)
spectre +define+TECH_28NM +define+SIM_SPECTRE +define+CORNER_FF \
    -raw sim/inv_28nm_ff tb_inverter_corners.sp

# 65nm slow corner (HSPICE)
hspice tb_inverter_corners.sp -D TECH_65NM -D SIM_HSPICE -D CORNER_SS \
    -o sim/inv_65nm_ss
```

### Monte Carlo Simulation

Enable statistical mismatch modeling with `ENABLE_MC`.

**65nm Monte Carlo:**
```bash
spectre +define+TECH_65NM +define+SIM_SPECTRE +define+ENABLE_MC \
    -raw sim/inv_65nm_mc tb_inverter_corners.sp
```

**28nm Monte Carlo (local mismatch only):**
```bash
spectre +define+TECH_28NM +define+SIM_SPECTRE +define+ENABLE_MC \
    -raw sim/inv_28nm_mc tb_inverter_corners.sp
```

**28nm Worst Corner + Mismatch:**

Edit `tb_inverter_corners.sp` line ~119 to uncomment:
```spice
.lib '...' global_ass_ps__local_mc
```
Then run:
```bash
spectre +define+TECH_28NM +define+SIM_SPECTRE +define+CORNER_SS +define+ENABLE_MC \
    -raw sim/inv_28nm_ss_mc tb_inverter_corners.sp
```

### Transient Noise Simulation

Enable thermal, shot, and flicker noise in transient analysis.

**Spectre with Transient Noise:**
```bash
spectre +define+TECH_28NM +define+SIM_SPECTRE +define+ENABLE_TNOISE \
    +define+ENABLE_NOISE_TYPICAL \
    -raw sim/inv_28nm_noise tb_inverter_corners.sp
```

**HSPICE with Transient Noise:**
```bash
hspice tb_inverter_corners.sp -D TECH_28NM -D SIM_HSPICE -D ENABLE_TNOISE \
    -o sim/inv_28nm_noise
```

**Noise Options:**
- `ENABLE_NOISE_TYPICAL` - Nominal 1/f noise (28nm only)
- `ENABLE_NOISE_WORST` - Worst-case 1/f noise (28nm only)
- For 65nm: noise is built into corner libraries

**How Transient Noise Works:**

When `ENABLE_TNOISE` is defined:
- **Spectre:** Uses `tnoiseanalysis=yes` with `noisefmax=10G`, `noisefmin=1k`
- **HSPICE:** Uses `.option trannoise=1` with `fmax=10G`, `fmin=1k`
- **Noise Sources Included:**
  - Thermal noise (channel noise in MOSFETs)
  - Shot noise (PN junction currents)
  - Flicker (1/f) noise
  - Resistor Johnson-Nyquist noise

**Important Parameters:**
- `fmax` / `noisefmax` - Sets noise bandwidth (should be 2× circuit BW)
- `fmin` / `noisefmin` - Sets 1/f noise corner frequency
- `seed` / `noiseseed` - Random seed for reproducibility

## Technology Parameters

Parameters automatically set by technology wrappers:

| Parameter | 65nm | 28nm |
|-----------|------|------|
| `VDD_NOM` | 1.2V | 0.9V |
| `VSS_NOM` | 0V | 0V |
| `LMIN` | 120nm | 30nm |
| `WN_UNIT` | 240nm | 120nm |
| `WP_UNIT` | 480nm | 240nm |
| `TEMP_NOM` | 27°C | 27°C |

## Device Mappings

Generic devices in `inverter.sp` map to PDK-specific models:

| Generic | 65nm PDK | 28nm PDK |
|---------|----------|----------|
| `nch_generic` | `nch_lvt` | `nch_lvt` |
| `pch_generic` | `pch_lvt` | `pch_lvt` |

## Customizing the Inverter

Edit `inverter.sp` to change sizing:

```spice
* Custom sizing example
xinv in out vdd vss inverter wp='4*WP_UNIT' wn='2*WN_UNIT' m=2
```

Or modify the subcircuit defaults:
```spice
.subckt inverter in out vdd vss wp='2*WP_UNIT' wn='WN_UNIT' lp='LMIN' ln='LMIN' m=1
```

## Measurements

All testbenches include these measurements:
- `tphl` - High-to-low propagation delay
- `tplh` - Low-to-high propagation delay
- `tpd` - Average propagation delay (tphl+tplh)/2
- `avg_power` - Average power consumption

Results appear in log output and `.mt*` measurement files.

## Solido/AFS Monte Carlo

For Solido variation-aware simulations, use Spectre-compatible syntax:

```bash
# Generate nominal netlist (Solido will handle MC)
spectre +define+TECH_28NM +define+SIM_SPECTRE +define+CORNER_TT \
    -raw sim/inv_28nm_nominal tb_inverter_corners.sp

# Then use Solido to run variation analysis on the generated netlist
```

## Technology Corner Naming

### 65nm Corners:
- `tt_lib` - Typical-Typical
- `ss_lib` - Slow-Slow
- `ff_lib` - Fast-Fast
- `sf_lib` - Slow NMOS, Fast PMOS
- `fs_lib` - Fast NMOS, Slow PMOS

### 28nm Corners:
Format: `a[transistor]_p[passive]`
- `att_pt` - Analog TT, Passive Typical
- `ass_ps` - Analog SS, Passive Slow
- `aff_pf` - Analog FF, Passive Fast
- `asf_ps` - Analog SF, Passive Slow
- `afs_pf` - Analog FS, Passive Fast

## Troubleshooting

**Simulation won't start:**
- Check that PDK paths in tech wrappers exist
- Verify technology and simulator defines are set
- Check for syntax errors: `spectre -checknetlist tb_inverter_corners.sp`

**Transient noise not working:**
- HSPICE: Ensure BSIM model has `tnoimod=1` parameter
- Spectre: Noise libraries must be loaded for 28nm
- Check that `fmax > 1/tstep` and `fmin < 1/tstop`

**Monte Carlo gives same results:**
- Change `seed`/`noiseseed` parameter
- Verify MC library is loaded (check .lib statements)
- For 28nm: ensure `local_mc` or `global_*_mc` section included

**Wrong VDD voltage:**
- Check technology wrapper is being included
- Verify `VDD_NOM` parameter is defined
- Use `.print param VDD_NOM` to debug parameter values

## Example Workflows

### Full Corner Sweep (65nm)
```bash
for corner in TT SS FF SF FS; do
    spectre +define+TECH_65NM +define+SIM_SPECTRE +define+CORNER_$corner \
        -raw sim/inv_65nm_$corner tb_inverter_corners.sp \
        > logs/inv_65nm_$corner.log 2>&1
done
grep "tpd=" logs/inv_65nm_*.log
```

### Noise + Corner Analysis (28nm)
```bash
spectre +define+TECH_28NM +define+SIM_SPECTRE +define+CORNER_SS \
    +define+ENABLE_TNOISE +define+ENABLE_NOISE_WORST \
    -raw sim/inv_28nm_ss_noise tb_inverter_corners.sp
```

### Cross-Simulator Comparison
```bash
# Spectre
spectre +define+TECH_65NM +define+SIM_SPECTRE \
    -raw sim/inv_spectre tb_inverter_portable.sp

# HSPICE
hspice tb_inverter_portable.sp -D TECH_65NM -D SIM_HSPICE \
    -o sim/inv_hspice

# Compare delay results from .mt* files
```

## Adding New Technologies

To add a new technology (e.g., 40nm):

1. Create `tech_wrapper_40nm.sp`:
   ```spice
   .subckt nch_generic d g s b w=200n l=40n m=1
   mn d g s b nch_hvt w=w l=l m=m
   .ends

   .subckt pch_generic d g s b w=400n l=40n m=1
   mp d g s b pch_hvt w=w l=l m=m
   .ends

   .param VDD_NOM=1.1
   .param LMIN=40n
   ...
   ```

2. Add technology selection to testbench:
   ```spice
   .if defined(TECH_40NM)
       .lib '/path/to/40nm/models.lib' tt_lib
       .include 'tech_wrapper_40nm.sp'
   .endif
   ```

3. Run with new define:
   ```bash
   spectre +define+TECH_40NM +define+SIM_SPECTRE tb_inverter_corners.sp
   ```

## References

- TSMC 65nm PDK: `/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/`
- TSMC 28nm PDK: `/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/.../models/`
- Spectre docs: Cadence Spectre Circuit Simulator User Guide
- HSPICE docs: Synopsys HSPICE User Guide (transient noise: Chapter on .option trannoise)
