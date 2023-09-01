This 

# Sensor

(simulation only)

Geant4 provides modeling from the initial source, be it and electron or hadron beamline, or radioactive source. It simulates the move of incident particles, as then pass through the sensor and calculates their energy deposition.

Based on this, the creation of electron hole pairs can be computed. [Lachnit, 2021, p37](https://www.physi.uni-heidelberg.de/Publications/BachelorLachnit.pdf)

Allpix² then provides several models for propogation of this charge in the sensor.

At it's core it relies on an accurate model of pixels is done via TCAD simulation, including electric field and doping profiles. This is essentially the a set of  a FE or FD discretation approach for creating a mesh, then together evalutated with a quasi stationary solver.

Allpix² then builds on top of this core

# Front End/Readout(contains some digital cells)

(Simulation and physical implementation. Some full custom layout, and some placed standard cells. But will be designed with an analog-on top flow, and all layout will be 'manual' (no synthesis, place and route, etc)

Using ngspice 

# Digital Readout (Simulation 

# Tooling Approach




## Tools & Their Purpose:
- TCAD (Charon vs Sentarus?)
- Allpix²
- SKY130/IHP130 PDK
- Hdl21
- ngspice
- Spectre
- GDSFactory (don't need schematic aware layout, but need to wrap hard macros, and want to have PDK abstracted layout templating)
    - Hard macros
    - native raw cells
    - (wrapped?) pcell raw cells
- Magic LVS/DRC?
- Calibre LVS/DRC
- 


## Types (of tools)

- External server tools, uncontainerizable, often proprietary and/or massive file sizes (eg. pdks?)
- Open source, command line tools, can be containerized
- Open source, graphical applications, not part of pipeline, just for interactive debug?
- Consider compiled vs interpreted tools

## Distribution methods

Consider OS/distribution/version; but do we want to become a distributor? I'd prefer to focus on core tooling, not supporting others via environment/workspace design. 

- dnf, apt, yum, pacman repositories
- venvs
- pip, anaconda, mamba
- docker, apptainer
- shell scripts
- git repositories



The best workflow are just to test again a collection of apptainer images, some of which are CentOS 7 and 8, to verify against

Then we can check against Ubuntu 22.04 LTS, ubuntu 23.04, Fedora 38, etc?



note: don't include dependecies in repo, just test against them, via 


![Alt text](notes/charon.png)




electric field can't be generated in metals, as the conduction and valence band are overlapped
there are no 'carriers'weighting field and shockely ramo theorem
