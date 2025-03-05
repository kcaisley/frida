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


9. The capacitor model is called `capacitor` and must be lower cased, else you get this error:

```
ERROR (SFE-23): "SB_saradc8_radixN.scs" 580: The instance `Capacitor_3' is referencing an undefined model or subcircuit, `Capacitor'. Either
    include the file containing the definition of `Capacitor', or define `Capacitor' before running the simulation.
```


10. The `save` statements at the end of the file use `<>` which must be escaped:

**MANUAL FIX: adding in parsing script to update**

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

11. the analog_include needs the path, and need quotes

**MANUAL FIX: adding in parsing script to update**

13. Fix: Updated the Spectre subsection of the .oa model to netlist with lowercase `capacitor` syntax.

```
WARNING (SFE-30): "SB_saradc8_radixN.scs" 583: Parameter `C', specified for primitive `capacitor', has been ignored because it is an invalid instance parameter. Specify a valid instance parameter and rerun the simulation. Type        `spectre -h capacitor' to get more information on valid instance parameters.
```

14. Error found by spectre in `PAGEFRAME', during circuit read-in.
    ERROR (SFE-23): "SB_saradc8_radixN.scs" 34: The instance `VERSION_1' is referencing an undefined model or subcircuit, `VERSION'. Either include the file containing the definition of `VERSION', or define `VERSION' before running the   simulation.

**Script fix: only write `if not line.startswith('VERSION'):`**

15. Note that spectre models are case sensitive, and the model definitions like `cap`, `res`, and `vsource` are needed to call the right backends in spectre.

16. The `-format nutascii` option in Spectre give the output most similar to T-spice's log format. Perhaps the 

17. Note that by default, Spectre will read new netlists in the SPICE format, so you don't need to specify it for PDK netlists. And inversely, if you are specifying your own subcircuits in new files in Spectre language, then you need to add `simulator lang=spectre`.

18. Output waveforms should have transition delays specfied.

```
Warning from spectre during AHDL read-in.
WARNING (VACOMP-1115): "vstepper.va", line 26: The compiler found no rise and fall times for the transition and no default_transition directive. Assuming ideal transition.
```

Fix: I supplied a 1ns value to transition() but 2nd argument is actually the propagation delay. So I corrected it via `V(out) <+ transition(vout, td, trisefall);`

19. From reading designer's guide to Spectre, and seeing some warnings, it looks like the top level ground should be set as simply a `0` node. Don't use `gnd!`.

```
V5 (syncn gnd!) vsource 
V6 (syncp gnd!) vsource 
V7 (clockn gnd!) vsource
V8 (clockp gnd!) vsource
```

FIX: Just changed the schematic to use a net labeled `0` to fix this.

20. Use the +preset=[mx, lx, cx, etc] mode to enable Spectre X which is the newest revision of Spectre. It might disable multithreading if design is too small.
Simulation string now looks like `spectre SB_saradc8_radixN.scs -format psfascii +preset=mx`.

21. 