# Status

The sampling switch is the second block on the [pipeline](../../docs/pipeline.md): `params.py` < `subckt.py` < `sim.py` < `types.py` < `analysis.py` < `plots.py` < `sweep.py`, each importing only those before it.

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | `netlist(Params)` and its nets `Nets`: an NMOS, PMOS or transmission-gate switch; half-size charge-injection dummies; a bootstrapped NMOS gate; PDK-compiled devices fingered to the row cells. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | The FRIDA-1 switch, the dummies' and the bootstrap's wiring, the designs the parameters refuse. Every instance's netlist can be hashed and compared by hand ([flow/netlist_hashes.py](../netlist_hashes.py)). |
| Parameters | ✓ | [params.py](params.py) | `Params` (the design: the switch type, `SwitchType.BOOTSTRAP` the bootstrapped NMOS switch; sizes positive; a dummy only on a switch of two units or more, `__post_init__`), `STRUCTURE` (the parameters that pick a hand-written floorplan), and `TbParams`, one testbench run: the PDK, the design, the supply, the load, the input level and its step, the clock, the periods. The bench every switch is characterized on: into 1 pF (`LOAD_F`) at a 10 ns clock (5 ns tracking, 50 ps edges), six periods, a sample every 5 ps; the input levels and supplies swept. |
| Testbench generator | ✓ | [sim.py](sim.py) | `testbench(TbParams)`: complementary clocks (tracking while `clk` is high), an input level and the load; with an input step the input toggles by it once per period in mid-hold, so every track phase settles from a known step. `simulate(tb, run_dir)`: one Spectre transient (`+preset=mx`, one thread) left on disk in nutbin: the ports and the supply current (`SAVES`) every 5 ps (`STROBE_S`), Spectre's step bounded to it. `flow.pipeline.read` reads it as a measurement, nothing resampled. |
| Simulation runners | ✓ | [sweep.py](sweep.py) | `python -m flow samp --to record`: the CLI's netlist, sim and record steps (`flow.sweep.runner`) characterize each instance by its 14 runs (`runs`): the input stepping a twelfth of the supply at 1/12 to 11/12 of the supply (`vin_1` to `vin_11`), at mid-supply input at 90, 110 and 120 % of the supply; `record` gives its metrics and plots, about 30 s an instance. The `frida1_transient` reference and the four-switch `samp_characterization` retired with their resampled `MeasSamp` measurements: the families hold the switches and sizes, `--instance` runs any named one. |
| Design space | ✓ | [sweep.py](sweep.py) | The grids and named instances below, 28 in each PDK. |
| Analysis | ✓ | [analysis.py](analysis.py), [types.py](types.py) | From the runs' measurements: `analyze_track` (the track phase's time constant from its 1/e to its 1/e^2 point, the on-resistance into the load, the bandwidth, the track error), `analyze_hold` (pedestal, droop, input feedthrough); `metrics`, the record's numbers. In TSMC65 into 1 pF (run 20261026_010439): FRIDA-1's transmission gate 130–550 Ω (highest at mid-supply), the NMOS switch from 140 Ω to open above 0.7 V, the bootstrapped one 140–230 Ω at 32 units and 30–45 Ω at 160; pedestals within ±0.7 mV for the transmission gates, −2 mV for the NMOS switches at 32 units, growing with the width (−10 mV at 160). |
| Plots | ✓ | [plots.py](plots.py) | `Plot` specs of a record's sweeps: the on-resistance, track error, pedestal and feedthrough over the input level, the on-resistance and pedestal over the supply. The viewer draws a record's; the figures step draws them with matplotlib. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py), [test_sim.py](test_sim.py), [test_plots.py](test_plots.py) | An ideal RC sampler of known time constant, pedestal and feedthrough through the analyses, the metrics and the record; the testbench and its saves; every figure drawn. |
| Layout generator | ✓ | [subckt.py](subckt.py) | The generator states its placement (`flow.layout.hdl21align`): rows top first for the bootstrap, the transmission gates (each beside its dummy) and the NMOS switch in two halves; ALIGN places the other structures on its own. Laid out by the shared step (`flow/layout/step.py`); identical to the hand-written floorplans it replaced (XOR, TSMC65 and IHP130). |
| Layout tests | ✓ | [test_subckt.py](test_subckt.py) | Every instance of the space states a complete placement or none; the named structures' rows. |
| Layout runner | ✓ | [step.py](../layout/step.py) | `python -m flow samp --to pex [--instance NAME] [--pdk P]`: a named switch, or the design space, by ALIGN, placed as its generator states, then signed off and extracted (the four in all six PDKs, laid out then also by cIcCreator and laygo, both since removed: all 66 layouts DRC clean and LVS correct). |
| DRC runner | ✓ | [step.py](../layout/step.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [step.py](../layout/step.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No standalone sampler runner. |
| Behavioral model | ✓ | [model.py](model.py), [test_model.py](test_model.py) | `samp.model.Model.of(pdk, samp.Params)`: the characterized on-resistance over the input level (the tracking lag `R(v) C dv/dt`), kT/C of the ADC's load, an assumed 2 ps jitter. The behavioral ADC runs the model's physics: `Model.Behavioral` (what `behavioral()` gives for a load) and `Model.sample`, each side held through its input-dependent RC with its noise and one jitter for both; `Model.resistance`, the measured curve or, without one, the triode conductances of the switch's sizing (`Model.conductances`, from the rough device constants in `params.py`). |

## How to run

```sh
uv run python -m flow samp --to record [--pdk P] [--instance I]    # characterize, into a new build/samp/<run>
uv run python -m flow samp --from layout --to pex                 # lay out the latest run's instances, signed off
uv run python -m flow samp --to lvs --instance frida1             # a named switch by ALIGN, without extraction
uv run python -m flow samp --from table --to table                # the viewer's table of the latest run
uv run python -m flow samp --to record --predict                  # what would run
uv run python -m flow samp --from figures --to figures --run DIR    # a run's figures
```

## Design space

- `scaled`: each switch 8 to 128 units wide, a quarter to four times FRIDA-1's (`scaled(tgate, mos_w=32, dummy=False)` is FRIDA-1's transmission gate; `tgate` with and without half-size dummies, `nmos`, and the bootstrapped switch by width, `scaled(bootstrap_w64)`, its boost capacitor half the switch and its helpers an eighth, none under 4 units, the finest PDK's minimum width).
- `long_channel`: each switch at twice its length.
- `boost_ladder`: the bootstrapped switch as an on-resistance ladder, the ADC study's samplers (`flow.adc.sweep._samplers`), each rung by its width: `boost_ladder(w32)` with the doubled boost capacitor, then `w64`, `w112` and `w160`, the boost capacitor as wide as the switch and the helpers an eighth, so every rung is boosted alike.
- `frida1`, `tgate_dummy`, `nmos`, `bootstrap`: the four switches by name, for their layouts (each its hand-written floorplan), not swept apart from their points in `scaled`.

The bootstrap keeps every PMOS body on vdd (the row cells' wells): the boosted node's junctions leak toward vdd while sampling. Its cascoded gate pull-down is a stack of two clocked devices (a gate on a rail has no route in the row cells).

TODO: sampling noise (kT/C) separately from comparator offset, and the resistance versus sizing. See [project TODO](../../docs/todo.md#samp).
