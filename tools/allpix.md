allpix on top (batch rune ngspice)
spice on top (batch run allpix first)
vs cosimulation

spice can be called from command line or as shared library
supplying an input signal to spice:
    verilog-A compact model of sensor
    macro model plus current/voltage stimulus (can't be nonlinear)
    cosimulation approach (like nutmeg/gss took)


If hits are changing alot, but circuit should be static, then some form of static transferfunction extraction make sense.

If hits are changing (MC method) and also we want to account for circuit noise/nonlinearity, then we need to run a seperate simulation for each instances. There are two approaches here:
- Run some sort of batch extraction of signal at collection electrode, fit these to a compact model/macro model in spice, and then run SPICE seperately
- Or create a cosimulation approach (probably with allpix as the dominante process) where simulations can be called as a subprocess. ngspice allows a 

For the latter: Look at how cppsim/vppsim nested ngspice, to allow local regions of complicated gate level simulation, while the top level algorithm is a simpler solver (but allows feedback and non-linearity)
