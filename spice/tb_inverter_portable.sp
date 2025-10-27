* Portable Inverter Testbench
* Works with 28nm or 65nm, Spectre or HSPICE or Solido
*
* Usage:
*   65nm Spectre: spectre +define+TECH_65NM +define+SIM_SPECTRE tb_inverter_portable.sp
*   28nm Spectre: spectre +define+TECH_28NM +define+SIM_SPECTRE tb_inverter_portable.sp
*   65nm HSPICE:  hspice tb_inverter_portable.sp -D TECH_65NM -D SIM_HSPICE
*   28nm HSPICE:  hspice tb_inverter_portable.sp -D TECH_28NM -D SIM_HSPICE

*******************************************************************************
* Simulator Language Selection
*******************************************************************************

.if defined(SIM_SPECTRE)
simulator lang=spectre insensitive=yes
.endif

.if defined(SIM_HSPICE)
.option post=2 ingold=2 numdgt=8
.endif

*******************************************************************************
* Technology Selection and PDK Includes
*******************************************************************************

* Default to 65nm if no technology specified
.if !defined(TECH_65NM) && !defined(TECH_28NM)
.define TECH_65NM
.endif

* TSMC 65nm PDK and wrapper
.if defined(TECH_65NM)

    .if defined(SIM_SPECTRE)
        * Spectre syntax for 65nm
        .lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' tt_lib
    .endif

    .if defined(SIM_HSPICE)
        * HSPICE syntax for 65nm (adjust path as needed)
        .lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/hspice/toplevel.l' tt_lib
    .endif

    * Include 65nm technology wrapper
    .include '/users/kcaisley/frida/spice/tech_wrapper_65nm.sp'

.endif

* TSMC 28nm HPC+ PDK and wrapper
.if defined(TECH_28NM)

    .if defined(SIM_SPECTRE)
        * Spectre syntax for 28nm - typical corner
        .lib '/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/toplevel.scs' att_pt
    .endif

    .if defined(SIM_HSPICE)
        * HSPICE syntax for 28nm (adjust path as needed)
        .lib '/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/hspice/toplevel.l' att_pt
    .endif

    * Include 28nm technology wrapper
    .include '/users/kcaisley/frida/spice/tech_wrapper_28nm.sp'

.endif

*******************************************************************************
* Design Under Test
*******************************************************************************

* Include inverter schematic (technology-independent)
.include '/users/kcaisley/frida/spice/inverter.sp'

*******************************************************************************
* Testbench Stimuli
*******************************************************************************

* Supply voltages (VDD_NOM defined in tech wrapper)
vdd vdd 0 'VDD_NOM'
vss vss 0 'VSS_NOM'

* Input stimulus - pulse from low to high
* pulse(v1 v2 tdelay trise tfall width period)
vin in 0 pulse(0 'VDD_NOM' 100p 100p 100p 900p 2n)

*******************************************************************************
* Device Under Test
*******************************************************************************

* Inverter instance with default sizing from tech wrapper
xinv in out vdd vss inverter

* Output load capacitance
cload out 0 10f

*******************************************************************************
* Analysis and Output
*******************************************************************************

* Save signals
.save v(in) v(out) i(vdd)

* Transient analysis: 5ns, 10ps timestep
.tran 10p 5n

* Measurements (works in both Spectre and HSPICE)
.if defined(SIM_SPECTRE)
    .measure tran tphl
    + trig v(in) val='VDD_NOM*0.5' rise=1
    + targ v(out) val='VDD_NOM*0.5' fall=1

    .measure tran tplh
    + trig v(in) val='VDD_NOM*0.5' fall=1
    + targ v(out) val='VDD_NOM*0.5' rise=1

    .measure tran avg_power avg p(vdd) from=0 to=5n
.endif

.if defined(SIM_HSPICE)
    .measure tran tphl
    + trig v(in) val='VDD_NOM*0.5' rise=1
    + targ v(out) val='VDD_NOM*0.5' fall=1

    .measure tran tplh
    + trig v(in) val='VDD_NOM*0.5' fall=1
    + targ v(out) val='VDD_NOM*0.5' rise=1

    .measure tran avg_power avg power from=0 to=5n
.endif

.end
