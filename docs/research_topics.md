R&D topics in Silab:
- ALTAS RD53: 28nm redesign, tracking, planar sensor, 3D and LGAD sensor TCAD, BDAQ53.
- Belle VTX: obelix, monolithic, monopix, post-metalization redistribution layer, guard rings TCAD, capacitive coupling, BDAQ-monopix, multi-chip readout, trigger logic
- LFmonopix
- EDET, depfets, DMC


What am I interested in:

chip-level design automation and optimization
GPPLs
circuit simulation, mainly analog
chip-level architecture
teaching and education
open source PDKs
machine config and system admin

Oppourtunities:

Top down:
- Figure of Merit, literature review, diagrams, chip architecture and optimization
- IWORID (apr 12 deadline, jul 1 pres)
- Working with Andreas
- Obelix VTX, etc

Bottom up:
- Substrate development/usage
- DPG presentation (mar 4 pres)

- industry colab
- MPG EDET (DMC)
- Python wrapper around design flow (from TCAD sensor, analog signal chain, and digital gates)
- Allpix + Tangerine projects

Both:
- teaching Electronics/signal proc. course (posting online?), w/ Jochen and Hans (organize in February)


Some oppourtunity in Paris?



HLL, DMC,

- substrate is the best suited tool for bottum up generation
- rust is complicated, but perhaps the best language for EDA tool design. Python code is slow, has bad package management, gets abandonded often, and 
- ATLAS RD53 is mature, and the Belle/monolithic groups are converging.
- working in PDKs that are 

- the best option is simply to work on something that my group is doing, and finish the PhD relatively quickly
- and i have to allow for the fact that I might want to move somewhere else before finishing
- plus, if I do something that directly helps the group, then I will sort of be acting like a consultant anyways and learning.

- in the short term, prepare something for:
    - DPG - March 4
    - IWORID - april 12 submit, jul 1
    - FSIC 2024 0 jun 19

gotta be DMC/HLL, or TJmonopix/obelix tapeout, or something with snow's guard rings and pixel sharing
    but layout faculties aren't ready in Substrate
    running a testbench, w/ substrate

run a spice simulation from actual design PDK, but in the short term just run against Sky130 PDK. At most borrow the netlist a TJ monopix circuit

ngspice now supports verilog -> verilator cosimulation

I'm visiting the DMC group on the 20th, and meeting with Hans. So I should have something by then.

The thing I'm going to submit to Iworid should also be about "methodology", and naturally my FSIC presentation should be the same.

The only thread that really links all of these together, is the idea of generating and testbenching and optimizing a ring-oscillator PLL. Let's get started.

# People have written many, many implementations of generator frameworks:
BAG, BAG opendb_template, xbase, gdspy, gdstk, laygo2, hdl21/layout21
klayout (python and ruby scripting)
PDKmaster
vpp/cppsim
stratus/Cairo/corialis at LIP6
ALIGN, MAGICAL, MUNEDA Wicked
GDS factory

verilog-A has superceded the need for actual simulation in something like Cppsim, but open source simulators still don't implement Verilog-A.
Nevertheless, OpenVAF has brought the device modeling aspect of VAMS to ngspice.
Perhaps the same can happen for behavioral modeling
In the mean-time, one should be able to get by with just verilog modeling

Since the past couple ngspice releases, we now have a VerilogA compact model support in ngspice, plus 

Complexity in generator software is inherit, and trying to simplify in the wrong way will create an unmaintainable mess

It's obvious that we need a language with strong typing, with good data modeling, fast execution, and metagprogramming to model the problem domain. Rust is complicated, but less so than C++, and gives a well contained set of syntax to use as the basis for our embedded DSL.



There are several keys tools and formats which shouldn't be replaced, and we should respect their input data format.
- SPICE/ngspice/spectre (PDK device spice decks are evaluated against a specific simulator, although )
- LVS and DRC (heavily PDK specific)
- Pcells? (just wrap their static output?

