# Custom I/O Placement for ADC Design
# Place P-side DAC pins on left, N-side DAC pins on right, others on bottom
# Metal layers controlled by IO_PLACER_H (M3) and IO_PLACER_V (M2) in config.mk

# Mirrored DAC mode pins (P left, N right: will use IO_PLACER_V = M2)
set_io_pin_constraint -region left:* -group -order -pin_names {dac_astate_p[15] dac_astate_p[14] dac_astate_p[13] dac_astate_p[12] dac_astate_p[11] dac_astate_p[10] dac_astate_p[9] dac_astate_p[8] dac_astate_p[7] dac_astate_p[6] dac_astate_p[5] dac_astate_p[4] dac_astate_p[3] dac_astate_p[2] dac_astate_p[1] dac_astate_p[0]}
set_io_pin_constraint -region right:* -group -order -pin_names {dac_astate_n[15] dac_astate_n[14] dac_astate_n[13] dac_astate_n[12] dac_astate_n[11] dac_astate_n[10] dac_astate_n[9] dac_astate_n[8] dac_astate_n[7] dac_astate_n[6] dac_astate_n[5] dac_astate_n[4] dac_astate_n[3] dac_astate_n[2] dac_astate_n[1] dac_astate_n[0]}
set_io_pin_constraint -region left:* -group -order -pin_names {dac_bstate_p[15] dac_bstate_p[14] dac_bstate_p[13] dac_bstate_p[12] dac_bstate_p[11] dac_bstate_p[10] dac_bstate_p[9] dac_bstate_p[8] dac_bstate_p[7] dac_bstate_p[6] dac_bstate_p[5] dac_bstate_p[4] dac_bstate_p[3] dac_bstate_p[2] dac_bstate_p[1] dac_bstate_p[0]}
set_io_pin_constraint -region right:* -group -order -pin_names {dac_bstate_n[15] dac_bstate_n[14] dac_bstate_n[13] dac_bstate_n[12] dac_bstate_n[11] dac_bstate_n[10] dac_bstate_n[9] dac_bstate_n[8] dac_bstate_n[7] dac_bstate_n[6] dac_bstate_n[5] dac_bstate_n[4] dac_bstate_n[3] dac_bstate_n[2] dac_bstate_n[1] dac_bstate_n[0]}

exclude_io_pin_region -region left:0-9 -region left:40-49 -region right:0-9 -region right:40-49


# Bottom center: Control signals (will use IO_PLACER_H = M3) - expanded region
set_io_pin_constraint -pin_names {dac_diffcaps dac_mode comp_out seq_init seq_samp seq_comp seq_update en_init en_samp_p en_samp_n en_comp en_update} -region bottom:24.8-35.2 -group -order

# Top center: Manual pin placement inside macro cutout area
# Y: 29um, X from 27-33um (7 pins spaced 1um apart)
#set_io_pin_constraint -pin_names {clk_samp_p clk_samp_p_b clk_samp_n clk_samp_n_b clk_comp comp_out_p comp_out_n} -region top:25-35 -group -order

place_pin -pin_name clk_samp_p -layer M3 -location {27.0 28.8}
place_pin -pin_name clk_samp_p_b -layer M3 -location {28.0 28.8}
place_pin -pin_name clk_samp_n -layer M3 -location {29.0 28.8}
place_pin -pin_name clk_samp_n_b -layer M3 -location {30.0 28.8}
place_pin -pin_name clk_comp -layer M3 -location {31.0 28.8}
place_pin -pin_name comp_out_p -layer M3 -location {32.0 28.8}
place_pin -pin_name comp_out_n -layer M3 -location {33.0 28.8}

# Bottom - DAC main state outputs - Manual placement
# Bottom left: Positive DAC main state outputs (17 pins from 0.9 to 13.7um, spacing ~0.8um)
place_pin -pin_name dac_state_p_main[0] -layer M3 -location {0.9 0.0}
place_pin -pin_name dac_state_p_main[1] -layer M3 -location {1.7 0.0}
place_pin -pin_name dac_state_p_main[2] -layer M3 -location {2.5 0.0}
place_pin -pin_name dac_state_p_main[3] -layer M3 -location {3.3 0.0}
place_pin -pin_name dac_state_p_main[4] -layer M3 -location {4.1 0.0}
place_pin -pin_name dac_state_p_main[5] -layer M3 -location {4.9 0.0}
place_pin -pin_name dac_state_p_main[6] -layer M3 -location {5.7 0.0}
place_pin -pin_name dac_state_p_main[7] -layer M3 -location {6.5 0.0}
place_pin -pin_name dac_state_p_main[8] -layer M3 -location {7.3 0.0}
place_pin -pin_name dac_state_p_main[9] -layer M3 -location {8.1 0.0}
place_pin -pin_name dac_state_p_main[10] -layer M3 -location {8.9 0.0}
place_pin -pin_name dac_state_p_main[11] -layer M3 -location {9.7 0.0}
place_pin -pin_name dac_state_p_main[12] -layer M3 -location {10.5 0.0}
place_pin -pin_name dac_state_p_main[13] -layer M3 -location {11.3 0.0}
place_pin -pin_name dac_state_p_main[14] -layer M3 -location {12.1 0.0}
place_pin -pin_name dac_state_p_main[15] -layer M3 -location {12.9 0.0}
place_pin -pin_name dac_invert_p_main -layer M3 -location {13.7 0.0}

# Bottom right: Negative DAC main state outputs (17 pins from 46.3 to 59.1um, spacing ~0.8um)
place_pin -pin_name dac_invert_n_main -layer M3 -location {46.3 0.0}
place_pin -pin_name dac_state_n_main[15] -layer M3 -location {47.1 0.0}
place_pin -pin_name dac_state_n_main[14] -layer M3 -location {47.9 0.0}
place_pin -pin_name dac_state_n_main[13] -layer M3 -location {48.7 0.0}
place_pin -pin_name dac_state_n_main[12] -layer M3 -location {49.5 0.0}
place_pin -pin_name dac_state_n_main[11] -layer M3 -location {50.3 0.0}
place_pin -pin_name dac_state_n_main[10] -layer M3 -location {51.1 0.0}
place_pin -pin_name dac_state_n_main[9] -layer M3 -location {51.9 0.0}
place_pin -pin_name dac_state_n_main[8] -layer M3 -location {52.7 0.0}
place_pin -pin_name dac_state_n_main[7] -layer M3 -location {53.5 0.0}
place_pin -pin_name dac_state_n_main[6] -layer M3 -location {54.3 0.0}
place_pin -pin_name dac_state_n_main[5] -layer M3 -location {55.1 0.0}
place_pin -pin_name dac_state_n_main[4] -layer M3 -location {55.9 0.0}
place_pin -pin_name dac_state_n_main[3] -layer M3 -location {56.7 0.0}
place_pin -pin_name dac_state_n_main[2] -layer M3 -location {57.5 0.0}
place_pin -pin_name dac_state_n_main[1] -layer M3 -location {58.3 0.0}
place_pin -pin_name dac_state_n_main[0] -layer M3 -location {59.1 0.0}

# Top - DAC diff state outputs - Manual placement
# Top left: Positive DAC diff state outputs (17 pins from 0.9 to 13.7um, spacing ~0.8um)
place_pin -pin_name dac_state_p_diff[0] -layer M3 -location {0.9 49.0}
place_pin -pin_name dac_state_p_diff[1] -layer M3 -location {1.7 49.0}
place_pin -pin_name dac_state_p_diff[2] -layer M3 -location {2.5 49.0}
place_pin -pin_name dac_state_p_diff[3] -layer M3 -location {3.3 49.0}
place_pin -pin_name dac_state_p_diff[4] -layer M3 -location {4.1 49.0}
place_pin -pin_name dac_state_p_diff[5] -layer M3 -location {4.9 49.0}
place_pin -pin_name dac_state_p_diff[6] -layer M3 -location {5.7 49.0}
place_pin -pin_name dac_state_p_diff[7] -layer M3 -location {6.5 49.0}
place_pin -pin_name dac_state_p_diff[8] -layer M3 -location {7.3 49.0}
place_pin -pin_name dac_state_p_diff[9] -layer M3 -location {8.1 49.0}
place_pin -pin_name dac_state_p_diff[10] -layer M3 -location {8.9 49.0}
place_pin -pin_name dac_state_p_diff[11] -layer M3 -location {9.7 49.0}
place_pin -pin_name dac_state_p_diff[12] -layer M3 -location {10.5 49.0}
place_pin -pin_name dac_state_p_diff[13] -layer M3 -location {11.3 49.0}
place_pin -pin_name dac_state_p_diff[14] -layer M3 -location {12.1 49.0}
place_pin -pin_name dac_state_p_diff[15] -layer M3 -location {12.9 49.0}
place_pin -pin_name dac_invert_p_diff -layer M3 -location {13.7 49.0}

# Top right: Negative DAC diff state outputs (17 pins from 46.3 to 59.1um, spacing ~0.8um)
place_pin -pin_name dac_invert_n_diff -layer M3 -location {46.3 49.0}
place_pin -pin_name dac_state_n_diff[15] -layer M3 -location {47.1 49.0}
place_pin -pin_name dac_state_n_diff[14] -layer M3 -location {47.9 49.0}
place_pin -pin_name dac_state_n_diff[13] -layer M3 -location {48.7 49.0}
place_pin -pin_name dac_state_n_diff[12] -layer M3 -location {49.5 49.0}
place_pin -pin_name dac_state_n_diff[11] -layer M3 -location {50.3 49.0}
place_pin -pin_name dac_state_n_diff[10] -layer M3 -location {51.1 49.0}
place_pin -pin_name dac_state_n_diff[9] -layer M3 -location {51.9 49.0}
place_pin -pin_name dac_state_n_diff[8] -layer M3 -location {52.7 49.0}
place_pin -pin_name dac_state_n_diff[7] -layer M3 -location {53.5 49.0}
place_pin -pin_name dac_state_n_diff[6] -layer M3 -location {54.3 49.0}
place_pin -pin_name dac_state_n_diff[5] -layer M3 -location {55.1 49.0}
place_pin -pin_name dac_state_n_diff[4] -layer M3 -location {55.9 49.0}
place_pin -pin_name dac_state_n_diff[3] -layer M3 -location {56.7 49.0}
place_pin -pin_name dac_state_n_diff[2] -layer M3 -location {57.5 49.0}
place_pin -pin_name dac_state_n_diff[1] -layer M3 -location {58.3 49.0}
place_pin -pin_name dac_state_n_diff[0] -layer M3 -location {59.1 49.0}
