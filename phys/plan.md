# Simulation Plan

Goal: model simplified sensor-side signal formation in Allpix Squared for
electron and photon hits, including drift/diffusion and induced pulse
waveforms, without modeling a continuous-reset frontend.

## Implementation checklist

- [ ] Replace the current single-purpose simulation setup with a transient-oriented structure:
  - separate electron and photon main configs
  - shared detector placement
  - shared detector model directory
  - sweep-oriented run layout
- [ ] Add `simulation_electron.conf`
  - use `DepositionPointCharge` with `source_type = mip`
  - use fixed center-of-pixel vertical line deposition
  - keep notes that this is a simplified straight-track model
- [ ] Add `simulation_photon.conf`
  - use `DepositionPointCharge` with `source_type = point`
  - use fixed point deposition at the pixel center, with configurable depth `z0`
  - keep notes that this is a simplified absorbed-photon model
- [ ] Replace the current propagation/transfer chain with a transient waveform chain:
  - `ElectricFieldReader`
  - `WeightingPotentialReader`
  - `TransientPropagation`
  - `PulseTransfer`
  - `ROOTObjectWriter`
- [ ] Remove any readout-digitizer assumptions from the first-version configs
  - no CSA
  - no thresholding
  - no continuously resetting frontend model
- [ ] Update detector models so they support the sweep space:
  - silicon only
  - thickness sweep
  - pixel pitch sweep
- [ ] Update sweep infrastructure so that it can vary:
  - sensor thickness
  - pixel pitch
  - bias voltage
  - effective electron deposition
  - effective photon deposition
  - frame / observation time
  - fluence at the study level
- [ ] Keep or rewrite the analysis step so it extracts:
  - pulse/current waveforms
  - integrated collected charge
  - timing summaries
  - hits per pixel per frame from fluence and frame time
- [ ] Keep relevant physics limitation notes in the configs and docs:
  - straight-line electron deposition is an approximation
  - point-like photon deposition is an approximation
  - dark current source is not modeled in first version
  - no APS reset/buffer/read sampling model in first version
- [ ] Mark future upgrade paths clearly in comments/docs:
  - Geant4 for more realistic particle transport and energy deposition
  - TCAD electric-field maps instead of linear fields
  - more realistic doping profiles
  - more realistic dark-current / frontend modeling
- [ ] Reorganize outputs so generated files are separated from hand-edited inputs
- [ ] Remove or retire obsolete parts of the current setup if they no longer match the new transient study

## Physics assumptions and limitations to retain

- Electron deposition is intentionally simplified to a straight vertical line
  through the sensor using `DepositionPointCharge` with `source_type = mip`.
  This is useful for waveform and charge-transport studies, but it does **not**
  model realistic low-energy electron scattering, stopping distributions, or
  secondaries. A future upgrade path is to replace this with Geant4-based
  transport and deposition.

- Photon deposition is intentionally simplified to a point-like charge deposit
  using `DepositionPointCharge` with `source_type = point`. This is useful for
  studying transport and induced waveforms from an absorbed-photon-like event,
  but it does **not** model interaction probability, realistic absorption depth
  statistics, fluorescence, or secondary transport. A future upgrade path is to
  use Geant4-based photon transport and deposition.

- Electric field modeling will use a simple analytic field in the first
  version. This is fast and easy to sweep, but it is still only an
  approximation. A future upgrade path is to use TCAD-derived field maps.

- Doping profile modeling will use a simple profile in the first version,
  primarily to enable recombination models if needed. A future upgrade path is
  to use piecewise or imported profiles.

- The first version is intentionally sensor-side only:
  - no digitizer
  - no CSA
  - no threshold model
  - no continuously resetting frontend
  - no explicit APS reset / sample / buffer model

- Dark current is **not** modeled as a first-class source in the first version.
  Transport losses such as recombination and trapping may be modeled, but
  reverse-bias leakage current and its noise are a separate future extension.

## Modeling order

1. **Detector model**
   - Module/file: detector model + `detector.conf`
   - Parameters:
     - `sensor_material = silicon` (fixed)
     - `sensor_thickness` — **sweep:** `25um, 50um, 75um, 100um`
     - `pixel_size` — **sweep:** `10um, 20um, 30um, 40um, 50um` pitch; this
       sets pixel area for hit rate per pixel and will also be used later for
       capacitance / noise / full-well interpretation
     - `number_of_pixels` — fixed for now

2. **Doping profile** *(optional first pass, likely simple/constant)*
   - Module: `DopingProfileReader`
   - Parameters:
     - `model = constant` (initial assumption)
     - `doping_concentration` — fixed initially, maybe sweep later if needed
   - Purpose:
     - enable recombination models in propagation
   - Future upgrade paths:
     - `regions`
     - imported `mesh` profile

3. **Electric field**
   - Module: `ElectricFieldReader`
   - Parameters:
     - `model = linear`
     - `bias_voltage` — **sweep**
     - `depletion_voltage` — fixed initially, maybe thickness-dependent later
   - Notes:
     - no TCAD field in first version
     - linear field is a simplification
   - Future upgrade paths:
     - `parabolic`
     - `custom`
     - `mesh` field

4. **Weighting potential**
   - Module: `WeightingPotentialReader`
   - Parameters:
     - `model = pad`
   - Notes:
     - use built-in analytic weighting potential
     - fixed initially
   - Future upgrade paths:
     - imported weighting-potential map if waveform fidelity needs to improve

5. **Charge deposition: electron case**
   - Module: `DepositionPointCharge`
   - Parameters:
     - `source_type = mip`
     - `model = fixed`
     - `position = 0um 0um` (pixel center)
     - `mip_direction = 0 0 1`
     - `number_of_charges` — **sweep by electron energy** as effective `e-h/um`
     - `number_of_steps` — fixed initially
   - Notes:
     - straight vertical line deposition
     - no Geant4 scattering/stopping in first version

6. **Charge deposition: photon case**
   - Module: `DepositionPointCharge`
   - Parameters:
     - `source_type = point`
     - `model = fixed`
     - `position = 0um 0um z0`
     - `number_of_charges` — **sweep by photon energy** as `E / 3.64eV`
     - `z0` — fixed initially (likely mid-depth), maybe sweep later
   - Notes:
     - point-like charge deposition
     - absorption probability / dark current not modeled in first version

7. **Transient transport**
   - Module: `TransientPropagation`
   - Parameters:
     - `temperature` — fixed initially
     - `timestep` — fixed initially
     - `integration_time` — **sweep with frame / observation time**
     - `charge_per_step` — fixed initially
     - `distance` — fixed initially
     - `propagate_electrons` / `propagate_holes` — likely both enabled
     - `recombination_model` — initial option: `none` or `constant`
     - `trapping_model` — initial option: `none` or `constant`
   - Sweep candidates:
     - recombination lifetime if we use `recombination_model = constant`
     - trapping lifetime if we use `trapping_model = constant`
   - Notes:
     - use this to obtain induced transient signal / timing

8. **Pulse combination**
   - Module: `PulseTransfer`
   - Parameters:
     - `output_pulsegraphs = true`
     - `timestep` — fixed to match transport resolution
   - Notes:
     - produces per-pixel induced pulse graphs
     - no digitizer in first version

9. **Output**
   - Module: `ROOTObjectWriter`
   - Parameters:
     - keep `PixelCharge`
     - keep pulse-related outputs
     - exclude unnecessarily large objects if needed
   - Notes:
     - no frontend reset / CSA / threshold module in first version

## Sweeps currently planned

- `sensor_thickness`: `25um, 50um, 75um, 100um`
- `pixel_size`: `10um, 20um, 30um, 40um, 50um` pitch; sweep this because
  larger pixels receive more hits per pixel for a uniform beam, and pixel area
  will also feed later capacitance / noise / full-well estimates
- `bias_voltage`: values TBD, likely a small set spanning under/fully depleted
  operation
- `fluence`: sweep at the study level in `hits/cm^2/s` (uniform beam
  assumption)
- `integration_time` / frame time: sweep at the study level to convert fluence
  into hits per pixel per frame
- electron effective deposition:
  - `number_of_charges` in `e-h/um`, mapped from chosen electron energies
- photon effective deposition:
  - `number_of_charges = E / 3.64eV`, mapped from chosen photon energies
- optional later:
  - photon deposition depth `z0`
  - recombination lifetime
  - trapping lifetime

## Explicit non-goals for first version

- no Geant4 particle transport
- no TCAD field maps
- no readout digitizer
- no continuous-reset / CSA frontend
- no dark current source model yet
- no explicit APS reset/buffer/read sampling model yet

## Planned `phys/` directory structure

```/dev/null/phys_tree.txt#L1-21
phys/
├── plan.md                    # input: planning document
├── detector.conf              # input: detector placement / instance config
├── simulation_electron.conf   # input: electron transient Allpix config
├── simulation_photon.conf     # input: photon transient Allpix config
├── run_sweep.sh               # input: scripted sweep launcher
├── analyze_sweep.py           # input: post-processing / summary analysis
├── detector_comparison.tex    # input: manually maintained report source
├── detector_comparison.pdf    # generated: compiled report artifact
├── models/                    # input: detector model files for pitch / thickness sweep
├── sweeps/                    # input: optional sweep definitions / run manifests
├── outputs/                   # generated: Allpix run products
│   └── <run_name>/            # generated: one subdirectory per sweep point
│       ├── data.root
│       ├── modules.root
│       ├── allpix.log
│       └── copied configs / metadata
├── plots/                     # generated: rendered plots / figures
└── reports/                   # generated: optional summaries / comparison notes
```

## Notes on file roles

- **Input** = authored and version-controlled configuration, model, sweep, or
  analysis files
- **Generated** = outputs from Allpix runs, plotting, or report compilation
- generated run products should stay out of the main hand-edited config area so
  that `phys/` remains easy to navigate