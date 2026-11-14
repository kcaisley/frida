# Status

The delay line and ring oscillator is a block on the [pipeline](../../docs/pipeline.md): `params.py` < `subckt.py` < `sim.py` < `types.py` < `analysis.py` < `plots.py` < `runs.py` < `model.py`, each importing only those before it.

| Feature | Status | File | Notes |
|---|---|---|---|
| Parameters | ✓ | [params.py](params.py) | `Params` (the design: `Stage.INVERTER` or `Stage.COUPLED` stages, `Control.NONE`, `STARVED` or `TAIL`, the number of stages, single-ended or differential, open or a ring, an injection device; sizes as positive multiples of the unit width and minimum length; the chains that do not build refused in `__post_init__`), and `TbParams`, one testbench run: the PDK, the design, the supply, the control voltage, the loads, the kick-start, the input clock, the enable, the transient's length and output interval. The bench every chain is characterized on: over the supply (`SUPPLY_SWEEP`) at the nominal control (`NOMINAL_CONTROL`), and over the control (`CONTROL_SWEEP`) at the PDK's supply; the gain about the nominal control from `GAIN_POINTS`. |
| Netlist generator | ✓ | [subckt.py](subckt.py) | `netlist(Params)` and its nets `Nets`: delay lines and ring oscillators of inverter or coupled pseudo-differential stages, single-ended or differential, current-starved or on a shared tail, a NAND enable and an injection device in a ring. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Stage wiring, ring closure and enable, coupling, starving and tail devices, the chains the parameters refuse. |
| Testbench generator | ✓ | [sim.py](sim.py) | `testbench(TbParams)`: one bench for every chain: supply, enable, a kick-start that holds the outputs apart after the enable (switches to the rails: a capacitive kick left tower180's coupled rings in their common-mode latch), a complementary input clock, one control voltage (`vbn`, `vctrl`, and `vdd - vbp`), output loads. `simulate(tb, run_dir)`: one Spectre transient (`+preset=mx`, one thread) left on disk in nutbin: the ports and the supply current (`SAVES`) every 2 ps, Spectre's step bounded to it. `flow.pipeline.read` reads it as a measurement, nothing resampled. |
| Testbench tests | ✓ | [test_sim.py](test_sim.py) | The bench's defaults, its sources, kick-start and loads, its saves, the values it refuses. |
| Simulation runners | ✓ | [runs.py](runs.py) | `python -m flow --block delay --run <run> --to results`: the CLI's steps (`flow.sweep.runner`, `flow.steps`) characterize each instance by its runs (`testbenches`): at the nominal control at 90, 100 and 110 % of the PDK's supply (`supply_90` to `supply_110`), and, a chain with a control, at the PDK's supply at 5/12 to all of it (`control_5` to `control_12`; the nominal one is `supply_100`). Three to ten Spectre transients of 40 ns. `results` gives its metrics and plots. |
| Design space | ✓ | [runs.py](runs.py) | The named chains (`@single`) and each of them at its sizes (`@grid sizes`), 48 in each PDK. |
| Analysis | ✓ | [analysis.py](analysis.py), [types.py](types.py) | From the runs' measurements: `analyze_oscillation` (a ring's frequency over ten cycles from the fifth rising output edge, the supply current, swing and duty cycle over the same window; its power, energy per cycle, stage delay and VCO gain), `analyze_propagation` (a delay line's 50 % delays to its rising and falling output, the output's 10–90 % rise and fall times, the supply current over two input periods; its power, energy per input cycle and stage delay); `metrics`, the record's numbers (`Metrics`). |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py), [test_plots.py](test_plots.py), [test_runs.py](test_runs.py) | Synthetic runs of known frequency, delay and current through the analyses, the metrics and the record; every figure drawn; the design space and each chain's runs. |
| Plots | ✓ | [plots.py](plots.py) | `Plot` specs of a record's sweeps, one curve each: over the supply a ring's frequency or a line's delays, the stage delay and the energy per cycle; over the control a ring's frequency and VCO gain or a line's delays and output rise and fall times, and the energy per cycle. The viewer draws a record's; the figures step draws them with matplotlib. |
| Layout generator | ✓ | [subckt.py](subckt.py) | The generator states its placement (`flow.layout.hdl21align`): rows top first, the starving PMOS heads, the inverters' PMOS, the coupling PMOS and NMOS, the inverters' NMOS (the shared tail in its middle), the starving NMOS feet; a ring's stages in its folded order, a differential line's rows mirrored. Laid out by the shared step (`flow/layout/step.py`). The rows are the hand-written floorplans' it replaced; the floorplans' pin escape sides are not stated. |
| Layout tests | ✓ | [test_subckt.py](test_subckt.py) | Every instance of the space states a complete placement; the named chains' rows. |
| Layout runner | ✓ | [step.py](../layout/step.py) | `python -m flow --block delay --run <run> --to pex`: a named chain or a grid by ALIGN, placed as its generator states, then signed off and extracted. |
| DRC runner | ✓ | [step.py](../layout/step.py) | gdscheck and the PDK's DRC for every layout. |
| LVS runner | ✓ | [step.py](../layout/step.py) | The PDK's LVS for every layout against the netlist the build placed. |
| Behavioral model | ✓ | [model.py](model.py), [test_model.py](test_model.py) | `delay.model.Model.of(pdk, delay.Params)`: the characterized delay per stage over the supply, a line's delay (its stages' delays) and a ring's frequency from it. |

## How to run

```sh
uv run python -m flow --block delay --run ring5_starved --to results     # characterize one named chain
uv run python -m flow --block delay --run sizes --to results             # every chain at every size
uv run python -m flow --block delay --run chain4 --to lvs                # one chain by ALIGN, without extraction
uv run python -m flow --block delay --run sizes --to results --dry-run   # what would run
```

## Design space

- `ring5`: five-stage inverter ring oscillator, enabled.
- `ring5_starved`: current-starved five-stage ring VCO.
- `ring4_coupled`: four-stage pseudo-differential coupled ring, with its injection device.
- `ring4_tail`: four-stage coupled ring on a shared tail.
- `chain4`: four-stage inverter delay line.
- `chain2_coupled`: two-stage coupled differential buffer.
- `chain4_starved`: four-stage current-starved delay line.
- `sizes`: each named chain at every size it has devices for, by the chain's name and the size's: every width scaled together to half, as it is, to twice and to four times (`sizes(ring5_half)`, `_nominal`, `_double`, `_quadruple`); the coupling inverters alone doubled (`_coupling`, coupled stages only); the starving devices and the tail doubled (`_control`, controlled chains only); the stage inverters at twice their length (`_long`).
