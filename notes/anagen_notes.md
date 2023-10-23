unix philosophy,

design and verification is agnostic to how

are test signal sources capable of generating input and loading sources for testbench? How is this


Is all of the analysis done by simply handing the design off to a simulator? 

Can exchange between spice netlists, verilogA/D, and python models?

methodology entities: thesdk, spice, rtl, ads, plot_format


principle of simulation:
	- self.test. A method to verify a device in a vacuum. Can do in python, RTL, spice, etc


TheSydekick is designed to support simulations
BAG is designed to provide software inferface for generating circuits

Are your layouts auto-generated with BAG2 Xbase engine?

ADS is for keysight?


Questions for BAG:

Can you use the generator libraries provided by BAG2? How many are there compared to BAG3?


2nd presentor:
- Expert Design Plan Language (EDPL): accessing and mod designs, TB creation, running simulations, analysis of results, use symbolic expressions and lookup tables
- Sizing functions e.g. x13.size(op, id=300ma, vt=120mv). Queries a lookup table, and then provides sizes for the devices based on this. More conv. than specifying sizes. 


Programs:
Laygo2
Xbase+Bag2
Xbase+Bag3
Hdl21+VLSIR+Layout21
GDS Factory
Gdstk/Gdspy
substrate2
TheSyDeKick
PDKMaster
Chisel
OpenVAF


Corporate: Anagen, PDGen, Mosaic orchestrator, Frauhaufter, Bosch EPDL,  


ML optimization:

there's not one best design, as there are multiple objectives. This is a parento front problem.
We use evolutinary algorithms, which is a stochastic optimization algorithm
This is sample inefficient, and simulation has high sample cost
Gaussian processes vs baysian optimization
Baysian isn't true multi object model -> it compresses to a single point

evalution methods used: constraint violation (how far away violating the constraints), alternative hypervolume

GDE3, MODEBI, MACE, EBO (evolutional baysian optimization)
3 of these use machine learning models (surrogate only)

GDE3 is common standard, MACE is another publication,o

Analog layout ML optimization:
Slicing: floorplan from repetiviely currting the floorplan in horizontal and vertical slices (normalized polish expression)
non slidcing: The opposite. Implemented by non-sequeunce pair algorithm

Key optimization algorithms:
Simulated annealing: stochastic optimization, using hill-climibing approach. Non-zero probability of moving from one local minim, to another, better one. Hopefully global.
Reinforcement learning: agent interacts with environment, and gets reward. Super sample inefficient.
evolutionary algorithm
integer linear programming
Graph neural netowork: a graph placement methodology for fast chip design. Mirhoseini, et al. 2021.

Analog routing ML optimization:
Most common/basic method: A* search, pathfinding algorithm.*
Pattern routing: predefine patterns of wiring. L-shaped (one bend) Z-shaped (2 bend)
To space apart, estimate congestion.
Then use rectilinear steiner minimum tree.


Papers: Liao 2019, 2020: Global and local routing algorithms, using Deep neural networks

In conclusion: stochastic methods like SA for floorplans, graph pathfinding like A-star search for routing


