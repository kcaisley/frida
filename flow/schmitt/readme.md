# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | The six-device CMOS Schmitt trigger: NMOS and PMOS stacks of two, a feedback device from the output into each stack's middle (an NMOS to vdd, a PMOS to vss), inverting; or a buffer with an output inverter (8 devices). The feedback's strength against the stacks' sets the hysteresis. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Stack and feedback wiring, the buffer's output inverter, invalid triggers. |
| Testbench generator | ✓ | [sim.py](sim.py) | The input a slow triangle from ground to the supply and back (1 µs a ramp: the trip points), or rail-to-rail steps with 50 ps edges (4 ns period: delays); 5 fF on the output. |
| Simulation runners | ✓ | [sim.py](sim.py) | `schmitt_characterization`: every case's triangle at 75–108 % of the supply and its step at the core supply, in each PDK (18 runs per PDK, all 108 in about a minute on 16 workers); `check=True` runs Spectre's static checks on the step. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasSchmitt`; `analyze_schmitt_trip` (the input where the output crosses mid-supply on the way up and down, their difference the hysteresis: `cross`, `value`), `analyze_schmitt_delay` (each edge's delay, `delayMeasure`; the output's 10–90 % transitions; the energy per cycle, `integ`). Run 20261019_020145, at the core supply: the inverting trigger's hysteresis 18–22 % of the supply in five PDKs (TSMC65 0.46/0.69 V, 228 mV) and 10 % in Tower180; the stronger feedback widens it to 24–31 %. At 75 % of the supply it is 10–18 % smaller (the wide trigger's 17–27 %), Tower180's inverting one unchanged. Delays 32–114 ps into 5 fF. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: the transfer on the triangle at the core supply with the trip points, hysteresis and delays in each title; the trip points versus supply; one figure set per PDK. Run by `flow.analysis.runner schmitt_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A hysteretic switch of known trip points on the triangle (inverting and buffer), a ramped step of known delay, transition and energy; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/schmitt_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Three cases in six PDKs with cIcCreator and laygo: all 36 layouts DRC clean and LVS correct. Each feedback device sits between its stack's two devices, on their shared middle node: beside them, cIcCreator could not route TSMC65's stronger-feedback trigger. ALIGN not run: `ALIGN_HOME` names a deleted install. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: RD53A `SchmittTrigger` (the power-on reset's), helena `inv_schmitttrigger`, `schmitttrigger`.
