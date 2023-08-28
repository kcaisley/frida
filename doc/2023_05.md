# Journal

optimization, generator-based design, front end sensors/signal processing, open source, tools, modeling

somewhere in the intersection of those interests is a specific problem, which pushes the boundary of human knowledge, which is small enough for me to be productive in, and is non-competitive enough for me to actually have the time to learn.



#### Thesis Statement

Physics-aware generator-based workflows for pixel detector design are novel, feasible, and useful.

hmm... Maybe I want to emphasize better: Mechanistic modeling, top-down design, top-level system modeling, FOM design, and optimization framework for specific applications.



This domain would allow me to:

* work primarily with software
* work alongside designers who are more experienced and/or focused than me, to capture their knowledge
* perhaps visit/embed at Berkeley, CERN, and other institutions in Italy, like Rivetti's group, for example
* learn about a wide range of detector design, without competing directly with others
* Perhaps even touch/connect to TCAD?
* Focus on higher level automation and optimization, as others can help build the individual building blocks, and I can just help them parameterize it.
* Liberates me from having to innovate in software, methodology, circuit arch, and circuit design all simultaneously. I can focus on higher level design.
* Allows me to work almost as an archaeologist, re-documenting and understanding past designs.



The danger here, is that this work borders on 'not really physics'. And so what I would like to do, is study the physics more deeply, and create an optimization framework which is very 'physics-aware'. I want to front-load the physics work, not backload it in testing. This will mean I will need to study the physics of detectors, and be able to create accurate models of how they interact to properly.



So let's try it again: My thesis introduces:

* System-level application-specific optimization for pixel detectors:

  * Physics based framework for calculating ideal desired specs
    * Using knowledge of physics to infer specs needed to not bottleneck measurement
      * what pitch is ideal? What sampling rate is needed? Which 
    * Inspired by ADC, TDC, and image sensor specs to give a FOM, to know the horizon?
    * Also built in part by reviewing existing designs, to understand/model physical trade-offs

  * System level model/optimization routine for picking architecture with approximate block specs
    * Data readout modeling for calculating if block level modeling is possible
    * Area consumption calculation, to know what 
  * 

* FOM
* System model/transfer function (requires generators for implementation and regression?)
* Optimization routine (requires FOM for objective function)
* Generators for subblocks (required for optimization)





# Conversation about circuit design software w/ Tomek

simulation	 xelicum  (c v 
formal verificaiton

cadence genus
synopysys design compiso
mentor

scan chain insertion, DFT
vector compression

tempus static timing analysis (singoff/QRC), 
voltus (voltage drop analysis)

1. stack at fold, push pattern expect ebahvior,

2. transient test, push the pattern, epxect some output,

3. iddq test no leakage test
4. Schmot plot (not production, just validation test)

produciont you 

validation is just with test unit, production is at mast producction.

like thermal cycles, for validation only

wafer test to make sure it works, then passing 

bridging test






# 45nm GPDK RAK PLL

I'm trying to figure out how to configure the project.cshrc script located at:

`pll_verification_ws_v1.0_001/WORK/pll_zambezi45/project.cshrc`

I thought originally that I needed to change the first line, but I think the following line is setting the variable to the directory two above the current one:

`setenv PROJECT `cd ../../ ; pwd``

When I run this though, it doesn't work, even in csh, with 'csh -l' option..

I've made some progress, I figured out that I was missing the 'endif' at the end of the bit if statement.

The next thing, is why is this endif statement not evaluating as true? Where is the CDSHOMe defined normally?

The four chips I'm aware the group is working on are:
RD53
Obelix
Cordia
DMC

Additionally, it seems like there might be some work to do with a chip for our local detector

the main 65nm startup script is /kcaisley/cadence/dmc65/run_tsmc65.sh but this just calls /cadence/local/bin/tsmc_crn65lp_1.7a_rd53 pretty much.

I think that the major problem I'm having is that the startup script provided doesn't include everything necessary for starting Cadence.

Let's examine one of the startup scripts for the 65nm process.

### Mon Jun 13
Hans sent me a bunch of instructions, but I'm confused on how he set these up.

at the top level, hans is missing config, readme, and release, 





# Projects in ASICLab (Wed June 22 meeting)
* RD53: ATLAS inner tracker
	* Data merger issue
* OBELIX/VTX
	* Marco: RDL/Passivation to connect resistors on the top, costs $4600
	* Design of redistribution
	* Creation of a DRC and LVS ruleset for Calibre
* Cordia
	* Working on report for ADC
	* Filter/SE->Diff converter arriving in mid-July
* DMC
	* Verification taken over by MPI Munich / HRL
		* They also invented Fully depleted CMOS and DEPFET concept
* AIDA/28nm
* Software/Hardware/PDK
	* Meeting with Macro, and walk him through the design flow
	* Licenses are Hans's work, we get Cadence ones directly from Europractice
* AOI







# Literature/research review plan

I want to balance 'productivity' with learning while I start to put together my understanding of PLLs. I need to stay realistic though, and give myself tasks which are possible for me to do.

Reading and synthesizing all the information in these papers is going to be an aimless pursuit unless I set clear goals for what I want to get from it. I will start by simply reading the Razavi paper, and then building on it as a baseline.

The approach is simple. Read the razavi paper, read the paper on the PLL







## 29 September

the simulation engine that works with my behavioral models should match that of my transistor level models Hence this is why Spectre AMS is necessary. i allows me to mix and match between Compact SPICE transistor modeling, analog behavioral, and Digital verilog.

each transistor level block, should have a corresponding with behavior model. Each component of the system, low test bench will instantiate a different mixture of behavioral and extracted parasitic netlists in order to verify the system.

no testbenching, stimuli, or post processing code, lives in the same database as the design library.


I can do my 65nm designs in xbase, as performance isn't cutting edge, and then I can more easily port to 28nm.

starting tomorrow, what I need to be doing is understanding how to write verilog behavioral A models, and how I can then simulate them.

Don't spend much (or any) time post processing the waveforms with ViVa or the calculator, as I will be doing that in Python.





## 19 September:

I really want to apply for this competition: https://github.com/sscs-ose/sscs-ose-code-a-chip.github.io

Its submission deadline is November 21, which would give me a perfect outlet for completing a functioning Jupyter notebook in a reasonable amount of time. I've already been here for 133 days, and I feel as though I haven't accomplished anything. For now though, don't tell Hans about this conference.

I want to learn how to use BAG, because OpenFASOC isn't really meant to work with analog chip design. The issue is that BAG3 doesn't support open source tools, and that access for the necessary OpenAccess library is apparently very difficult to get anyways.

I want to use BAG3, as BAG2 is not going to be further developed. My main question then is what are the major differences between the two? I'm meeting with Thomas tomorrow, and he seems to understand the better the status of BAG.

So what if I did the following.... built a generator which is able to produce a functioning VCO layout.. or even PLL, and do it in a way that uses the toolchain of BAG3? If I accomplished this, I would be the first person to successfully use BAG3 outside of Berkeley. Other papers, few of which exist, have used BAG2 only.

The issue now, is that I'm not sure if I can really build a functioning tool chain with BAG3. It doesn't support open source tools yet, and getting it to even work with Cadence seems nigh impossible for those outside Berkeley/BlueCheetah. I should confirm this by reading papers, tomorrow, of course. I think I can get through a lot of material by the time I meet with Thomas Parry at 3pm.

One thing I'm realizing though is that a lot of the design process doesn't really require me to have a function BAG installation. XBase seems like it is very tied to BAG, but I think LayGO2 is less BAG-centric? I should really check with JD Han to figure out how I'm expected to produce a layout in 65nm if I don't have this special Cadence OpenAccess library. Perhaps I can w

Mirjana is a member of the committee which decides the winners of the code-a-chip competition, and so if I were to develop a notebook with her guidance, then there is a *very* good chance of being accepted.

Another note, I should consider giving a group presentation on Sep 29th, because I told Hans that I would. Maybe I should break this promise though. I should explain to Hans that understanding the status of all this open source code has taken significantly more time than I anticipated. Explain that I've made connections with two important people though!

If I don't use BAG, then how do I work with the schematics needed to compare against LayGO layouts during LVS?

If I want to design a process portable generator, do I target the layout constraints of a small-fill factor 28nm design, and then expect it to scale to a 65nm, or even 130nm process? I think this makes more sense, as there are less degrees of freedom in 28nm.

Can this tool (LayGO2) be used in isolation, without BAG?  I think it can!

One thing that is amazing about this, is that Laygo is written entirely in Python, and so I shouldn't have any huge problems getting it to run. No compilation required, etc. It's a 1-way path for generation.

Also, much of the design work 'back of the envelope work' can be done in Python scripts, without any circuit simulation at all. But, then, once I get to circuit simulation, I wonder if I am able to run parasitic extraction with Magic on open source Tools on 65nm? If think seems to work well, then I think I can trust it enough to do large cell design without re-running a DRC/LVS ruleset in Calibrew. To be double sure, I can simply run a final Parasitic extraction and DRC and LVS test against Cadence.

There's also no reason why my schematics would necessarily need to be be designed in cadence source tools, right? If I am looking for process portability though, I think that I need to use something like BAG, where I am am able to make schematic and test bench generators.

So one question is: If I'm not using BAG... how do I achieve process portability in my schematics, such that I can quickly compare them against laygo? I think that the basic Laygo workflow uses hand-crafted primitives, which aren't process agnostic. On the other hand, I think that Lay

I can slowly replace every part of the 65nm workflow in Cadence, with equivalents in 65nm technology.

#### BAG Notes:

I think the functionality is primarily good for the Analog Chip Bottom, where the SAR ADC, the Bandgap references, the Analog Multiplexer, and monitor ADCs, the Calibration Injection Voltages, the Serdes, and the CDR and TX/RX Circuits live. This is where documentation, reusability, comprehension, and testability are much, much more important that cutting edge performance.

Generators are also best suited for instances where you will need to do many different iterations, in possilbly different 

BAG3 is a major upgrade, as it reworks the way layouts are generated in the tool. There is no AnalogBase/DigitalBase constructs anymore, just MOSBase.

As long as devices share the same 'row' information, you can tile NMOs, PMOS, and TAPs right next to each other.

Don't specify the width of each wire, have 'wire classes' which have preset widths.

MOSBase just places the drawn transistors, and isn't necessarily DRC clean. MOSBase Wrapper then comes back and fill in the dummy devices, extension regions, and boundaries.

In the YAML file, we have to define the properties of each row. It's more complicated in BAG3.

The layouts may only have one type of tile, or you may have a more complicated multi-tile type layout.

In BAG2 AnalogBase, you only have access to M3 and 4, (maybe more in Digital Base). But in BAG3



Zhaokai Liu showed a BAG3 repository example on Github, but it's a private repo right now, and we can't see it.

Bulk contacts are completed with TAP devices in BAG3.

Different length devices are implemented with stacking devices, to increase effective channel length.

To place transistors, you first specify the tile you are placing in, and then use XY coordinate (e.g.) within the tile. It defaults to position 0 for X and Y.

BAG2 only supports ADEXL. BAG3 doesn't support any ADE package, Assembler, XL, or otherwise. Design variables are returned, but Stimuli and Data post processing must be done in Python, as we are just directly  calling Spectre.

Notice how all the BAG developers are also using BAG to build real circuits.

BAG3 includes BAG2 

Behavioral model of circuits are completed

Marco in Finland

Infineon guys also putting money into it

Mattias is from Klayout














## ? October

Perhaps I have been overly stressing about dreaming big in my PhD. Marco pointed out to me today that Kostas, who was very successful, was assigned a small power of the monolithic chip, but ended up taking over a large portion of the design work once he had demonstrate that he was so prolific.

Some students fail to dream big, and see the full picture of their work. I don't have that issues - some days all I do is drea. If I instead want to be prolific, what I need to do is focus on the task on hand, and simply <b>produce</b> each day.

This is easier to wish for, than it is to implement though... how do I know what can be considered as 'work product'? I actually really do like the idea of, for example, solving one textbook problem per day from my analog circuit textbooks. Is this a good use of my time?

Also, how do I fit in the other things I want to do with my time, like socializing, running, rock climbing, reading, learning languages, travel, and spending time with Lise? This is tricky. One key thing to keep in mind, though, is that there is no difference between this phase of my life, and the rest of it. The habits I build for how I spend my time today will last me for a lifetime.





## 2 October

**Imagine**



One of the disadvantages of a university research group is that the PhD students are continuously coming in an out of the door, and they leave once they are becoming quite qualified.



A small team like this will benefit most, if they can all focus on one central process... but this is tricky as each student will want to publish something that is unique.



Perhaps there is a workflow for groups which can solve this issue, where the professor takes a more hands on approach to managing their students. Making sure each of them understands what they are working on, and that they have some common background.



One should make it such that PhD students can spend as much of their day as necessary working. Part of this should be a guaranteed time during the day where paper reading is completed.



But give students the leeway to suggest improvements to the process! They need to feel ownership.



Most PhD students typically feel overwhelmed by the fact that they are working on a project all alone.



Papers/Publications can be organized into a repository of: ideas, in progress, in writing, published, etc!





**Mixed Signal, Top Down, Design and Verification**



Systems should be modeled and simulated before that can be built. Behavioral modeling of a system requires a language meant for hardware description. This is where Verilog-AMS comes in. Also, these models should be parametric as they will likely be later updated. Also, a good MS-HDL must be able to be synthesized into a hardware implementation, and also should be able to be co-simulated alongside a transistor level netlist.



The simulator that runs this model should not be something home spun. This is where NGSpice or Spectre comes in. It must be trusted, and should be able to be used for cosimulation with spice netlists.





However, testbench control and data analysis also needs to be separate. This is because programmatic languages are better suited for actions like plotting.

















This is the case for working on a unified,  monolithically integrated, generated PHY interface for pixel detectors, 

1. the research group i am a part of is responsible for producing the three of the most important pixel detector ASIC chipsets in the world, and so it would be madness to try and focus on imaging systems, or systems for XRays. Just like the systems below, I should focus on *massive* particle *detection*
   1. RD53 (ATLAS and CMS)
   2. DepFET ASM/Switcher/DHPT chipset (Belle [and EDET!])
   3. LFmonopix/TJmonopix/Obelix/MALTA (Belle outer PDX, ALICE)
2. On the chips that we haven't completely designed, like RD53, we were in charge of most of the top level integration and the PHY. The AFE wasn't our responsibilty in this case.
3. I don't enjoy full digital design, and the digital cores aren't very interesting or specialized, as the HEP application doesn't change design much. 
4. Analog design for the front end is very competative, and I don't have the skill to compete well with Amanda and all.
5. Alternative, new analog circuit features are not something I'm able to dream up well right now.
6. People aren't that interested in the implementation details of the data readout, but our group specializes in this, and I would have little competition. 
7. We also have the corresponding chip testing infrastructure. Intimate knowledge of the BDAQ system is super useful when deciding how to arhitecture the next generation Readout.
8. Working on a set of 28nm and 65nm SERDES PHY macros gives me a clear set of engineering constraits, and plenty of previous examples to base my design on, lots of papers, and a clear source of funding for my design.
9. PHY cells are perfect for design automation, because there is high likelyhood of parallelization, and different variations. In light of the funding that Jochen has, I think there's a good likelyhood that I can use funding from this (as PCELLs were one of the goals)

### Next Steps:

* figure out what the PHY infrastructure looks like on DepFET, RD53B, Belle PXD II, LFMonopix/TJMonopix/Malta
* on the above, also figure out what the data rate generation is, and how that 











## Open Source Circuit Design Tool Chain

Wherever possible, specific design instances should be produced with text-based generators, rather than manually created.

Make sure my flow follows a 'top-down design' patten. Then you just fill in the top-down design with flexible generators, in a process guided by and testing constantly against the top level design. *Most generators I see are very much bottom-up, but this isn't the way to proceed all the way to a finished chip.*

Therefore, we need one top simulator workflow where we can mix and match different types of analytic/symbolic (latter is more precise), stochastic, deterministic, measured data, emprical, SPICE/device, extracted TCAD, electromagnetic, and plug them into a simulator that can describe the behavior of the system that can be mixed-signal in nature. Can Verilog AMS handle this?

I want to be able to work entirely in VSCode / Jupyter Notebook when designing my chips. All I should need is my MacBook. My productive work output should exist entirely as a self contained code base, with nothing exterior. My design should be a stand alone generator script.

The high level design languages I work in should be compact enough for me to have them fit in-line with a JupyterNotebook.

I want all of my research & studying, however, to occur organically and manually: with paper and pencil, notebook, textbook, and printed journal articles.

Nearly every real-world chip design starts with some existing framework around you, with an existing mixture of Fab PDKs data, Verilog, Verilog-A, a PCB file, a wireline Touchstone file, a TCAD extracted model, Virtuoso Schematics, Virtuoso Layouts, GDS, netlists, etc. How can I work through incorporating these?

Start design at top level. Specify pin-accurate top level model, the important top level parameters and define the types of simulations, and the imp

The architecture I want to therefore follow is that every step of circuit creation should be specified by some 

## November 8th

I've had some realizations, which is that for building high level schematics, no SPICE netlist is needed for simulation.... Verilog-A can completely capture the connectivity.

Also, at a low level, the BSIM compact devices models these days are even represented by Verilog-AMS now (and not C code).

However, we still have a SPICE netlist dependency when we go to create a physical layout, as we need to run LVS, and this isn't possible unless there is a 1-1 correspondance between the devices in the layout and those in the netlist. Therefore, it's obvious that we need a workflow where we use locked-in Verilog-A models as the starting point for specifying our designs.

Also, BAG relys on having a schematic template from which to work from, so this an additional reason why a netlist/schematic is a necessary step to be produced during my design.

[Reading this article about](https://blog.ouseful.info/2018/08/07/an-easier-approach-to-electrical-circuit-diagram-generation-lcapy/) the package Lcapy, as listed below, we find that it doesn't fit our use case. We don't want to ever specify our circuits in a format that can't be fed into a SPICE class simulator. It's features of symbolic analysis are nice, but we need to restrict ourselves to Verilog-A for this work. 

CircuiTikz

[Lcapy](https://lcapy.readthedocs.io/en/latest/index.html): Lcapy is a Python package for linear circuit analysis. It uses SymPy for symbolic mathematics. The circuit is described using netlists, similar to SPICE, and can also manipulate continuous-time and discrete-time expressions. Has support for generating Latex & Jupyter Notebooks diagrams with CircuiTikz package.

[This article](https://blog.ouseful.info/2018/08/07/reproducible-diagram-generators-first-thoughts-on-electrical-circuit-diagrams/) by the same author above talks about the lower level circuiTikZ package, but this is just plain awful to work in. 

[This article on the PySpice](https://pyspice.fabrice-salvaire.fr/releases/v1.6/example-introduction.html) docs site discusses a couple different strategies for creating schematics. They mention SKiDL and Schemdraw, as options for schematic germination. This is important as PySpice doesn't generate netlists for you.

[Here are some advanced examples of analog simulation with PySpice.](https://github.com/PyLCARS/PySpiceExsamples/blob/master/MosfetTopologies/AnalogMOSFET_Tobologies.ipynb)

Also,  it mentions Pyterate and Pweave, which are simpler options to Jupyter notebook, that don't rely on a complicated XML format, which allows for source control.

[Pyterate](https://fabricesalvaire.github.io/Pyterate/) is a Sphinx add-on that can convert the output of a python file with in-line components into a .html, .pdf, or markdown file. It's not particularly interactive, but is lightweight, fast, and plaintext. It's written by author of PySpice.

[Pweave](https://mpastell.com/pweave/) appears to be similar to Pyterate, but it has some fancier features by using a real Jupyter kernel, like caching all code to make subsequent runs faster. It can actually even output to a .ipynb or sphinx document, along with .html, .pdf, or .md.

[SchemDraw](https://schemdraw.readthedocs.io/en/latest/index.html): Python package for producing high quality diagrams, and uses the backends of Matplotlib (great for use with Jupyter Notebook) or SVG (for use in LaTex -> PDF). It's cool, but again, you're specifying the design in a language written link this:

```python
with schemdraw.Drawing() as d:
    d += elm.Resistor().label('100KΩ')
    d += elm.Capacitor().down().label('0.1μF', loc='bottom')
    d += elm.Line().left()
    d += elm.Ground()
    d += elm.SourceV().up().label('10V')
```

This is super cool, but again, I really need to use Verilog-A and SPICE netlists as my "source of truth" when generating schematics.

Finally [SKiDL](https://github.com/devbisme/skidl), which lets you compactly describe the interconnection of electronic circuits and components. The resulting Python program performs electrical rules checking for common mistakes and outputs a full SPICE netlist.

![SKiDL + PyCircuit + Ngspice + matplotlib data flow.](https://raw.githubusercontent.com/devbisme/skidl/0d3cf9dca19a5fc4d58308d1872f1ed78363adfa/examples/spice-sim-intro/dataflow.png)

[Image Source](https://github.com/devbisme/skidl/blob/master/examples/spice-sim-intro/spice-sim-intro.ipynb)

Example code:

 ```python
 from skidl import *
 
 # Create part templates.
 q = Part("Device", "Q_PNP_CBE", dest=TEMPLATE)
 r = Part("Device", "R", dest=TEMPLATE)
 
 # Create nets.
 gnd, vcc = Net("GND"), Net("VCC")
 a, b, a_and_b = Net("A"), Net("B"), Net("A_AND_B")
 
 # Instantiate parts.
 gndt = Part("power", "GND")             # Ground terminal.
 vcct = Part("power", "VCC")             # Power terminal.
 q1, q2 = q(2)                           # Two transistors.
 r1, r2, r3, r4, r5 = r(5, value="10K")  # Five 10K resistors.
 
 # Make connections between parts.
 a & r1 & q1["B C"] & r4 & q2["B C"] & a_and_b & r5 & gnd
 b & r2 & q1["B"]
 q1["C"] & r3 & gnd
 vcc += q1["E"], q2["E"], vcct
 gnd += gndt
 
 generate_netlist() #Can generate for SPICE, KiCAD, etc
 ```

The future work page of [PySPICE](https://pyspice.fabrice-salvaire.fr/releases/v1.5/example-introduction.html) mentioned a pure python simulator called [ahkab](https://ahkab.readthedocs.io/en/latest/help/Netlist-Syntax.html#the-netlist-file). It's not going to compete with Spectre, but it's very interesting.

### Conclusions

The link I'm trying to establish is the ability to write a Verilog-A model, use it as a starting point to built a SPICE netlist, and at any point, from either the netlist or the Verilog-A model, generate a good looking schematic which can be place inline in Jupyter notebook, or eventually rendered as a SVG/PDF and placed in a LaTex document. Critically, the schematic of each circuit block should represent the content of the block, and not be the high-level symbol of the block itself. At the high level implementation of the system, the design loop will look like this:

> Verilog-AMS model w/ hard-coded in-cell specs -> VAMS testbench w/ plots and specs measurement-> Play w/ simulation to learn needed specs -> Parameterize VAMS model -> Solve for parameters needed for given specs with optimization loop

At the low level now, when making primitives cells there isn't likely any need to have schematic of the behavioral model of the cell, and so the design flow should look like this:

> VAMS High-level parameters becomes Specs file -> Netlist(s) (Template(s)) -> Schematic (w/ no sizes) -> Pick init sizes and run Layout Generator -> Parasitic Extraction -> VAMS high-level model becomes Test Bench -> Play with Simulation -> 

I think that Python doesn't have that much use in the high-level design flow, but in the low-level flow it may have a shot. I was thinking that I should write a mark-up for SPICE netlists which allows schematics to be produced from it. But this forces me to work in a low level language, and then also to write in some form of markup.

A better approach would be to express my circuit in a simpler, high-level manner, which can generate both a SPICE netlist **and** a schematic. This could be where SKiDL comes in. So... maybe....

* Behavioral
  * Verilog-AMS and Verilog-D stays as is. 
  * BAG / PySpice (with Matplotlib) can replace the need for ADE
  * Spectre/AMS Designer stays as is, so I can run Verilog-AMS and Verilog
* Implementation
  * SKIDL / PySpice replace schematic drawing (artistic or functional .OA) and netlist generation
  * BAG / PySpice (with Matplotlib) can replace the need for ADE
  * Spectre/AMS Designer stays as is, so I can run Verilog-AMS, Verilog, SPICE, and PEX netlists all in one environment.
  * BAG or LayGO2 replace the work of layout tools.
  * Calibre DRC / LVS / PEX stay as is



ADMS: Can translate some portions of the Verilog-a language into C code, but I think it's limited to the continuous-time subset of the language. Some of the discrete time components aren't supported, for example (I think).

[Xyce](https://xyce.sandia.gov) 

Ngspice

XSPICE: Add a subset of discrete time primitives into the SPICE language, but it doesn't support Verilog-D, which is a huge problem, as this is what is used for the actual design. At most we could use this for some modeling in test benches, but ultimately this isn't useful.

MagicVLSI: Old school layout tool which has a command line DRC, LVS, and PEX option.

[laygo2](https://laygo2.github.io/overview.html): 

BAG3

Klayout: More mode

Verilog-AMS



Others:

... the entire digital flow??

Verilog, Chisel, yosys, Verilator, CocoTB, 

Charon: Open source TCAD simulation



In order to learn more about the type of Spectre/SPICE simulations.

`/cadence/cadence/SPECTRE161/bin/spectre -help pss | less` (or qpac, etc)



# Literate Programming

[Literate programming](https://en.wikipedia.org/wiki/Literate_programming) is a programing paradigm where instead of generating documentation from well structured comments in your code base, you instead generate your code from well structure snippets in your documentation. Tools like Sphinx are not organic or intuitive, they are mechanical and machine-like, and understanding the internal logic of the design isn't easy.

Instead, literate programming leads the new reader almost step-by-step through the code-base, presenting the code almost in a book format. The generated output of the literate source files are both the pure machine source code, as well as the 'woven' documentation.

The literate programming file uses tags, to separate markdown docs from code. When you first show a subset of a larger function, you can create a macro for it, so that you don't have to manually copy that same code later when showing the 'complete file.'

Pweave is one contendor for this literate programming flow, as you write Python code inline with markdown. The literate source is plaintext.

Jupyter notebook is the most popular option, but the source isn't plaintext. I also can't use the web interface for Jupyter notebooks by themselves if I want debugging and linting features. As it's not plaintext, I can't write it in Vim. But I can write them in VSCode, as it has a built in Jupyter kernel to support opening notebooks.

Additionally, if I want to weave the Jupyter source into .html documentation, or tangle it into source code, I can use [nbdev](https://github.blog/2020-11-20-nbdev-a-literate-programming-environment-that-democratizes-software-engineering-best-practices/) from Github/FastAI.

The main problem I see with Jupyter notebooks is that they're aren't really documents that 'contain complete programs', but rather contain snippets... According to [this](https://slott56.github.io/PyLit-3/_build/html/literate-programming.html) source, the requirements for a true literate programming experience are:

1. Code and extended, detailed comments are intermingled.
2. The code sections can be written in whatever order is best for people to understand, and are re-ordered automatically when the computer needs to run the program.
3. The program and its documentation can be handsomely typeset into a single article that explains the program and how it works. Indices and cross-references are generated automatically.

[PyLit](https://github.com/gmilde/PyLit) and [Pweave](https://github.com/mpastell/Pweave) are both fairly uncommonly used. Compare this to [nbdev](https://github.blog/2020-11-20-nbdev-a-literate-programming-environment-that-democratizes-software-engineering-best-practices/), which has over 10x the number of stars (> 4k). Jupyter notebooks are so common, that it doesn't make any sense for me to choose anything else. Plus, I can view my diagrams interactively in the notebook. There is a reason the Code-a-chip challenge requested that submissions be in the Jupyter notebook format.

I think I might be able to just write in Pweave, but output to a Jupyter notebook format, or just feed to a Jupyter kernel for actual interpretation.

Also, I have to work with languages like Verilog-AMS. Does Pweave support this?


## Why I don't like Jupyter Notebooks:
[Link](https://docs.google.com/presentation/d/1n2RlMdmv1p25Xy5thJUhkKGvjtV-dkAIsUXP-AL4ffI/edit#slide=id.g37ce315c78_0_76)
The good: Inline markdown, and inline images
The bad:
* unknown states if you don't run notebook from beginning, so not really interactive in a trustworthy way
* almost impossible to write tests for your code
* no way to easily import some code into another, as a module
* isn't really that much 'faster' than using a code editor
* you lose many of the helpful features of a texteditor
	* autocomplete isn't fast, requires reruning cells, and recommends local files first?
	* no docstrings
	* no easy way to benefit from type annotations
	* no built-in linter
* shared states make the repoducibility crisis even worse
* jupyter notebook also makes code poorly factored
* jupyter notebooks don't track dependencies well at all...
* no way to copy inputs and outputs into slack, for example
* a whole pile of runnable code is not a good tutorial
* can't break class or function definitions up to aid in explanation


Instead, we can get the similar benefit by just using a top level run_experiment.py and then simply add on a requirments.txt, a load_data.py, a model.py, unit tests, and documentation.

## Literate Programming, Again

I've decided that the best way to provide a literate programming framework it to have markdown format, where the code is in fenced off blocks, with instructions about how they will be executed/interpreted (which language, etc).



This is how [`mdsh`](https://github.com/bashup/mdsh#processing-non-shell-languages) handles it, a multi-lingual tool. I like how it supports both bash and python, but I don't think this will allow things like documentation weaving for .html, or inline plots from python. The file is prefixed by `\#!/usr/bin/env mdsh` so users don't have to do anything special when running it. Any non-shell language (i.e. not Bash/Zsh) like Python or C will be executed by running 
```
#!/usr/bin/env mdsh
```

# Hello World in Python

The following code block is executed at compile time (due to the `@mdsh`).
(The first word on the opening line could be `shell` or `sh` or anything
else, as long as the second word is `@mdsh`.)

```bash @mdsh
mdsh-lang-python() { python; }
```

Now that we've defined a language handler for `python`, this next code
block is translated to shell code that runs python with the block's
contents on stdin:

```python
print("hello world!")
```


Another option is [`knot`](https://github.com/mqsoh/knot) which is written in Erlang, and seems to only do the 'tangling' component of literate programming. The argument is that the hosting repos already will convert markdown into a rendered webpage, so you actually achieve better reproducibility by not having a  built-in 'weave' function.

I don't think this is for me though, as I do really want to be able to show the outputs of the code in the results. As I'm describing a design process, I need the document to actually include the results of my process.

Yet another option is [`lmt`](https://github.com/driusan/lmt), written in Go, which is almost identical to `knot` as it is language-agnostic, and only provides the tangling component of the literate programing workflow. In each fenced code block, you must specify the language and the file name/relatie path to export to.

#### Quarto:

This is my tool!!!!  I should also look at 'Handout' in Python, and Weave.jl in Julia.

https://quarto.org/docs/get-started/hello/text-editor.html

## November 2

Designs should be written in such a way that they reduce complexity. I always need to put myself in the position of how other engineers are going to see my work output.

Therefore, I should be careful about my work product is organized, how it is documented, and the number of things that a person needs to know as a prerequisite in order to work on my code.

For example, creating a complete generator tool, that has too many interconnected loops and optimizations is just going to become something another person can't use.

This is one reason why I like the idea of a JupyterNotebook, which can provide a linear path through the work that I do.

Object orientation is good when describing a CAD design process. But I need to be careful as it's likely that if I start recording my designs as a complex template-based generator system, that few people are going to be able to pick up where I left off.

Is there someway that I can specify the design intent of a circuit, without having to rely on templates?

> With OOP-inflected programming languages, computer software becomes more verbose, less readable, less descriptive, and harder to modify and maintain. Quote: [Richard Mansfield](http://www.4js.com/files/documents/products/genero/WhitePaperHasOOPFailed.pdf)

A very abstract and complex description of hardware will also make it harder to maintain.

The thing is, good engineers can look at a transistor level schematic or at a completed layout file and will be able to intuit the purpose and performance of the design.

I don't like schematics that have a bunch of variables in them. This increases abstraction in a way that I very much dislike. I want a very much "functional" circuit design, where specifications and a diagram of the circuit are fed together to produce a completed layout that can be extracted.

In short, I want a certain representation of the circuit to be consistent in the level of discipline it follows.

I don't mind if a topology template schematic produces a sized schematic as it's output, as this is a clear assembly line process in my head. I can "trust but verify" the black box of a circuit generator, as it's obvious to me the design intent, with the specifications.

A physical object of any kind does not inherently explain why a thing is the way it is. My idea is that the intent of the design needs to be recorded in a fashion that actually shows how the intent was translated into the implementation.

> The implementation of a design is never suffient explanation for why that thing is the way it is. And simply adding 'comments' onto something isn't always the correct fix.

Recognizing that the design process (procedural) is seperate from the design product itself (clean, authoratative instance, without legacy), we can 

## November 16

Programming is a design discipline.

You will figure out what you're build as you build it, you won't know exactly what you need until you actually built it. The spec is always wrong, it doesn't matter how fleshed out it is. The only complete description of a system is it's source. And even when it's right, it's still wrong, as systems change over time. Therefore:

> Debuggability > Correctness by construction

Programming is actually mostly debugging. 

Batch mode programming still dominates the majority of programming, and this is not great. There is no interactivity while programming. Let's examing a few languages:

C++: completely unprincipled. Three as so many ways to complete a different task, and the language has so many ideas which aren't compatible with each other, that everybody who uses it essentially just needs to pick a certain subset of the language and limit themselves to that if they hope to be productive.

Javascript: Same thing happening as C++; tons of new features being added, fairly disorganized. 

Go: Go-routines and garbage collectors are nice, but it's really just another punch-card batch processing complile and run language. Also not a good library language, as will always need to bundle the go run-time.

Rust: Good library language, but again is a punch-card type system. But it's super complicated, and as it's a compile and test language, you can't easily understand that complication. Stop-the-world garbage collection is bad, and go solves that, but so is stop-the-world typechecking.

#### So what doesn't suck?

How about systems that read code, and give you a visualization of what it does? You shouldn't have to manually create representations and keep them in sync with your code. Visualization tools should sit cleanly on top of source code, and and allow you to double check it's functionality in a visual manner.

## November 18

I've realized that there is no golden method for circuit design, and that the process of circuit design really is a completely custom and human driven endeavor.

I want to understand at a lower level how primitive models are defined in SPICE (look at Ngspice and tsmc65).... wait I do know how they are defined. If I just look at the < BSIM4 models, I can clearly see that the compact models for devices have been historically written in C (or is it C++?).

Tools like Xyce, Cppsim, adms, and Ngspice are all written in C or C++ as well. Verilator isn't a interpreter for Verilog-D, but instead a complier which converts the high-level HDL to a monolithic simulator executable in C++ (originally C) which is then compiled and executed. Gnucap is as well, written entirely in C++.

This makes clear for me the issues then: Can I somehow write models in Verilog-A, which can be translated into something directly executable by Ngspice? This would be an amazing proposition, but I don't know if SPICE can deal with the sort of discrete time constructs in the superset Verilog-AMS language.

So let's move one step at a time. Let take a look at the base models provided by the Sky130 PDK. Are they BSIM models? How are the PCELLs implemented? How is the radition hardness specified? What sort of digital timing files are included? What format are the Standard Cells in?

#### a closing argument (on November 18)

1. Cadence has invested a lot of though in building it's ecosystem the way it it. Not all of it is good, but I can't know criticize it thoroughly enough to develop a good replacement, until I actually know it's limitations and it's good ideas. The same way a person needs to learn C/C++ before they can build Go, Rust, or Carbon, I need to understand the Cadence workflow with Spectre and Open Access before I can properly make anything.
2. Similarly, I can dream as much as I want about using Julia, but I can't reinvent all of modern chip design myself, in the time frame of a PhD. If I want to start innovating, I need to adopt a fully functional ecosystem now for my current work, and replace things '1 piece at a time, depending on what hurts the most'. If I do this, not only will I be more likely to build something that solves lots of other people's pain points as well, but that thing is more likely to get noticed and used by other people too, as it will plug directly into their fully functional ecosystem, and be a direct improvement, without forcing them to give up their current way of working.
3. In order to build something that is useful, I also need to be a user of the tool that I'm building. I don't clearly know chip design that well, and so to become a truly good tool-maker, I must become expert at the making of the tools themselves.
4. Finally, there are plenty of aspects of the EDA ecosystem that I don't fully understand right now. If I try to build my own tools with my current knowledge, I can easily be wrecked by a single issue - like for example like `Ngspice` not being able to simulate proprietary foundry (like tsmc65?) models, or `Ngspice` not being able to read in Verilog-A code. The better workflow is to, again, start with a fully functional workflow, and use it as a test bench to see which places I can actually replace, vs not. If I try to jump fully in, without testing, I won't get anywhere fast.

In short: 

> Proprietary tools can sometimes prevent you from learning how to think deeply about your design, but if you force yourself to learn how everything core inside it works, you can learn best practices and what works, start to see the cracks in what doesn't, and have a modular test bench to replace and verify your improved custom solutions, without sacrificing enormous hits to your productivity or ostracizing yourself from your groups workflow.


# Late December

Why does the field of ASIC design not use super computing resources?

[LBNL history of Jupyter and IPython](https://cs.lbl.gov/news-media/news/2021/project-jupyter-a-computer-code-that-transformed-science/)

Design files, PDK data, and tool executables should be able to be bundled and send off to super computer to execute specific operation. Critically though, the Jupyter notebook/programming interface should be able to be run on a local machine.

Store massive data sets in a global file system, and then run the software executables, stored in containers, to be moved around.

Notebooks need to become the interface for developing tools, and for then disseminating knowledge about how those chips were designed.

The key then will be to use Spectre/NGspice/Xyce as a cross-compatible back-end running the design notebook for a chip.

Different graphical viewers, including Virtuoso, Klayout, Xscheme, etc should be used for debugging purposes, but shouldn't be part of the core development flow.

[Scientific Paper is Dead](https://www.theatlantic.com/science/archive/2018/04/the-scientific-paper-is-obsolete/556676/)

Before scientific papers, there was no public (not letters), non-ephemeral (not lectures), incremental (not books), way of documenting science.

These papers were easier to follow, less specialized, and what "computation" was used could easily include data and equations on a single page, and be verified by hand.

The data processing paper now **is** the paper, and despite this, is often left out of the results. Scientists haven't really taken full advantage of computers. They're simply trying to emulate older methods. The fact is, software is a dynamic medium, but paper isn't. Papers are stuck in the past, where we're not able to play with the modern simulated toy models we use to build our works. Why should our readers be stuck with an overly formal, paper only representation of what I'm working on?

Idea is to play with computers, in a carefully authored "computational essay", or notebook. In any field, the prefix of "computational X" is starting to be applied. The fundamental shift in thinking is similar to what happened in the 1600s when people starting to apply mathematical notation to their fields. One thing especially nice about a interactive notebook is that there is no "fudging", the written models inherently completely describe the process.

You know the need for a good new tool when you feel like you're using a hodgepodge of systems, with constant context switching. This limits the ability to be exploratory, and a new tool can unify and fix the work. One should use the computer as a "thinking partner". You should be able to "sketch" out the problem.

> The paper announcing the first confirmed detection of gravitational waves was published in the traditional way, as a PDF, but with a supplemental IPython notebook. The notebook walks through the work that generated every figure in the paper. Anyone who wants to can run the code for themselves, tweaking parts of it as they see fit, playing with the calculations to get a better handle on how each one works. At a certain point in the notebook, it gets to the part where the signal that generated the gravitational waves is processed into sound, and this you can play in your browser, hearing for yourself what the scientists heard first, the bloop of two black holes colliding.

Of course, until journals require notebooks, there will be minimal incentive for any individual to do it, as it will allow others to take their work most easily. Sharing doesn't earn prestige right now.

Often, the people who build good tools have to leave academia for industry, and will sacrifice their academic career in order to build the tools they really want to use. But this is slowly changing.

To build not just good, but **successful** tools, the values of the developers must align with the values of the users. 

[https://www.nature.com/articles/d41586-021-00075-2](Discussion of how software has changed science)

> “We really do have quite phenomenal amounts of computing at our hands today. Trouble is, it still requires thinking.”













## 26.01.2023

These past two months have been overwhelming, as I find myself totally unable to function due to my overwhelming desire to optomize my technological life, but at the same time wish I wasn't thinking about it at all. I have found some solace in the command line, however. On the command line, I feel as though I have control. I feel as though I can access the internet on my own physcological terms. When I work and write in a browser, having access to the internet being something difficult and automated works boons for my anxiety. I finally feel like I own my physche when working in this text only interface.

If I don't have any apps on my iphone, and if I don't keep any data on my phone, then it no longer retains the status of holding my "entire life". I won't keep passwords, or notes, or audio files on the phone. It can be reset, lost, or any manner of other personalization. While I do dream of somehow switching to a device that can allow me to completely remove my dependency smartphones, I fear that may just become a black hole of tweaking and customization and deep diving. I want to get outside, to see the sunshine, and to stop using technology as much.

I can start by getting rid of my Mac. It's not necessary in any capacity. I also think that if possible, it would be good for my wifi to go. I spent a lot of time traveling, and so I end up paying for something I don't use anyways. I can then just keep my cell phone plan at 8 EUR per months and go from there.

What about my account passwords and user data? When I travel, I can take my Airbnb/Bewelcome, Posteo email, and Bank Account password. Other than that, I don't think I should bring anything. All of my personal file, passwords, and archived documents can then be stored on a pair on thumb drives, which can then be stored along with all of my paper documents. These documents can be cleaned up on a regular interval, by loading them into a linux computer. I can use Git to store recovery data, incase I accidentally delete a file.

What I like about Fedora is that it's not a blank slate. It's a flexible and customizable OS, but with a opiniated set of defaults the closely track the modern state of the art. I can easily modify it when necessary, but it gives me as a base a set of defaults that are sane and which teach me. I have to "know the rules, before I can break them".



# Sunday 29 January

Thinking about the sort of work that I want to do professionally, I've come to the following thoughts:

* I enjoy vanilla, simple technology and understanding those concept deeply. Deep tech doesn't exist in the world of SaaS and APIs. These B2B companies aren't truly producing and selling anything profoundlly innovative.
* The core infrastructures around us, be they water, electricity, gas, transportation (roads, bridges, railways, airports, shipping lanes), waste management, food, housing, and information system, represent core technologies, with deep meaningful impact on peoples lives. Changing these, both through regulation/laws and technological advancement is key to having a lasting impact on the world, and therefoe this is likely the area that I want to play in. "Boring" infrastructure isn't boring, it's amazingly powerful, important, and interesting.
* I want to build a employee-owned, debt-free, sustainable buisness. I don't have world domination plans. I want to be scrappy, see what can be done with less, and with older used technology.
* I'm not interesting in getting rich. I see companies and miniture corporations, and I think that each person at the company should make a similar salary, and only benefit make more if they world longer, or a later on in their career. Companies can never have zero-impact on the world around them, but this is fundementally because *people* can never have zero-impact on the world. We fundementally require energy inputs.
* Building a company that makes open source tools and then uses them to produce highly-documented, standardized, open source chips is the dream that I have. I want these chips to support the companies that are willing to open source their PDKs, and those that want to build open source end-user equipment that respects the users privacy and intelligence. The idea is that if you build a system with a open source hardware component, then you need to open source the hardware that you build with it. I'm still not sure if that's a good idea, but I think increasingly it is.
* I think if the chip design company is very transparent about what it's doing, and tells governments "hey, here is a reference design, you can buy from us, but if we ever go under, the revisions of the chip are public, and you can order future versions" then that is a big sell. Also, I think having really extreme transparency about our pricing is an wonderful idea, as it would allow people to see why a chip costs so much, which would help them stomach the cost of a more expensive device.
* Improved transparency and documentation will also allow system designers to understand how to properly repair and service their designs.
* My first step is to write circuit design software which can be user to create chips. I need it to somehow be both flexible and easy to use. Perhaps I can rewrite large portions of BAG in order to all it to simply run as a simple, single python module?
* Then I can essentially just use raw python immitating a domain specific language, with a back-end written in C++? The object oriented nature of C++ makes it ideal for modeling the design of electronic circuits, as they themselves are described as objects.

The environment here at Uni-Bonn is the perfect place to recieve financial support while pursuing this goal of building my tools. In fact, even after I graduate, I think I can add substantial value to the open source chip design environment by redesigning large portions of the chips needed for physics using these tools. Subtle improvements on these technologies, combined with strong inter-generational knowledge transfer as I reimplement these designs would be a boon for me to properly learn and succeed. Also the financial stability of working at Uni-Bonn is paramount, if I decide to have other interests outside of work. Finally, the pressure of the Uni-Bonn group needing to build real systems will force me to ultimately produce things of value, and keep me focused on making real world impacts.

I'm no longer in the phase of 'preparing for life'. This is my life now, and I want to live it in my desired manner, right now.


## another date:
I am developing a collection of circuit synthesis engines which are able to produce complete radiation hardened IP blocks including PLLs, TDCs, and readout pixels signal chains.

Top level design of the system is initially completed in Verilog-A. The trick is that we need to be able to make sure that we write Verilog-A which is actually then synthesizable down into an analog layout.

Each parameter of the high level verilog-A model is something that will serve as a parameter which is then passed down to the low level analog implementation.

The high-level specification will populate the high level 

The clearly parameterized Verilog-A model is the the input to the analog generator, and the output, which is a complete layout alongside an extracted schematic, is then characterized and the absolute values are back propogated to the Verilog-A behavioral model.

28nm and 65nm are going to be the target processes, and one should note that 28nm has a more restricted method of 

1. Developing a Verilog-A model a ROSC VCO, which is then able to be simulated in both Cadence and Xyce and NGSpice. I can only use built-in analysis techniques from Cadence/Xyce/ngspice if they are features that are available across all three, beyond that, my evalutation/post processing pipline should be written in Python. Critically, I shouldn't be trying to predict realistic values for the VCO based on some input parameters, or trying to model the internal structure of the VCO. I just want to have a terminal and pin accurate behavior model.

2. Taking an existing VCO design, which was designed in Spectre, and making in cross platform simulatable. This is necessary because I've never built a VCO before, and I want to be able to be able to verify the precision of my model. Once my model matches the real VCO, including parameters that might matter for which it is nested in a PLL (like phase delay, and phase jitter, and power consumption.)

3. When specifying this model, some of the parameters should be input parameters, and some of them should be 'output' calculated parameters. For example, you can't achieve any artibtray combination of bandwidth/speed, power, and gain in an amplifier. Trying an artibrary combination will likely result in an over constrained specification, and so we should be clear about what are the parameters that become fixed (like frequency) and which parameters are 


Okay, so I want to put together a simple and lightweight chip design environment which is 'IDE aware'. I should look into being inspired by the rust compiler and analyzer. That software apparently works quite well.


In terms of top and bottom up design, I think I still have a log of thinking to do in this regard. However, it appears that properly working with high-level Verilog-A models of devices isn't something that I can make cross platform right now. ADMS is deprecated, and it appears OpenVAF still has a ways to go before being integrated into Xyce, and even in the ngspice integration, doesn't support higher level modeling concepts. It just doesn't low-level compact models, for individual devices. Furthermore, working with Verilog-A models at a high level is less-useful if I don't have a library of components from which I can extra operating parameters. I will struggle to know if my Verilog-A models are accurate, if I can't compare them.

Therefore, what I aim to do is build some simple low-level generators, particularly VCOs to get started. By working in bottom up, I eliminate the need to worry about Verilog-A compatility of my simulators. I can simply generate layouts, using TSMC28 and TSMC65 and then extract their performance characteristics.

I should work inside of Cadence virtuoso, but restrict myself to only using scs netlists, Spectre command line input, and Spectre commandline output. Then I will handle all of the generation of a circuit in Python, and analyze the results in Python. For analysis, I should only use fundamental analysis types in Spectre, and should do all pos processing beyond these in Python, including plotting.

It looks like ngspice has a Spectre and Hspice compatibility mode, and that Xyce support Hspice too, with respect to netlist formats. However, I don't want to spend a bunch of time manually modifying Spectre style netlists into compatibility. 

Therefore, at least for the time being, I want to create my netlists in a Spectre compatible fashion, and verify I'm doing so by using the schematics XL tool, but at least when I start I will only be building a couple different classes of VCO, which are relatively low in transistor count. If I later migrate away from the Spectre netlist format, with OA cells, I won't have made a huge investment.

Actually, on second though, I think I should just write raw netlist files, and not extract them from a schematic GUI. Is this even possible, if I want to use the BAG primitive template transistors? My motivation is that I'm working remotely at the moment, and a full gui is very connection intensive. Perhaps Spectre is even flexible when it comes to the netlist format, and so I can write in a non-Spectre format.

I should look at the code of BAG with OA, and try to understand how it is 'removing' the OA dependency. Is the OA code still there? Or has it just been decoupled, such that an a parrallel implementation could be written? I can find these answers on Github, I suppose.

Another thing I still need to understand is how BAG and TSMC PDK would behave differently in creating individual transistor layouts. Does XBase build on the PDK Pcells, and how are these Pcells written? If not, how do the final netlist for simulations gurantee model accuracy? I think I can rewatch the two BAG tutorials on Youtube to figure out the answer to this question.

One reason why VCOs are a great circuit for me to start with is that they are rather small in terms of transistor count, and also have a fairly well defined interface. For a standard VCO, I simply need three amplifiers. Perhaps with an auxilarry biasing circuit. Then I can also try implementing a DCO circuit, which will have a different transfer function type, and my job is to understand how to homogonize them.

Even this relatively simple circuit will have a whole world of optimization for me to learn about. I can get quite sophisticated in how I analyze and construct this device. I could even learn how to write my own optimization routines, so that the generator isn't just feedforward. Something with generations of the design, perturbing around each point to optimize it. I can try building it in different processes, optimizing it for different oscillation frequencies, and try different architectures. Even just this simple VCO/DCO space could take years of my life. We'll try to limit it to within 10 months though. 

Once I figure out how to properly build BAG and start it, I can successfully limit the scope of knowledge that I need to work on. To just build a bottom-up VCO and DCO generator, I can cut out Verilog-A, semicondutor physics, standard cells, Verilog-D, detector physics, Cadence ADE/assembler, mixed signal simulation, etc.

1: Analog circuit design: Razavi Analog, to size transistors and simulate VCO
2: PLL circuit design: Razavi PLL, to understand design/application space, in substition for hands on higher level models and test benches
3: Python Programming: Python docs, Chat gpt, BAG codebase and docs?
4: PDK organization: BSIM, TSMC65/28nm, PCells, DFM files, layers

This is much more servicble.






Technical Notes

10.02.2023

Using Python as an IDE for circuit dev

To help make this more manageable, I don't want or need IDE integration, Jupiter notebook, or any open source GUI applications. I just need raw Python and C++ command line software. All the viewing and editing will be done in Cadence. But the whole flow will be in a hand written Python/C++ workflow, except for the key place that I target Spectre, etc. All the post processing is done in Python. LVS and DRC aren't "in the loop", and they cause the loop to fail if there is a problem, but their output isn't needed to design the actual device.

Also, to keep it simple, digital sub components shouldn't rely on standard cells, right? Do they create digital gates with Xbase? Or do they mix between full custom and Pcells?

Finally, I won't try to use this for high-level integration. Only for blocks.

My goal is to make this run on a modern Fedora install. I will only use code that is super useful, and anything that doesn't fit my dependencies I will update and integrate.


I'm not sure how to solve the problem yet where I want my test bench to be run from python, but sometimes I need devices and stimuli that are best described in python, sometime I need them best described in Verilog-A, sometimes in Verilog, and sometimes even they are best described in native spice devices like sinusoidal sources. 

Also, often it's not just at the test bench on the perimeter, it's somewhere in the loop or in the forward signal path. This is the whole point with the design schemes discussed on Designers guide, with Top-down, Mixed-signal designs.

People who work on CocoTB will know this, and it looks like Ayan maybe know. Also, I suppose that Cppsim and Spectre may have solutions for this.


General Purpose Languages, DSLs, and Engines:

Python: Numpy, Scipy, Matplotlib, Sympy, ML libraries, Jupyter Notebooks, IPython

PyBind11/Boost Python and other binding libraries

BAG
Xbase
Laygo2

CocoTB

C++: Boost, fmt, spdlog, 
C
SPICE decks
ngSPICE
Xyce
Low level C/C++ BSIM models, now in VA
Verilog-A
Verilog
System Verilog
CLPSim (does it have Python bindings?)
Spectre
Cadence (Schematic, Layout, Waveform Viewer)

Verilator
Icarus Verilog
Magic
Klayout

Bash Script/Unix Terminal.  This is interactive!!!

CMake
Make
gcc
git
llvm

Foundary PDK
LVS Runsets
Standard Cells/PCells

LaTeX
Markdown
HTML/CSS
Pandoc


Schematic rendering tools from netlists, etc?


GPU acceleration
CUDA
CPU Clusters and GPU Clusters

Each step of the process requires deep understanding of the mathematics involved. But perhaps I should be amenable to just running the most naive elementary in un-accelerated implementations, in order to ensure I understand the core mathematics and procedure. Else I will be swamped by trying to understand too many disciplines.










The ideal pixel detector signal processing chain:

Measures the energy (ignoring timing and spatial resolution at this point)
Zero power, zero mass, instant response, digital w/ infinite resolution, zero error, perfect precision.
Also, we would like to understand the interplay between pixel dimensions, spatial energy error, and timing energy error. This gets complicated fast.

In it's most basic sense, we have signals with a continuous time and amplitude. We want to get a 

Basic Building Blocks:

Digitization: ADCs, TDCs, do this, but:
1) The don't have infinite precision
2) They don't have instance response
3) They can't read

they don't have infinite dynamic range, and so we need to rescale the signal to be in this range

Let's first simply consider our signal as a single dimensional signal in a continuous amplitude. Even here, we have issues of gain/linearity/dynamic range/distortion. Our initial detector has a transfer function, and the output of it is not in the range of a normal ADC, as so we need to apply gain. Also, our signal would go right from energy into digital bits, but sensors convert to charge, and so we need to work from charge to voltage, and then finally to digital bits. Noise also exists, but is is possible to consider this without considering time? Yes, I think it is. We can just say that on a measurement, there is a noise modeled by a random error which is sampled. We need to digitize this, to make it userful, and so now we face the issues of quatization error (which is a precision error). We will introduce the concept of decibeels, both in terms of gain, and in terms of noise. Gain: one wait to implement this is with a classic op-amp in feedback, but this isn't the only way. To avoid the intractible mathematics involved with non-linearity and distortion, we have to assume our signal is falling within the dynamic range.

Next let's say we also want to measure timing precision. In fact, even is we don't, we would have to acknowledge that our signal is actually two dimensional. This requires we consider the issues of jitter (timing noise), and bandwidth, and frequency response of a signal. The frequency response component is core to understanding this two dimensional problem. We must consider the issues of triggering, and realize that our signal is an inherintely two dimensional signal. The interaction of gain and time creates errors like time walk. Our initial charge signal is no instant. It's delivered by a current signal overtime, which based on sensor is converted to a voltage signal. But the placement of a feedback amplifier actually modifies the characteristics of this node, and so we have a complicated interaction. The limited bandwidth of components means that the gain available is diffferent at different speeds. Noise is also two dimensional, though, which can benefit us thorugh Filtering: Necessary because sometimes there are parts of the signal we don't want, or because there is noise, and it exists in domains of the frequency response that make it beneficial to be selective. It's in this stage that we really like to model our systems as linear and time invariant. This allows us to consider both the amplitude and time domain, with out the problem becoming mathematically intractable. Are Bode plots, transfer functions, fourier transfers, and laplace transforms something that exist in the undergraduate curriculm at Uni-Bonn? Shannon-Nyquist sampling theory may be able to be skipped in this discussion, as 


Once you add in time domain, however, things get complicated, because there are three fundamental components of noise: The shot noise, the thermal noise, and the 1/f noise. The pulse shaping filter, which has a high and a low frequency cutoff, but which should mainly be thought of as acting in the time domain to create a nice pulse with a return to baseline, has a different effect on each of these noises. If I remember correctly, thermal noise is not effected at all, and shot noise is reduced by pulse shaping, but 1/f noise is actually made worse by standard pulse shaping schemes. (But I may have flipped flopped the terms, so be sure to double check this.)

Next add in the question of spatial resolution. This requires that we acknowledge the challenges of power and space. Pixel detectors are physical devices that take up space.

Finally, let's dicuss implementation, and how analog and digital components can be instantiated by many different technologies including custom ASICs, board level components, and even FPGAs.








# 24.10.2023



Analog: Noise, Distortion/Linearity, Gain(all dC) then (AC) considering bandwidth and noise band width. Placing in feedback adds complication.

Then digital:

Quantization has relationship to all of the above terms. DNL and INL leads to distortion, etc.




PyTorch, LuaTorch, Torch7, TH

LuaTorch = C code (TH) bound to Lua

Templates are a source of frustration, using D types, as they aren't type checked at compile time. So error messages can be cryptic.

Autograd on tensors

Code generation has some pros and cons:

Cons: jump to definition doesn't work
Pros: allows for more powerful meta programming in C++, beyond what templates can do. Also templates have a level of obscuring, you never are directly looking at the final output code, like you do in code generation.

Templates get better with "compsets"? (Spelling)

Manifesto: "Writing Python in C++"

"Ref/Rev? counts" in C++. Atomic vs non-atomic

CMake generates Build files, like Makefiles or Ninja Files
Also basil and buck builds exist, which also need to be changed for PyTorch

PyTorch and 'Cafe2' are mixed together, from when the projects merged.


# 28.02.2023

If I limit myself to low level block design, generation, and optimization, I can get away with test-benches and simulation built entirely with SPICE and python

This will eliminate the need for Verilog-A support, cadence schematic support, and will make me simulator independent.

Think about moving backwards in technology. 

My goal is to do the same design tasks that have always been done, but to do them in a more open and free manner.

Let us not forget the wisdom of our forebears.


Python
Pybind11
cmake
c++
OpenAccess Schematic, Layout, Parasitic
Spectre Netlist
YAML

ext2spice

My end goal is to minimize my effort to output ratio, and then work a normal amount, to seem like I have super powers.



I'm interested in system modeling that homogenizes across a range of time scales (like a pll), in a range of detail scales (semiconductor, analog, digital, Em, heat), using various mathematical represenations











# March 2




I am developing a collection of circuit synthesis engines which are able to produce complete radiation hardened IP blocks including PLLs, TDCs, and readout pixels signal chains.

Top level design of the system is initially completed in Verilog-A. The trick is that we need to be able to make sure that we write Verilog-A which is actually then synthesizable down into an analog layout.

Each parameter of the high level verilog-A model is something that will serve as a parameter which is then passed down to the low level analog implementation.

The high-level specification will populate the high level 

The clearly parameterized Verilog-A model is the the input to the analog generator, and the output, which is a complete layout alongside an extracted schematic, is then characterized and the absolute values are back propogated to the Verilog-A behavioral model.

28nm and 65nm are going to be the target processes, and one should note that 28nm has a more restricted method of 

1. Developing a Verilog-A model a ROSC VCO, which is then able to be simulated in both Cadence and Xyce and NGSpice. I can only use built-in analysis techniques from Cadence/Xyce/ngspice if they are features that are available across all three, beyond that, my evalutation/post processing pipline should be written in Python. Critically, I shouldn't be trying to predict realistic values for the VCO based on some input parameters, or trying to model the internal structure of the VCO. I just want to have a terminal and pin accurate behavior model.

2. Taking an existing VCO design, which was designed in Spectre, and making in cross platform simulatable. This is necessary because I've never built a VCO before, and I want to be able to be able to verify the precision of my model. Once my model matches the real VCO, including parameters that might matter for which it is nested in a PLL (like phase delay, and phase jitter, and power consumption.)

3. When specifying this model, some of the parameters should be input parameters, and some of them should be 'output' calculated parameters. For example, you can't achieve any artibtray combination of bandwidth/speed, power, and gain in an amplifier. Trying an artibrary combination will likely result in an over constrained specification, and so we should be clear about what are the parameters that become fixed (like frequency) and which parameters are 


Okay, so I want to put together a simple and lightweight chip design environment which is 'IDE aware'. I should look into being inspired by the rust compiler and analyzer. That software apparently works quite well.


In terms of top and bottom up design, I think I still have a log of thinking to do in this regard. However, it appears that properly working with high-level Verilog-A models of devices isn't something that I can make cross platform right now. ADMS is deprecated, and it appears OpenVAF still has a ways to go before being integrated into Xyce, and even in the ngspice integration, doesn't support higher level modeling concepts. It just doesn't low-level compact models, for individual devices. Furthermore, working with Verilog-A models at a high level is less-useful if I don't have a library of components from which I can extra operating parameters. I will struggle to know if my Verilog-A models are accurate, if I can't compare them.

Therefore, what I aim to do is build some simple low-level generators, particularly VCOs to get started. By working in bottom up, I eliminate the need to worry about Verilog-A compatility of my simulators. I can simply generate layouts, using TSMC28 and TSMC65 and then extract their performance characteristics.

I should work inside of Cadence virtuoso, but restrict myself to only using scs netlists, Spectre command line input, and Spectre commandline output. Then I will handle all of the generation of a circuit in Python, and analyze the results in Python. For analysis, I should only use fundamental analysis types in Spectre, and should do all pos processing beyond these in Python, including plotting.

It looks like ngspice has a Spectre and Hspice compatibility mode, and that Xyce support Hspice too, with respect to netlist formats. However, I don't want to spend a bunch of time manually modifying Spectre style netlists into compatibility. 

Therefore, at least for the time being, I want to create my netlists in a Spectre compatible fashion, and verify I'm doing so by using the schematics XL tool, but at least when I start I will only be building a couple different classes of VCO, which are relatively low in transistor count. If I later migrate away from the Spectre netlist format, with OA cells, I won't have made a huge investment.

Actually, on second though, I think I should just write raw netlist files, and not extract them from a schematic GUI. Is this even possible, if I want to use the BAG primitive template transistors? My motivation is that I'm working remotely at the moment, and a full gui is very connection intensive. Perhaps Spectre is even flexible when it comes to the netlist format, and so I can write in a non-Spectre format.

I should look at the code of BAG with OA, and try to understand how it is 'removing' the OA dependency. Is the OA code still there? Or has it just been decoupled, such that an a parrallel implementation could be written? I can find these answers on Github, I suppose.

Another thing I still need to understand is how BAG and TSMC PDK would behave differently in creating individual transistor layouts. Does XBase build on the PDK Pcells, and how are these Pcells written? If not, how do the final netlist for simulations gurantee model accuracy? I think I can rewatch the two BAG tutorials on Youtube to figure out the answer to this question.

One reason why VCOs are a great circuit for me to start with is that they are rather small in terms of transistor count, and also have a fairly well defined interface. For a standard VCO, I simply need three amplifiers. Perhaps with an auxilarry biasing circuit. Then I can also try implementing a DCO circuit, which will have a different transfer function type, and my job is to understand how to homogonize them.

Even this relatively simple circuit will have a whole world of optimization for me to learn about. I can get quite sophisticated in how I analyze and construct this device. I could even learn how to write my own optimization routines, so that the generator isn't just feedforward. Something with generations of the design, perturbing around each point to optimize it. I can try building it in different processes, optimizing it for different oscillation frequencies, and try different architectures. Even just this simple VCO/DCO space could take years of my life. We'll try to limit it to within 10 months though. 

Once I figure out how to properly build BAG and start it, I can successfully limit the scope of knowledge that I need to work on. To just build a bottom-up VCO and DCO generator, I can cut out Verilog-A, semicondutor physics, standard cells, Verilog-D, detector physics, Cadence ADE/assembler, mixed signal simulation, etc.

1: Analog circuit design: Razavi Analog, to size transistors and simulate VCO
2: PLL circuit design: Razavi PLL, to understand design/application space, in substition for hands on higher level models and test benches
3: Python Programming: Python docs, Chat gpt, BAG codebase and docs?
4: PDK organization: BSIM, TSMC65/28nm, PCells, DFM files, layers

This is much more servicble.














I want to be retentionally familiar with the fundamentals, and so I will aim to build cards to review information of the basics.




General Analog: Razavi Analog
Semicondutor Devices:
Transitor Modeling:
PLL Analog: Razavi PLL


Verilog-A modeling
SPICE simulator and methods
Python, C, and C++ programming


The reality of the situation is that even a single journal will publish papers encapsulating knowledge beyond what I could even hope to learn in my lifetime.

If I really want to do science that matters, I need to clearly define what I'm interested in accomplishing. To summarize, I want to work on monolithic pixel detectors, and I want to design them using intelligent algorithms, and want to understand, explain, and even modify the software that I use to accomplish that goal.

I need to reduce the scope even more, but I am running into the fundamental issues of the fact that I'm in a physics PhD, and so I need to understand the physics well enough to design chips that will make a difference. No, but I can successfully reduce the scope, because I can rely on the expertise of others in my group to design chips that matter. What I need to be is an expert on chip design.

To that end, I need Razavi Analog, Razavi PLL, Verilog-A modeling, and a passing understanding of Python, C++, and Linux so that I can properly integrate the software that I hope to use.

My productive output is characterized by my github commits, as everything I want to do I aim to do in code. From here, all the necessary mathematics will follow. Verilog-A is important, because it gives a domain specific modeling and synthesis input. Python is important because it gives me a glue language to analyze everything I'm doing at a high level.

My goal is to make my python code work, so I will learn only 'what I need', within reason, to get unstuck. This is why chatgpt is so useful. It allows me to get unstuck quickly.

As I delve more deeply into working with Verilog-A and SPICE, I want to learn about the analysis techniques used by Spectre, Xyce, and ngspice, to know how the method works, and what it's limitations are. But this isn't to write my own code. It just to simply to make sure that I'm using the analyses correctly, and not pushing them beyond their limits.

I should pursue mixed-signal implementations of my PLL. This doesn't mean that I need to use synthesized digital logic, but it does mean that I should try to use digital control, calibration, and measurement throughout my design.

I'm especially interested in small footprint, low power designs with intelligent calibration algorithms. Take something that's ideally compact and low-power, and then figure out a clever way to reuse and calibrate my way to excellence.

If I stick in the area of TDCs, and PLLs, I can become an expert at mixed signal design and simulation, and can get experience building compacts ADC, TDCs, Ring VCOs, and simple implementations of charge pumps, amplifiers, etc. This is good because I'll constantly be needing to thinks and design in mixed signal domains, and will build up a library of generates and their high levels models in Bag and Verilog-A, so that over time I'm able to quickly experiment with different architectures and pick the best one for a certain application.

These thoroughly mixed signal generators are ideal because they are more portable across different processes and it seems that some people in physics are still sort of stuck in the only way of doing things. For boiler plate circuit functionality, like a PLL for running a chip, it's important that we be able to quickly produce something that just works. Also, if I'm able to see one design flow targetting multiple applications and processes, then I think that I will grow more as an engineer.

 





















# March 3

I'm learning about optimization techniques for integrated circuit design. My initially imagined ideas for how the circuits should be designed is turning out to be rather naive.
As post layout simulation is extremely expensive, I can't simply just do random gradient descent with anything other than the simplest of circuits.

It appears that building ML trained models of circuits isn't that feasible, as the simulations necessary to train the model in the first place are so expensive that the model would be quite low quality.

The paper on BagNet explains that a better approach is to build a generator, which can take a wide range of input transistor and generate a DRC and LVS layout, with parasitics extration. But this components shouldn't have any intelligence in it. We then can nest this in an external human-driven or machine-driven optimization process. We shouldn't intermix the generation and evaluation loops.

To a degree, it's okay to limit the range of possible input values to some maximum size, in the case that they would get too large to have a parameterizable layout. Also, it's okay if the layout isn't as compact as it could be. It's not a good use of designer time to optimize generic analog building blocks for size, normally. Usually performace comes a lot more from sizing that metal layer spacing. This is within reason though. The layout plan should be chosen to balance the need for a simpler script, a wide range of possible inputs, and minimized parasitics/silicon area.

# While in Paris:

chipathon (starts each may)
code-a-chip (starts each april)
code-a-chip2 (starts each november)
3-4 physics convferences per year
group presentations

pull requests to github


1. get code to work on my computer		may 2022 - march 2023
2. understand how to use code
3. use it to build small circuit
4. share with group for feedback + feeling good	
5. leads to conference poster/sumissions to competition
   
      
   

DPG conference smuk23.dpg-tagugen.de

bttb11, AIDAInnova
HPC Summer School (end of august, deadline 31.03)
IWORID (end of july, deadline 01.04)
TIPP2023 (Beginning of sep. deadline 15.04)
Twepp 2023 (OCt 2-6, deadline april 30)
pixel2022 (was in december 2022)
ieee nssmic rtsd 2022
FOSDEM: Early February
PIXEL: Mid December
IEEE NSS: Early November 
ISSCC: Late February (Oct for Student Research Preview, November for Code-A-Chip)
SSCS Pico Program/Chip-a-thon: https://sscs.ieee.org/about/solid-state-circuits-directions/sscs-pico-program
VLSI Symposium: Mid June
ISCAS: Late May














09.03.2023

Fundamentally all modeling can be done in C or C++.

When we write code at higher levels, like in Python or in Verilog, or Verilog-A, it is typically either compiling down to binaries which are then linked against the simulator, or they are interpreted by a compiled program (ie Python) which connects back to C or C++.

21.03.2023

Julia is the perfect workspace for designing integrated circuits.

Like MatLab it has inline plotting, symbolic mathematics support, intuitive notation for mathematics (matrixes, DEQ, etc), interactivity

Like Python it has machine learning, large library support, plotting, interactivity, general purpose programming capability, REPL

Like C it has speed.


Like Verilog-A it allows arbitrary modeling of devices, but it has the benefit of extensibility to operators and primitives. Also the JIT Julia language compiler, alongside the necessary libraries, IS the interpreter for the model. This means you don't need to have some sort of division between the model and simulator. They share a representation.

I like the composability of this tool because it allows the user to dig down into understanding mathematical algorithms for their work without having to switch language (like Python bindings around C/C++ extensions). It also allows homogenous integration of other domains like EM solvers, thermal modeling, wireline channels, etc.

Most interesting chip design problems require the combination of multiple problem domains, and proprietary tools will often not be able to keep up with this.

Even within a chip, you can easily run into problems like those seen in a PLL, where you need to simultaneously consider fs-scale jitter and us-scale feedback system dynamics. Another example is modeling on-chip pixels detectors which need to be modeled at the semiconductor level, which then drive circuit-level signal processing, and then feed digital level controls and data output.

Layout generators are critical because they significantly restrict the degrees of freedom of optimization. Even though sub-65nm design are more sensitive than ever to parasitics, the range of solutions for a "good layout" is minimal, and so layout generators increasingly are able generate optimal layouts with minimal exceptions for a wide range of device sizing.



# March 27
With a convolutional neural network approach, I need to decide what my different input nodes are.

Having multiple channels inside a single pixel is likely not the best approach, unless my goal is simply to overcome the device mismatch issues.

That means, my neural network should either act on the different signals present in adjacent pixels, or it should be be monitoring different versions of the signal temporally. Perhaps some delayed copies of the signal could be acted on to identify the character of the pulse.

But this is tricky, as signals are extremely fast. In the current system, they amplify and temporality stretch the pulse, to then feed it into a comparator with inferior input noise and jitter. Finally this is just reset by a global 40Mhz clock edge cycling every 25 nano seconds.

What if there were some way to observe the gradient across local pixels to extremely quickly discover a hit in the matrix. Hmm, this might not work well though, as a perfectly aligned particle track could hit only a single pixel, and then we could have no comparison? Oh wait, so we would have an extremely good comparison. Adjacent pixels staying static is the ideal case.

The minimum activation concept seems to be necessary for neural links, and this is the same basic concept as a discriminator. If this is just one building block of a full neural network (as it is in a detector), perhaps it wouldn't be less hardware intensive.

While discriminator and thresholds seems mandatory, maybe the part we still can cut out is the amplification and pulse shaping. Perhaps we can "directly" monitor the input and feed it into a convolutional network? 

Current signal processing systems are essentially monitoring the input continuously, and upon hit, saturate, and then reduce the time and amplitude dimensionality of the data to a single pair of coarse resolution time stamps.




# April 7

Quote: "Real artists ship."

I've identified the following responsibilities which I'm tending to take on:
* setting up servers with RAID, NFS, Backups, FreeIPA Identity Management, License Server, and "Fleet Management?"
* setting up and installing EDA and TCAD tools, and PDK kits, and init/containers
* configuring workstations to connect to the server, run each of the commercial tools
* working with bag code base, and building it for our internal use, a Python project with C++ extensions
* writing generator scripts which generate and simulate AMS designs, and binding against 28nm PDK
* designing real systems which need to be simulated, integrated, debugged, tested, and interacted upon
* teaching and reviewing fundamentals of analog electronics, digital, signal processing, simulation engines, semiconductor devices, detector physics
* doing example problems, perhaps with Julia, in order to refine my knowledge, in tandem with coursework
* writing blogs and papers about my work, and presenting at conferences


# Tuesday, April 11

I need to put out requests for help to get unstuck. And there are a number of places I can probably ask for help.

I'm looking for mentoring/tutoring in debugging/troubleshooting the install of a rather complicated and poorly documented C++/CMake/Pybind11 code base which I've inherited.

Ayan Biswas
Other Berkeley student
Thomas Party
Mariana on open source design
Other guy from Pakistan
Open source chip design slack
Maybe even Klayout dev?
Boost::spirit issue tracker
Hans and FTD, like Klaas?
Elsewhere in Bonn (ask Georgi, and informatics department)

Not everybody has oa libs
Also I need to document more


Real artists ship:

I'm getting excited about Julia's composability and homogenous modeling concept, but it appears that area a long way off in terms of having a full stack solution.

And gdstk + gdsfactory seems super impressive, but the reality is my PDKs are distributed with device Spectre models/SCS files, Virtuoso schematic symbols (OA), and Open Access layout Pcells.

I only get 1-2 innovation tokens, and I don't want to spent it trying a process other than TSMC 28nm/65nm or writing my own simulation engine, and therefor I should work within the Cadence toolchain to be productive.

As my group already uses Python, it would be a poorly compatible contribution to their workflow if I worked in Julia.

I want to spend my "innovation tokens" on:

    building a framework for modeling a pixel detector signal chain, which can be used to compare designs using FOMs and discover room for improvements. This would be using a combination of Python and Verilog-AMS. I can use Verilog-AMS not just to behaviorally model transistor circuits, but also to homogenize with complex digital circuits and device level simulators while staying in Spectre.
    generate designs which improve on this signal chain using BAG and Xbase. Xbase is the tool for the job, because I want to be able to tune transistor sizes in Python.
    slowly and interatively learn programming and contribute to BAG/Xbase, especially in the vein of refactoring the code into one self-contained library, with convenient packaging. Ultimately programming is programming, and I will learn morning being pragmatic and working with other people, then I will ever by myself off in Julia land.

# Wednesday, April 12

Presentation from Dan Fritchman on Hdl21, Hdl21Schematics, and Vlsir. Given on Tuesday December 6, 2022, during the Chips alliance Analog working group meeting.  [Link Here.](https://www.youtube.com/watch?v=FnLz2Wx2DxY)

* [Hdl21](https://github.com/dan-fritchman/Hdl21)
* [HDL21Schematics](https://github.com/Vlsir/Hdl21Schematics)
* [VLSIR](https://github.com/Vlsir/Vlsir)
* [Layout21](https://github.com/dan-fritchman/Layout21) meta crate containing GDS, LEF, raw layout, and tetris layout crates written in Rust
* [BAG->HDL21](https://github.com/Vlsir/Hdl21BagPorting)


I want to look into this work more. Apparently data serialization and compilers come together to allow for intermediate representations (IR).

It appear there are many different representations for data serialization, and they can be broadly classified as such:

So here's how I think this fits into all the other different types of data serialization, aka 'binary formats'.

* Schema-ful, copying: Protobuf, Thrift, plenty more
* Schema-ful, zero-copy: Cap'n'proto, Flatbuffers
* Schema-less, copying: Json (binary and other variants included), XML
* Schema-less, zero-copy: Flexbuffers (Any others? This seems new to me) 

I'm not sure how these compare relative to like OpenLane/OpenRoad's database thing called 'OpenDB'. But it must be on the same axis?

## Chips Alliance Analog Working Group

There are additionally 6 other presentations which I think are worth watching.

One day after the Dan Fritchman presentation, there was this: https://www.mos-ak.org/silicon_valley_2022/

It was given on [December 7 2022](https://www.youtube.com/watch?v=pJ7S_usjEps)

Then watch the series of 5 presentations from 01.24 until 04.04

* 24 January: Open Source Tools for Modeling - Hands on Overview. with Markus Muller hosting. First discussion of Open VAF.
* 31 January: Silicon CMOS Operating at Cryogenic Temperatures
* 28 February: Han-Chi Han & Professor Christian Enz will present their work on SKY130 silicon measurements and associated data. 
* 21st March: Pascal and Ken on OpenVAF
* 4th April: Update from Tim Edwards on Magic and PEX extraction
* 18th April: Ecosystem of compact model development from Sadayuki Yoshitomi <----- Next presentation
* 2nd May (tentative): Update from EPFL C. Enz and test structures measurements

## Met with Hans, same day as above.

Asked about power consumption limit of 500mW per square centimeter. Hans said the basic problem of power consumption is that the operating temperature of the detector layers must be kept at around -20Celcius during operation, or else thermal runaway in the sensors will lead to irreversable damage. As the operating temperature is limited to -20 C, then therefore the available material budget (which must be limited to prevent multiple scattering), especially in e+ e- colliders like Belle, determines the amount of power dissipation that can be allowed, between the sensor and the hybrid readout electronics. The leakage current of the sensors can range in the nano-amps, and increases over the radiated lifetime of the sensor, but it also runs at a much higher voltage. Overall, about half the power dissapation originates in the sensor and the other half in the readout chip.

Next we talked about coupling of the sensors, to the readout electronics, and how the leakage current in the sensor affects the system. In systems that are DC coupled, which is the majority of the sensors, any additional current will manifest as error signal in the integration period, and so you need a compensation circuit. It sounds like charge-sensitive amplifiers somehow manage to work around this partially, by somehow ignoring the dc component using their 'bandpass' characteristic. But I suppose this isn't perfect?

The other approach, which has been tried, is AC coupling the sensor which prevents the DC leakage from affecting the readout electronics. However, this will form a capacitive divider with the pixel sensor capacitance. The ratio of sensor_cap:coupling_cap roughly forms the ratio of signal loss so a much larger coupling cap is needed. For example a 1:10 ratio means that 10% of the signal charge is lost (I think???).  Seeing as typical pixels have a capacitance on the order of 50fF, we would need a coupling capacitance of around 5 pF (100x) in order to get around only a 1% loss in the sensor's signal charge.

Finally, we discussed the issue of tracking. The majority of hits in the sensor will not be read out, but we can't know which hits to discard until we recieve the tracking data. In super high luminosity experiments, however, there is no way to readout all of the hits, as we would quickly hit our limit on the digital IO. Therefor a huge amount of chip are and space is spent holding the potential hit data in memories, which then are mostly discarded when tracking data is recieved after a fixed delay. Some people have investigated different ways of acquiring simple tracking information on-chip, so that a larger portion of the hits can be discarded immediately.

Tomorrow, I want to chat with Hans about the potential for looking at a free-running integrating VCO. A couple ideas I have:

1) Using nearby pixels to infer false/true positives? Perhaps from the gradient?
2) Using inter-pixel signal gradients to do baseline correct/cancellation. Think of it sort of link correlated double sampling, but using adjacent pixels during the same time references, rather than the same pixel twice.
3) Alleviating the need for a pixel-wide clock, by using neighbors as a reference? But perhaps neighbors can't be used for both 'double-sampling' noise reduction and and referencing for 
4) other ideas?

## 13 April

I should add GitHub to my phone, so that I can take notes and read docs in a centralized but limited fashion

—-

The primary limitations on my workflow is the speed at which I am able to iterate on layouts. Accurate simulation relies on parasitic extraction, and right now I'm dis-incentivized to modify the layout many times because it takes so long to tweak.

If instead, my layout was scripted with a significant degree of constraining the dimensions in the layout, then I think I could quickly try wildly different different layouts. In the current approach, I tend to lock myself into a certain region within which I can only optimize marginally.

## HDL21

The scope is the construction of a netlist, but not one of a SPICE variety. I can export to a netlist, which then can be fed to SPECTRE for simulation. Critically, it is compatible with foundary BIM models, because the BSIM is handled internally inside of the SPECTRE files

# 13.04.2023

I think that this SPICE netlist simulation could be something of interest to Dominic. I am interested if he would be willing to invest 1 day in building out a model of his circuit, and running a simulation of it in ngspice. I should try to understand what his device models are, build his schematic in the netlister, and then attempt to run a simulation which reproduces what he has built in his LTSpice setup.

He might even help me with learning to use and debug the library.


I need to think about how I want to produce my layouts. I need to consider that I have Pcells for transistors, caps, and resistors. I need someway to translate these into Python-based Parameterized cells. I wonder if I could somehow import into Synopsys PyCell designer, and get a python version?

Alternatively, I could somehow extract a fixed library of transistor GDS files, hopefully constrained within reason on the limited/fixed sizing of small 28nm process node?

1. Klayout python scripting. Even not using GUI, I think the Python scripting is very manual and limited. On the brigt side, python PCells appear to be supported? But perhaps not in the same format.

2. BAG, which directly reads and writes to the OA format (or Skill, if using without OA). But this is very cadence dependent still, even so far as requiring a OA schematic to begin from. Perhaps I could instead read in a SPICE netlist, generated from HDL21, as my starting point?

3. GDSFactory / GDSTk. Appear focused on low level devices and architecturally simple microwave/optical circuits, but it is very mature.

4. Layout21 and VLSIR.

## Potential problems:

The HDL21 system doesn't seem at all concerned with abstraction macro models for simulation. But perhaps that is the point. As it is an embedded DSL, it assumes that anything else needed can be satisfied by the general-purpose programming language status of python. It's pragmatic because it doesn't try to model devices, it assumes they are black boxes. At it doesn't try to simulate them either. It just produces an industry standard netlist and lets to feed and recieve back from standard simulators. The pragmatism comes from simplifying but fundamentally accepting the paradigm of circuit designers. And perhaps I need to do this too, if I want to get anything done.

But one question then - what is the BAG conversion tool doing? It's just importing the schematic generator component of BAG! It doesn't deal with the layout component.

## The plan (13.04.2022)

Alright, so I think that the best approach then for me is to just get started with the Schematic and Simulation workflows with HDL21 and VLSIR simulation. I need to be able to show that I can genereate Spectre netlists, and run Spectre simulations, with 28nm device models, in order for Hans to approve and support me.

I will then use python to do some higher level system modeling. This will prevent me from having to learn another language like Verilog-AMS. At this level I will ask and answer questions like, what is the best arch. for pixel detectors. I want a plot show where you would use certain architectures built in both 65 and 28nm, depending on the maximum power dissapation per unit area (which implies detector type/material budget/cooling). On the Y axis would be the 'performance', which I suppose should be effective resolution. Also, hit rate information should be somehow included. This forms the trifecta FOM of sampling rate, resolution, and power. But somehow pixel size is split between affecting both resolution (spatial quantization noise) and power (via pixel layout density). I think the key to understanding this all is in the originating signal itself. We must understand what we want to know about to particles, with what precision and accuracy, before we can make any meaningful decisions about the readout.

In parrallel I will try and see if I can finish building and setting up BAG. Both of these steps will require me to install and understand the 28nm PDK. But I don't want to actually try designing anything.

Then I will evaluate the layout creation process in both Layout21 and BAG. If BAG seems most appropriate, I will hack around to force it to accept Spectre schematics. Or perhaps just import them. If Layout21 is the most appropriate 

To start making any progress, I need to start sketching out some ideas and tests. The only meaningful place for me to start sketching these ideas, as an electrical engineer is with schematics. As long as my schematics simulate against TSMC28 and potentially TSMC65, I should have no issue getting a fairly accurate estimate of circuit performance.

The primary concern I have of course is widely underestimating layout parasitics, but I should be able to do some basic layout tests in Cadence to get some estimated numbers. Other factors like mismatch and noise will be harder to account for, but not impossible. The simplicity of schematic simulation should be more than worth the potential for inaccuracy.

Along the way, I am encouraged to find mathematical models that simply explain the performance of different blocks.

Once the tool ecosystem matures, I can then start investigating how to create layouts. I should try and put layout off for some time. As long as I don't have to make a real device, I can avoid huge amounts of arduous clicking and non-reproducible work.

To pursue more high-level work and avoid too much drudgery with pad rings and tap out, I should align more with Jochen, so that he can understand what I'm doing and see the value.

Tapeouts are expensive, and so avoiding them unless there is something actually worth testing is a good principle to follow.

A good first step would be working with Dominic to build a Python model and simulation of his  LtSPICE netlist. Pulling in the actual PDK transistor models and then simulating them, and returning to Python is something that could be super high value to Dominic. But it looks like measurements will still be the largest aspect of his thesis.


Also.... Do protocol buffers (intermediate representation compilers) actually secretly suck? These are the first I've heard of them, so there must be large downsides to using them? Perhaps I can search online for people's thoughts around protocol buffers. I guess they have both a streaming, in memory, and on-disk representation. That seems like a killer feature. I guess it's part of what is making VSCode so well integrated with language servers, for example? Parsing sucks. So write a single parsing format, and have everybody read and write from it. Have the interchange format be specified separately seems like it would also allow for simple future updates, which applications can choose to support or not?


———

Before chatting with Dominic, I should maybe just see if I can simulate an inverter. I hope this is easy with the built int SKY130 PDK. One I know that works, I can customize for my process, or Dominic's. Actually I will want to do both, anyways, and so starting with either is fine. But even before this, I should just try all the defaults so see if HDL21 is even working...


———

imec download and check, email them
C++ email
chat with Dominic about circuit and hike
Email jochen about Greece 

Later:
working on full PDK install
And HDL21 can wait until later


# april 14


Parameterized device layouts for Sky130

The purpose of this project is to expand the set of available parameterized devices available in magic for use with the SkyWater Sky130 foundry process. These devices are created using an existing framework written in Tcl/Tk, although most of the code involves magic command-line commands (which are implemented in Tcl). Only a basic understanding of Tcl variables, conditionals, loops, and subroutine calls is needed.

Existing devices could use more thorough checks of DRC cleanliness across a wide range of parameters. FET devices could use an option to have all gate contacts merged into a single net, which would also allow a tighter pitch for the smallest length devices.

New devices of interest that have not yet been done in parameterized cells include (but are not limited to): The photodiode, extended-drain MOSFETs, bipolar transistors, ESD transistors, inductors, metal fuses, UHV (ultra-high-voltage) devices.

Each new device should follow the design specifications for device layout from the SkyWater DRC manual, and needs to implement five routines that (1) define the device parameters and limits, (2) convert parameters from a SPICE netlist, (3) define the user interface dialog (UI) for setting those parameters, (4) check and enforce parameter limits, and (5) draw the device. After implementing, each device needs to be checked for DRC correctness by generating a “torture test” of a large array of devices with different sets of parameters which can be passed to the DRC checkers to make sure that the drawing routine produces DRC clean layouts.

Skill level: Intermediate/Advanced

Duration: medium (175 hours)

Language/Tools: Tcl/Tk, Magic

Mentors: Tim Edwards
Parameterized device layouts for GF180MCU

The purpose of this project is to expand the set of available parameterized devices available in magic for use with the Global Foundries GF180MCU foundry process. These devices are created using an existing framework written in Tcl/Tk, although most of the code involves magic command-line commands (which are implemented in Tcl). Only a basic understanding of Tcl variables, conditionals, loops, and subroutine calls is needed.

At the moment, even the basic parameterized devices for GF180MCU have not been thoroughly vetted and checked across a large number of parameters.

New devices of interest that have not yet been done in parameterized cells include (but are not limited to): Extended-drain MOSFETs (LDNMOS, LDPMOS), bipolar transistors, schottky diode, ESD devices (salidice-blocked drain (SAB) devices), fuse devices (metal, poly, and eFuse).

Each new device should follow the design specifications for device layout from the GF180MCU DRC manual, and needs to implement five routines that (1) define the device parameters and limits, (2) convert parameters from a SPICE netlist, (3) define the user interface dialog (UI) for setting those parameters, (4) check and enforce parameter limits, and (5) draw the device. After implementing, each device needs to be checked for DRC correctness by generating a “torture test” of a large array of devices with different sets of parameters which can be passed to the DRC checkers to make sure that the drawing routine produces DRC clean layouts.

Time permitting (e.g., 350 hour internship instead of 175 hour), the internship can include general improvements to the methods for Tcl-scripted parameterized devices in Magic.
​
