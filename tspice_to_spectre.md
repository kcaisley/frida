.param redefinedparams=ignore
is needed to stop the error from redefined params, if running a .spc in spectre
`redefinedparams=ignore` is needed in spectre options, if running a .scs in spectre


simulator lang=spectre or spice

** is supported by tspice and spectre, but ^ isn't supported by spectre for exponents


reading veriloga files needed a "" around the file name, which T-spice was unwilling to do in spice mode


Note that if you are passing a parameter to a SPICE primitive, it's model needs to have a user param to match that param. Otherwise it won't fill it in.


include statements in spectre need a `section=tt` instead of just `tt`
include "/users/kcaisley/helena/tech/tsmc65/default_testbench_header_55ulp_linux.lib" section=tt


the `patten` argument of a pwl source needs parenthesis, which T-spice won't do on normal export:
e.g.
Source_v_pwl_1 (gnd inp) Source_v_pwl pattern="0 log_VCC simtime 0.5*log_VCC"


In the 'heirarchy priority list' you should put:


cell name w/ !		view type	view name (can be set abitrarylity, but is often the same as the view type)
!comparator_latch	veriloga	veriloga_test1

^ note that the 'view' column in the software is showing the "view name" not the view type. The real view type is hiding off to the right.


For spectre, the ahdl import needs to look like this:
ahdl_include "SB_saradc8_radixN.HDL/comparator_latch.va"


