# Status

The follower is a block on the [pipeline](../../docs/pipeline.md): `params.py` < `subckt.py` < `sim.py` < `types.py` < `analysis.py` < `plots.py` < `runs.py`, each importing only those before it.

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | `netlist(Params)` and its nets `Nets`: source followers and flipped voltage followers, NMOS or PMOS input, an optional output sink on a flipped follower; PDK-compiled devices fingered to the row cells. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Drain and gate wiring, the flipped follower's feedback, the designs the parameters refuse, the named followers and the grid's sizings. Every instance's netlist can be hashed and compared by hand ([flow/netlist_hashes.py](../netlist_hashes.py)). |
| Parameters | ✓ | [params.py](params.py) | `Params` (the design: `Topology`, the input device's type, sizes positive; an output sink only on a flipped follower, `__post_init__`) and `TbParams`, one testbench run: the PDK, the design, what it drives (`Stimulus`: the AC on the input, the AC on a test current into the output, or an input step), the supply, the load, the input level, the reference current, the frequency sweep, the step. The bench every follower is characterized on: into 100 fF (`LOAD_F`), 20 µA references at the named followers' current-source widths (`IREF_A`, `IREF_W`), the test current through 1 MΩ, 1 kHz to 100 GHz; the input levels and supplies swept, each follower's nominal input (`NOMINAL_VIN`). |
| Testbench generator | ✓ | [sim.py](sim.py) | `testbench(TbParams)`: the input a DC level with 1 V of AC, current-reference biases (a diode-connected copy of the current-source device fed the reference current from a supply of its own), the load; or the AC on a test current into the output (1 V through 1 MΩ, DC blocked) for the output impedance; or the input stepping up about its level and back down. `simulate(tb, run_dir)`: one Spectre run (`+preset=mx`, one thread) left on disk in nutbin: the ports and the supply current (`SAVES`); the AC response (`ac`) and every source's transfer to `vout` (`xf`, for the PSRR) after the operating point (`opdc`), or the step's transient (`tran`) every 5 ps. `flow.pipeline.read` reads it as a measurement. |
| Simulation runners | ✓ | [runs.py](runs.py) | `python -m flow --block follower --run <run> --to results`: the CLI's steps characterize each instance by its 29 runs (`testbenches`): at each input level from ground to the supply in twelfths the AC on the input (`input_vin_0` to `input_vin_12`) and on the output (`output_vin_0` to `output_vin_12`); at its nominal input the supply at 90 and 110 % (`supply_90`, `supply_110`) and a step of a quarter of the supply (`step`); `results` gives its metrics and plots. About a minute an instance on one worker in TSMC65. |
| Design space | ✓ | [runs.py](runs.py) | The single designs and the grid below (`@single`, `@grid`), 30 in each PDK. |
| Analysis | ✓ | [analysis.py](analysis.py), [types.py](types.py) | From the runs' measurements: `analyze_transfer` (the operating point's output level and supply current, the small-signal gain at the lowest frequency, the −3 dB bandwidth, the PSRR: that gain over the supply's to the output), `analyze_impedance` (the output impedance over frequency, from the test current's divider), `analyze_slew` (the output's 10–90 % slew rates, 1 % settling and overshoot on each edge of the step: `slewrate`, `settlingTime`, `overshoot`); `metrics`, the record's numbers (`Metrics`, each with which way is better). |
| Plots | ✓ | [plots.py](plots.py) | `Plot` specs of a record's sweeps: the output level, gain, bandwidth, output impedance and PSRR over the input level; the response and the output impedance over frequency at the nominal input; the gain, bandwidth and PSRR over the supply. The viewer draws a record's; the figures step draws them with matplotlib. The step's waveforms are the record's `waves`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py), [test_sim.py](test_sim.py), [test_plots.py](test_plots.py) | Single-pole responses of known gain, bandwidth, impedance and rejection and a ramped step of known slew and settling through the analyses, the metrics and the record; the testbench of each stimulus, its saves and an instance's runs; every figure drawn. |
| Layout generator | ✓ | [subckt.py](subckt.py) | The generator states its placement (`flow.layout.hdl21align`), rows top first: a source follower's input device above its current source; a flipped follower's PMOS devices above its NMOS ones, the input device beside its shunt device, the current source beside the sink. Laid out by the shared step (`flow/layout/step.py`). |
| Layout tests | ✓ | [test_subckt.py](test_subckt.py) | Every instance of the space states a complete placement; the named followers' rows. |
| Layout runner | ✓ | [step.py](../layout/step.py) | `python -m flow --block follower --run <run> --to pex`: a follower, or the grid, by ALIGN, placed as its generator states, then signed off and extracted. |
| DRC runner | ✓ | [step.py](../layout/step.py) | The kit's checker for every layout (the drc step). |
| LVS runner | ✓ | [step.py](../layout/step.py) | The kit's LVS for every layout against the netlist the build placed (the lvs step). |
| PEX runner | ✓ | [step.py](../layout/step.py) | The pex step's extraction, back-annotated by the postsim step. |
| Behavioral model | ✓ | [model.py](model.py), [test_model.py](test_model.py) | `follower.model.Model.of(pdk, follower.Params)`: the characterized output level over the input level, interpolated (`Model.output`), with the gain, bandwidth and output impedance at the nominal input. |

## How to run

```sh
uv run python -m flow --block follower --run scaled --to results                # characterize the grid
uv run python -m flow --block follower --run source --to presim                 # one follower's pre-layout runs
uv run python -m flow --block follower --run flipped --to lvs                   # one follower by ALIGN, without extraction
uv run python -m flow --block follower --run scaled --from table --to table     # the viewer's table
uv run python -m flow --block follower --run scaled --to results --dry-run      # what would run
uv run python -m flow --block follower --run source --to figures                # post-layout, its figures drawn
```

## Design space

- `source`, `source_pmos`, `flipped`, `flipped_pmos`: the four followers by name: the NMOS and the PMOS source follower (input device 32 units wide, current source 16), the NMOS flipped voltage follower and the PMOS one with an output sink (input and shunt devices 16 units, current sources 8).
- `scaled`: each of them at eight sizings (a source follower has no shunt device to size: seven), by name: its widths scaled together, `scaled(source_x0.5)`, `scaled(source_x1)` (the named one), `scaled(source_x2)`, `scaled(source_x4)`; then one size alone doubled, `scaled(flipped_in_w_x2)`, `scaled(flipped_fb_w_x2)`, `scaled(flipped_in_l_x2)`, `scaled(flipped_bias_l_x2)`. The reference current scales with the current source's width (20 µA at the named follower's).

A follower's nominal input is where one of its topology and input type follows: an NMOS source follower 3/4 up the supply, a PMOS one 1/4, the flipped ones 1/2 (NMOS) and 1/4 (PMOS). The metrics are taken there; the input range is the run of input levels around it whose gain stays within 10 % of its gain there, in steps of a twelfth of the supply.

## Measured

TSMC65, pre-layout, at each follower's nominal input, into 100 fF:

- `source`, the NMOS source follower (20 µA, the input at 0.9 V of 1.2 V): gain 0.853, level shift 0.38 V, bandwidth 624 MHz, output impedance 2.44 kΩ, PSRR 20 dB, supply current 20.6 µA, slew +0.73 V/ns through the device and −0.17 V/ns at its bias current (20 µA into 100 fF is 0.2 V/ns), no overshoot. Post-layout (ALIGN, 3.28 µm × 3.93 µm, DRC clean, LVS matching, 4.4 fF added) the bandwidth and the slew rates fall by 2 %.
- `flipped_pmos`, the PMOS flipped voltage follower with its sink (the input at 0.3 V): gain 0.798, the output 0.56 V above the input, bandwidth 4.1 GHz, output impedance 326 Ω (peaking to about 0.8 kΩ near 2.5 GHz: its local loop), PSRR 11 dB, supply current 42.8 µA, slew +2.1 V/ns through the shunt device and −0.37 V/ns, 15 % overshoot on the rising edge, the gain within 10 % over 0.4 V of input. Post-layout (3.68 µm × 3.93 µm, DRC clean, LVS matching, 4.5 fF added) the bandwidth falls by 15 % and the rising slew rate by 17 %.
