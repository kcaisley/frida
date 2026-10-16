# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | NMOS, PMOS, or transmission-gate switch; half-size charge-injection dummies; bootstrapped NMOS gate (after ciccreator's SARBSSW and BAG's bootstrap, with a MOS boost capacitor); PDK-compiled devices fingered to the row cells. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Generator checks, dummies and bootstrap wiring. |
| Testbench generator | ✓ | [sim.py](sim.py) | Complementary clocks, DC input, and capacitive load. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 transient target; not a full resistance/noise characterization. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN (`flow/layout`) from hand-written floorplans (`design/layout/samp_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes ports the netlist connects. |
| Layout runner | ✓ | [layout.py](layout.py) | Transmission gate, transmission gate with dummies and bootstrapped switch in all six PDKs, all 54 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No standalone sampler runner. |

The bootstrap keeps every PMOS body on vdd (the row cells' wells): the boosted node's junctions leak toward vdd while sampling. Its cascoded gate pull-down is a stack of two clocked devices (a gate on a rail has no route in the row cells).

TODO: characterize sampling time, resistance versus sizing/input voltage, and sampling noise separately from comparator offset. See [project TODO](../../docs/todo.md#samp).
