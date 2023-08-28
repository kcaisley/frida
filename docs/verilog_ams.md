# Verilog-A

Verilog-A is the analog component of Verilog-AMS, and can be understood by the SPICE kernel in a AMS simulator.


One important thing to know, is that in Virtuoso, if you was a graphical representation of your system, you need to have “SPICE on top”, with the Verilog-A as only “leaf modules.” I think, as least?

`<+` contribution operators assign (and only assign) values/relations to branch potentials or flows.

starting with ` means something is a compiler directive


functions with $ start are not synthesizable?

base units of time, and the time precision are specified like this:

```
`timescale 1s / 1ns
```

It isn't mandatory to use a base of 1 second, but since Verilog-AMS allows SI uni suffixes, we normally stick to this.
The second unit is used for rounding/quantization of the time
And for the output of the $realtime function


Wires:
Must be driven, continous or discrete, continous has a 'discipline' like a voltage/current
'Nets' are wires that move between modules. They can be implicitely created, or explicitely.
Can also be named 'tri' for tristate, and this syntax should just be used to explain that it's a wire that probably can have bus contentions or high-impedance outputs.


Spectre-AMS Course -> about the AMS Designer Virtuoso Use Model (AVUM)

Discipline Resolution and signals crossing A/D domain boundaries
Unified Netlister (UNL) in Virtuoso ADE Explorer w/ Xrun executible
AMSD Flex option allows mixing and matching digital and analog kernels

HED - Heirarchy Editor

AMS Designer simulator can be invoked from either Virtuoso/Spectre or Xcelium

Using the Spectre/Virtuoso option:
Spectre is highly accurate for small designs,APS is for larger designers
Support for Verilog, Verilog-AMS, ANSI-C/C++, and SV Design and Assertion (but no Real number modeling)

SystemVerilog and Verilog-AMS both have support for real number modeling (called real/wreal, respectively). This is faster, but less performant that SPICE or more complex Verilog-AMS models, because real/wreal models don't require 'solvers'. The IO behavior is simply defined by a function, and is evaluted with simple discrete event solver. Therefor it does not behave well for models that involve feedback.

Unified/Commond Power Format (https://www.techdesignforums.com/practice/guides/unified-power-format-upf/)


Spectre AMS connect connects the uniform timestep SPICE/Spectre Simulator with an event based Xcelium simulator.

Spectre AMS Simulator/Design is not just an interprocess communication between two separate kernels, but instead a pair of tightly coupled enginge which access a shared memory storing the state of the circuit during simulation.


Two ways to run AMS Design/Simulator:
1) AVUM for GUI
2) AXUM for command line

In the Virtuoso USe model, config views are used to select the cellview for each cell.

normal: ac, dc, noise sp, stb, xf, tran
hb:     ac, noise, sp, stb, xf
p:	ac, noise, sp, ss, stb, xf
qp:	ac, noise, sp, ss, xf

the hb, p, and qp analysis flavors aren't available in AMS Designer

## Digital Simulation

modelsim
questa
nc-sim
xcelium (most modern from Cadence?)

some are use by fpga
cocotb used questa with bdaq

vivado uses modelsim?

synonpsys uses another?

## Hierarchical Structures

Hierarchical structures are a Verilog concept that allow interconnection of modules at different levels of hierarchy. This is essentially the same function as the netlist but defined within a Verilog-A module.

In this phase-locked loop example, all modules and the top level module interconnecting them are in the same file. However this isn't necessary and it is possible to have each Verilog-A module in its own file. In this case a .LOAD statement must be included in the netlist to load all Verilog-A module accessed in the instance statements

#### The main two uses for a AMS language are simulation and synthesis

But the latter isn't really possible with Verilog-AMS. The prior though can be broken down:

1. To model components: Unlike traditional SPICE simulation libraries which only support a limited number of devices, model SPICE simulators which support Verilog-AMS can describe 
   1. Basic devices (R, L, C)
   2. Compact models like Gummel-Poon BJT, VBIC BJT, Mextram BJT, MOS3, BSIM3+4, and EKV MOS. BSIM4 is written in a bunch of C files. BSIM-Bulk, the newest version of BSIM is instead a single Verilog-A model.
   3. Functional blocks like ADCs, de/modulators, samplers, filters, etc
   4. Multi-disciplinary components such as sensors, actuators, transducers, etc.
   5. Logic components
   6. Test bench components like sources and monitors?
2. To create testbenches: testbench devices will often not be ideal, so this is perfect for Verilog-A
3. To accelerate simulation: replacing non-examined blocks in each simulation with a more abstract representation. In end, this is part of the testbench, as the  
4. To verify mixed-signal simulation
5. To support the top-down design process
