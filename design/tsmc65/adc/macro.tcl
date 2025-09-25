# Manual macro placement for FRIDA ADC TSMC65
# Place macros using place_macro commands for 60x60 design


# Place comp at center above caparrays
place_macro -macro_name comp -location {20.5 34.5}

# # Place samp_p above caparray_p
place_macro -macro_name samp_p -location {10.0 50.0}

# # Place samp_n above caparray_n
place_macro -macro_name samp_n -location {40.8 50.0} -orientation MY

# Place caparray_p at left side, within core area
place_macro -macro_name caparray_p -location {10.0 3.0} -exact -allow_overlap

# Place caparray_n at right side, within core area
place_macro -macro_name caparray_n -location {49.0 3.0} -orientation MY  -exact -allow_overlap

puts "Manual macro placement completed"