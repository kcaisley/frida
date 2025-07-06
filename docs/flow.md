-A collection of cell netlists is my starting point, where transistor dimensions are relative to the PDK minimum dimensions and passives have a design value (or also dimension)
- To build a circuit, devices can be 'strength scaled' to create different block variations, and then circuit blocks can be heirarchically arranged to build different systems.
- It's tempting to express each of these variations programmatically, and then generate netlists, however since each netlist variations corresponds to a rather long simulation, and since often multiple test cases are saved themselves as design collateral, it better if we just manually maintain different spice netlists for each base cell, and for the different permutations of the heirachy which one wants to utilize.
- Also, even though our netlists are not PDK specific, they are still trivially simulatable against PDKs of our choice, because we can use a include and mapping file.
    - The above strategy might also work for LVS and PEX runs, but I am concerned that it might not work for final import into Cadence. In this case, we certainly neet some form of skill mapping.
    - In this case, it seems that some form of Symbol library combined annotations in the netlist could help with viewing this.


In terms of the schematic-aware-layout, it's important to know that raw GDS files are not aware of the concept of net names. Pins however do exist, and one can probe connectivity in Klayout. Therefore

This means that our netlists would benefit from containing the following:
- Pin names and directions (for schematic visualization)
- descriptive device names? (to actually know what they are?)
- Using device order



Visualizing the schematic is best done with the Concept engineering tool starvision, however the tool file-import-spice in cadence also has an analog flag which is apparently okay?


The Starvisision suite would be best for visualizing my netlists, simulation results, and probing and navigating the design.

The next best thing could be if I either add ascii art to my netlists, or even have an automatic netlist to SVG visualizer, then I could then simply navigate files in vscode, and simply see the schematic visualized. And jumping to a block could be done by simply 'jumping to definition' in the code editor (based on what I see in the visual)

One advantage of this, either with the netlist, or the static SVG, is that if I'm working on a remote server, I wouldn't be depedent on X11 forwarding, etc. Also, on github, with the ASCII the architecture of the netlist would be visible simultaneously (rather than relying on a runtime).

ciccreator could be a great tool to translate the schematic, plus some extra info, to a layout, but the issue I'm currently facing in using it are:
- Primitives transitors appear to be limited to a specific unit area? Perhaps I can scale this somehow?
    - With the previous point, it doesn't appear that the ascii primitive are anything other than fixed? Is Multiplicity my only option
- Expressing capacitor layouts appears to be relatively complicated, and I'm concerned I'd need to write my own C++?
- The output to skill layout and schematic is nice, but this isn't that hard to replicate, and I could also just use the stream in netlist in features of Cadence. And when I give netlists to Caeleste they could do the equivalent in their flow.


- With that being said, I think the following flow could be great:


inv1
- netlist.sp (including pin directions, )
- schematic.svg (created by running a python -m command?)
- tb.sp (simulation bench, which instatiates and simulates the netlist. Includes a single header which 
            going from tb.sp to the sim.dir should use a python -m run script, 
- /sim -> /temp/inv1/tsmc65 and tsmc28 (symlink to simulation directories, with raw data and also figures? Python command)

Actually organizing by cell doesn't make a lot of sense. Instead, organize by file type for the following reasons:
- SPICE finds components by file name, and so if they're in other files it's easiest to include if the file name matches the cell.
- The files which need to be included vs excluded from the src are based on type, not cell.
- One way to think about it: the pipeline can follow a one stage per cell type of perspective
- One exception to this might be the Test benches. Perhaps these should be in the same directory, to enable easy navigation?

I can still use code to help me in building netlists, but these shouldn't be something a user needs to rerun upon cloning my repo. They are simply used during my construction of the design library.

Some ideas are:
- create different sizing variations of a cell in a new netlist
- to parse in and out of virtuoso's schematics .oa files (via skill and cdlout)
- to build up heirachy of my netlists (which allows them to be super specific, and not even needing to do netlist parsing, only writing which is easier)
- 

NOTE: I can also use LLMs to generate variations of cells, perhaps. 


Simulation is I will start generating out of build data. The images and simulation should be able to repoduced entirely from code, if I rerun the pipeline, but I don't want to do this very often, if not at all.

In this case, I should create a helper script which assists me in copying around simulation data which I might produce on my laptop vs on the server. I will essentially use `rsync` to copy around the collateral.


July 2:

Replacement for flow:

netlists with annotations: schematic replacement (still need a viewer for this?)
CACE: ade explorer style testbenching, test runner, meeting specs (does it parse raw files well?)
RAW files visualization: gaw, spicewave, 
spice simulation: ngspice + openvaf
klayout + gdsfactory: layout pcells, plus layout engine
analog on top cosim: ngspice + verilator integration (see Carsten wulff's example)
DRC / LVS: stay with foundary Calibre / PVS / Assura decks a long as possible (alternatives are netgen, or DRC / LVS in klayout, or in magic?)
RCX / PEX: stay with foundary decks as long as possible, but fastercap, magic, or klayout-pex (which also offers others as back ends, are good)


yosys: synthesis suite
openroad + openlane runscripts: rtl to gds and run scripts
verilator: simulation
cocotb: verification / digital testbenching
wavefrom viewer: icarus verilog / gtkwave
digital on top cosim: spicebind -> any vpi compatible simulator
libretto or charlib: standard cell characterization, not necessary for existing PDKs


Questions for Tomek:
Is verilator VPI compatible for this spicebind application

Questions for Andrew:
Flowscript vs librelane differences and assumptions?




# Tuesday notes:
# ihp 130 verilog A models

.va code compiled with openVAF
compile with openvaf file.va
then load with open osdi interface

resisotr R3_CMC model, for polysilicon rppd 1u/10u

diode are currently using the built in SPICE model
proposal is to replace it with CMC_diode model

- SG13G2 varicap i.e. varactor model, implemented as a macro model. (But in spice or?)
- Q: to what degree does mismatch rely on the model, vs the spice deck?


# Standard cell characterization:
- liberty a NLDM (non linearity delay mode), given input slew rate and output loading, list the delay in a lookup-table
- Based on the truth table in verilog, find the right input combination to create an output transition
- Generate a test harness next: comtinational circuits are easy, sequential circuits have a complex testbench, even for just 2 states
- liberty file and python automatic generation of slew rate.
- PDK information can either be stored in a central .yaml file, or in each individual liberty file
- automatic cell recognition not yet supported, and neither is verilog output
- liberty files also contain a dimensinos for power, voltage, temperature and and output dimension of power consumption


# Llbretto
- delay and energy! function of input slope and output loading
- netlist of cell is automatically generated
- Ngspice backend has more than 100x difference in run time, vs tools like Hspice, but same simulation accuracy

# frigate, panamax, and chippalooza
- doing something using cadence tools?
- lvds cells!

# sub-threshold

- current cells are 100x commercial 0.8V logic, with compaction (custom layout, not standard cells) one can reach 50x

# VACASK:
- so many notes, but they support different

# Open EMS:
full field solver openems
excite port with a gaussian pulse, for a widebank 

