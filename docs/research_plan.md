
# Research
* Archeology: Understanding previous research efforts. How well did they perform?
* Benchmarking: Framework for comparing via a figure-of-merit. Accounting for pitch, power, area, resolution, Compare previous designs.
* Mathematical Analysis: What is an optimal (highest FOM) signal processing system, given a pulse input signal, desired extracted output data, certain process, and engineering constraints (stuff outside FOM).
* Apply this knowledge to find a unexplored gap in designs, and postulate what 

# Service Work
* IT infrastructure: mostly done, just needing documentation and clean up
* Educational material: Circuit design, or signal processing for pixel chips. A good class would probably be using HDL21 to draw visual schematics, and then create a basic signal processing chain. Perhaps compile against SKY130 technology. This wouldn't require any licenses, or special software.

# Plan for the near future
Before making any plans for the near future, I need to understand what some good time frame area. One good one is like the 24th of July, when I return to Bonn. This would be a good time during which I want to show what I've been working on. What can I accomplish in this time? How about:

* Focus only on a ring-osc VCO design. I want a basic layout, and transient simulations.
* Using HDL21 to generate various sizes of VCOs. Compile them against TSMC 28nm.
* I don't quite fully understand the flow. I can't use layout pcells, so I'll need to create my own. Either generate a collection of static GDS layouts, which can be combined, or For transistor models, I know I'll need to simply send out a Spectre netlist.
    * How do I trigger a LVS and DRC and PEX run from this?
    * 

Can I create an inverter with ideal transistors, compile it to a SKY130 version, then send to ngspice for sim? Then plot?
Then compile it to a 28nm version, and then send it to cadence for simulation? This is my job tonight.

Let's just focus on Spice class design and simulation. This means we'll just use HDL21.