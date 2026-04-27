* Standalone testbench for comp_latch only
*
* Usage:
*   ngspice -r scratch/tb_comp_latch.raw design/spice/test/tb_comp_latch.sp
*
* Purpose:
*   Exercise only the dynamic latch core, without the downstream SR latch.
*   The negative input is held at mid-supply while the positive input ramps
*   from 0 V to 1.2 V. The latch is clocked 6 times during the ramp.

.lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/hspice/toplevel.l' tt_lib
.lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/hspice/toplevel.l' pre_simu

* Include the full comparator netlist file and instantiate comp_latch only.
.include '../comp.sp'

* Supplies
VDD vdd 0 1.2

* Inputs
* Hold INN at mid-supply
VINN inn 0 0.6

* Ramp INP from 0 V to 1.2 V over 120 ns
VINP inp 0 pwl(0n 0.0 120n 1.2)

* Clock: 6 pulses, 20 ns period, starting at 10 ns
VCLK clk 0 pulse(0 1.2 10n 0.1n 0.1n 4n 20n)

* DUT
XLATCH clk gnd inn inp outn outp vdd comp_latch

* Mild startup guidance and transient settings
.nodeset v(outp)=1.2 v(outn)=1.2 v(xlatch.net031)=1.2 v(xlatch.net037)=1.2 v(xlatch.tail)=0
.options reltol=1e-3 vabstol=1u iabstol=1p gmin=1e-12 method=gear maxord=2 itl1=500 itl4=200 cshunt=1e-15
.tran 0.02n 140n

.print tran v(clk) v(inp) v(inn) v(xlatch.tail) v(xlatch.net031) v(xlatch.net037) v(outp) v(outn)
.save v(clk) v(inp) v(inn) v(xlatch.tail) v(xlatch.net031) v(xlatch.net037) v(outp) v(outn)

.end
