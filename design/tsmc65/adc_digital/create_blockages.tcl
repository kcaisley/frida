# Placement blockages for future analog macro integration
# Reserve space for analog macros that will be placed during top-level integration

puts "Creating blockages for analog macro areas..."

# Reserve area for comparator (19um wide, centered in 60um area)
# Expanded by 1um: X0-1, Y0-1, X1+1 (keeping Y1 the same)
create_blockage -region {17.5 27.0 42.5 49}
puts "Created blockage for comparator: 19.5 28.6 40.5 48.6"

# Reserve areas for sampling switches (two separate locations)
# Expanded by 1um: X0-1, Y0-1, X1+1 (keeping Y1 the same)
create_blockage -region {14 42.6 21 49}
puts "Created blockage for sampling switch 1: 14 42.6 21 49"

create_blockage -region {39 42.6 46 49}
puts "Created blockage for sampling switch 2: 39 42.6 46 49"

# Note: No blockages needed for capacitor arrays as they will be placed externally