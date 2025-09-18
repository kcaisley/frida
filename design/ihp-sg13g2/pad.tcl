# FRIDA Pad Placement Script for IHP-SG13G2
# 1.5mm x 1.5mm die with I/O pad ring and bondpads
# 7 positions per side (some positions empty, filled by filler cells)

set IO_LENGTH 180
set IO_WIDTH 80
set BONDPAD_SIZE 70
set SEALRING_OFFSET 75
set IO_OFFSET [expr { $SEALRING_OFFSET }]

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

# Create IO Rows
make_io_sites \
  -horizontal_site IOLibSite \
  -vertical_site IOLibSite \
  -corner_site IOLibCSite \
  -offset $IO_OFFSET

# Place Pads - 7 positions per side (all positions filled)
# SOUTH Edge (7 pads): SPI interface, comparator outputs, and reserved
place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    0 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_spi_sdi} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    1 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_spi_sdo} \
  -master sg13g2_IOPadOut4mA

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    2 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_spi_sclk} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    3 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_spi_cs_b} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    4 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_comp_out_p} \
  -master sg13g2_IOPadOut4mA

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    5 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_comp_out_n} \
  -master sg13g2_IOPadOut4mA

place_pad \
  -row IO_SOUTH \
  -location [calc_horizontal_pad_location \
    6 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_cmos_reserved_0} \
  -master sg13g2_IOPadOut4mA

# WEST Edge (7 pads): Power supplies and sequencer init/sample (bottom to top)
place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    0 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_vdd_io} \
  -master sg13g2_IOPadIOVdd

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    1 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_seq_samp_n} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    2 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_seq_samp_p} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    3 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_seq_init_n} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    4 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_seq_init_p} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    5 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_vss_a} \
  -master sg13g2_IOPadVss

place_pad \
  -row IO_WEST \
  -location [calc_vertical_pad_location \
    6 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_vdd_a} \
  -master sg13g2_IOPadVdd

# EAST Edge (7 pads): Digital power and sequencer compare/logic (bottom to top)
place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    0 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_vss_io} \
  -master sg13g2_IOPadIOVss

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    1 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_seq_logic_n} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    2 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_seq_logic_p} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    3 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_seq_cmp_n} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    4 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_seq_cmp_p} \
  -master sg13g2_IOPadIn

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    5 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_vss_d} \
  -master sg13g2_IOPadVss

place_pad \
  -row IO_EAST \
  -location [calc_vertical_pad_location \
    6 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_vdd_d} \
  -master sg13g2_IOPadVdd

# NORTH Edge (7 pads): reserved, vdd_dac, vss_dac, reserved, vin_p, vin_n, reserved (left to right)
place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    0 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_cmos_reserved_1} \
  -master sg13g2_IOPadOut4mA

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    1 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_vdd_dac} \
  -master sg13g2_IOPadVdd

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    2 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_vss_dac} \
  -master sg13g2_IOPadIOVss

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    3 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_cmos_reserved_2} \
  -master sg13g2_IOPadOut4mA

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    4 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_vin_p} \
  -master sg13g2_IOPadAnalog

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    5 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_vin_n} \
  -master sg13g2_IOPadAnalog

place_pad \
  -row IO_NORTH \
  -location [calc_horizontal_pad_location \
    6 7 $IO_LENGTH $IO_WIDTH $BONDPAD_SIZE $SEALRING_OFFSET] \
  {sg13g2_IOPad_cmos_reserved_3} \
  -master sg13g2_IOPadOut4mA

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

# NOTE: place_io_terminals not needed for top-level port design
# The command is designed for instance pins (u_clk.u_in), not top-level ports (cmos_reserved_0_PAD)
# Top-level ports should be automatically connected during global placement

# Place bondpads on all I/O pads
place_bondpad -bond bondpad_70x70 sg13g2_IOPad_* -offset {5.0 -70.0}

remove_io_rows