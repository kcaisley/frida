* Portable Inverter Testbench with Corner and Noise Support
* Supports 28nm/65nm, Spectre/HSPICE, TT/SS/FF corners, and noise analysis
*
* Usage Examples:
*   65nm TT:         spectre +define+TECH_65NM +define+CORNER_TT tb_inverter_corners.sp
*   65nm SS:         spectre +define+TECH_65NM +define+CORNER_SS tb_inverter_corners.sp
*   28nm TT:         spectre +define+TECH_28NM +define+CORNER_TT tb_inverter_corners.sp
*   28nm SS + MC:    spectre +define+TECH_28NM +define+CORNER_SS +define+ENABLE_MC tb_inverter_corners.sp
*   28nm + Noise:    spectre +define+TECH_28NM +define+ENABLE_TNOISE tb_inverter_corners.sp

*******************************************************************************
* Simulator Detection and Configuration
*******************************************************************************

.if defined(SIM_SPECTRE)
simulator lang=spectre insensitive=yes
.endif

.if defined(SIM_HSPICE)
.option post=2 ingold=2 numdgt=8
.endif

*******************************************************************************
* Default Settings
*******************************************************************************

* Default to 65nm if not specified
.if !defined(TECH_65NM) && !defined(TECH_28NM)
.define TECH_65NM
.endif

* Default to TT corner if not specified
.if !defined(CORNER_TT) && !defined(CORNER_SS) && !defined(CORNER_FF) && !defined(CORNER_SF) && !defined(CORNER_FS)
.define CORNER_TT
.endif

*******************************************************************************
* TSMC 65nm Technology
*******************************************************************************

.if defined(TECH_65NM)

    * Select corner
    .if defined(CORNER_TT)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' tt_lib
        .endif
    .endif

    .if defined(CORNER_SS)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' ss_lib
        .endif
    .endif

    .if defined(CORNER_FF)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' ff_lib
        .endif
    .endif

    .if defined(CORNER_SF)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' sf_lib
        .endif
    .endif

    .if defined(CORNER_FS)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' fs_lib
        .endif
    .endif

    * Monte Carlo support for 65nm
    .if defined(ENABLE_MC)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs' mc_lib
        .endif
    .endif

    * Include technology wrapper
    .include '/users/kcaisley/frida/spice/tech_wrapper_65nm.sp'

.endif

*******************************************************************************
* TSMC 28nm Technology
*******************************************************************************

.if defined(TECH_28NM)

    * Select corner (28nm uses analog_passive notation)
    .if defined(CORNER_TT)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/toplevel.scs' att_pt
        .endif
    .endif

    .if defined(CORNER_SS)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/toplevel.scs' ass_ps
        .endif
    .endif

    .if defined(CORNER_FF)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/toplevel.scs' aff_pf
        .endif
    .endif

    .if defined(CORNER_SF)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/toplevel.scs' asf_ps
        .endif
    .endif

    .if defined(CORNER_FS)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/toplevel.scs' afs_pf
        .endif
    .endif

    * Monte Carlo support for 28nm
    .if defined(ENABLE_MC)
        .if defined(SIM_SPECTRE)
            * Local mismatch only
            .lib '/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/toplevel.scs' local_mc

            * Or use corner + mismatch (comment out local_mc above, uncomment below)
            * .lib '/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/toplevel.scs' global_ass_ps__local_mc
        .endif
    .endif

    * Noise modeling for 28nm
    .if defined(ENABLE_NOISE_WORST)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/crn28ull_1d8_elk_v1d8_2p2_shrink0d9_embedded_usage.scs' noise_worst
        .endif
    .endif

    .if defined(ENABLE_NOISE_TYPICAL)
        .if defined(SIM_SPECTRE)
            .lib '/eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/crn28ull_1d8_elk_v1d8_2p2_shrink0d9_embedded_usage.scs' noise_typical
        .endif
    .endif

    * Include technology wrapper
    .include '/users/kcaisley/frida/spice/tech_wrapper_28nm.sp'

.endif

*******************************************************************************
* Design Under Test
*******************************************************************************

.include '/users/kcaisley/frida/spice/inverter.sp'

*******************************************************************************
* Testbench Circuit
*******************************************************************************

* Supply voltages
vdd vdd 0 'VDD_NOM'
vss vss 0 'VSS_NOM'

* Input stimulus
vin in 0 pulse(0 'VDD_NOM' 100p 100p 100p 900p 2n)

* DUT instance
xinv in out vdd vss inverter

* Load
cload out 0 10f

*******************************************************************************
* Analysis Configuration
*******************************************************************************

* Save signals
.save v(in) v(out) i(vdd)

* Transient noise setup - portable across simulators
.if defined(ENABLE_TNOISE)
    .if defined(SIM_SPECTRE)
        * Spectre transient noise syntax
        simulatorOptions options \
            tnoiseanalysis=yes \
            noisefmax=10G \
            noisefmin=1k \
            noiseseed=42
    .endif

    .if defined(SIM_HSPICE)
        * HSPICE transient noise syntax
        * fmax controls noise bandwidth (default: 1/tstep)
        * fmin controls 1/f noise corner (default: 1/tstop)
        * seed for reproducible random noise
        .option trannoise=1 fmax=10G fmin=1k seed=42
    .endif
.endif

* Temperature setting
.temp 'TEMP_NOM'

* Transient analysis
.tran 10p 5n

*******************************************************************************
* Measurements
*******************************************************************************

.measure tran tphl
+ trig v(in) val='VDD_NOM*0.5' rise=1
+ targ v(out) val='VDD_NOM*0.5' fall=1

.measure tran tplh
+ trig v(in) val='VDD_NOM*0.5' fall=1
+ targ v(out) val='VDD_NOM*0.5' rise=1

.measure tran tpd param='(tphl+tplh)/2'

.if defined(SIM_SPECTRE)
    .measure tran avg_power avg p(vdd) from=0 to=5n
.endif

.if defined(SIM_HSPICE)
    .measure tran avg_power avg power from=0 to=5n
.endif

.end
