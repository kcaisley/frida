* Function explanation:
* - XOR gates implement: dac_drive[i] = dac_state[i] XOR dac_drive_invert
* - When dac_drive_invert = 0: dac_drive[i] = dac_state[i] (buffer mode)
* - When dac_drive_invert = 1: dac_drive[i] = ~dac_state[i] (invert mode)
*
* Control signal behavior (dac_drive_invert is active high):
* - dac_drive_invert = 0: Output direct DAC state (normal operation)
* - dac_drive_invert = 1: Output inverted DAC state (differential mode)
*
* Driver sizing follows C0-first conversion-stage order:
* - Stages 0-1: 2x CKXOR2D4LVT = ~8x drive strength
* - Stages 2-3: 1x CKXOR2D4LVT = ~4x drive strength
* - Stages 4-15: 1x CKXOR2D2LVT = ~2x drive strength
*
* This provides binary-weighted drive strength that matches the binary-weighted
* capacitor array structure typical in SAR ADC designs.


.SUBCKT capdriver dac_state[15] dac_state[14] dac_state[13] dac_state[12] dac_state[11] dac_state[10] dac_state[9] dac_state[8] dac_state[7] dac_state[6] dac_state[5] dac_state[4] dac_state[3] dac_state[2] dac_state[1] dac_state[0] dac_drive_invert dac_drive[15] dac_drive[14] dac_drive[13] dac_drive[12] dac_drive[11] dac_drive[10] dac_drive[9] dac_drive[8] dac_drive[7] dac_drive[6] dac_drive[5] dac_drive[4] dac_drive[3] dac_drive[2] dac_drive[1] dac_drive[0] vdd_dac vss_dac

Xxor15 dac_drive_invert dac_state[15] dac_drive[15] vdd_dac vss_dac CKXOR2D2LVT
Xxor14 dac_drive_invert dac_state[14] dac_drive[14] vdd_dac vss_dac CKXOR2D2LVT
Xxor13 dac_drive_invert dac_state[13] dac_drive[13] vdd_dac vss_dac CKXOR2D2LVT
Xxor12 dac_drive_invert dac_state[12] dac_drive[12] vdd_dac vss_dac CKXOR2D2LVT
Xxor11 dac_drive_invert dac_state[11] dac_drive[11] vdd_dac vss_dac CKXOR2D2LVT
Xxor10 dac_drive_invert dac_state[10] dac_drive[10] vdd_dac vss_dac CKXOR2D2LVT
Xxor9 dac_drive_invert dac_state[9] dac_drive[9] vdd_dac vss_dac CKXOR2D2LVT
Xxor8 dac_drive_invert dac_state[8] dac_drive[8] vdd_dac vss_dac CKXOR2D2LVT
Xxor7 dac_drive_invert dac_state[7] dac_drive[7] vdd_dac vss_dac CKXOR2D2LVT
Xxor6 dac_drive_invert dac_state[6] dac_drive[6] vdd_dac vss_dac CKXOR2D2LVT
Xxor5 dac_drive_invert dac_state[5] dac_drive[5] vdd_dac vss_dac CKXOR2D2LVT
Xxor4 dac_drive_invert dac_state[4] dac_drive[4] vdd_dac vss_dac CKXOR2D2LVT
Xxor3 dac_drive_invert dac_state[3] dac_drive[3] vdd_dac vss_dac CKXOR2D4LVT
Xxor2 dac_drive_invert dac_state[2] dac_drive[2] vdd_dac vss_dac CKXOR2D4LVT
Xxor1_0 dac_drive_invert dac_state[1] dac_drive[1] vdd_dac vss_dac CKXOR2D4LVT
Xxor1_1 dac_drive_invert dac_state[1] dac_drive[1] vdd_dac vss_dac CKXOR2D4LVT
Xxor0_0 dac_drive_invert dac_state[0] dac_drive[0] vdd_dac vss_dac CKXOR2D4LVT
Xxor0_1 dac_drive_invert dac_state[0] dac_drive[0] vdd_dac vss_dac CKXOR2D4LVT

.ENDS capdriver
