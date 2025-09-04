# FRIDA Pad Placement Script
# 1mm x 1mm die with CUP pad ring
# Based on TSMC65 CUP pad technology
# 7 pads per side with 100μm pitch

# Constants for positioning calculations
set PAD_PITCH 100.0
set CORNER_SW_X 27.925
set CORNER_SW_Y 27.925
set CORNER_NE_X 972.075
set CORNER_NE_Y 972.075

# Helper functions for calculating pad positions (100μm pitch spacing)
proc calc_south_pad_location { index } {
    global CORNER_SW_X PAD_PITCH
    return [expr { $CORNER_SW_X + ($index * $PAD_PITCH) + 50.0 }]
}

proc calc_north_pad_location { index } {
    global CORNER_SW_X PAD_PITCH
    return [expr { $CORNER_SW_X + ($index * $PAD_PITCH) + 50.0 }]
}

proc calc_west_pad_location { index } {
    global CORNER_SW_Y PAD_PITCH
    return [expr { $CORNER_SW_Y + ($index * $PAD_PITCH) + 50.0 }]
}

proc calc_east_pad_location { index } {
    global CORNER_SW_Y PAD_PITCH
    return [expr { $CORNER_SW_Y + ($index * $PAD_PITCH) + 50.0 }]
}

# Create fake IO sites (physical-only, no electrical connections needed)
make_fake_io_site -name CUP_IOSite -width 100 -height 100
make_fake_io_site -name CUP_CornerSite -width 100 -height 100

# Create IO Rows
make_io_sites \
  -horizontal_site CUP_IOSite \
  -vertical_site CUP_IOSite \
  -corner_site CUP_CornerSite \
  -offset 160

# Place Corner Cells
place_pad \
  -row IO_SOUTH \
  -location $CORNER_SW_X \
  {sf_corner_sw} \
  -master SF_CORNER

place_pad \
  -row IO_SOUTH \
  -location $CORNER_NE_X \
  {sf_corner_se} \
  -master SF_CORNER

place_pad \
  -row IO_NORTH \
  -location $CORNER_SW_X \
  {sf_corner_nw} \
  -master SF_CORNER

place_pad \
  -row IO_NORTH \
  -location $CORNER_NE_X \
  {sf_corner_ne} \
  -master SF_CORNER

# SOUTH Edge Pads (7 positions, left to right)
# Position 0: SPI SDI
place_pad \
  -row IO_SOUTH \
  -location [calc_south_pad_location 0] \
  {cmos_spi_sdi} \
  -master CMOS_IO_CUP_pad

# Position 1: SPI SDO  
place_pad \
  -row IO_SOUTH \
  -location [calc_south_pad_location 1] \
  {cmos_spi_sdo} \
  -master CMOS_IO_CUP_pad

# Position 2: SPI SCLK
place_pad \
  -row IO_SOUTH \
  -location [calc_south_pad_location 2] \
  {cmos_spi_sclk} \
  -master CMOS_IO_CUP_pad

# Position 3: SPI CS_B
place_pad \
  -row IO_SOUTH \
  -location [calc_south_pad_location 3] \
  {cmos_spi_cs_b} \
  -master CMOS_IO_CUP_pad

# Position 4-5: LVDS TX (comp_out) - double width at specified coordinates
place_pad \
  -row IO_SOUTH \
  -location 575.0 \
  {lvds_comp_out} \
  -master LVDS_TX_CUP_pad

# Position 6: Reset
place_pad \
  -row IO_SOUTH \
  -location [calc_south_pad_location 6] \
  {cmos_reset_b} \
  -master CMOS_IO_CUP_pad

# WEST Edge Pads (7 positions, top to bottom)
# Position 0: VDD_A
place_pad \
  -row IO_WEST \
  -location [calc_west_pad_location 6] \
  {power_vdd_a} \
  -master POWER_CUP_pad

# Position 1: VSS_A
place_pad \
  -row IO_WEST \
  -location [calc_west_pad_location 5] \
  {ground_vss_a} \
  -master GROUND_CUP_pad

# POWERCUT between positions 2-3
place_pad \
  -row IO_WEST \
  -location [expr { ([calc_west_pad_location 4] + [calc_west_pad_location 3]) / 2.0 }] \
  {powercut_west_analog_io} \
  -master POWERCUT_CUP

# Position 2: VDD_IO  
place_pad \
  -row IO_WEST \
  -location [calc_west_pad_location 4] \
  {power_vdd_io} \
  -master POWER_CUP_pad

# Position 3-4: LVDS RX seq_init - double width at specified coordinates
place_pad \
  -row IO_WEST \
  -location 325.0 \
  {lvds_seq_init} \
  -master LVDS_RX_CUP_pad

# Position 5-6: LVDS RX seq_samp - double width
place_pad \
  -row IO_WEST \
  -location [calc_west_pad_location 1] \
  {lvds_seq_samp} \
  -master LVDS_RX_CUP_pad

# EAST Edge Pads (7 positions, top to bottom)
# Position 0: VDD_D
place_pad \
  -row IO_EAST \
  -location [calc_east_pad_location 6] \
  {power_vdd_d} \
  -master POWER_CUP_pad

# Position 1: VSS_D
place_pad \
  -row IO_EAST \
  -location [calc_east_pad_location 5] \
  {ground_vss_d} \
  -master GROUND_CUP_pad

# POWERCUT between positions 2-3
place_pad \
  -row IO_EAST \
  -location [expr { ([calc_east_pad_location 4] + [calc_east_pad_location 3]) / 2.0 }] \
  {powercut_east_digital_io} \
  -master POWERCUT_CUP

# Position 2: VSS_IO
place_pad \
  -row IO_EAST \
  -location [calc_east_pad_location 4] \
  {ground_vss_io} \
  -master GROUND_CUP_pad

# Position 3-4: LVDS RX seq_cmp - double width  
place_pad \
  -row IO_EAST \
  -location [calc_east_pad_location 3] \
  {lvds_seq_cmp} \
  -master LVDS_RX_CUP_pad

# Position 5-6: LVDS RX seq_logic - double width
place_pad \
  -row IO_EAST \
  -location [calc_east_pad_location 1] \
  {lvds_seq_logic} \
  -master LVDS_RX_CUP_pad

# NORTH Edge Pads (7 positions, left to right)
# Position 0: Reserved passive
place_pad \
  -row IO_NORTH \
  -location [calc_north_pad_location 0] \
  {passive_reserved_0} \
  -master PASSIVE_CUP_pad

# POWERCUT between positions 1-2
place_pad \
  -row IO_NORTH \
  -location [expr { ([calc_north_pad_location 0] + [calc_north_pad_location 1]) / 2.0 }] \
  {powercut_north_dac_1} \
  -master POWERCUT_CUP

# Position 1: VDD_DAC
place_pad \
  -row IO_NORTH \
  -location [calc_north_pad_location 1] \
  {power_vdd_dac} \
  -master POWER_CUP_pad

# Position 2: VSS_DAC
place_pad \
  -row IO_NORTH \
  -location [calc_north_pad_location 2] \
  {ground_vss_dac} \
  -master GROUND_CUP_pad

# POWERCUT between positions 3-4
place_pad \
  -row IO_NORTH \
  -location [expr { ([calc_north_pad_location 2] + [calc_north_pad_location 3]) / 2.0 }] \
  {powercut_north_analog_input} \
  -master POWERCUT_CUP

# Position 3: VIN_P
place_pad \
  -row IO_NORTH \
  -location [calc_north_pad_location 3] \
  {passive_vin_p} \
  -master PASSIVE_CUP_pad

# Position 4: VIN_N
place_pad \
  -row IO_NORTH \
  -location [calc_north_pad_location 4] \
  {passive_vin_n} \
  -master PASSIVE_CUP_pad

# POWERCUT between positions 5-6
place_pad \
  -row IO_NORTH \
  -location [expr { ([calc_north_pad_location 4] + [calc_north_pad_location 5]) / 2.0 }] \
  {powercut_north_reserved} \
  -master POWERCUT_CUP

# Position 5: Reserved CMOS 1
place_pad \
  -row IO_NORTH \
  -location [calc_north_pad_location 5] \
  {cmos_reserved_1} \
  -master CMOS_IO_CUP_pad

# Position 6: Reserved CMOS 2
place_pad \
  -row IO_NORTH \
  -location [calc_north_pad_location 6] \
  {cmos_reserved_2} \
  -master CMOS_IO_CUP_pad

# Fill remaining spaces with fillers
# Note: SF_FILLER50_CUP and SF_FILLER_CUP will be placed automatically
# between pads to maintain power ring continuity

# Connect adjacent pads by abutment
connect_by_abutment

# Remove IO rows when complete
remove_io_rows