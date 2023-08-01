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

All of the important PDK data is here.... everything else is more setup or just links pointing inside here.

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



This techfile/pdk are verified with the following tool version.

*Virtuoso          sub-version  IC6.1.7-64b.500.19
*Spectre           sub-version  16.1.0.614.isr13
*Hspice            M-2017.03-SP2-1
*Calibre           v2019.2_14.13
*StarRC            L-2016.06
*Perl              v5.12.2
*ncsim             11.10-s069
*PycellStudio      L-2016.06-1
                   4.6-L4
*Python            2.6.2
*Tcl               8.4
*Linux             2.6.32-642.13.1.el6.x86_64
*Custom Compiler   O-2018.09-SP1-3
*Laker             L-2018.06-1

---

d Calibre       Calibre DRC/LVS files
d CCI           Calibre connectivity interface (to CDS and Mentor tools)
* cds.lib       CDS Library directory list
* display.drf   virtuoso layout display file
d iDeck         dir with icellmap.yaml referecing ivpcell views. ivPcell usually improves readability of extracted views when doing PVS, but you can live with "auLvs" or "symbol". These parasitic symbols on layout view are typically copies of the schematic symbol, which are scaled to match the layout size, and are called an ivPcell view.
d models        Spectre and Hspice models, but it only appears for
* PDK.config
d PDK_doc
* pdkInstall.cfg
* pdkInstall.pl
d PlugIn_bin
d PVS_QUANTUS
d PycellStudio_2016.06-1
d PycellStudio_46
* QRC.config
* readme
* Recommended_tool_version_number.txt
* ReleaseNote.txt
* REVISION
d skill
* StarRCXT_XRC.config
d Tcl
* techfile
d Techfile
* tsmcDeckPlugIn_Utility.pl
d tsmcN28
d v1.9a




```
// Anonymous `circuit.Package`
// Generated by `vlsirtools.SpectreNetlister`
// 

subckt Inverter_e9ec42e0ad8a10b0b94af3b210a115d9_ 
  + vss vdd vin vout 
  + // No parameters 
  
  pmos
  + // Ports: 
  + ( vout vin vdd vdd )
  +  pch_lvt_mac 
  +  w=300n l=100n multi=1 nf=1 
  
  nmos
  + // Ports: 
  + ( vout vin vss vss )
  +  nch_lvt_mac 
  +  w=300n l=100n multi=1 nf=1 

ends 

```

```netlist
subckt inv vdd vin vout vss
    M0 (vout vin vss vss) nch_lvt_mac l=50n w=200n multi=1 nf=1 sd=100n \
        ad=1.5e-14 as=1.5e-14 pd=550.0n ps=550.0n nrd=2.828877 \
        nrs=2.828877 sa=75.0n sb=75.0n sa1=75.0n sa2=75.0n sa3=75.0n \
        sa4=75.0n sb1=75.0n sb2=75.0n sb3=75.0n spa=100n spa1=100n \
        spa2=100n spa3=100n sap=91.9776n sapb=120.93n spba=121.244n \
        spba1=123.39n dfm_flag=0 spmt=1.11111e+15 spomt=0 \
        spomt1=1.11111e+60 spmb=1.11111e+15 spomb=0 spomb1=1.11111e+60
    M1 (vout vin vdd vdd) pch_lvt_mac l=50n w=200n multi=1 nf=1 sd=100n \
        ad=1.5e-14 as=1.5e-14 pd=550.0n ps=550.0n nrd=1.688887 \
        nrs=1.688887 sa=75.0n sb=75.0n sa1=75.0n sa2=75.0n sa3=75.0n \
        sa4=75.0n sb1=75.0n sb2=75.0n sb3=75.0n spa=100n spa1=100n \
        spa2=100n spa3=100n sap=91.9776n sapb=120.93n spba=121.244n \
        spba1=123.39n dfm_flag=0 spmt=1.11111e+15 spomt=0 \
        spomt1=1.11111e+60 spmb=1.11111e+15 spomb=0 spomb1=1.11111e+60
ends inv
```

```input.scs
// Generated for: spectre
// Generated on: Jul 26 18:29:27 2023
// Design library name: test28
// Design cell name: tb_inv
// Design view name: schematic
simulator lang=spectre
global 0
parameters vsweep=0
include "/tools/kits/TSMC/CRN28HPC+/HEP_DesignKit_TSMC28_HPCplusRF_v1.0/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/tsmcN28/../models/spectre/toplevel.scs" section=att_pt

// Library name: test28
// Cell name: inv
// View name: schematic
subckt inv in out vdd vss
    M0 (out in vss vss) nch_lvt_mac l=30n w=100n multi=1 nf=1 sd=100n \
        ad=7.5e-15 as=7.5e-15 pd=350.0n ps=350.0n nrd=2.576626 \
        nrs=2.576626 sa=75.0n sb=75.0n sa1=75.0n sa2=75.0n sa3=75.0n \
        sa4=75.0n sb1=75.0n sb2=75.0n sb3=75.0n spa=100n spa1=100n \
        spa2=100n spa3=100n sap=91.9776n sapb=114.444n spba=115.715n \
        spba1=117.043n dfm_flag=0 spmt=1.11111e+15 spomt=0 \
        spomt1=1.11111e+60 spmb=1.11111e+15 spomb=0 spomb1=1.11111e+60
    M1 (out in vdd vdd) pch_lvt_mac l=30n w=100n multi=1 nf=1 sd=100n \
        ad=7.5e-15 as=7.5e-15 pd=350.0n ps=350.0n nrd=1.466664 \
        nrs=1.466664 sa=75.0n sb=75.0n sa1=75.0n sa2=75.0n sa3=75.0n \
        sa4=75.0n sb1=75.0n sb2=75.0n sb3=75.0n spa=100n spa1=100n \
        spa2=100n spa3=100n sap=91.9776n sapb=114.444n spba=115.715n \
        spba1=117.043n dfm_flag=0 spmt=1.11111e+15 spomt=0 \
        spomt1=1.11111e+60 spmb=1.11111e+15 spomb=0 spomb1=1.11111e+60
ends inv
// End of subcircuit definition.

// Library name: test28
// Cell name: tb_inv
// View name: schematic
I0 (vin vout vdd 0) inv
V1 (vdd 0) vsource dc=1 type=dc
V0 (vin 0) vsource dc=vsweep type=dc
simulatorOptions options reltol=1e-3 vabstol=1e-6 iabstol=1e-12 temp=27 \
    tnom=27 scalem=1.0 scale=1.0 gmin=1e-12 rforce=1 maxnotes=5 maxwarns=5 \
    digits=5 cols=80 pivrel=1e-3 sensfile="../psf/sens.output" \
    checklimitdest=psf 
dc dc param=vsweep start=0 stop=1 step=0.1 write="spectre.dc" \
    oppoint=rawfile maxiters=150 maxsteps=10000 annotate=status 
modelParameter info what=models where=rawfile
element info what=inst where=rawfile
outputParameter info what=output where=rawfile
designParamVals info what=parameters where=rawfile
primitives info what=primitives where=rawfile
subckts info what=subckts where=rawfile
save vin vout 
saveOptions options save=allpub
```

# July 31

# Review of PDK Docs:

All document are found in prefix: `/tools/kits/TSMC/CRN28HPC+/HEP_DesignKit_TSMC28_HPCplusRF_v1.0/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/PDK_doc/TSMC_DOC_WM/`

- `PDK/Application_note_for_customized_cells.pdf`: instructions on adding 3rd party IP into TSMC PDK, by streaming in layouts, assigning pins

- `PDK/N28_APP_of_MonteCarlo_statistical_simulation.pdf`: MonteCarlo is done by changing `top_tt` library for `top_globalmc_localmc` model cards of transistors. Is this do-able with Spectre natively, or do we need 'ADE XL' as a front end?

- `PDK/parasitic_rc_UserGuide.pdf`: Raphael 2D and 3D parasitic models for PEX. (Actually in pdk, under do-not-use) See: ![](https://cseweb.ucsd.edu/classes/fa12/cse291-c/slides/L5extract.pdf)

- `PDK/tsmcN28MSOAEnablement.pdf`: summarizes metal stack up, MSOA (mixed signal open access) explanation

- `PDK/tsmc_PDK_usage_guide.pdf`: I see that I need to copy `display.drf` and `ln -s` link in `models` and `steam` to my `tsmc28` init directory.

- `model/2d5 (or 1d8) /cln28ull_v1d0_2_usage_guide.pdf`: And finally, the master document for transitor models. Version 2d5 vs 1d8 folder doesn't matter

    - primitive MOSFET models have been replaced with macro model (compiled TMI shared library)
    - core transistor is BSIM6 version BSIMBULK binary model, surrounding layout effect are macro
    - diodes use standard spice model
    - resistors, mom varactors, and fmom use TSMC proprietary models
    - You should see a `** TMI Share Library Version XXXXXX` in the sim log, if not there may be problem
    - SPICE netlist difference
        ```
        For primitive model:
        M1 d g s b nch l=30n w=0.6u
        .print dc I1(M1)

        For macro model:
        X1 d g s b nch_mac l=30n w=0.6u
        .print dc I1(X1.main)
        ```
    - Layout effects are modeled in either SPICE model or macro surroundings
    - OD rouding, poly rounding, contact placement, and edge finger LOD are in macro
    - LOD, WPE, PSE (poly space effect), OSE (OD to OD space effect), MBE (metal boundary effect), RDR
    - In BSIM6 there are Instance Parameters which are set and passed in the netlist, and there are model parameters which are part of the compiled model binary, and don't change from device to device.
    - How are parameters passed to the macro model? Perhaps it relies on the same input instance parameters that the core BSIM model uses?
    - RDR = restrictive design rules. Should double check these devices, if the length is under 100nm.
    - There is a 0.9 shrinkage in the "model usage files", so don't add it in netlists. It comes from the 'geoshrink' or in Spectre called the `.param scalefactor`. Therefore don't 
    - There are four modes for variation simulation: trad. total corner, global corner, local monte carlo, global+local monte carlo
    - Variation models are selected with high-level `.lib` statements, check slides 36-40 for instructions
    - Full MC (Case 4) give most silicon accuracy, but is expensive. Instead use global corner (Case 2) for digital long path circuit, as global var dominates.
    - And for analog design, mismatch matters, so do Case 2+MC or just Case 3 which includes MC by default
    - you can run mismatch only for key devices, if designer
    - `soa_warn=yes` will give warnings for over voltage
    - `.lib 'usage.l' noise_mc` and related command will enable flicker noise models, which are independant of device corner

# Short conversation with Hans:
* For TSMC 65: 1.2V was core, IO voltages 1.8, 2.5, 3.3 V
* Core devices have a thinner oxide, which is good for TID hardness
    * we don't want to use IO devices, due to thicker oxide
    * oxide thickness is a property of geometry, and uses a seperate mask
* On the other hand, transistor thresholds flavors are not geometry determined but instead by doping profiles.
    * you are limited by 
* check CERN PDK, to understand which flavors of thresholda are compatible -> every additional threshold costs money
- Requesting runs for Cern needs to be done 4 months in advance. Today is ~Aug 1.
    - 4 months from Aug 1 is Nov 30 MPW
    - 4.5 months from Aug 1 is Dec 15 MPW
    - 6 months from Aug 1 is Feb 2 mini@sic
    - If I want any of these next two runs, I should send my email application to CERN tomorrow.

# Notes on simulation runs:

Two subsequent runs, all that changes is the mpssession number

```
/tools/cadence/2020-21/RHELx86/SPECTRE_20.10.073/tools.lnx86/bin/spectre  \
-64 input.scs +escchars +log ../psf/spectre.out +inter=mpsc  \
+mpssession=spectre0_897169_5 -format psfxl -raw ../psf  \
+lqtimeout 900 -maxw 5 -maxn 5 -env ade
```

```
/tools/cadence/2020-21/RHELx86/SPECTRE_20.10.073/tools.lnx86/bin/spectre  \
-64 input.scs +escchars +log ../psf/spectre.out +inter=mpsc  \
+mpssession=spectre0_897169_6 -format psfxl -raw ../psf  \
+lqtimeout 900 -maxw 5 -maxn 5 -env ade
```

full command
```
/tools/cadence/2020-21/RHELx86/SPECTRE_20.10.073/tools.lnx86/bin/spectre -64 input.scs +escchars +log ../psf/spectre.out +inter=mpsc +mpssession=spectre0_897169_7 -format psfxl -raw ../psf +lqtimeout 900 -maxw 5 -maxn 5 -env ade
```

or just
```
spectre input.scs
```


# Task Question Checklist:

- [x] Simulation not working: Just needed to install cpp library inside
- [ ] How to fix naming convention of modules from generator. Look like I need to just live with it, or rename 'manually after generation'
    - [Primitives can't be instantiated with name arg. #91](https://github.com/dan-fritchman/Hdl21/issues/91)
    - [Renaming Module Attributes #94](https://github.com/dan-fritchman/Hdl21/issues/94)
    - [Netlist Subcircuit Name #96](https://github.com/dan-fritchman/Hdl21/issues/96)
- [ ] What are these extra parameters being spit out by Spectre. Where are they being generated coming from? Can I leave them out in simulation?
- [ ] Do layout macro models present a challenge for Hdl21?
- [ ] Reach out to LBNL to get my old design files
- [ ] Open Github issue for understanding how to name instances
- [ ] Email dan asking about 28nm PDK setup?

# Aug 1
Only create a single generator, top to bottom. Don't try to do any partitioning **yet**
Don't work on parameterizing with 65nm yet

Let's run `spectre input.scs`, with and without all the params after `nf` removed.

```
    M0 (vout vin vss vss) nch_lvt_mac l=50n w=200n multi=1 nf=1 sd=100n \
        ad=1.5e-14 as=1.5e-14 pd=550.0n ps=550.0n nrd=2.828877 \
        nrs=2.828877 sa=75.0n sb=75.0n sa1=75.0n sa2=75.0n sa3=75.0n \
        sa4=75.0n sb1=75.0n sb2=75.0n sb3=75.0n spa=100n spa1=100n \
        spa2=100n spa3=100n sap=91.9776n sapb=120.93n spba=121.244n \
        spba1=123.39n dfm_flag=0 spmt=1.11111e+15 spomt=0 \
        spomt1=1.11111e+60 spmb=1.11111e+15 spomb=0 spomb1=1.11111e+60
    M1 (vout vin vdd vdd) pch_lvt_mac l=50n w=200n multi=1 nf=1 sd=100n \
        ad=1.5e-14 as=1.5e-14 pd=550.0n ps=550.0n nrd=1.688887 \
        nrs=1.688887 sa=75.0n sb=75.0n sa1=75.0n sa2=75.0n sa3=75.0n \
        sa4=75.0n sb1=75.0n sb2=75.0n sb3=75.0n spa=100n spa1=100n \
        spa2=100n spa3=100n sap=91.9776n sapb=120.93n spba=121.244n \
        spba1=123.39n dfm_flag=0 spmt=1.11111e+15 spomt=0 \
        spomt1=1.11111e+60 spmb=1.11111e+15 spomb=0 spomb1=1.11111e+60
ends inv
```

Deleting all of the parameters from this file, we see slightly different results:


Before: `spectre.dc`
```
# CHECKPOINT_VERSION 1
# Generated by spectre (mode: Spectre) from circuit file `input.scs' during analysis dc.
# 1:41:04 PM, Tue Aug 1, 2023
# Number of equations = 10
# The default unit is V, otherwise its unit is after #unit
V0:p	4.63439809742315e-14   #unit A
V1:p	-1.06013974024808e-05   #unit A
vdd	0.9
vin	0.4
vout	0.5480143793553
I0.M0:int_di	0.547459563449464
I0.M0:int_si	0.000554815823079183
I0.M1:int_di	0.548417232001795
I0.M1:int_si	0.899597147450026
```

After: `spectre.dc`

```
# CHECKPOINT_VERSION 1
# Generated by spectre (mode: Spectre) from circuit file `input.scs' during analysis dc.
# 3:00:09 PM, Tue Aug 1, 2023
# Number of equations = 10
# The default unit is V, otherwise its unit is after #unit
V0:p	3.8030586214743e-14   #unit A
V1:p	-1.41076442329871e-05   #unit A
vdd	0.9
vin	0.4
vout	0.560396636650559
I0.M0:int_di	0.560352920588334
I0.M0:int_si	4.37160578571883e-05
I0.M1:int_di	0.560449804834346
I0.M1:int_si	0.899946831824211
```
