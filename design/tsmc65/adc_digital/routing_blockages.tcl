# Routing blockages for analog macro areas
puts "NED ADDED: Creating routing blockages for analog macro areas..."

# Written based on example: flow/scripts/add_routing_blk.tcl

set db [::ord::get_db]
set block [[$db getChip] getBlock]
set tech [$db getTech]

# Get routing layers
set layer_M1 [$tech findLayer M1]
set layer_M2 [$tech findLayer M2]
set layer_M3 [$tech findLayer M3]
set layer_M4 [$tech findLayer M4]

# DBU conversion
set dbu [$tech getDbUnitsPerMicron]

# Comparator area: 19.5 28.6 40.5 48.6 (X0-1, Y0-1, X1+1)
set comp_llx [expr int(19.5 * $dbu)]
set comp_lly [expr int(28.8 * $dbu)]
set comp_urx [expr int(40.5 * $dbu)]
set comp_ury [expr int(49.0 * $dbu)]

odb::dbObstruction_create $block $layer_M1 $comp_llx $comp_lly $comp_urx $comp_ury
odb::dbObstruction_create $block $layer_M2 $comp_llx $comp_lly $comp_urx $comp_ury
odb::dbObstruction_create $block $layer_M3 $comp_llx $comp_lly $comp_urx $comp_ury
odb::dbObstruction_create $block $layer_M4 $comp_llx $comp_lly $comp_urx $comp_ury

# Sampling switch 1: 14 42.6 21 49 (X0-1, Y0-1, X1+1)
set sw1_llx [expr int(14.0 * $dbu)]
set sw1_lly [expr int(42.0 * $dbu)]
set sw1_urx [expr int(21.0 * $dbu)]
set sw1_ury [expr int(49.0 * $dbu)]

odb::dbObstruction_create $block $layer_M1 $sw1_llx $sw1_lly $sw1_urx $sw1_ury
odb::dbObstruction_create $block $layer_M2 $sw1_llx $sw1_lly $sw1_urx $sw1_ury
odb::dbObstruction_create $block $layer_M3 $sw1_llx $sw1_lly $sw1_urx $sw1_ury
odb::dbObstruction_create $block $layer_M4 $sw1_llx $sw1_lly $sw1_urx $sw1_ury

# Sampling switch 2: 39 42.6 46 49 (X0-1, Y0-1, X1+1)
set sw2_llx [expr int(39.0 * $dbu)]
set sw2_lly [expr int(42.0 * $dbu)]
set sw2_urx [expr int(46.0 * $dbu)]
set sw2_ury [expr int(49.0 * $dbu)]

odb::dbObstruction_create $block $layer_M1 $sw2_llx $sw2_lly $sw2_urx $sw2_ury
odb::dbObstruction_create $block $layer_M2 $sw2_llx $sw2_lly $sw2_urx $sw2_ury
odb::dbObstruction_create $block $layer_M3 $sw2_llx $sw2_lly $sw2_urx $sw2_ury
odb::dbObstruction_create $block $layer_M4 $sw2_llx $sw2_lly $sw2_urx $sw2_ury

puts "Created routing blockages on M1-M4 for all analog macro areas"
