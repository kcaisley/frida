# Hdl21 notes

External file, with PDK specific information. In this file, we should produce a family of transistors, and resistors.
Each one of these then recieves an 'external module'? Wait no, I'm not dealing with layout at this point, just schematic sim.
Therefore, I can simply wrap my BSIM models with external modules, and parameterize them with some MosParams. I should also be able
to create my own sort of a macromodel, which improves parasitic accuracy. Theses can be ideal capacitors, which can be removed during LVS comparison, and/or conversion to layout. 
Part of this stack should be a core transistor simulator, which extracts the parameters I can most about. I should be able to base my generator off a netlist. After examining what can be physically achieved by layout, we should develop a 'unit trasistor' size, and then use those as the sizes which are evaluated via our simulation test bench. One can store those inside of `.npy` files.


Let's give up now with making the script process agnostic. Let's assume we just copy and modify, in order to port to a new technology.

Is there still a problem here? If we know the structure we want to generate, and what we want to achieve specwise, can we simply use design equations to achieve a well-optimized system? Let's assume we just know transistor level parameters. If we work from design equations, we could produce a family of inverters by taking the ratio of the transconductance of the devices as the P:N width ratio. Once that is instantiated, we can use a generator which produces a family of modules. The generator will take as an input the base length (not necessarily minimum size, for rad hard), the unit width (which is just nmos width, probably) (again not necessarily min size), and produce a family of inverter.

How do you work around the fact than an NMOS and PMOS probably shouldn't have the same width, in order to balance them? Maybe just make the unit width of the cell layouts that of the larger PMOS, and then simply have the NMOS take up less space?

The purpose of a generator is to take a collection of desired specs (sometimes parameterized, like an amplifier, sometimes always consistent, like a inverter), known properties about a technology, and a library of corresponding components, and produce one or more valid supercircuit that meet that spec.

So for an inverter generator, we'd give it the technology properties (extracted by schematic), and a subset of valid device sizes, and it would use it's internal knowledge of an inverter's topology, plus simulation-free feed-foward/open-loop design methodology, to produce a set of ExternalModule corresponding to Inv1, Inv2, Inv4, Inv8, Inv16, etc

Now, when we reuse these blocks, on the level of a ring oscillator, how do we write the generator? Can it be written to be agnostic of the process? Perhaps, if like the inverter generator, it is written to accept a variable for target technology?

Notice something interesting here though. As soon as we are one level of heirarchy above base level 'schematics' with transistors, we no longer need to be making decisions about transistor sizes, in the generator. That means that we could maybe take a library based approach, with pregenerated and characterized cells at the base level, and then simply make structural decisions, based on mechanistic design equations.

The opposite approach to the base level library is to have even the lowest level of transistor 'schematics' be parameterizable. Is this a good idea? not sure.

Assuming the library approach: When we draft these higher heirachy design generators, when tempted to 'hardcode' a parameter, we should ask whether, in the context of our design, that parameter will need to be updated. Consider the case of a ring oscillator. The parameter for number of stages, frequency of oscillation, phase noise, and choice of unit cell are all interconnected, and not mutually indepedant. So which do I set as the input parameters? **This is a question to answer with Hans. And this is where I aim to be by next Wednesday. Perhaps even with both 28nm and 65nm**

# Other generator ideas

In parrallel, in the process agnostic flow:
Start with a basic topology, using generic devices, embedded as a module inside of a generator.

Generators should be use to produce topology in generic tech, but not to size devices?

The issue is that the compile function needs to take a module as input, and modules don't have parameters, and so I would need to
know the sizes of devices before compiling.

Err on the side of producing all 'useful' combinations of a device, rather than iteratively solve for and only produce a specific instance
This will preserve the feed forward nature of the generator

Modules can't have any parameters. They need to be 'just data'. Is an unsized schematic, 'just data'?

Paramclass

Compile function from generic -> PDK tech

You have to define a class, but you don't have to create an param object from it before feeding it to a generator object.
If, in the definition of the corresponding generator object, it knows to expect a inp


# Code notes
When creating a module from a class, some additional fancy stuff is happening... it's not just the same as creating an object from a standard class. For example. If we run this:

```python
class TestClass:
    def __init__(self, value):
        self.value = value

objTestClass = TestClass(10)

print(TestClass)
print(objTestClass)
```

We get:

```python
<class '__main__.TestClass'>
<__main__.TestClass object at 0x7f47b26698d0>
```

Notice how these signatures tell us that both the class and object are sort of 'runtime' objects.


For now examine these two runs:

```python
import hdl21 as h

m = h.Module(name="MyModule")
m.i = h.Input()
m.o = h.Output(width=8)
m.s = h.Signal()

print(m)

@h.module
class MyModule2:
    i = h.Input()
    o = h.Output(width=8)
    s = h.Signal()

print(MyModule2)
```

This yields:

```python
Module(name=MyModule)
Module(name=MyModule2)
```

Q: Why are these two annotated this way?

A: The print outputs for `Module(name=MyModule)` and `Module(name=MyModule2)` indicate that these are instances of a custom class (like `objTestClass`) named Module with specific attributes and values. The different annotations `Module(name=...)` are likely defined as part of the `__repr__` or `__str__` method within the Module class, which returns a string representation of the object.


# 28nm PDK notes

I'm looking for the spice models for the transistors

```
├── cdsusers
│   ├── cds.lib
│   └── setup.csh
├── CERN
│   ├── digital
│   ├── models
│   ├── StartFiles
│   └── streamout_map
├── doc
├── pdk
│   └── 1P9M_5X1Y1Z1U_UT_AlRDL
└── TSMCHOME
    ├── cds.cern.1p9.lib -> ../TSMCHOME/digital/Back_End/cdk/cds.lib.1P9M_5X1Y1Z1U_UT_AlRDL
    ├── digital
    ├── IMPORTANT.NOTE
    └── VERSION_NUMBERING_SCHEME.txt
```

I see the following inside ./CERN/models/

```
DefaultSpiceLib SPECTRE {
  ../models/spectre/toplevel.scs      att_pt                         y
  ../models/spectre/toplevel.scs      att_ps                         n
  ../models/spectre/toplevel.scs      att_pf                         n
  ../models/spectre/toplevel.scs      ass_pt                         n
  ../models/spectre/toplevel.scs      ass_ps                         n
  ../models/spectre/toplevel.scs      ass_pf                         n
  ../models/spectre/toplevel.scs      aff_pt                         n
  ../models/spectre/toplevel.scs      aff_ps                         n
  ../models/spectre/toplevel.scs      aff_pf                         n
  ../models/spectre/toplevel.scs      afs_pt                         n
  ../models/spectre/toplevel.scs      afs_ps                         n
  ../models/spectre/toplevel.scs      afs_pf                         nq
  ../models/spectre/toplevel.scs      local_mc                       n
  ../models/spectre/toplevel.scs      global_mc__local_mc            n
```

All of the important PDK data is here.... everthing else is more setup or just links pointing inside here.

```
/tools/kits/TSMC/CRN28HPC+/HEP_DesignKit_TSMC28_HPCplusRF_v1.0/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK
```



# Steps


- Create basic VCO generator
- Work through Ravazi PLL book, comparing against real circuits
- Implement noise simulation via Spectre in HDL21
- Work on physical implementation in SKY130, 65nm, and 28nm
- Short feedback loops in sharing the work.

By the end of this week, I want to have a simulation of a VCO, in 130nm SKYWATER. I want to run it against Spectre, as I want to plot large signal noise, in an eye diagram. Contribute that code as a Pull request. Start from gated ring oscillator example provided by examples. 

Don't do anything that would require having visual access to cadence yet. This includes creating a parallel design in Cadence, creating layouts, or creating images showing how the graphical component of design normally works. 

https://github.com/aviralpandey/CT-DS-ADC_generator/blob/main/characterize_technology.py

https://github.com/aviralpandey/CT-DS-ADC_generator/blob/main/database_query.py
