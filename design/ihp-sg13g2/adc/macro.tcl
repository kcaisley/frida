# Manual macro placement for FRIDA ADC IHP-SG13G2

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