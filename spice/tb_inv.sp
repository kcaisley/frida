* ========================================================================
* Inverter Testbench - SPICE Wrapper
* ========================================================================
* Tests CMOS inverter with exhaustive input patterns to measure
* propagation delay and switching characteristics.
*
* Family: inv
* Cells: inv_static
*
* Test pattern:
*   - Both input states (0, 1)
*   - 4 cycles per state at 10ns period
*   - Total simulation time: 2 states × 4 cycles × 10ns = 80ns
*
* Measured parameters:
*   - Propagation delay (tpd, tphl, tplh)
*   - Rise/fall times (tr, tf)
*   - Dynamic switching energy
*   - Static leakage current
* ========================================================================

simulator lang=spice

* Include technology models (replaced by Python script)
PLACEHOLDER_PDK_MODELS

* Include device under test netlist (replaced by Python script)
.include "PLACEHOLDER_DUT_NETLIST"

* Include Verilog-A testbench (replaced by Python script)
.ahdl_include "PLACEHOLDER_TESTBENCH_VA"

* ========================================================================
* Testbench instantiation
* ========================================================================
* The Verilog-A testbench (tb_inv.va) contains:
*   - Power supplies (VDD, VSS)
*   - Input stimulus generation (both logic states)
*   - Output load capacitance (20fF typical)
*   - DUT instantiation (inv_static)
* ========================================================================
xtb tb_inv

* ========================================================================
* Simulation control
* ========================================================================
* Transient analysis: 1ns resolution, 80ns total
*   - 2 input states (0, 1)
*   - 4 cycles per state
*   - 10ns period per cycle
*   - Total: 2 × 4 × 10ns = 80ns
.tran 1n 80n

* Simulation options
.options temp=27 scale=1.0 soft_bin=allmodels

* Save all voltages and currents for post-processing
.save all

.end
