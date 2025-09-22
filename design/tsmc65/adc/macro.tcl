# Manual macro placement for FRIDA ADC TSMC65
# Place macros using place_macro commands for smaller 60x60 design

# Place caparray_p at (10, 3) - left side, original position
place_macro -macro_name caparray_p -location {10.1 3.2}

# Place caparray_n at (32, 3) - right side, original position
place_macro -macro_name caparray_n -location {31.7 3.2}

# Place comp at (20, 28.4) - center above caparrays, shifted down by 3.6μm (2×1.8μm)
place_macro -macro_name comp -location {20.5 28.0}

# Place samp_p at (10, 46) - above caparray_p, original position
place_macro -macro_name samp_p -location {10.1 46.4}

# Place samp_n at (41, 46) - above caparray_n, original position
place_macro -macro_name samp_n -location {40.7 46.4}

puts "Manual macro placement completed"