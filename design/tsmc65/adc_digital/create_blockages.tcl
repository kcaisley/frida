# Placement blockages for future analog macro integration
# Reserve space for analog macros that will be placed during top-level integration

puts "Creating blockages for analog macro areas..."

# Reserve area for comparator (19um wide, centered in 60um area)
# Center: 60/2 = 30um, so 19um wide = 30 ± 9.5um = 20.5 to 39.5
create_blockage -region {20.5 29.6 39.5 48.6}
puts "Created blockage for comparator: 20.5 29.6 39.5 48.6"

# Reserve areas for sampling switches (two separate locations)
# Need to determine width - assuming similar width as before (10um each)
create_blockage -region {15 43.6 20 49}
puts "Created blockage for sampling switch 1: 11 43.6 21 49"

create_blockage -region {40 43.6 45 49}
puts "Created blockage for sampling switch 2: 34 43.6 44 49"

# Note: No blockages needed for capacitor arrays as they will be placed externally