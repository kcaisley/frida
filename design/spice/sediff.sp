* Single-Ended to Differential Amplifier (PCB Front-End)
*
* Simplified model of the FRIDA PCB input stage around U1 (THS4541).
* Converts a single-ended input from the function generator into a
* differential signal pair for the ADC.
*
* Jumpers and SMA jacks removed. Configuration:
*   - Single-ended mode (J5: negative input grounded via R14)
*   - Cable termination (R19, R20) present
*   - Output taken directly at J10 terminals (no bypass path)
*   - VOCM set by R23/R24 voltage divider from vdd
*   - Amplifier supplies (VS_P, VS_N) set internally
*
* Gain = Rf/Rin = 499/499 = 1 (unity, differential)
*
* Reference: design/pcb/frida65A.kicad_sch (input amplifier section)

* ths4541.sp must be included by the top-level wrapper (tb_adc.sp or amscontrol.scs)

.subckt sediff vin_p_ext vin_p vin_n vdd

* =====================================================================
* Amplifier supplies (fixed inside wrapper)
* =====================================================================
Vvsp vs_p 0 3.3
Vvsn vs_n 0 -1.0

* =====================================================================
* VOCM voltage divider (R23, R24: VDD to GND)
* VOCM = VDD / 2 = 0.6V (with VDD = 1.2V)
* =====================================================================
R23 vdd vocm 1k
R24 vocm 0 1k

* =====================================================================
* Input termination and network
* =====================================================================

* Cable termination (54.9 ohm, normally for 50-ohm coax matching)
R19 vin_p_ext 0 54.9
R20 se_gnd 0 54.9

* Negative input grounded (single-ended mode: J3 → R14 to GND)
R14 0 se_gnd 50

* Input resistors to amplifier
R16 vin_p_ext inp 499
R17 se_gnd inn 499

* =====================================================================
* THS4541 fully differential amplifier (U1)
* Pin order: VOUTM VOUTP VOCM VINM VINP VEE VCC PD
* =====================================================================
XU1 outm outp vocm inn inp vs_n vs_p vs_p THS4541

* =====================================================================
* Feedback network (unity gain)
* =====================================================================
R21 outm inp 499
C4  outm inp 51p
R22 outp inn 499
C5  outp inn 51p

* =====================================================================
* Output network (series resistors + differential cap, up to J10)
* =====================================================================
R25 outm vin_n 499
R26 outp vin_p 499
C6  vin_n vin_p 51p

.ends sediff
