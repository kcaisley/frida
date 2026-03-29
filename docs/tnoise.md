# Transient Noise in ngspice: Status and Effort Estimate

## Current state (ngspice 45.2)

ngspice has **no device-level transient noise**. The `.noise` analysis computes
frequency-domain noise spectral densities using device models (thermal + flicker
for MOSFETs, thermal + 1/f for resistors), but this does not feed into the
transient simulation engine.

The `trnoise` keyword exists only on `vsrc` and `isrc` — it injects user-specified
white/1/f/RTS noise on voltage and current sources. This is useful for modeling
external noise (supply ripple, etc.) but does not model intrinsic device noise.

### What works today

- `.noise v(out) Vin dec 10 1 1G` — frequency-domain noise analysis, fully
  supported with PDK device models. Standard approach for input-referred noise.
- `V1 a 0 dc 0.6 trnoise(100u 10p 0 0)` — white noise injected on a source.
  Amplitude set manually, not derived from device physics.
- `reset` in a `.control` loop re-seeds `agauss()`/`gauss()` for Monte Carlo
  mismatch analysis. This is process variation, not noise.

### What does NOT work

- `.options TRTHERMAL` — undocumented/unimplemented. No effect.
- `.options TRNOISE FMAX=...` — only affects `trnoise` sources, not devices.
- Resistors, MOSFETs, BJTs produce zero transient noise regardless of settings.

## Source code analysis

The `trnoise_state` infrastructure (`src/include/ngspice/1-f-code.h`) handles
white noise + 1/f noise + RTS noise generation. It is referenced **only** from
`vsrc/vsrcload.c` and `isrc/isrcload.c`. Zero references from any device model.

The device noise files (`b4v7noi.c`, `resnoise.c`, etc.) implement only the
frequency-domain `.noise` analysis via `NOISEAN` structures. There is no path
from these into the transient engine.

## Effort estimate to add transient device noise

### Resistor (easy, ~200 lines of C, 2-3 days)

`RESload()` is 38 lines — trivially simple. The thermal noise PSD is already
computed in `resnoise.c` (`4kT * conductance`). Implementation:

1. Add `trnoise_state *` to `RESinstance` in `resdefs.h` (~5 lines)
2. Initialize noise state in `REStemp()` using `i_rms = sqrt(4kT/R)` (~20 lines)
3. In `RESload()`, during transient, inject noise current into RHS vector (~15 lines):
   ```c
   if (ckt->CKTmode & MODETRAN && here->REStrnoise_state) {
       double i_noise = trnoise_state_get(state, ckt, n);
       *(ckt->CKTrhs + here->RESposNode) += i_noise;
       *(ckt->CKTrhs + here->RESnegNode) -= i_noise;
   }
   ```
4. Cleanup in `RESdelete()` (~3 lines)

This would be immediately useful for kT/C noise in sampling switches.

### MOSFET / BSIM4 (moderate, ~400-600 lines, 1-2 weeks)

MOSFET noise is operating-point-dependent (Vgs, Vds, gm, gds change every
timestep). The noise PSD formulas exist in `b4v7noi.c` but need to be
extracted and evaluated at each timestep.

1. Add `trnoise_state *` pointers to `BSIM4instance` (~10 lines)
2. Compute drain-source noise current PSD from operating point — reuse
   `noizDens` calculation from `b4v7noi.c` (~50 lines)
3. Inject noise current in `BSIM4load()` (~20 lines)
4. Freeze noise during Newton-Raphson iterations (generate once per timestep,
   not once per NR iteration) (~30 lines)
5. Update `trnoise_state` amplitude as operating point changes (~30 lines)

### Convergence and timestep handling (hard, ~200 lines, 1-2 weeks)

The difficult part is not the noise injection itself but maintaining simulator
stability:

- Random noise currents can cause NR convergence failures. Noise must be frozen
  during iterations and only updated when the timestep advances.
- The adaptive timestep controller sees noise as "fast changes" and may shrink
  the timestep aggressively, making simulation extremely slow. A noise bandwidth
  limit or minimum timestep override is needed.
- 1/f noise generation at very low frequencies has numerical stability issues.

### Summary

| Component | Lines of C | Difficulty | Time estimate |
|-----------|-----------|------------|---------------|
| Resistor transient noise | ~150-200 | Easy | 2-3 days |
| BSIM4 transient noise | ~400-600 | Moderate | 1-2 weeks |
| Convergence/timestep handling | ~200 | Hard | 1-2 weeks |
| Testing + validation | — | Moderate | 1 week |
| **Total** | **~1000** | | **4-6 weeks** |

## Workaround for FRIDA

For comparator noise characterization, use `.noise` analysis in `scope=sim` mode
(standalone SPICE, no cosim). This gives input-referred noise spectral density
directly.

For transient effects (e.g., comparator metastability near threshold), add
calibrated `trnoise` sources at the comparator differential input with amplitude
derived from the `.noise` analysis results:

```spice
* Calibrated input-referred noise source
* nV_rms from .noise analysis, tstep = 1/(2*f_bandwidth)
Vnoise_p inp inp_noisy trnoise(9.1n 100p 0 0)
Vnoise_n inn inn_noisy trnoise(9.1n 100p 0 0)
```
