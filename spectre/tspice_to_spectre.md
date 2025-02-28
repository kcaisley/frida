# Netlist, schematic, and Simulation Setup corrections:

1. SPICE `.option` isn't supported. S-edit is smart enough to remove these in an AFS/Spectre export, but 

```
WARNING (SFE-105): "/users/kcaisley/helena/tech/tsmc65/default_testbench_header_55ulp_linux.lib" 97: `threads' has been ignored because it is not
    an option. Correct the name and rerun the simulation. Type `spectre -h options' to get more information on valid option parameters.

WARNING (SFE-105): "/users/kcaisley/helena/tech/tsmc65/default_testbench_header_55ulp_linux.lib" 98: `monteinfo' has been ignored because it is not
    an option. Correct the name and rerun the simulation. Type `spectre -h options' to get more information on valid option parameters.
```

The relevant setting from this file is below, where we can see `.option`

```
 96 .lib tt
 97         .option threads = 1   * run on multiple cores of computer
 98         .option monteinfo = 2 * monteinfo=1 only print histogram
 99                           * monteinfo=2 print all simulation results
100     .param log_only=0
101     .param rh=0
102     .param lvs=0
103     .lib 'default_testbench_header_55ulp_linux.lib' NOM_MODEL
104     .lib 'default_testbench_header_55ulp_linux.lib' setting
105 .endl
```

But we can't fix this for now, without editing the underlying .lib file.

2. Redefining the params gives a lot of noisy warnings, in both T-spice and Spectre. In the latter at least, we can go into settings and add:

`.param redefinedparams=ignore`is needed to stop the error from redefined params, if running a .spc in spectre
`redefinedparams=ignore` is needed in spectre options, if running a .scs in spectre. It will netlist correctly.


3. `simulator lang=spectre` or `spice` is needed by Spectre. The S-Edit export already does this though in AFS/Spectre mode.

4. `**` is supported by tspice and spectre, but `^` isn't supported by spectre for exponents. I've updated the schematic in S-edit to fix this.

The C param of each capacitor is now set to: `cap/2/radix**2`

5. Reading verilog-A files needed a "" around the file name, which T-spice was unwilling to do in spice mode.

```
    ERROR (SFE-23): "SB_saradc8_radixN.scs" 637: The instance `vstepper_n' is referencing an undefined model or subcircuit, `vstepper'. Either include
        the file containing the definition of `vstepper', or define `vstepper' before running the simulation.
    ERROR (SFE-23): "SB_saradc8_radixN.scs" 638: The instance `vstepper_p' is referencing an undefined model or subcircuit, `vstepper'. Either include
        the file containing the definition of `vstepper', or define `vstepper' before running the simulation.
```
The relevant commands would be for e.g. `ahdl_include comparator_latch.va` and `ahdl_include vstepper.va`.

If exporting (instead of netlisting) one need to make sure to *un-check* `Exclude ahdl_include`.



6. include statements in spectre need a `section=tt` instead of just `tt`, and the include needs double quotes. This can be achieved by changing the string in the `Setup Simulation > General > Spectre Library Files` and set it to `"/users/kcaisley/helena/tech/tsmc65/default_testbench_header_55ulp_linux.lib" tt` to produce the output netlist string `include "/users/kcaisley/helena/tech/tsmc65/default_testbench_header_55ulp_linux.lib" section=tt`


7. In the 'heirarchy priority list' you should put:

```
cell name w/ !		view type	view name (can be set abitrarylity, but is often the same as the view type)
!comparator_latch	veriloga	veriloga_test1
```

8. The single quotes below on the width param throw the error `Cannot run the simulation because an unexpected character ''' was found`
```
V5 (syncn gnd!) vsource type=pulse val0=log_VCC val1=0 period=convtime  delay=-convtime/48  rise=100p fall=100p width='(convtime/24)-100p'
V6 (syncp gnd!) vsource type=pulse val0=0 val1=log_VCC period=convtime  delay=-convtime/48  rise=100p fall=100p width='(convtime/24)-100p'
V7 (clockn gnd!) vsource type=pulse val0=log_VCC val1=0 period=convtime/12 delay=0 rise=100p fall=100p width='(convtime/24)-100p'
V8 (clockp gnd!) vsource type=pulse val0=0 val1=log_VCC period=convtime/12 delay=0 rise=100p fall=100p width='(convtime/24)-100p'
```



# Manual fixes:

1. The capacitor model is called `capacitor` and must be lower cased, else you get this error:

```
ERROR (SFE-23): "SB_saradc8_radixN.scs" 580: The instance `Capacitor_3' is referencing an undefined model or subcircuit, `Capacitor'. Either
    include the file containing the definition of `Capacitor', or define `Capacitor' before running the simulation.
```


2. The `save` statements at the end of the file use `<>` which must be escaped:

```
save data\<0\>  
save data\<1\>  
save data\<2\>  
save data\<3\>  
save data\<4\>  
save data\<5\>  
save data\<6\>  
save data<\7\> 
```

3. the analog lib need the path, and need quotes.

4.     WARNING (SFE-30): "SB_saradc8_radixN.scs" 583: Parameter `C', specified for primitive `capacitor', has been ignored because it is an invalid instance parameter. Specify a valid instance parameter and rerun the simulation. Type        `spectre -h capacitor' to get more information on valid instance parameters.

5. Error found by spectre in `PAGEFRAME', during circuit read-in.
    ERROR (SFE-23): "SB_saradc8_radixN.scs" 34: The instance `VERSION_1' is referencing an undefined model or subcircuit, `VERSION'. Either include the file containing the definition of `VERSION', or define `VERSION' before running the   simulation.

# Others:


the `patten` argument of a pwl source needs parenthesis, which T-spice won't do on normal export:
e.g.
Source_v_pwl_1 (gnd inp) Source_v_pwl pattern="0 log_VCC simtime 0.5*log_VCC"




^ note that the 'view' column in the software is showing the "view name" not the view type. The real view type is hiding off to the right.


Note: Does "Use spectre models and includes" mandate built in models of Spectre? And how does it work with .l type spice decks?

For spectre, the ahdl import needs to look like this:
ahdl_include "SB_saradc8_radixN.HDL/comparator_latch.va"


Note that if you are passing a parameter to a SPICE primitive, it's model needs to have a user param to match that param. Otherwise it won't fill it in.


