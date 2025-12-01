simulator lang=spice
.lib "PLACEHOLDER_PDK_MODELS" tt_lib
.include "PLACEHOLDER_DUT_NETLIST"
.ahdl_include "PLACEHOLDER_TESTBENCH_VA"

* Instantiate the testbench
xtb tb_comp

.tran 1n 35u
.options temp=27 scale=1.0 soft_bin=allmodels
.save all
