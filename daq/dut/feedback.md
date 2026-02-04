level-shifter
cap feedback
input devices/switching for buffer
pulldown for reset (nmos) and 20k resistor and reset
forward vdd_fpga voltage on one of the extra pins
negative rail for buffer (configurable w/ neg or ground)
share input connector pins, but have headers to measure current
tvs diode for reverse polarity protection (not for transients)
clamp diodes to protect frida chip from external or buffer sources (vin_p and vin_n)
    use solder/pin jumper
    check for impact on ENOB
    vdd_dac and gnd 
fixt testpoint on vin_n
check for new / app sheets on ad and ti
