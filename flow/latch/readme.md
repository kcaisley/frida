# Status

The latch, flip-flop, divider and SR latch are a block on the [pipeline](../../docs/pipeline.md): `params.py` < `subckt.py` < `sim.py` < `types.py` < `analysis.py` < `plots.py` < `runs.py` < `model.py`, each importing only those before it.

| Feature | Status | File | Notes |
|---|---|---|---|
| Parameters | ✓ | [params.py](params.py) | `Params` (the design: `Style.CLOCKED` static C2MOS, `Style.TSPC`, `Style.DICE`, `Style.SR_NAND`, `Style.SR_NOR`; `flop`, `divider`, `reset`; widths and length as positive multiples of the PDK's unit; the combinations that do not build refused in `__post_init__`), `Bench` (the timing or the upset bench) and `TbParams`, one testbench run: the PDK, the design, the supply, the loads, the clock, the data offset, the reset, the set and reset period, the edges, the cycles, a strike's charge and time. The sweeps every design is characterized over: `SUPPLY_SWEEP`, `DATA_OFFSET_SWEEP_S`, `PERIOD_SWEEP_S`, `UPSET_CHARGES_C`. |
| Netlist generator | ✓ | [subckt.py](subckt.py) | `netlist(Params)` and its nets `Nets`: static C2MOS latches with an optional asynchronous reset, master-slave and divide-by-two flip-flops, TSPC flip-flops and dividers (three dynamic stages on clk alone and an output inverter, 11 devices), DICE latches (four interlocked storage nodes, each written by a clocked inverter of its own, 30 devices), NAND and NOR SR latches. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Clocked-inverter wiring, master and slave clocks, divider feedback, TSPC stages on clk alone, DICE interlock and writers, SR gates, the designs the parameters refuse, the runs' designs. |
| Testbench generator | ✓ | [sim.py](sim.py) | `testbench(TbParams)`: on the timing bench complementary clocks, data toggling once per cycle a set offset before each capturing edge (a flip-flop's rising, a latch's closing edge), an initial reset, set and reset pulses, output loads; on the upset bench the latch takes a 1 for a nanosecond and holds it, and a double-exponential current (a Spectre literal on the hierarchical node) puts a charge on the storage node then holding a 0, which carries no load in either latch. `simulate(tb, run_dir)`: one Spectre transient (`+preset=mx`, one thread) left on disk in nutbin, the ports and the supply current (`SAVES`) every picosecond. `flow.pipeline.read` reads it as a measurement. |
| Testbench tests | ✓ | [test_sim.py](test_sim.py) | The data's timing against the capturing edge, the SR pulses' polarity, the upset bench's hold and load, the saves, the values a run refuses. |
| Simulation runners | ✓ | [runs.py](runs.py) | `python -m flow --block latch --run <run> --to results`: each instance at 90, 100 and 110 % of the supply (`supply_<percent>`); a latch or flip-flop over the data offset, −200 to 300 ps (`offset_<ps>ps`); a flip-flop or divider over the clock period, 1 ns to 30 ps, its edges and data offset scaled with it (`period_<ps>ps`); a C2MOS or DICE latch without reset struck with 1 to 200 fC (`upset_<fC>fc`). Three to 34 Spectre runs an instance (`testbenches`); `results` gives its metrics and plots. |
| Design space | ✓ | [runs.py](runs.py) | The single designs and grids below (`@single`, `@grid`). |
| Analysis | ✓ | [analysis.py](analysis.py), [types.py](types.py) | `analyze_timing` (launch-to-q delays rising and falling, the edges taking the new or keeping the old value, the supply current, the energy per cycle), `analyze_constraint` (setup at a 10 % delay pushout, hold), `analyze_sr` (set and reset delays, the supply current), `analyze_upset` (whether a strike flips the held 1, q's dip, the critical charge); `metrics`, the record's numbers (`Metrics`). |
| Plots | ✓ | [plots.py](plots.py) | `Plot` specs of a record's sweeps, one curve each: the delays to q rising and falling and the energy over the supply; the clock-to-Q delays and the fractions captured and held over the data offset; the fraction captured and the clock-to-Q delays over the clock frequency; q's dip and the upset over a strike's charge. The viewer draws a record's; the figures step draws them with matplotlib. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py), [test_plots.py](test_plots.py), [test_runs.py](test_runs.py) | A synthetic flip-flop and latch of known setup and clock-to-q, a synthetic SR latch, strikes of known dip and critical charge, through the analyses, the metrics and the record; every figure drawn; each design's runs. |
| Layout generator | ✓ | [subckt.py](subckt.py) | The generator states its placement (`flow.layout.hdl21align`): a PMOS row above an NMOS row, each clocked inverter's stack side by side, the feedback beside the forward stage, the output last; a flip-flop's master above its slave; a DICE latch's writers above its interlocked storage devices. Laid out by the shared step (`flow/layout/step.py`). |
| Layout tests | ✓ | [test_subckt.py](test_subckt.py) | Every instance of the runs states a complete placement in every PDK checked out; the named designs' rows. |
| Behavioral model | ✓ | [model.py](model.py), [test_model.py](test_model.py) | `latch.model.Model.of(pdk, latch.Params)`: the characterized delays, energy per cycle, setup and hold; `Model.captures` (data taken from the setup on, kept out from the hold on) and `Model.delay_s`. |

## How to run

```sh
uv run python -m flow --block latch --run flop_rst --to results     # characterize one design
uv run python -m flow --block latch --run scaled --to results       # a grid
uv run python -m flow --block latch --run latch_dice --to lvs       # one design by ALIGN, signed off
uv run python -m flow --block latch --run scaled --to results --dry-run
```

## Design space

- `latch`, `latch_rst`, `flop_rst`, `div2`, `flop_tspc`, `div2_tspc`, `latch_dice`, `sr_nand`, `sr_nor`: the nine designs by name.
- `scaled`: each of the nine with every width scaled together, half to four times its own (none under one unit), by its name and scale (`scaled(latch_x2)`).
- `strong_feedback`: each design with feedback devices (the C2MOS designs' feedback inverters, the DICE latch's storage devices) with those alone at twice their width.
- `long_channel`: each of the nine with every device at twice its length.
