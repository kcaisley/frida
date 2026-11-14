# Status

The charge-sensitive amplifier is a block on the [pipeline](../../docs/pipeline.md): `params.py` < `subckt.py` < `sim.py` < `types.py` < `analysis.py` < `plots.py` < `runs.py`, each importing only those before it, `model.py` above them.

## What it measures

Each amplifier is driven on one bench so that amplifiers compare: a detector's capacitance on the
input, a known charge injected through a small capacitor by a voltage step, a discriminator's
input capacitance on the output, biases mirrored from reference currents on a supply of their own.

- The response to each charge (0.25 to 2 fC): the output's baseline before the charge, its largest
  excursion (the amplitude) and that over the charge (the charge gain), the peaking time from the
  injection to the maximum, the 10–90 % rise time, the time over a threshold at half the smallest
  charge's amplitude, and the return to within 5 % of the amplitude of the baseline.
- The amplitude's nonlinearity: the largest deviation from the straight line through zero charge
  and the largest charge, over the largest amplitude (Razavi's end-point definition).
- The output noise without charge, integrated from 1 Hz to 1 THz (the band's last decade, on the
  output's f^-2 tail, holds under 0.1 % of the power), and the equivalent noise charge: the rms
  output noise over the smallest charge's gain, in electrons, with no shaper.
- The supply's power at rest, and over the supply (90, 100 and 110 % of nominal) the smallest
  charge's gain and peaking time, the ENC and the power.

| Feature | Status | File | Notes |
|---|---|---|---|
| Parameters | ✓ | [params.py](params.py) | `Params` (the design: the input device's type, `Feedback`, the feedback capacitor `cf`, sizes positive, `cf` not negative), `layout_view` (the design without `cf`, which the row cells do not draw), and `TbParams`, one testbench run: the PDK, the design, the run's `Stimulus` (`CHARGE`: a charge injected, a transient; `NOISE`: no charge, the output noise), the supply, the detector, injection and load capacitances, the charge, the bias currents and voltages, the timing, the noise sweep. The bench every amplifier is characterized on and the charges and supplies swept. |
| Netlist generator | ✓ | [subckt.py](subckt.py) | `netlist(Params)` and its nets `Nets`: a cascoded common-source preamplifier with a current-source load of the other type, NMOS or PMOS input; Krummenacher feedback (a pair of the other type against `vref`, its mirror filtered by a MOS capacitor), continuous feedback (one long device biased by `vfb`) or reset feedback (a switch driven by `vfb`). 5 devices, 9 with the Krummenacher. The feedback capacitor `cf` (5 fF) is simulation-only. A source follower after `out` is the follower block. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Core and feedback wiring for each amplifier, the Krummenacher pair's type, no `cf` at zero or in the layout view, the designs the parameters refuse, the named amplifiers and the grid's sizes. Every instance's netlist can be hashed and compared by hand ([flow/netlist_hashes.py](../netlist_hashes.py)). |
| Testbench generator | ✓ | [sim.py](sim.py) | `testbench(TbParams)`: 100 fF of detector on the input, the charge injected through 1 fF by a voltage step (electrons into an NMOS input, holes into a PMOS one), 10 fF on the output. Diode-connected references for the load (mirrored from 4 µA) and the Krummenacher tail (twice the 10 nA discharge); a copy fed 4 µA for the cascode, standing 150 mV off the input device's rail; for the continuous feedback's gate, the feedback device's copy fed 10 nA standing on a copy of the amplifier's core (load, cascode and input device, its input tied to its output as the feedback device ties them at rest). Every bias gate is held to its rail by 1 mF, so the output noise is the amplifier's own. The reset opens 50 ns before the charge. `simulate(tb, run_dir)`: after the operating point (`opdc`), the charge run's transient (nutbin, strobed every 50 ps, the step Spectre X's own) or the noise run's output noise at `out` referred to the injection source, 1 Hz–1 THz at 50 points a decade (PSF ASCII); `flow.pipeline.read` reads either. |
| Testbench tests | ✓ | [test_sim.py](test_sim.py) | The bench's defaults, the injection's sign, the references and replicas (the continuous feedback's copy of the core for both input types), each bias gate's bypass, the reset, the noise run, the saves, the runs of one instance, the values a run refuses. |
| Simulation runners | ✓ | [runs.py](runs.py) | `python -m flow --block csa --run <run> --to results`: each instance by its runs (`testbenches`): 0.25, 0.5, 1 and 2 fC (`q250` to `q2000`) and, but for the reset amplifier, the noise run (`noise`) at the PDK's supply; the smallest charge and the noise at 90 and 110 % of it (`supply_90`, `supply_90_noise`, ...). Seven to nine Spectre runs. `results` gives its metrics and the plots that hold a value. |
| Design space | ✓ | [runs.py](runs.py) | The four amplifiers by name (`krum`, `krum_pmos`, `continuous`, `reset`, `@single`) and the grid `scaled` (`@grid`): each at seven sizes, the widths of its input device, cascode and load at half, as named, twice and four times (`scaled(krum_x0.5)`), the input device twice as wide or as long, the load twice as long (`scaled(krum_in_w_x2)`, `scaled(krum_load_l_x2)`): 28 in each PDK. |
| Analysis | ✓ | [analysis.py](analysis.py), [types.py](types.py) | `analyze_pulse` (baseline, amplitude and charge gain per charge, peaking time refined between the strobes, 10–90 % rise time, time over a threshold half the smallest charge's amplitude, return to within 5 % of the baseline, supply current; NaN timings where the output does not respond; the responses on one grid), `analyze_noise` (output rms noise over the sweep and, over the smallest charge's gain, the unshaped ENC), `analyze_supply` (the smallest charge's gain and peaking time, the ENC and the power over the supply); `metrics`, the record's numbers (`Metrics`), among them the amplitude's end-point nonlinearity over the four charges. Every field cites its textbook source or says it is not in the reference texts. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | Closed forms on a simulator's uneven steps and on the strobes: piecewise-linear pulses (NMOS and PMOS polarity), the CR-RC pulse (amplitude, peaking time between strobes, Lambert-W rise, time over threshold and return), the reset's single-pole step, an undershoot, a pulse slower than its record, no response, unstrobed runs resampled onto one grid; an RC low-pass's noise (kT/C over the band) and its ENC; a compressing amplitude's nonlinearity; the supply sweep, the metrics and the record. |
| Plots | ✓ | [plots.py](plots.py), [test_plots.py](test_plots.py) | `Plot` specs of a record, one curve each: the response to each charge from the injection (`pulse_q250` to `pulse_q2000`), the amplitude, charge gain and time over threshold over the charge, the output noise density, the charge gain, peaking time, ENC and power over the supply (in volts). The viewer draws a record's; the figures step draws them with matplotlib. |
| Layout generator | ✓ | [subckt.py](subckt.py) | The generator states its placement (`flow.layout.hdl21align`): rows top first, the input type's rail at the bottom for an NMOS input and at the top for a PMOS one; laid out by the shared step (`flow/layout/step.py`) from `layout_view`, without `cf`. |
| Layout tests | ✓ | [test_subckt.py](test_subckt.py) | Every instance of the space states a complete placement; the named amplifiers' rows. |
| Behavioral model | ✓ | [model.py](model.py), [test_model.py](test_model.py) | `csa.model.Model.of(pdk, csa.Params)`: the characterized amplitude over the injected charge (interpolated), the charge gain, peaking time and ENC at the smallest charge. |
| Feedback capacitor | ✗ | - | `cf` is ideal: the row cells draw no capacitor (a MOM or MIM `cf` would come from `flow.layout.devices.momcap`). |
| Monte Carlo | ✗ | - | No mismatch: the threshold dispersion would need a Monte Carlo. |

## How to run

```sh
uv run python -m flow --block csa --run krum --to presim                 # one amplifier, pre-layout
uv run python -m flow --block csa --run krum --to results                # laid out, extracted, simulated again
uv run python -m flow --block csa --run scaled --to results --dry-run    # what a grid would run
```
