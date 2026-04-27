* Minimal standalone comparator testbench
* Sweeps vin_p from 0V to 1.2V while vin_n stays at mid-supply.
* Repeatedly clocks the comparator 6 times during the ramp.
*
* Intended use:
*   ngspice frida/design/spice/test/tb_comp_ramp.sp
*
* Notes:
*   - Uses the standalone comparator netlist in ../comp.cdl
*   - Includes TSMC65 device models and standard-cell SPICE used by comp_sr
*   - Saves key internal and output nodes for debugging convergence / behavior

.lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/hspice/toplevel.l' tt_lib
.lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/hspice/toplevel.l' pre_simu

.include '/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lp_200a/tcbn65lp_200a.spi'
.include '/eda/kits/TSMC/65LP/2024/digital/Back_End/spice/tcbn65lplvt_200a/tcbn65lplvt_200a.spi'

* NOTE: ngspice does not accept CDL-style "/" subckt prefixes in comp.cdl.
* Use the ngspice-compatible converted netlist instead for this standalone testbench.
.include '../comp.sp'

* Supplies
VDD vdd_a 0 1.2
VSS vss_a 0 0

* Inputs
* vin_n fixed at mid-supply
VINN vin_n 0 0.6

* vin_p ramps from ground to VDD over 120ns
VINP vin_p 0 pwl(0n 0.0 120n 1.2)

* Comparator clock
* 6 pulses, one every 20ns, starting at 10ns
* Reset/precharge when clk=0, evaluate when clk=1
VCLK clk 0 pulse(0 1.2 10n 0.1n 0.1n 4n 20n)

* DUT
XCOMP vin_p vin_n dout_p dout_n clk vdd_a vss_a comp

* Mild startup guidance for the regenerative nodes
.nodeset v(dout_p)=1.2 v(dout_n)=1.2
.options reltol=1e-3 vabstol=1u iabstol=1p gmin=1e-12 method=gear maxord=2 itl1=500 itl4=200 cshunt=1e-15
.tran 0.02n 140n

.print tran v(vin_p) v(vin_n) v(clk) v(dout_p) v(dout_n)
.save v(vin_p) v(vin_n) v(clk) v(dout_p) v(dout_n)
.save v(xcomp.comp_p) v(xcomp.comp_n)
.save v(xcomp.xi3.net35) v(xcomp.xi3.net38) v(xcomp.xi3.net41) v(xcomp.xi3.net42)
.save v(xcomp.xlatch.net031) v(xcomp.xlatch.net037)

.end
