Open source netlist:


schematic only has width and length
but layout has a bunch of other device level info per device, like pins, etc



TCL scripts are used for generating the Parameterized cells. You can set defaults for the additional devices parameters, which can't be automatically inferred from the layout (this is anything other than width and length) and then you can generated a mass of unconnected

You can only get port directions from the LEF file, not from the schematic, as spice netlists don't have direction.

you can run 'drc why' in Magic Tcl window

You should choose width of metal wires based on elecomigration and loading capacitance. Too small and electromigration is a problem, and too large and you are adding unecessary capacitance. Don't do routing too long on local interconnection, as it's high resistance.

Two questions:

As somebody who has only done analog design using Cadence tools where PCells which are normally in the OpenAcess format, could you explain a bit more on how the parametrized cells for Magic are written? Are they .tcl scripts, which are then read-in by Magic to flesh out the little 'params' GUI that we see? And are they provided as part of the SKY130 PDK in a standard format, or have they be translated from the PDK data into a Magic-specific TCL format?


## Both
* Harold Pretl has a Docker container, there is also efabless (foss-asic-tools i think) or from iic-jku (iic-osic-tools)?
* No gravity option
* Skywater PDK now has revision B (has support for ReRAM)
* Some device level parasitics are included in device models, if they are fully determined by W and L
* In SKY130, we have ti layer, which is titanium nitride, which is similar to poly, but about halfway between poly and metal in resistivity. It's how to local interconnect is done.
* In SKY130, for PVT and monte carlo, the models include all corners (both the standard process corners and monte carlo, which are separate things).
* To seperate analog and digital substrates, In the sky130 process in magic, there's an "isosub" layer that acts like sxcut.

## Magic VLSI
* In magic, there's a separate command for checking antenna rules.
* Klayout is unique because it doesn't have an internal database, and acts straight on GDS files.
* Magic supports online DRC, wheras klayout doesn't
* Only knowns what is 'one net' in layout via rules, and can't examing the schematic at all.
* for stretching, there is in fact the command is "stretch".
* 'drc where' to fin

## Klayout
* Supports Python and Ruby TCL PCells.
* You have to manually create each device from it's PCell form, and name everything to match Schematic.
* don't forget to set your own shortcut keys




Hi Matthias and all,

​

Thank you for being willing to take a look at the problem I'm facing. I keep the current status of my workspace online at this git repo: https://github.com/SiLab-Bonn/pybag. It is a fork of the main repository hosted by UC Berkeley, with several fixes added by me, plus instructions for reproducing the build.

​

To help you help me, I'm going to try and explain the following details in order:

​

A. The organization of the code base I'm trying to build, and the boundary between project code and external dependencies.

B. The general overview of what the build process (using CMake and Pybind11)

C. Discussion of where I am stuck in the build, the log, and what I've tried.

​

​

Code Organization:

​

I am currently trying to build 'pybag' which is the python module which underlies the higher level features of the BAG3 ecosystem (bag3 and xbase). Pybag is written in C++, and is wrapped to become an importable shared library (.so) in Python via the PyBind11 project. It's architecture is shown below:

​

[img]

​

Again, I have a fork of the top level PyBag repo, found here, along with my steps for setup and compilation:

https://github.com/SiLab-Bonn/pybag

​

The git repo includes all the BAG specific sub-components (cbag, cbag_polygon, and pybind11_generics) as git submodules. There are additionally several open-source external dependencies, as seen in the diagram. I have been acquiring them accordingly:

​

Boost: Manually downloaded, compiled, and installed

fmt, spdlog, and yaml-cpp: Fetched and installed via Microsoft's vcpkg manager

pybind11: Included as a git submodule

​

Finally, this project depends on the OpenAccess libraries from the Si2 Consortium. These are proprietary binaries, and difficult to acquire. This limitation is the reason why BAG3 has seen virtually no usage outside of Berkeley. Ayan Biswas at Berkeley is currently working refactor the code to remove this dependency. For the time being I am working in parallel of him to reproduce a working build of PyBAG as it exists, so that we have a reference to test the OA-free version again.

​

To understand the compliation erro basic flow I follow for compilation is the following:

​

1. A top-level setup.py file is executed which creates a build directory, and emits a CMake config/generate commands to be run on the command line.

2. The CMake configure commands are automatically run, which generate the makefiles for the multiple levels of C++ code, based on the CMakeLists.txt files stored in each of the BAG specific sub-components (again these are cbag, cbag_polygon, and pybind11_generics)

​
* I'm not a c++ developer, so I don't really know how to debug code.
* dumping (nm command)
* circular dependencies
* multiple defenitions
