# FRIDA Pad Placement Script
# 1mm x 1mm die with CUP pad ring
# 7 pads per side with 100μm pitch

# Constants for positioning calculations
# 1000μm die with 50μm inset for 25μm sealring

# From config.mk: set DIE_AREA {0 0 1000 1000}

set IO_LENGTH 119.895
set IO_WIDTH 50
set CORNER_SIZE 121.655
set SEALRING_OFFSET 24.505
set INTERCELL_SPACING 50
set CORNER_TO_FIRST_CELL_SPACING 5
set IO_OFFSET [expr { $SEALRING_OFFSET }]

# spacing pattern:
# hxxxPxPxPxPxPxPxPxxxh

proc calc_horizontal_pad_location { index total IO_LENGTH IO_WIDTH SEALRING_OFFSET CORNER_SIZE CORNER_TO_FIRST_CELL_SPACING INTERCELL_SPACING } {
  # Start position: corner + spacing to first cell (175-5.66)
  set START_X {169.340}
  # set START_X [expr { $CORNER_SIZE + $CORNER_TO_FIRST_CELL_SPACING }]
  #               175         1-4
  set location [format "%.3f" [expr { $START_X + ($index - 1) * ($IO_WIDTH + $INTERCELL_SPACING) }]]
  puts "Horizontal pad index $index: location = $location"
  return $location
}

proc calc_vertical_pad_location { index total IO_LENGTH IO_WIDTH SEALRING_OFFSET CORNER_SIZE CORNER_TO_FIRST_CELL_SPACING INTERCELL_SPACING } {
  # Start position from BOTTOM: corner + spacing to first cell (175-5.66)
  set START_Y {169.340}
  # set START_Y [expr { $CORNER_SIZE + $CORNER_TO_FIRST_CELL_SPACING }]

  # Place from bottom to top (add for each index)
  set location [format "%.3f" [expr { $START_Y + ($index - 1) * ($IO_WIDTH + $INTERCELL_SPACING) }]]
  puts "Vertical pad index $index: location = $location"
  return $location
}

# Create fake IO sites (physical-only, no electrical connections needed)
# The IHP example shows that corner and normal pads all use the same real site, but they still make these dummy ones:
make_fake_io_site -name IOLibSite -width 1 -height $IO_LENGTH

# SF_CORNER is 123.42μm × 123.42μm
make_fake_io_site -name IOLibCSite -width $CORNER_SIZE -height $CORNER_SIZE

# Create IO Rows
make_io_sites \
  -horizontal_site IOLibSite \
  -vertical_site IOLibSite \
  -corner_site IOLibCSite \
  -offset $IO_OFFSET

# SOUTH Edge Pads (7 positions, left to right)
# Position 1: SPI SDI
place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location 1 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {cmos_spi_sdi} \
  -master CMOS_IO_CUP_pad


# Position 2: SPI SDO
place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location 2 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {cmos_spi_sdo} \
  -master CMOS_IO_CUP_pad


# Position 3: SPI SCLK
place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location 3 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {cmos_spi_sclk} \
  -master CMOS_IO_CUP_pad


# Position 4: SPI CS_B
place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location 4 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {cmos_spi_cs_b} \
  -master CMOS_IO_CUP_pad

# Position 5-6: LVDS TX (comp_out) - 150μm wide (double width) - no filler needed
place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location 5 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {lvds_comp_out} \
  -master LVDS_TX_CUP_pad

# Position 7: Reset
# FIXME! This should be a vss_sub_cup_pad!
place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location 7 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {cmos_reset_b} \
  -master CMOS_IO_CUP_pad

# WEST Edge Pads (7 positions, bottom to top)
# Position 1: VDD_IO
place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location 1 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {power_vdd_io} \
  -master POWER_CUP_pad

# Position 2: LVDS RX seq_init - 150μm wide (double width)
place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location 2 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {lvds_seq_init} \
  -master LVDS_RX_CUP_pad

# Position 4: LVDS RX seq_samp - 150μm wide (double width)
place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location 4 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {lvds_seq_samp} \
  -master LVDS_RX_CUP_pad

# Position 6: VSS_A
place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location 6 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {ground_vss_a} \
  -master GROUND_CUP_pad

# Position 7: VDD_A
place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location 7 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {power_vdd_a} \
  -master POWER_CUP_pad

# EAST Edge Pads (7 positions, bottom to top)
# Position 1: VSS_IO
place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location 1 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {ground_vss_io} \
  -master GROUND_CUP_pad

# Position 2: LVDS RX seq_cmp - 150μm wide (double width)
place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location 2 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {lvds_seq_cmp} \
  -master LVDS_RX_CUP_pad

# Position 4: LVDS RX seq_logic - 150μm wide (double width)
place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location 4 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {lvds_seq_logic} \
  -master LVDS_RX_CUP_pad

# Position 6: VSS_D
place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location 6 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {ground_vss_d} \
  -master GROUND_CUP_pad

# Position 7: VDD_D
place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location 7 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {power_vdd_d} \
  -master POWER_CUP_pad

# NORTH Edge Pads (7 positions, left to right)
# Position 0: Reserved passive
place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location 1 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {passive_reserved_0} \
  -master PASSIVE_CUP_pad


# Position 1: VDD_DAC
place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location 2 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {power_vdd_dac} \
  -master POWER_CUP_pad

# Position 2: VSS_DAC
place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location 3 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {ground_vss_dac} \
  -master GROUND_CUP_pad


# Position 3: VIN_P
place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location 4 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {passive_vin_p} \
  -master PASSIVE_CUP_pad


# Position 4: VIN_N
place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location 5 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {passive_vin_n} \
  -master PASSIVE_CUP_pad


# Position 5: Reserved CMOS 1
place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location 6 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {cmos_reserved_1} \
  -master CMOS_IO_CUP_pad


# Position 6: Reserved CMOS 2
place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location 7 7 $IO_LENGTH $IO_WIDTH $SEALRING_OFFSET $CORNER_SIZE $CORNER_TO_FIRST_CELL_SPACING $INTERCELL_SPACING] \
  {cmos_reserved_2} \
  -master CMOS_IO_CUP_pad

# # Place Corner cells manually accounting for LEF origin offset (3.42, 3.42)
# set CORNER_ORIGIN_OFFSET 3.42

# # SW Corner (no mirror - default orientation)
# place_pad \
#   -master SF_CORNER \
#   -row IO_SOUTH \
#   -location [expr { $IO_OFFSET + $CORNER_ORIGIN_OFFSET }] \
#   {sf_corner_sw}

# # SE Corner (mirrored)
# place_pad \
#   -mirror \
#   -master SF_CORNER \
#   -row IO_SOUTH \
#   -location [expr { 1000 - $IO_OFFSET - $CORNER_ORIGIN_OFFSET }] \
#   {sf_corner_se}

# # NW Corner (mirrored)
# place_pad \
#   -mirror \
#   -master SF_CORNER \
#   -row IO_NORTH \
#   -location [expr { $IO_OFFSET + $CORNER_ORIGIN_OFFSET }] \
#   {sf_corner_nw}

# # NE Corner (mirrored)
# place_pad \
#   -mirror \
#   -master SF_CORNER \
#   -row IO_NORTH \
#   -location [expr { 1000 - $IO_OFFSET - $CORNER_ORIGIN_OFFSET }] \
#   {sf_corner_ne}

# place_io_fill \
#   -row IO_NORTH \
#   -permit_overlaps SF_FILLER_CUP \
#   SF_FILLER50_CUP SF_FILLER25_CUP SF_FILLER_CUP
# place_io_fill \
#   -row IO_SOUTH \
#   -permit_overlaps SF_FILLER_CUP \
#   SF_FILLER50_CUP SF_FILLER25_CUP SF_FILLER_CUP
# place_io_fill \
#   -row IO_WEST \
#   -permit_overlaps SF_FILLER_CUP \
#   SF_FILLER50_CUP SF_FILLER25_CUP SF_FILLER_CUP
# place_io_fill \
#   -row IO_EAST \
#   -permit_overlaps SF_FILLER_CUP \
#   SF_FILLER50_CUP SF_FILLER25_CUP SF_FILLER_CUP

connect_by_abutment

# remove_io_rows