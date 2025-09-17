# FRIDA Pad Placement Script for IHP-SG13G2
# 1.5mm x 1.5mm die with I/O pad ring and bondpads
# 7 pads per side (28 total) using sg13g2_IOPad* masters

set IO_LENGTH 180
set IO_WIDTH 80
set BONDPAD_SIZE 70
set SEALRING_OFFSET 70
set IO_OFFSET [expr { $BONDPAD_SIZE + $SEALRING_OFFSET }]

proc calc_horizontal_pad_location { index total IO_LENGTH IO_WIDTH BONDPAD_SIZE SEALRING_OFFSET } {
  set DIE_WIDTH [expr { [lindex $::env(DIE_AREA) 2] - [lindex $::env(DIE_AREA) 0] }]
  set PAD_OFFSET [expr { $IO_LENGTH + $BONDPAD_SIZE + $SEALRING_OFFSET }]
  set PAD_AREA_WIDTH [expr { $DIE_WIDTH - ($PAD_OFFSET * 2) }]
  set HORIZONTAL_PAD_DISTANCE [expr { ($PAD_AREA_WIDTH / $total) - $IO_WIDTH }]

  return [expr {
    $PAD_OFFSET + (($IO_WIDTH + $HORIZONTAL_PAD_DISTANCE) * $index)
    + ($HORIZONTAL_PAD_DISTANCE / 2)
  }]
}

proc calc_vertical_pad_location { index total IO_LENGTH IO_WIDTH BONDPAD_SIZE SEALRING_OFFSET } {
  set DIE_HEIGHT [expr { [lindex $::env(DIE_AREA) 3] - [lindex $::env(DIE_AREA) 1] }]
  set PAD_OFFSET [expr { $IO_LENGTH + $BONDPAD_SIZE + $SEALRING_OFFSET }]
  set PAD_AREA_HEIGHT [expr { $DIE_HEIGHT - ($PAD_OFFSET * 2) }]
  set VERTICAL_PAD_DISTANCE [expr { ($PAD_AREA_HEIGHT / $total) - $IO_WIDTH }]

  return [expr {
    $PAD_OFFSET + (($IO_WIDTH + $VERTICAL_PAD_DISTANCE) * $index)
    + ($VERTICAL_PAD_DISTANCE / 2)
  }]
}

make_fake_io_site -name IOLibSite -width 1 -height $IO_LENGTH
make_fake_io_site -name IOLibCSite -width $IO_LENGTH -height $IO_LENGTH

set IO_OFFSET [expr { $BONDPAD_SIZE + $SEALRING_OFFSET }]
# Create IO Rows
make_io_sites \
  -horizontal_site IOLibSite \
  -vertical_site IOLibSite \
  -corner_site IOLibCSite \
  -offset $IO_OFFSET

# Place Pads - 7 pads per side
# SOUTH Edge (7 pads): SPI interface and comparator outputs
place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    0 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {spi_sdi_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    1 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {spi_sdo_PAD} \
  -master sg13g2_IOPadOut4mA

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    2 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {spi_sclk_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    3 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {spi_cs_b_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    4 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {comp_out_p_PAD} \
  -master sg13g2_IOPadOut4mA

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    5 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {comp_out_n_PAD} \
  -master sg13g2_IOPadOut4mA

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    6 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {reset_b_PAD} \
  -master sg13g2_IOPadIn

# WEST Edge (7 pads): Power supplies and sequencer init/sample
place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    0 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {vdd_a_PAD} \
  -master sg13g2_IOPadVdd

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    1 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {vss_a_PAD} \
  -master sg13g2_IOPadVss

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    2 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {seq_init_p_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    3 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {seq_init_n_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    4 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {seq_samp_p_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    5 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {seq_samp_n_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    6 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {vdd_dac_PAD} \
  -master sg13g2_IOPadVdd

# EAST Edge (7 pads): Digital power and sequencer compare/logic
place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    0 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {vdd_d_PAD} \
  -master sg13g2_IOPadVdd

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    1 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {vss_d_PAD} \
  -master sg13g2_IOPadVss

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    2 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {seq_cmp_p_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    3 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {seq_cmp_n_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    4 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {seq_logic_p_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    5 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {seq_logic_n_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    6 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {vss_dac_PAD} \
  -master sg13g2_IOPadIOVss

# NORTH Edge (7 pads): Analog inputs and I/O power
place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    0 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {vin_p_PAD} \
  -master sg13g2_IOPadInOut4mA

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    1 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {vin_n_PAD} \
  -master sg13g2_IOPadInOut4mA

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    2 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {vdd_io_PAD} \
  -master sg13g2_IOPadIOVdd

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    3 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {vss_io_PAD} \
  -master sg13g2_IOPadIOVss

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    4 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {clk_PAD} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    5 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {extra_vdd_PAD} \
  -master sg13g2_IOPadVdd

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    6 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {extra_vss_PAD} \
  -master sg13g2_IOPadVss

# Place Corner Cells and Filler
place_corners sg13g2_Corner

set iofill {
    sg13g2_Filler10000
    sg13g2_Filler4000
    sg13g2_Filler2000
    sg13g2_Filler1000
    sg13g2_Filler400
    sg13g2_Filler200
}

place_io_fill -row IO_NORTH {*}$iofill
place_io_fill -row IO_SOUTH {*}$iofill
place_io_fill -row IO_WEST {*}$iofill
place_io_fill -row IO_EAST {*}$iofill

connect_by_abutment

# Place bondpads on all I/O pads
place_bondpad -bond bondpad_70x70 *_PAD -offset {5.0 -70.0}

remove_io_rows