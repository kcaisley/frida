simulator lang=spice
PLACEHOLDER_PDK_MODELS
.include "PLACEHOLDER_DUT_NETLIST"
.ahdl_include "PLACEHOLDER_TESTBENCH_VA"

* Instantiate the testbench
xtb tb_samp

.tran 1n 7.5u
.options temp=27 scale=1.0 soft_bin=allmodels
.save all
