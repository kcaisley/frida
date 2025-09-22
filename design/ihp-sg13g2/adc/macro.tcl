# Manual macro placement for FRIDA ADC IHP-SG13G2
# Place macros using place_macro commands and custom place_cover_macro for CLASS COVER

# Custom procedure to place CLASS COVER macros using direct ODB calls
proc place_cover_macro { args } {
  # Parse arguments similar to place_macro
  set cover_name ""
  set location ""

  for {set i 0} {$i < [llength $args]} {incr i} {
    set arg [lindex $args $i]
    if {$arg == "-cover_name"} {
      incr i
      set cover_name [lindex $args $i]
    } elseif {$arg == "-location"} {
      incr i
      set location [lindex $args $i]
    }
  }

  if {$cover_name == ""} {
    puts "Error: -cover_name is required"
    return
  }
  if {$location == ""} {
    puts "Error: -location is required"
    return
  }

  # Extract x and y coordinates
  if {[llength $location] != 2} {
    puts "Error: -location must be a list of 2 values {x y}"
    return
  }

  set x [lindex $location 0]
  set y [lindex $location 1]

  # Find and place the instance using direct ODB calls
  set block [ord::get_db_block]
  set inst [$block findInst $cover_name]
  if { $inst != "NULL" } {
    # Convert coordinates to database units (micrometers * 1000)
    set x_dbu [expr {int($x * 1000)}]
    set y_dbu [expr {int($y * 1000)}]
    $inst setLocation $x_dbu $y_dbu
    $inst setPlacementStatus "PLACED"
    puts "Placed cover macro $cover_name at ($x, $y)"
  } else {
    puts "Warning: Could not find instance $cover_name"
  }
}

# Place caparray_p at (30, 10) using custom command
# place_cover_macro -cover_name caparray_p -location {29.82 9.66}

# Place caparray_n at (80, 10) using custom command
# place_cover_macro -cover_name caparray_n -location {78.96 9.66}

# Place caparray_p at (30, 10) - original position
place_macro -macro_name caparray_p -location {29.82 9.66}

# Place caparray_n at (80, 10) - original position
place_macro -macro_name caparray_n -location {78.96 9.66}

# Place comp at (60, 106.4) - shifted down by 3.6μm (2×1.8μm) from 110.0
place_macro -macro_name comp -location {60 106.4}

# Place samp_p at (45, 110.0) - original position
place_macro -macro_name samp_p -location {45 110.0}

# Place samp_n at (95, 110.0) - original position
place_macro -macro_name samp_n -location {95 110.0}

puts "Manual macro placement completed"