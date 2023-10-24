# Hdl21

# Laygo2
clone repo
sudo dnf install python3-devel g++ gcc
pip install gdspy matplotlib cairosvg

# Conda environment
A conda environment is useful to have everything linked against a specific python interpreter. It can also help with managing sourcing everything when activating the environment.

# Boost
1. Download boost source code and extract
2. From extracted folder run `./bootstrap.sh --with-python=python --prefix=/path/to/install/location`
3. Run './b2 install --prefix=/path/to/install/location'

# ROOT
Dependencies: https://root.cern/install/dependencies/
1. Clone ROOT to any fodler and create a separate (not in source dir) build folder
2. Run `cmake -DCMAKE_INSTALL_PREFIX=/path/to/install/location -DPython3_EXECUTABLE=python -DCMAKE_CXX_STANDARD=17 -Dgnuinstall=OFF root/source/dir`
3. From build folder run `cmake --build . --target install -- -jN` with `N` the number of threads to run with
4. (Optional) Source `thisroot.sh` from `install_dir/bin` and run `root -l` in terminal to see if it works

# Geant4
Dependencies:
- xerces-c libraries and headers
- QT5 libraries & headers
- OpenGL libraries & headers (should be installed with ROOT dependencies)
- Motif libraries & headers
- Python3 and Boost.Python libaries and headers (former are fulfilled with a conda install/env))

1. Download geant4 source code and extract. Create a separate build folder
2. Set `BOOST_ROOT` environment variable to install location of boost
3. Run (recommended and working, but not necessarily required)
```
cmake -DCMAKE_INSTALL_PREFIX=/path/to/install/location \
  -DGEANT4_INSTALL_DATA=ON \
  -DGEANT4_USE_GDML=ON \
  -DGEANT4_USE_QT=ON \
  -DGEANT4_USE_XM=ON \
  -DGEANT4_USE_OPENGL_X11=ON \
  -DGEANT4_USE_SYSTEM_CLHEP=OFF \
  -DGEANT4_BUILD_CXXSTD=17 \
  -DGEANT4_BUILD_MULTITHREADED=ON \
  -DGEANT4_BUILD_MULTITHREADED=ON \
  -DGEANT4_USE_PYTHON=ON \
  -DGEANT4_BUILD_TLS_MODEL=global-dynamic \
  geant4/source/dir
```
4. Build with `make -jN` with `N` again the number of threads to run with
5. Install runnng `make install`

# Allpix
1. Clone allpix source code to any location and create a build folder (can be in source dir)
2. Run `cmake -DCMAKE_INSTALL_PREFIX=/path/to/install/location /path/to/source`
3. Run `make -jN` as usual to build
4. Run `make install`
5. (Optional) Run `/path/to/install/bin/allpix --version` to check if it works

# Setup conda environment
Create two folders `activate.d` and `deactivate.d` in `/miniconda_install_dir/env/env_name/etc/conda`
Put shell scripts in both folders to run at activation and deactivation respectively.

Activation:
```bash
#!/bin/sh

source /home/silab/software/geant4/bin/geant4.sh
source /home/silab/software/root/bin/thisroot.sh
```

Deactivation:
```bash
#!/bin/sh

unset ROOTSYS
unset $(compgen -v | grep "G4")
```
At deactivation, all Geant4 variables will be deactivated. Root alters LD_LIBRARY_PATH and PYTHONPATH, which are not unset, just a few obvious ones.





# Other tools

# Tools for Analog Design

List of open-source projects tools for analog/mixed-signal circuit design.


* [Verilog-AMS](https://verilogams.com/)
* [BAG]()
* [gdstk]() gdspy successor, written as a C++ extension to python
* [gdsfactory](https://gdsfactory.github.io/gdsfactory/) python stack, based around gdstk, klayout, etc
* [phidl](https://github.com/amccaugh/phidl) legacy layout too, superceded by gdsfactory
* [CppSim](https://www.cppsim.com/)
* [OpenVAF](https://openvaf.semimod.de/) Rust Verilog-A compiler, only supporting compact models (no AMS behavioral yet). [More info.](https://www.youtube.com/watch?v=4Cf00ZeueNc)
* [VerilogAE](https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=9193978) Also from Semimod. Python component wrt OpenVAF
* [Devices.jl](https://painterqubits.github.io/Devices.jl/)
* [Cedar EDA](https://cedar-eda.com/) 
* [Klayout]() made by Mattias
* [Xyce](https://xyce.sandia.gov/)
* [Magic VLSI]() Includes 'ext2spice' which is the only open source parasitic extraction tool I know
* [CocoTB]()
* [BSIM models]()
* [EKV models]() now combined with BSIM
* [ngspice]()
* [xbase]()
* [laygo2]()
* [Layout21](https://github.com/dan-fritchman/Layout21) Rust library w/ GDS, LEF, etc support
* [PyCells]()
* [Skywater130 PDK]()
* [IcarusVerilog]()
* [ADMS]() Deprecated, don't use
* [PySpice](https://github.com/PySpice-org/PySpice) Python front-end for controlling Nspice and Xyce
* [SKiDL](https://github.com/devbisme/skidl) Python Library for embedded DSL for schematic entry
* [Gnucap](https://www.gnu.org/software/gnucap/gnucap.html)
* [Verilog]() Also called 'Verilog-D'
* [OpenFASOC]()
* [OpenROAD]()
* [Verilator]()
* [Chisel]()
* [Yosys]()
* [OpenFOAM](https://www.openfoam.com/)
* [Modelica](https://en.wikipedia.org/wiki/Modelica)
* [Charon](https://charon.sandia.gov/) semiconductor device modeling code, widely referred to as a TCAD (technology computer-aided design) code, developed at Sandia National Laboratories. It is written in C++ and relies on another Sandia open-source project, Trilinos
* [Elmer](https://www.csc.fi/web/elmer) The only open source open for EM simulation
* [AI-mag](https://github.com/ethz-pes/AI-mag) Technically open source, but relies on MATLAB and COMSOL
* Verilog-A
  TheSyDeKick
  OpenVAF
  Substrate2
  Cppsim and vppsim

  What if there were a verilog A to simulatable kernel like Verilator?

# Electromagnetic Simulation:

* [FastCap](https://github.com/ediloren/FastCap2)
* [FastHenry](https://github.com/ediloren/FastHenry2)

[This site](https://www.matecdev.com/posts/differences-fdtd-fem-mom.html) has information about the three basic numerical approaches for electromagnetic simulation, namely:

* Finite-differences-time domain (FDTD)
* Finite Element Method (FEM), like Elmer
* Method of Moments (MoM), or equivalently, Boundary Element Method (BEM)

It also documents the available solver types.

