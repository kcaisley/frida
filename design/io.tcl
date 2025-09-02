# Custom I/O Placement for ADC Design
# Place P-side DAC pins on left, N-side DAC pins on right, others on bottom
# Metal layers controlled by IO_PLACER_H (M3) and IO_PLACER_V (M2) in config.mk

# Mirrored DAC mode pins (P left, N right: will use IO_PLACER_V = M2)
set_io_pin_constraint -region left:* -group -order -pin_names {dac_astate_p[15] dac_astate_p[14] dac_astate_p[13] dac_astate_p[12] dac_astate_p[11] dac_astate_p[10] dac_astate_p[9] dac_astate_p[8] dac_astate_p[7] dac_astate_p[6] dac_astate_p[5] dac_astate_p[4] dac_astate_p[3] dac_astate_p[2] dac_astate_p[1] dac_astate_p[0]}
set_io_pin_constraint -region right:* -group -order -pin_names {dac_astate_n[15] dac_astate_n[14] dac_astate_n[13] dac_astate_n[12] dac_astate_n[11] dac_astate_n[10] dac_astate_n[9] dac_astate_n[8] dac_astate_n[7] dac_astate_n[6] dac_astate_n[5] dac_astate_n[4] dac_astate_n[3] dac_astate_n[2] dac_astate_n[1] dac_astate_n[0]}
set_io_pin_constraint -region left:* -group -order -pin_names {dac_bstate_p[15] dac_bstate_p[14] dac_bstate_p[13] dac_bstate_p[12] dac_bstate_p[11] dac_bstate_p[10] dac_bstate_p[9] dac_bstate_p[8] dac_bstate_p[7] dac_bstate_p[6] dac_bstate_p[5] dac_bstate_p[4] dac_bstate_p[3] dac_bstate_p[2] dac_bstate_p[1] dac_bstate_p[0]}
set_io_pin_constraint -region right:* -group -order -pin_names {dac_bstate_n[15] dac_bstate_n[14] dac_bstate_n[13] dac_bstate_n[12] dac_bstate_n[11] dac_bstate_n[10] dac_bstate_n[9] dac_bstate_n[8] dac_bstate_n[7] dac_bstate_n[6] dac_bstate_n[5] dac_bstate_n[4] dac_bstate_n[3] dac_bstate_n[2] dac_bstate_n[1] dac_bstate_n[0]}


# Bottom - All control signals (will use IO_PLACER_V = M2)
set_io_pin_constraint -pin_names {seq_init seq_samp seq_comp seq_update} -region bottom:* -group -order
set_io_pin_constraint -pin_names {en_init en_samp_p en_samp_n en_comp en_update} -region bottom:* -group -order
set_io_pin_constraint -pin_names {dac_diffcaps rst comp_out} -region bottom:* -group -order
set_io_pin_constraint -pin_names {dac_mode_p dac_mode_n} -region bottom:* -group -order

# Top - Analog pins (will use IO_PLACER_V = M2)
set_io_pin_constraint -pin_names {vin_p vin_n} -region top:* -group -order