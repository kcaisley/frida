# Soft placement blockage in upper 2/3 of die
# This discourages placement in the ADC macro region
# and encourages SPI register cells to stay near bottom edge pins

puts "Creating soft blockage in upper 2/3..."

# Die area: 0 0 540 540 (540um x 540um)
# Upper 2/3: 0 180 540 540 (soft blockage - reserved for ADCs)

create_blockage -region {0 120 540 540} -soft

puts "Created soft blockage in upper 2/3 (0 180 540 540)"
