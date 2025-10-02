# Custom I/O Placement for ADC Design
# Place P-side DAC pins on left, N-side DAC pins on right, others on bottom
# Metal layers controlled by IO_PLACER_H (M3) and IO_PLACER_V (M2) in config.mk

# Mirrored DAC mode pins (P left, N right: will use IO_PLACER_V = M2)
set_io_pin_constraint -region left:* -group -order -pin_names {dac_astate_p[15] dac_astate_p[14] dac_astate_p[13] dac_astate_p[12] dac_astate_p[11] dac_astate_p[10] dac_astate_p[9] dac_astate_p[8] dac_astate_p[7] dac_astate_p[6] dac_astate_p[5] dac_astate_p[4] dac_astate_p[3] dac_astate_p[2] dac_astate_p[1] dac_astate_p[0]}
set_io_pin_constraint -region right:* -group -order -pin_names {dac_astate_n[15] dac_astate_n[14] dac_astate_n[13] dac_astate_n[12] dac_astate_n[11] dac_astate_n[10] dac_astate_n[9] dac_astate_n[8] dac_astate_n[7] dac_astate_n[6] dac_astate_n[5] dac_astate_n[4] dac_astate_n[3] dac_astate_n[2] dac_astate_n[1] dac_astate_n[0]}
set_io_pin_constraint -region left:* -group -order -pin_names {dac_bstate_p[15] dac_bstate_p[14] dac_bstate_p[13] dac_bstate_p[12] dac_bstate_p[11] dac_bstate_p[10] dac_bstate_p[9] dac_bstate_p[8] dac_bstate_p[7] dac_bstate_p[6] dac_bstate_p[5] dac_bstate_p[4] dac_bstate_p[3] dac_bstate_p[2] dac_bstate_p[1] dac_bstate_p[0]}
set_io_pin_constraint -region right:* -group -order -pin_names {dac_bstate_n[15] dac_bstate_n[14] dac_bstate_n[13] dac_bstate_n[12] dac_bstate_n[11] dac_bstate_n[10] dac_bstate_n[9] dac_bstate_n[8] dac_bstate_n[7] dac_bstate_n[6] dac_bstate_n[5] dac_bstate_n[4] dac_bstate_n[3] dac_bstate_n[2] dac_bstate_n[1] dac_bstate_n[0]}

exclude_io_pin_region -region left:0-8 -region left:41-49 -region right:0-8 -region right:41-49


# Bottom center: Control signals (will use IO_PLACER_H = M3) - expanded region
set_io_pin_constraint -pin_names {dac_diffcaps dac_mode comp_out seq_init seq_samp seq_comp seq_update en_init en_samp_p en_samp_n en_comp en_update} -region bottom:24-36 -group -order


set_io_pin_constraint -pin_names {clk_samp_p clk_samp_p_b clk_samp_n clk_samp_n_b clk_comp comp_out_p comp_out_n} -region top:25-35 -group -order

# Bottom - DAC main state outputs
# Bottom left: Positive DAC main state outputs (16 bits)
set_io_pin_constraint -region bottom:3-20 -group -order -pin_names {dac_state_p_main[0] dac_state_p_main[1] dac_state_p_main[2] dac_state_p_main[3] dac_state_p_main[4] dac_state_p_main[5] dac_state_p_main[6] dac_state_p_main[7] dac_state_p_main[8] dac_state_p_main[9] dac_state_p_main[10] dac_state_p_main[11] dac_state_p_main[12] dac_state_p_main[13] dac_state_p_main[14] dac_state_p_main[15]}

# Bottom right: Negative DAC main state outputs (16 bits)
set_io_pin_constraint -region bottom:40-57 -group -order -pin_names {dac_state_n_main[15] dac_state_n_main[14] dac_state_n_main[13] dac_state_n_main[12] dac_state_n_main[11] dac_state_n_main[10] dac_state_n_main[9] dac_state_n_main[8] dac_state_n_main[7] dac_state_n_main[6] dac_state_n_main[5] dac_state_n_main[4] dac_state_n_main[3] dac_state_n_main[2] dac_state_n_main[1] dac_state_n_main[0]}

# Top - DAC diff state outputs and analog pins
# Top left: Positive DAC diff state outputs (16 bits)
set_io_pin_constraint -region top:3-20 -group -order -pin_names {dac_state_p_diff[0] dac_state_p_diff[1] dac_state_p_diff[2] dac_state_p_diff[3] dac_state_p_diff[4] dac_state_p_diff[5] dac_state_p_diff[6] dac_state_p_diff[7] dac_state_p_diff[8] dac_state_p_diff[9] dac_state_p_diff[10] dac_state_p_diff[11] dac_state_p_diff[12] dac_state_p_diff[13] dac_state_p_diff[14] dac_state_p_diff[15]}

# Top right: Negative DAC diff state outputs (16 bits)
set_io_pin_constraint -region top:40-57 -group -order -pin_names {dac_state_n_diff[15] dac_state_n_diff[14] dac_state_n_diff[13] dac_state_n_diff[12] dac_state_n_diff[11] dac_state_n_diff[10] dac_state_n_diff[9] dac_state_n_diff[8] dac_state_n_diff[7] dac_state_n_diff[6] dac_state_n_diff[5] dac_state_n_diff[4] dac_state_n_diff[3] dac_state_n_diff[2] dac_state_n_diff[1] dac_state_n_diff[0]}
