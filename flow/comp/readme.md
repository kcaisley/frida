# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Single/two-stage comparator variants with held differential outputs. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Default topology and output-latch wiring. |
| Testbench generator | ✓ | [sim.py](sim.py) | Common-mode/differential-input sweeps and repeated decisions. |
| Simulation runners | ✓ | [sim.py](sim.py) | `comp_characterization`: six topologies (StrongARM, triple tail, double tail, and the self-timed and modified double tails) at one sizing, in each PDK at its core supply: four common modes (3/8–5/8 of the supply), at each the noise-free delay over ten differential inputs and a transient-noise S-curve (±3 mV, 100 decisions per point); about two hours on 16 workers for all six PDKs. `hdl21_comp_perf_vs_size` (the 297-case size sweep) and `frida1_fixed_input_noise` stay TSMC65 references. |
| Analysis | ✓ | [analysis.py](analysis.py) | `analyze_comp_timing` (clock-to-decision delay, settling, unresolved trials), `analyze_comp_delay` (the delay over common mode and input), `analyze_comp_power` (power, energy per decision), `analyze_comp_candidate` (a sweep candidate's summary). `MeasComp` and the offset, noise and common-mode analyses lab captures share stay in `flow/analysis`. |
| Plots | ✓ | [plots.py](plots.py) | The size sweep's candidates; one panel per topology: delay versus input, noise and delay versus common mode, energy and systematic offset versus common mode, one figure set per PDK. Run by `flow.analysis.runner comp_characterization_study` and `comp_candidate_sweep_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | Timing, settling, power and candidates on synthetic decisions; every characterization plot renders. |
| Layout generator | ✓ | [floorplan.py](../layout/floorplan.py) | Standard-cell rows with cIcCreator, laygo and ALIGN (`flow/layout`), from a hand-written floorplan or ALIGN's placement. |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry and per-tool failure collection; the floorplan conversion in `flow/layout`. |
| Layout runner | ✓ | [layout.py](layout.py) | 42 per-PDK targets (frida1 and c040: manual, auto, gates; mos_inv), seven all-PDK targets, `all_comp_layouts`. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No comparator extraction. |

TODO: investigate settling, metastability, kickback, and offset; the tools placing by the floorplans' ALIGN groups. See [project TODO](../../docs/todo.md#comp).
