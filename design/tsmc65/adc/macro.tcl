# Manual macro placement for FRIDA ADC TSMC65
# Place macros using place_macro commands for smaller 60x60 design
# Core area: (2, 3.6) to (58, 57.6)

# Place caparray_p at left side, within core area
place_macro -macro_name caparray_p -location {10.1 5.0}

# Place caparray_n at right side, within core area
place_macro -macro_name caparray_n -location {31.7 5.0}

# Place comp at center above caparrays
place_macro -macro_name comp -location {20.5 30.0}

# Place samp_p above caparray_p
place_macro -macro_name samp_p -location {10.1 50.0}

# Place samp_n above caparray_n
place_macro -macro_name samp_n -location {40.7 50.0}

puts "Manual macro placement completed"