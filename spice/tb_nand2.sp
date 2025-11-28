* ========================================================================
* NAND2 Gate Testbench - SPICE Wrapper
* ========================================================================
* Tests 2-input NAND gate with exhaustive truth table patterns to measure
* propagation delay and switching characteristics.
*
* Family: nand2
* Cells: nand2_static
*
* Test pattern:
*   - All input combinations (4 states for 2-input gates)
*   - 4 cycles per state at 10ns period
*   - Total simulation time: 4 states × 4 cycles × 10ns = 160ns
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
* The Verilog-A testbench (tb_nand2.va) contains:
*   - Power supplies (VDD, VSS)
*   - Input stimulus generation (truth table exhaustive testing)
*   - Output load capacitance (20fF typical)
*   - DUT instantiation (nand2_static)
* ========================================================================
xtb tb_nand2

* ========================================================================
* Simulation control
* ========================================================================
* Transient analysis: 1ns resolution, 160ns total
*   - 4 input states (2-input truth table: 00, 01, 10, 11)
*   - 4 cycles per state
*   - 10ns period per cycle
*   - Total: 4 × 4 × 10ns = 160ns
.tran 1n 160n

* Simulation options
.options temp=27 scale=1.0 soft_bin=allmodels

* Save all voltages and currents for post-processing
.save all

.end
