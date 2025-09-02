# Frida ADC Macro Placement Script
# 5 analog macro instances for mixed-signal layout
#
# Layout Plan:
# - 2x caparray (positive & negative) centered above logic on M5/M6
# - 1x comp (comparator) centered in upper middle
# - 2x sampswitch (positive & negative) on either side
#
# Macro Sizes:
# - caparray: 18.160 x 53.740 µm
# - comp: 18.82 x 19.085 µm  
# - sampswitch: 9.25 x 3.75 µm

# Place macros with coordinates in micrometers
# Format: place_macro instance_name x y orientation

# Testing with caparray macros only first
# Positive capacitor array - left, above logic
place_macro -macro_name caparray_p -location {0 0} -orientation R0 -exact

# Negative capacitor array - right, above logic  
place_macro -macro_name caparray_n -location {30 0} -orientation R0 -exact

# Positive sampling switch - top left of comparator
place_macro -macro_name samp_p -location {10 35} -orientation R0 -exact

# Comparator - upper middle center
place_macro -macro_name comp -location {20 35} -orientation R0 -exact

# Negative sampling switch - top right of comparator
place_macro -macro_name samp_n -location {40 35} -orientation R0 -exact