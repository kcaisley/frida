# Refactoring

## build (get and compile 
no environment variabes, if possible
building on EL7, EL8, EL9, Ubuntu 20.04 containers. Do this on machine you control. For example: Running Openlane2 on github takes 4 cumulative hours on github actions. 33 hours is the limit per month (2000 mins)
clone git repos
fetch 

PDK, Virtuoso, Klayout, Ngspice, etc, are all limiting as they take up a lot of space?

## install (workspace component)
use bash or python
using cookiecutter? or something similar?
how do work around PDK dependency?

## test

pytest? No, I think just a smoke test. Design generators are good integration tests. Unit tests aren't helpful at this stage, before refactoring.
Use built in generators as the smoke test.

## run
environment variables should be avoided
running bag should be done with `bag` command
Is YAML okay? How can we make it more structured?

## General
Can we get a logo?
What top level to use for this repo?
How can the repositories be best refactored?
- tools solving a similar problem are:
    - UCB chipyard (see /scripts/build-setup.sh): https://github.com/ucb-bar/chipyard
        - Their flow: https://github.com/ucb-bar/chipyard/blob/main/.github/workflows/chipyard-full-flow.yml
    - UCB hammer https://github.com/ucb-bar/hammer
    - CERN flowkit
    - Efabless openlane2
	
How many minutes does SiLab have on CI runners?
    How can I run the CI on my local machine?
How can I start refactoring things together, in my local repo, while still being able to merge in upstream changes?
Sounds like I should maintainer a local repo, with branches that track the upsteam, and then 

To make github actions runnable locally, just use github as the top level runner, and then run a bash script:

```
jobs:
  run_tests:
    runs-on: ubuntu-20.04
    steps:
    - uses: actions/checkout@v2
    - name: Run script file
      run: |
         chmod +x ./public/scripts/test.sh
         ./public/scripts/test.sh
      shell: bash
```

To run against local cadence environments, I should be able to use a 'local runner'.
These may run inside a container, but they could also run on the hardware, if the bash script contains a 'uninstall' portion?
Does this require github premium?


# BAG3++ Install

## Container .def file:

```
Bootstrap: docker
From: centos:7

# build me with the command: apptainer build /tmp/virtuoso_centos7.sif ./bag3++_centos7.def
# and start me with: apptainer shell -B /tools,/users /tmp/bag3++_centos7.sif

%setup
    #run on the host system after base image. Filepaths are relative to host.
    mkdir ${APPTAINER_ROOTFS}/users
    mkdir ${APPTAINER_ROOTFS}/tools

    #used to mount scratch disks
    mkdir ${APPTAINER_ROOTFS}/run/media
%post
    #CentOS 7 image on dockerhub isn't updated, so run this first
    yum -y update && yum clean all
    
    # Extras repo needed to provide some packages below
    yum install -y centos-release-scl centos-release-scl-rh
    
    # rh-git29 isn't in official repos anymore, so use this instead
    yum install -y devtoolset-8 httpd24-curl httpd24-libcurl rh-git218

    # additional tools
    yum install -y curl make wget
```




* rh-git218 (git with nice visual colors; newer git versions don't track symlinks)

Note: rh-git29 is not longer available, so update to rh-git218.

Note, these packages are available in the SCL repository, which must be installed: yum install centos-release-scl-rh centos-release-scl

rh-git29 didn't exist: https://www.softwarecollections.org/en/scls/rhscl/rh-git29/



## Immutable mode

Build the container, in an immutable mode:

```
sudo apptainer build /tmp/virtuoso_centos7.sif ./bag3++_centos7.def
```

Run the immutable container, and start a shell inside:

```
apptainer shell -B /tools,/users /tmp/bag3++_centos7.sif
```

## Sandbox mode

for prototyping, I make a container in sandbox mode:

```
sudo apptainer build --sandbox /tmp/bag3++_centos7_sandbox.sif ./bag3++_centos7.def
```

And start a shell inside this writable container, as root, so that you can install and modify contents:

```
apptainer shell -B /tools,/users --writable /tmp/bag3++_centos7_sandbox.sif/
```



## Building Container:

```
kcaisley > sudo apptainer build bag3++_centos7_test.sif bag3++_centos7.def
```

works, with permissions kcaisley:base

```
kcaisley > sudo apptainer build --sandbox bag3++_centos7_sandbox.sif bag3++_centos7.def
```

works, but makes with permissions root:root. Can this be run with sudo shell?



targeting the main .sif with this command seems to work?:

```
apptainer shell -B /tools,/users --writable-tmpfs bag3++_centos7.sif
```

okay let's try two things:

```
asiclab > apptainer build bag3++_centos7.sif bag3++_centos7.def
```

works and makes permissions asiclab:asiclab

```
asiclab > apptainer build --sandbox bag3++_centos7_sandbox.sif bag3++_centos7.def
```

works and makes with permissions asiclab:asiclab



```
WARNING: The sandbox contain files/dirs that cannot be removed with 'rm'.
WARNING: Use 'chmod -R u+rwX' to set permissions that allow removal with 'rm -rf'
WARNING: Use the '--fix-perms' option to 'apptainer build' to modify permissions at build time.
```

Final build

(in /scratch and as kcaisley)

```bash
sudo apptainer build --force bag3++_centos7.sif bag3++_centos7.def
```

then just

```bash
apptainer shell -B /tools,/users,/run/media bag3++_centos7.sif
```

I left out the idea of building a sandbox, and just debugged what I needed before building



# Server Environment

I need to get conda, which isn't easily available from pip, as it appears corrupted. Therefore:

From inside the container, and while at the working dir

```
Apptainer > wget https://repo.anaconda.com/miniconda/Miniconda3-py37_23.1.0-1-Linux-x86_64.sh
```

run the script, from working dir

```
Apptainer > bash Miniconda3-py37_23.1.0-1-Linux-x86_64.sh -b -f -p ./miniconda3
```

and manually set the install location

```
Miniconda3 will now be installed into this location:
/users/kcaisley/miniconda3

  - Press ENTER to confirm the location
  - Press CTRL-C to abort the installation
  - Or specify a different location below

[/users/kcaisley/miniconda3] >>> /tools/foss/bag/miniconda3
```



conda install doesn't work well: https://github.com/ContinuumIO/anaconda-issues/issues/9480


Run this from the working directory, where the conda environmental.yml file is.

```
./miniconda3/bin/conda env create -f environment.yml --force -p ./miniconda3/envs/bag_python37
```

Okay, this works!

autoreconf fixed for libfyaml: https://askubuntu.com/questions/27677/cannot-find-install-sh-install-sh-or-shtool-in-ac-aux	

autreconf failing, needed libtool: https://www.cyberithub.com/solved-autoreconf-automake-failed-with-exit-status-1/

```
autoreconf -vif
```



For Bash, I add the line:

```
using python : 3.7 : /run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c : /run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/include/python3.7m ;
```

notes for things to change in install instructions:

* fix typo 'many Python and C++ depe'
* fix alignment in point 4
* explain that devtoolset should be 'scl enable' into order to compile with it
* perhaps update git version, but does the version I picked track symlinks?
* write out the command to the conda install prefix in the conda env create
* clean up the confusion between /path/to/conda/env vs /path/to/programs
* It's HDF5, not the other way arround. Fix this in the install instructions
* add note about requiring openssl-devel package for building cmake

# Workspace

`.bashrc_bag`

```bash
export BAG_WORK_DIR=$(pwd)
export BAG_TOOLS_ROOT=/run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c
export BAG_FRAMEWORK=${BAG_WORK_DIR}/BAG_framework
export BAG_TECH_CONFIG_DIR=${BAG_WORK_DIR}/cds_ff_mpt
export BAG_TEMP_DIR=/run/media/kcaisley/scratch/space
export IPYTHONDIR=${BAG_WORK_DIR}/.ipython
# disable hash-salting. We need stable hashing across sessions for caching purposes.
export PYTHONHASHSEED=0
# set program locations
export BAG_PYTHON=${BAG_TOOLS_ROOT}/bin/python3

# set location of BAG configuration file
export BAG_CONFIG_PATH=${BAG_WORK_DIR}/bag_config.yaml

# setup pybag
export PYBAG_PYTHON=${BAG_PYTHON}
```

`.bashrc`

```bash
export PYTHONPATH=""

### Setup BAG
source .bashrc_bag

# location of various tools
export CDS_INST_DIR=/tools/cadence/IC618
export SPECTRE_HOME=/tools/cadence/2020-21/RHELx86/SPECTRE_20.10.073
export QRC_HOME=/tools/cadence/EXT191
export CMAKE_HOME=/run/media/kcaisley/scratch/cmake-3.17.0

export CDSHOME=${CDS_INST_DIR}
export MMSIM_HOME=${SPECTRE_HOME}
export PVS_HOME=/tools/cadence/2019-20/RHELx86/PVS_19.10.000

# OA settings
export OA_CDS_ROOT=${CDS_INST_DIR}/oa_v22.60.063
export OA_PLUGIN_PATH=${OA_CDS_ROOT}/data/plugins:${OA_PLUGIN_PATH:-}
export OA_BIT=64

# PATH setup
export PATH=${PVS_HOME}/bin:${PATH}
export PATH=${QRC_HOME}/bin:${PATH}
export PATH=${CDS_INST_DIR}/tools/plot/bin:${PATH}
export PATH=${CDS_INST_DIR}/tools/dfII/bin:${PATH}
export PATH=${CDS_INST_DIR}/tools/bin:${PATH}
export PATH=${MMSIM_HOME}/bin:${PATH}
export PATH=${CMAKE_HOME}/bin:${PATH}
export PATH=${BAG_TOOLS_ROOT}/bin:${PATH}

# LD_LIBRARY_PATH setup
export LD_LIBRARY_PATH=${BAG_WORK_DIR}/cadence_libs:${LD_LIBRARY_PATH}
export LD_LIBRARY_PATH=${BAG_TOOLS_ROOT}/lib:${LD_LIBRARY_PATH}
export LD_LIBRARY_PATH=${BAG_TOOLS_ROOT}/lib64:${LD_LIBRARY_PATH}

# Virtuoso options
export SPECTRE_DEFAULTS=-E
export CDS_Netlisting_Mode="Analog"
export CDS_AUTO_64BIT=ALL

# License setup
# source /tools/flexlm/flexlm.sh  #May still need to update this?

export LM_LICENSE_FILE=8000@faust02.physik.uni-bonn.de

# This is for cluseter computing
# Setup LSF
# source /tools/support/lsf/conf/profile.lsf  #May still need to update this?
# export LBS_BASE_SYSTEM=LBS_LSF

# Enable devtoolset
source /opt/rh/devtoolset-8/enable
source /opt/rh/rh-git218/enable
source /opt/rh/httpd24/enable

# pybag compiler settings
export CMAKE_PREFIX_PATH=${BAG_TOOLS_ROOT}
```


in `.cdsenv` add line:

```
asimenv.startup	simulator	string	"spectre"
asimenv.startup projectDir string "/run/media/kcaisley/scratch/space"
```

then fixed the symbolic link at:
`/users/kcaisley/cadence/bag3_ams_cds_ff_mpt/cds_ff_mpt/workspace_setup`

```
lrwxrwxrwx.  1 kcaisley base    37 Jun 13 17:12 PDK -> /tools/kits/CADENCE/cds_ff_mpt_v_1.1/
```




# Starting Container/Workspace:

```
xhost +
```

```
apptainer shell -B /tools,/users,/run/media /tools/containers/bag_centos7.sif
```

```
cd ~/cadence/bag3_ams_cds_ff_mpt
```

```
source .bashrc
```

```
virtuoso &
```

## Deprecated starting steps:

Start container
```
apptainer shell -B /tools,/users,/run/media /run/media/kcaisley/scratch/bag3++_centos7.sif
```

Then to enable scl environments (not necessary, as it's added to path in bashrc script)

```
scl enable devtoolset-8 bash
```

```
scl enable rh-git218 bash
```

clearing and issue with: (not an issue if you don't have conda init put stuff in bashrc)

```
__vte_prompt_command() { true; }
```

To activate this environment, use (not necessary, as it's added to path in bashrc script)


```
source ~/.bashrc    #not necessary if done correctly
conda activate /run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c
```

To deactivate

```
conda deactivate
```

But I don't want to have to have conda init or conda in my path, so this is my case:

[Link to source of material below](https://stackoverflow.com/posts/37230019/timeline)

If `conda` is on your path: (not necessary, as it's added to path in bashrc script)


`source activate <env name> && python xxx.py && source deactivate`

If `conda` isn't on your path but is installed: (not necessary, as it's added to path in bashrc script)


`source /path/to/conda/bin/activate /path/to/desired/env_name/ && python xxx.py && source deactivate`

The following command will activate the environment: (not necessary, as it's added to path in bashrc script)

```
source /run/media/kcaisley/scratch/miniconda3/bin/activate /run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/
```

```
cd ~/cadence/bag3_ams_cds_ff_mpt/
```


# Debugging Generator

First warning that was noticed was that rpm stopped working. This is because the rpm library depending on liblzma, and the LD_LIBRARY_PATH had some paths added to it in the conda install, which constains a incompatible version.

### RPM and LibLZMA issue

```
rpm: /tools/packages/miniconda3/envs/bag_py3d7_c/lib/liblzma.so.5: version `XZ_5.1.2alpha' not found (required by /lib64/librpmio.so.3)
```

```
Apptainer> ldd /lib64/librpmio.so.3
/lib64/librpmio.so.3: /tools/packages/miniconda3/envs/bag_py3d7_c/lib/liblzma.so.5: version `XZ_5.1.2alpha' not found (required by /lib64/librpmio.so.3)
	linux-vdso.so.1 =>  (0x00007fffa8be8000)
	libnss3.so => /lib64/libnss3.so (0x00007fd35c800000)
	libbz2.so.1 => /lib64/libbz2.so.1 (0x00007fd35c400000)
	libz.so.1 => /tools/packages/miniconda3/envs/bag_py3d7_c/lib/libz.so.1 (0x00007fd35d356000)
	libelf.so.1 => /lib64/libelf.so.1 (0x00007fd35c000000)
	libpopt.so.0 => /lib64/libpopt.so.0 (0x00007fd35bc00000)
	liblzma.so.5 => /tools/packages/miniconda3/envs/bag_py3d7_c/lib/liblzma.so.5 (0x00007fd35d32c000)
	liblua-5.1.so => /lib64/liblua-5.1.so (0x00007fd35b800000)
	libm.so.6 => /lib64/libm.so.6 (0x00007fd35b400000)
	libaudit.so.1 => /lib64/libaudit.so.1 (0x00007fd35b000000)
	libdl.so.2 => /lib64/libdl.so.2 (0x00007fd35ac00000)
	libpthread.so.0 => /lib64/libpthread.so.0 (0x00007fd35a800000)
	libc.so.6 => /lib64/libc.so.6 (0x00007fd35a400000)
	libnssutil3.so => /lib64/libnssutil3.so (0x00007fd35a000000)
	libplc4.so => /lib64/libplc4.so (0x00007fd359c00000)
	libplds4.so => /lib64/libplds4.so (0x00007fd359800000)
	libnspr4.so => /lib64/libnspr4.so (0x00007fd359400000)
	/lib64/ld-linux-x86-64.so.2 (0x00007fd35d000000)
	librt.so.1 => /lib64/librt.so.1 (0x00007fd359000000)
	libcap-ng.so.0 => /lib64/libcap-ng.so.0 (0x00007fd358c00000)
```
This is where `liblzma.so.5` should be coming from:
```
Apptainer> ldconfig -p | grep liblzma   
	liblzma.so.5 (libc6,x86-64) => /lib64/liblzma.so.5
	liblzma.so.5 (libc6) => /lib/liblzma.so.5
```

This isn't an issue for BAG, but it does mean that Virtuoso will issue a warning, as RPM doesn't work, and therefor the checksystem version script fails. To temporarily make RPM work (at the expense of BAG), simply remove the BAG conda env locations from $LD_LIBRARY_PATH.


### Qt Plugin Issue

When running `./meas_cell.sh` I'm getting some issues with a Qt GUI starting:

```bash
[2023-06-16 10:17:12.535] [sim_db] [info] Returning previous simulation data
This application failed to start because it could not find or load the Qt platform plugin "xcb"
in "".

Available platform plugins are: eglfs, linuxfb, minimal, minimalegl, offscreen, vnc, xcb.

Reinstalling the application may fix this problem.
[2023-06-16 10:17:12.544] [cbag] [critical] 	stack dump [1]  /lib64/libpthread.so.0+0xf630 [0x7f08ce00f630]
```

From [this page](https://askubuntu.com/posts/1054691/timeline), before you start (dangerously) messing around with symlinks to shared libraries, I strongly suggest that you run

`export QT_DEBUG_PLUGINS=1`

and then run your failing executable again in the Terminal. Read the actual error message thrown by QT, since none of the above solutions addressed the cause of this error in my case. This gave me:
```bash
Got keys from plugin meta data ("xcb")
QFactoryLoader::QFactoryLoader() checking directory path "/run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/bin/platforms" ...
Cannot load library /run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/lib/python3.7/site-packages/PyQt5/Qt/plugins/platforms/libqxcb.so: (/run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/lib/libQt5XcbQpa.so.5: symbol _ZNK15QPlatformWindow15safeAreaMarginsEv, version Qt_5_PRIVATE_API not defined in file libQt5Gui.so.5 with link time reference)
QLibraryPrivate::loadPlugin failed on "/run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/lib/python3.7/site-packages/PyQt5/Qt/plugins/platforms/libqxcb.so" : "Cannot load library /run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/lib/python3.7/site-packages/PyQt5/Qt/plugins/platforms/libqxcb.so: (/run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/lib/libQt5XcbQpa.so.5: symbol _ZNK15QPlatformWindow15safeAreaMarginsEv, version Qt_5_PRIVATE_API not defined in file libQt5Gui.so.5 with link time reference)"
This application failed to start because it could not find or load the Qt platform plugin "xcb" in "".
```

The relevant part is: `symbol _ZNK15QPlatformWindow15safeAreaMarginsEv, version Qt_5_PRIVATE_API not defined in file libQt5Gui.so.5 with link time reference`

Googling this, lead me to this: https://superuser.com/questions/1397366/what-is-wrong-with-my-qt-environment-it-reports-could-not-find-or-load-the-qt

> It looks like you have a Qt libraries version mismatch.
> I see Qt libraries coming from both `/usr/bin/platforms/libqeglfs.so` and `/usr/lib/x86_64-linux-gnu/qt5/plugins/platforms`, which are probably not consistent.
> You might need to specify the path like: `export LD_LIBRARY_PATH:/path/to/right/libs:$LD_LIBRARY_PATH`

Sure enough, I'm checking my error log, and I see references to both:

```bash
/run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/lib/python3.7/site-packages/PyQt5/Qt/plugins/platforms/
/run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/bin/platforms
```

But check it, there is also:

```bash
/run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/lib/python3.7/site-packages/PyQt5/Qt/lib/libQt5XcbQpa.so.5
```

The solution was modifying the LD_LIBRARY_PATH:

```
export LD_LIBRARY_PATH=/run/media/kcaisley/scratch/miniconda3/envs/bag_py3d7_c/lib/python3.7/site-packages/PyQt5/Qt/lib:$LD_LIBRARY_PATH
```

But I think I should just fix the bashrc file? Maybe add things to the end of the path.

### XDG_RUNTIME_PATH issue

```
QStandardPaths: XDG_RUNTIME_DIR points to non-existing path '/run/user/2002', please create it with 0700 permissions.
```

These were fixed by:

https://unix.stackexchange.com/questions/162900/what-is-this-folder-run-user-1000

```
export XDG_RUNTIME_DIR=/run/media/kcaisley/scratch/space
```


### Session Manager Issue

```
Qt: Session management error: None of the authentication protocols specified are supported
```

https://stackoverflow.com/questions/59057653/qt-session-management-error-none-of-the-authentication-protocols-specified-are

```
unset SESSION_MANAGER
```

Now, nothing is appearing graphically, but I see:

```python
{'delay_fall': array([[1.44678203e-11, 2.12270059e-11, 2.79859170e-11],
       [1.90778681e-11, 2.83911787e-11, 3.75218904e-11],
       [1.19660825e-11, 1.76068935e-11, 2.31339914e-11]]),
 'delay_rise': array([[1.84293439e-11, 2.77868968e-11, 3.69646259e-11],
       [2.38278466e-11, 3.62280028e-11, 4.84479263e-11],
       [1.69927221e-11, 2.59050590e-11, 3.46498162e-11]]),
 'pwr_avg': array([[1.62404387e-05, 2.72441252e-05, 3.80507290e-05],
       [1.30442844e-05, 2.19406111e-05, 3.05181711e-05],
       [2.07834708e-05, 3.39967189e-05, 4.71144087e-05]]),
 'sim_data': {'ff_125': <bag.simulation.data.SimData object at 0x7f14efdebb90>,
              'ss_m40': <bag.simulation.data.SimData object at 0x7f14efdd7990>,
              'tt_25': <bag.simulation.data.SimData object at 0x7f14efdd7890>},
 'sim_envs': ['tt_25', 'ss_m40', 'ff_125'],
 'trans_fall': array([[1.68837592e-11, 2.92186103e-11, 4.21613994e-11],
       [2.26158479e-11, 3.93678371e-11, 5.56614052e-11],
       [1.42056520e-11, 2.44467640e-11, 3.53796199e-11]]),
 'trans_rise': array([[2.44673691e-11, 4.21319603e-11, 5.96973391e-11],
       [3.17268196e-11, 5.53270956e-11, 7.88278387e-11],
       [2.25445377e-11, 3.87765963e-11, 5.49322180e-11]])}
```

```python
{'beta': 1.375,
 'delay_error_avg': 0.000919131708073776,
 'seg_n': 8,
 'seg_p': 11}
```

I suppose it looks like it's working now?

# Generator Workflow Flow

`./gen_cell.sh`, and it's kind are simple wrapper scripts, which just call their corresponding python equivalents, in `BAG_framework/run_scripts/`

```
dsn_cell.py
extract_cell.py
gen_cell.py
import_sch_cellview.py
meas_cell.py
sim_cell.py

There are also additional .py file there:

export_layout.py
copy_pytest_outputs.py
gds_filter.py
gds_import.py
generate_verilog.py
gen_wrapper.py
import_layout.py
meas_cell_old.py
netlist_config.py
reformat_schematic.py
run_em_cell.py
setup_submodules.py
verify.py
write_tech_info.py
```


```
├── data    (process specific data, in submodules, for corresponding generators)
│   ├── aib_ams
│   ├── bag3_digital
│   └── bag3_testbenches
├── gen_libs    (init empty, holds generated OA cell views)
│   └── AAA_INV
├── gen_outputs (initially empty)
│   ├── inv3
│   └── mos_char_nch_18n
├── gen_outputs_scratch -> /run/media/kcaisley/scratch/space/simulations/gen_outputs
```

Let's first consider the input files, for an inverter schematic generator:

Running a schematic generator of a simple inverter:

```bash
$ ./gen_cell.sh data/bag3_digital/specs_blk/inv/gen_sch.yaml
```

This first script is just a wrapper for the basic `run_bag.sh` script:

```bash
./run_bag.sh BAG_framework/run_scripts/gen_cell.py $@
```

This script, in turn, is just a wrapper for executing the subsequent python script with the environment's version of python:

```bash
source .bashrc_pypath

if [ -z ${BAG_PYTHON} ]
then
    echo "BAG_PYTHON is unset"
    exit 1
fi

exec ${BAG_PYTHON} $@
```

So for example, the expanded command would be: `/usr/bin/python gen_cell.py gen_sch.yaml -raw -mod -lef`


Python is used to executed the runscript `gen_cell.py`:

```python
import argparse

from bag.io import read_yaml
from bag.core import BagProject
from bag.util.misc import register_pdb_hook

register_pdb_hook()


def parse_options() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate cell from spec file.')
    parser.add_argument('specs', help='YAML specs file name.')
    parser.add_argument('-d', '--drc', dest='run_drc', action='store_true', default=False,
                        help='run DRC.')
    parser.add_argument('-v', '--lvs', dest='run_lvs', action='store_true', default=False,
                        help='run LVS.')
    parser.add_argument('-x', '--rcx', dest='run_rcx', action='store_true', default=False,
                        help='run RCX.')
    parser.add_argument('-raw', dest='raw', action='store_true', default=False,
                        help='generate GDS/netlist files instead of OA cellviews.')
    parser.add_argument('-flat', dest='flat', action='store_true', default=False,
                        help='generate flat netlist.')
    parser.add_argument('-lef', dest='gen_lef', action='store_true', default=False,
                        help='generate LEF.')
    parser.add_argument('-hier', '--gen-hier', dest='gen_hier', action='store_true', default=False,
                        help='generate Hierarchy.')
    parser.add_argument('-mod', '--gen-model', dest='gen_mod', action='store_true', default=False,
                        help='generate behavioral model files.')
    parser.add_argument('-sim', dest='gen_sim', action='store_true', default=False,
                        help='generate simulation netlist instead.')
    parser.add_argument('-shell', dest='gen_shell', action='store_true', default=False,
                        help='generate verilog shell file.')
    parser.add_argument('-lay', dest='export_lay', action='store_true', default=False,
                        help='export layout file.')
    parser.add_argument('-netlist', dest='gen_netlist', action='store_true', default=False,
                        help='generate netlist file.')
    parser.add_argument('--no-layout', dest='gen_lay', action='store_false', default=True,
                        help='disable layout.')
    parser.add_argument('--no-sch', dest='gen_sch', action='store_false', default=True,
                        help='disable schematic.')
    args = parser.parse_args()
    return args


def run_main(prj: BagProject, args: argparse.Namespace) -> None:
    specs = read_yaml(args.specs)
    prj.generate_cell(specs, raw=args.raw, gen_lay=args.gen_lay, run_drc=args.run_drc,
                      gen_sch=args.gen_sch, run_lvs=args.run_lvs, run_rcx=args.run_rcx,
                      gen_lef=args.gen_lef, flat=args.flat, sim_netlist=args.gen_sim,
                      gen_hier=args.gen_hier, gen_model=args.gen_mod,
                      gen_shell=args.gen_shell, export_lay=args.export_lay,
                      gen_netlist=args.gen_netlist)


if __name__ == '__main__':
    _args = parse_options()

    local_dict = locals()
    if 'bprj' not in local_dict:
        print('creating BAG project')
        _prj = BagProject()
    else:
        print('loading BAG project')
        _prj = local_dict['bprj']

    run_main(_prj, _args)
```



Next, examining the agument `gen_sch.yaml` file, we see the following:

```yaml
dut_class: bag3_digital.schematic.inv.bag3_digital__inv
impl_lib: AAA_INV
impl_cell: AA_inv
root_dir: gen_outputs/inv

params:
  lch: 36
  w_p: 4
  w_n: 4
  th_p: standard
  th_n: standard
  seg_p: 4
  seg_n: 4
```

This, in turn gives the dot notation identifier of the class in: `./bag3_digital/src/bag3_digital/schematic/inv.py`, which looks like the following:

```python
from typing import Dict, Any, List, Optional

import os
import pkg_resources

from pybag.enum import TermType

from bag.design.module import Module
from bag.design.database import ModuleDB
from bag.util.immutable import Param


# noinspection PyPep8Naming
# This class inherits from the Module superclass
class bag3_digital__inv(Module):
    """Module for library bag3_digital cell inv.

    Fill in high level description here.
    """

    yaml_file = pkg_resources.resource_filename(__name__,
                                                os.path.join('netlist_info',
                                                             'inv.yaml'))

	# constructor method automatically called when object is created from class
	# we can see that the super class Module.__init__ method is also called
	# self is passed as argument so that method can access other class components
	# arguments have type annotations (eg :Param) for the expected type/class
	# there is no return, to 'None' is type hint
    def __init__(self, database: ModuleDB, params: Param, **kwargs: Any) -> None:
        Module.__init__(self, self.yaml_file, database, params, **kwargs)

    @classmethod
    def get_params_info(cls) -> Dict[str, str]:
        return dict(
            lch='channel length in resolution units.',
            w_p='pmos width, in number of fins or resolution units.',
            w_n='nmos width, in number of fins or resolution units.',
            th_p='pmos threshold flavor.',
            th_n='nmos threshold flavor.',
            seg='segments of transistors',
            seg_p='segments of pmos',
            seg_n='segments of nmos',
            stack_p='number of transistors in a stack.',
            stack_n='number of transistors in a stack.',
            p_in_gate_numbers='a List indicating input number of the gate',
            n_in_gate_numbers='a List indicating input number of the gate',
            has_vtop='True if PMOS drain is not connected to VDD, but instead VTOP',
            has_vbot='True if NMOS drain is not connected to VSS, but instead VBOT',
        )

    @classmethod
    def get_default_param_values(cls) -> Dict[str, Any]:
        return dict(
            seg=-1,
            seg_p=-1,
            seg_n=-1,
            stack_p=1,
            stack_n=1,
            p_in_gate_numbers=None,
            n_in_gate_numbers=None,
            has_vtop=False,
            has_vbot=False,
        )

    def design(self, seg: int, seg_p: int, seg_n: int, lch: int, w_p: int, w_n: int, th_p: str,
               th_n: str, stack_p: int, stack_n: int, has_vtop: bool, has_vbot: bool,
               p_in_gate_numbers: Optional[List[int]] = None,
               n_in_gate_numbers: Optional[List[int]] = None) -> None:
        if seg_p <= 0:
            seg_p = seg
        if seg_n <= 0:
            seg_n = seg
        if seg_p <= 0 or seg_n <= 0:
            raise ValueError('Cannot have negative number of segments.')

        self.instances['XN'].design(w=w_n, lch=lch, seg=seg_n, intent=th_n, stack=stack_n)
        self.instances['XP'].design(w=w_p, lch=lch, seg=seg_p, intent=th_p, stack=stack_p)

        self._reconnect_gate('XP', stack_p, p_in_gate_numbers, 'VSS')
        self._reconnect_gate('XN', stack_n, n_in_gate_numbers, 'VDD')

        if has_vbot:
            self.reconnect_instance_terminal('XN', 's', 'VBOT')
            self.add_pin('VBOT', TermType.inout)
        if has_vtop:
            self.reconnect_instance_terminal('XP', 's', 'VTOP')
            self.add_pin('VTOP', TermType.inout)

    def _reconnect_gate(self, inst_name: str, stack: int, idx_list: Optional[List[int]], sup: str
                        ) -> None:
        if stack > 1:
            g_term = f'g<{stack - 1}:0>'
            if idx_list:
                glist = [sup] * stack
                for i in idx_list:
                    glist[i] = 'in'
                self.reconnect_instance_terminal(inst_name, g_term, ','.join(glist))
            else:
                self.reconnect_instance_terminal(inst_name, g_term, 'in')
        else:
            self.reconnect_instance_terminal(inst_name, 'g', 'in')
```

## Play-by-play breakdown of execution:

The order of execution flow between the Python files and the YAML file is as follows:

1. The bash command `python gen_cell.py gen_sch.yaml -raw -mod -lef` is executed in the command line.
2. The command line arguments (`gen_sch.yaml`, `-raw`, `-mod`, `-lef`) are passed to the gen_cell.py script.
3. The `gen_cell.py` script imports necessary modules and defines functions and classes. The `register_pdb_hook()` function is called which sets the standard exception behavior for batch mode (but not interactive). In other words, it's setting the unhandled exception hook to called the default Python Debugger `pdb` for post mortem analysis.
4. The `parse_options()` function is called to parse the command line arguments and return an argparse.Namespace object containing the parsed arguments, which is saved in `_args` variable.


    The `parser.parse_args()` function in the `argparse` module parses the command-line arguments based on the defined arguments in the `ArgumentParser` object (`parser`). Although `parse_args()` doesn't take any arguments explicitly, it accesses the command-line arguments provided to the script when it is executed.

    When you call `parser.parse_args()`, the function internally reads the command-line arguments from `sys.argv`, which is a list that contains the command-line arguments passed to the script. It uses the argument definitions in the `ArgumentParser` object to determine how to parse and interpret the command-line arguments.

    Here's a breakdown of how `parse_args()` works:

    - When you execute the Python script with command-line arguments, for example:
    ```
    $ python script.py arg1 arg2 --option1 value1
    ```
    - The `parse_args()` function internally reads the command-line arguments from `sys.argv`. It considers `sys.argv[1:]`, excluding the script name itself (`script.py`), as the list of arguments to parse.
    - `parse_args()` looks at the argument definitions specified in the `ArgumentParser` object (`parser`) to determine how to interpret each argument.
    - It identifies positional arguments based on their order and assigns them to the corresponding attributes of the `args` object.
    - It identifies optional arguments (those with flags like `-f` or `--flag`) and their corresponding values, and assigns them to the appropriate attributes of the `args` object.
    - Once all the arguments have been parsed and assigned, `parse_args()` returns the populated `args` object.

    By defining the arguments using `add_argument()` on the `ArgumentParser` object before calling `parse_args()`, you provide instructions to `parse_args()` on how to parse the command-line arguments and store them in the `args` object.

    Note that `parse_args()` can raise an error if the command-line arguments are not valid according to the defined arguments in the `ArgumentParser`. It performs argument type validation, checks for missing or incorrect arguments, and provides error messages accordingly.



5. The run_main() function is called with the BagProject object (_prj) and the parsed arguments (_args). Note, this is defined inside the same run script still. `_prj` is the current project being worked on, which is gathered from the environment variable. `_args` is the YAML file and additional flags like `-raw`.

6. The `run_main()` function reads the YAML file specified in the `args.specs` argument using the `read_yaml()` function.
7. The `prj.generate_cell()` method is called with the YAML specifications, as well as other arguments based on the command line options (`args`). This is the point at which the runscript's role ends.

    ```
    prj.generate_cell(specs, raw=args.raw, gen_lay=args.gen_lay, run_drc=args.run_drc,
                        gen_sch=args.gen_sch, run_lvs=args.run_lvs, run_rcx=args.run_rcx,
                        gen_lef=args.gen_lef, flat=args.flat, sim_netlist=args.gen_sim,
                        gen_hier=args.gen_hier, gen_model=args.gen_mod,
                        gen_shell=args.gen_shell, export_lay=args.export_lay,
                        gen_netlist=args.gen_netlist)
    ```

8. Now inside `core.py` which defines `prj.generate_cell()`, the specified YAML file is used to generate a cell. The specs and other options are passed to the generate_cell() method of the BagProject object. The generate_cell() method in BagProject class is responsible for generating the cell based on the specifications.











10. During cell generation, the YAML parameters are used to create an instance of the bag3_digital__inv class from the bag3_digital.schematic.inv module.
11. The bag3_digital__inv class is a subclass of the Module class, and its __init__ method is called to initialize the instance with the specified parameters.
12. The design() method of the bag3_digital__inv class is called to perform the design of the cell using the provided parameters.
13. The design() method implements the logic to design the cell based on the given parameters and connections.
14. After the cell is generated, further processing may be performed based on the command line options, such as running DRC, LVS, generating GDS/netlist files, etc.

In summary, the execution flow starts with the bash command, passes the command line arguments to the Python script, which then reads the YAML file, generates a cell based on the specifications, and performs additional processing as specified by the command line options. The YAML file provides the specifications for the cell design, and the Python script controls the execution flow and interacts with the BagProject and Module classes to generate the desired cell.




# Example Generate Scripts

From the AIB instruction notes, I found:

For each block, there will be a gds (.gds), lef (.lef), lib (.lib),
netlist (.net or .cdl), model (.v or .sv) and a shell (.v). There will
also be log files and some extra files containing the data necessary to
generate these results, but this document only shows the final outputs.

**Example: DCC Delay Line**

Gen cell command:
```
./run_bag.sh BAG_framework/run_scripts/gen_cell.py data/aib_ams/specs_ip/dcc_delay_cell.yaml -raw -mod -lef
```

Gen Lib command:
```
./run_bag.sh bag3_digital/scripts_util/gen_lib.py data/aib_ams/specs_ip/dcc_delay_cell_lib.yaml
```

Output files:
```
gen_outputs/ip_blocks/dcc_delay_cell/
```

Should have the files:

-  `dcc_delay_cell.gds`

-  `dcc_delay_cell_shell.v`

-  `dcc_delay_cell_tt_25_0p900_0p800.lib`

-  `dcc_delay_cell.cdl`

-  `dcc_delay_cell.lef`

-  `dcc_delay_cell.sv`

# Example Design Scripts:

A design script will run through a design procedure for the given block,
and if successful in execution will generate similar collateral to the
previous generation scripts. Please note that since we are reusing the
lib file generation from the gen cell commands, the lib file is
generated in the same location as it was previously.

All the commands will follow the format of:

```
./run_bag.sh BAG_framework/run_scripts/dsn_cell.py data/aib_ams/specs_dsn/\*.yaml
```

With the exact full command and output files detailed below.

**Example: DCC Delay Line:**

Yaml file: `dcc_delay_line.yaml`

Full command:
```
./run_bag.sh BAG_framework/run_scripts/dsn_cell.py data/aib_ams/specs_dsn/dcc_delay_line.yaml
```

Folder:
```
gen_outputs/dsn_delay_line_final
```

Generated collateral:
- `aib_delay_line.gds`

- `aib_delay_line.cdl`

- `aib_delay_line.lef`

- `aib_delay_line_shell.v`

Lib file location:
```
gen_outputs/ip_blocks/dcc_delay_line/dcc_delay_line_tt_25_0p900_0p800.lib
```

And here is the `inv.py` file:

# Gen Cells Explanation

Reproduce a copy of the gen_cell.generate_cell() method, but only including the sections that would run if `gen_sch` boolean is true, and all the other booleans are false.

1. Okay, so by default `gen_lay` and `gen_sch` are true, and all the other booleans are false. That includes raw, run_drc, run_lvs, run_rcx, lay_db, sch_db, gen_lef, sim_netlist, flat, gen_hier, gen_model, mismatch, gen_shell, export_lay, and gen_netlist.

2. As there are very few parameters in the YAML file, and no arguments are passed. 

    root_dir: It will be set to the value of the key root_dir from the YAML, which is "gen_outputs/inv".

    impl_lib: It will be set to the value of the key impl_lib from the YAML, which is "AAA_INV".

    impl_cell: It will be set to the value of the key impl_cell from the YAML, which is "AA_inv".

    params: It will be set to the value of the key params from the YAML, which is a dictionary containing various parameter settings:

This line is critical, it checks the class of the `dut_class` and `layout_cls` key value pairs in the specs.yaml file, and returns some booleans. 

```
has_lay, lay_cls, sch_cls = self.get_dut_class_info(specs)
```

In this case, since `dut_class` is specfied as a subclass of `Module` e.g. it is a schematic generator. Therefore `has_lay = False`, `lay_cls=None`, and `sch_cls=Module`.



Next, there is a set of code which uses the `DesignOutputs` enum:

```python
class DesignOutput(IntEnum):
    LAYOUT = 0
    GDS = 1
    SCHEMATIC = 2
    YAML = 3
    CDL = 4
    VERILOG = 5
    SYSVERILOG = 6
    SPECTRE = 7
    OASIS = 8
```

To set some file types:

```python
lay_type_specs: Union[str, List[str]] = specs.get('layout_type', 'GDS')
mod_type: DesignOutput = DesignOutput[mod_type_str]
#...etc...
if isinstance(lay_type_specs, str):
    lay_type_list: List[DesignOutput] = [DesignOutput[lay_type_specs]]
else:
    lay_type_list: List[DesignOutput] = [DesignOutput[v] for v in lay_type_specs]
```

In this code, `lay_type_list` will at least contain `GDS` and `mod_type` will be `SYSVERILOG` by default.

Next, there are a bunch of variables which are skipped, in our simple case, related to DRC, layout, models, Verilog, etc. Despite the fact that `gen_lay=True`, if is constantly A big if-else pair evaluates, and:

```python

if has_lay:
    #etc
else:
    sch_params = params
```

Keep in mind there an instances where a schematic isn't explicitly generated, where having one would still be necessary. These are, for example, when LVS or RCX extraction are enabled.


# ------------------- BAG OLD NOTES----------------------

### Crossely ICCAD'13

* produce only **sized** schematic, the topology is up to the designer
* Good for:
  * technology characterization
  * schematic and testbench translation
  * simulator interfacing
  * physical verification and extraction
  * parameterized layout creation for common *styles *of layout. 
* BAG, in it's basic form belongs to the 'knowledge-based' design automation class, although specific sub-circuits area free to be optimized with some algorithm. This is especially useful with BAG, as we already have the ability to produce a high-quality subset of design to choose between.
* Knowledge-based design scripts are especially useful, as they self-document the design process. They also keep the designer 'in control' of the process.
* a completed BAG script helps with top level design, as you can specify the top level parameters, and then recursively instantiate the subblocks

"In our approach to analog circuit automation, a designer’s deliverable is not a single instance of a sized schematic and clean layout for a particular circuit, but rather a generator for a desired class of circuits that can replicate, in an automated fashion, the design procedure that would have been used for a traditional, manual design."

* Each realized circuit Generator much implement the methods of the interface
  * ReadSpecification()
  * DesignSchematic()
  * DesignLayout()
  * VerifyArchitecture()
  * WritePerformance()
* Because tasks are often the same between circuit generators though, there are abstract classes which provide connections to common actions in the design process, and to connect to tools.
  * CodeStubGeneration()
  * RunOptimizer()
  * LaunchSimulations()
  * RunDRCandLVS()
  * IO_OpenAccess()

# BAG Install Notes

BAG_prim is cadence library, with device used to build schematic template (called a schematic generator)
Schematic generators are schematic templates are used as in input to design modules, which then produce new design instances as an output

Drop in replacement for instances in a schematic generator 

### Monday June 27

I'm at the point in the tutorial where I've installed the necessary python packages, and now it's instructing me on how to set up the 'configuration file. But I don't understand where the Configuration file is?

Actually wait, it seems that I need to make these config files, and that they aren't BAG specific. I just need to 'point' to them from within the BAG database, so that BAG knows where they are?

env_file, lvs_runset, rcx_runset, and cell_map all appear to be files that are used normally for Cadence work.

Okay, so then the page with 'BAG Configuration File' listed must be listing items that I should interact with through the BAG interactive session?

Okay, so do I need to import python, and then try to import the BAG library?

I think I understand now; I need to load the bag2 code base from within python3, and use the `setup.py` and `__init__.py` file as my starting point for library import.

To install this module, I really want to use pip, but as I have multiple python version on the remote, I should launch pip from the anaconda python environment:

https://stackoverflow.com/questions/40392499/why-is-m-needed-for-python-m-pip-install

https://stackoverflow.com/questions/25749621/whats-the-difference-between-pip-install-and-python-m-pip-install



# Installing BAG Environment

Start by getting the latest version of Anaconda, using this page:
https://linuxize.com/post/how-to-install-anaconda-on-centos-7/

This is the version of Anaconda I selected:
Anaconda3-2022.05-Linux-x86_64.sh

After anaconda was installed, I tried to setup the BAG3 code, but the source for the documentation didn't exist, so I also downloaded the BAG2 code, to try and generate the documentation. 

I got the following error trying to build the sphinx documentation:

`(base) bash-4.2$ make html`
`sphinx-build -b html -d build/doctrees   source build/html`
`Running Sphinx v4.4.0`
`making output directory... done`
`WARNING: sphinx_rtd_theme (< 0.3.0) found. It will not be available since Sphinx-6.0`
`
`
`Theme error:`
`no theme named 'sphinx_rtd_theme' found (missing theme.conf?)`
`make: *** [html] Error 2`
`
`
I think I could try installing this with pip, but because I'm relying on Anaconda for this installation, I searched for a method using anaconda.

https://anaconda.org/conda-forge/sphinx_rtd_theme

To install this package with conda run one of the following:
conda install -c conda-forge sphinx_rtd_theme 

Rerunning 'make html' I get the following: (It looks like it worked?

Build finished. The HTML pages are in build/html.

the documentation is working! It looks like I will be using a lot of Git, so I figured it would be best if I just updated my version of git:
https://computingforgeeks.com/how-to-install-latest-version-of-git-git-2-x-on-centos-7/

Getting ready:

* Update git version on asiclab008
* Configure easy ssh access with key authentication
* Building the documentation
* Mounting the remote drive as a SMB share, so that it's locally available on mac os (also considered StrongSync)





## Cadence Crashing Notes:

For Friday:

x Figure out if Cadence is actually crashing  (yes, it is!)
x test linux config, to find a way to not make it crash. (Just use IC618)

The current version of my redhat/centOS distribution can be checked via:
cat /etc/redhat-release

To check Cadence config:

/cadence/cadence/IC618/tools.lnx86/bin/checkSysConf IC6.1.8


output of this indicated that the following packages are needed:
sudo yum install 

	xorg-x11-fonts-ISO8859-1-75dpi
	redhat-lsb
	xorg-x11-server-Xvfb

Now everything is passing for IC618!

Let's examine our two startup scripts:

/faust/user/kcaisley/cadence/tsmc65/cdr/tsmc_crn65lp_1.7a_rd53b

	-starts with /bin/csh -f
	-setenv CDSDIR /cadence/cadence/IC617
	-finishes with 'virtuoso'

the other script is, completely:
	#!/bin/bash
	export DMC_RUN_DIR=$(pwd)
	export DMC_SOS_DIR=/faust/user/kcaisley/designs/dmc65
	/cadence/local/bin/tsmc_crn65lp_1.7a_rd53 &
examining this other nested script tsmc_crn65lp_1.7a_rd53
	
We want to create a new startup script for running with cadence, we will put it in our personal directories for now.

Changing the following lines:

setenv CDSDIR /cadence/cadence/IC617 -> setenv CDSDIR /cadence/cadence/IC618
virtuoso -> vituoso &

This works now, as long as I start it as an executable './script_name'


In hind sight, it looks like we might not have some support for IC617, including no ASSURA618 version.

Therefore, I should probably just use the startup script tsmc_crn65lp_1.7a_rd53, and call it from piotrs script, as this adds additional DMC-specific variables.

Nope, it just freezes when it starts, so I recopied the central script, made the two changes, and will work from there.


# Anaconda Install:

Cheatsheet for using Conda:
https://docs.conda.io/projects/conda/en/4.6.0/_downloads/52a95608c49671267e40c689e0bc00ca/conda-cheatsheet.pdf

Conda Environments Guide:
https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html

open anaconda navigator:
anaconda-navigator &

listing conda environments:
conda env list

changing between conda envs:
conda active bag3

create conda new env:
conda create --name [myenv]


# August 26:

to figure out current tty number
w


to show which tty are being used
ps -e | grep tty


to kill another tty
pkill -9 -t tty1

to show process numbers
ps -f

another tool which is useful for identifying and killing processes is top/htop.
i think that top can do everything htop can, but more easily
perhaps i should learn to play with top more in the future



# Thursday June 23 🍎🍎

`BAG_prim` is cadence library, with device used to build schematic template (called a schematic generator)

Schematic generators are schematic templates are used as in input to design modules, which then produce new design instances as an output

Drop in replacement for instances in a schematic generator 

# Monday June 27 🍎🍎🍎🍎🍎

I'm at the point in the tutorial where I've installed the necessary python packages, and now it's instructing me on how to set up the 'configuration file. But I don't understand where the Configuration file is?

Actually wait, it seems that I need to make these config files, and that they aren't BAG specific. I just need to 'point' to them from within the BAG database, so that BAG knows where they are?

`env_file`, `lvs_runset`, `rcx_runset`, and `cell_map` all appear to be files that are used normally for Cadence work.

Okay, so then the page with 'BAG Configuration File' listed must be listing items that I should interact with through the BAG interactive session?

Okay, so do I need to import python, and then try to import the BAG library?

Found this online:

>  *Package* - A folder/directory that contains `__init__.py` file. *Module* - A valid python file with `.py` extension. *Distribution* - How one *package* relates to other *packages* and *modules*.

I think I understand now; I need to load the BAG3 code base from within Python3, and use the `setup.py` and `__init__.py` file as my starting point for library import.

To install this package, [I really want to use pip](https://stackoverflow.com/questions/15724093/difference-between-python-setup-py-install-and-pip-install), but as I have multiple python version on the remote, I should launch pip from the anaconda python environment:

It still wasn't working, but it's because I had to target the directory explicitily, and not the `setup.py` file.

The [command](https://stackoverflow.com/questions/40392499/why-is-m-needed-for-python-m-pip-install) that appears to have finally worked for me is `python -m pip install /faust/user/kcaisley/bag3`

It's important to remember that a 'module' in Python is the name for any file ending in a .py extension.

It [appears](https://stackoverflow.com/questions/1471994/what-is-setup-py) that I could have actually just ran `pip install .` while inside the bag3 directory. Oh well 💁🏼‍♂️



Mark helped me understand that it's better to use conda virtual environements. We built a python environement with

​	`conda create -n bag3 python=3.9.12`

​	`conda activate bag3`

And then we reinstalled our BAG3 package in this virtual environement with the following command, run in our `/faust/user/kcaisley/bag3` directory:

- `python setup.py develop`

My next task is to figure out how to edit the configuration options of BAG, and how to start using it in an environement like JupyterNotebooks.

It's obvious that the BAG environment is running as a sqlite database, and that we need to initialize that database to interact with it.




# Other BAG thoughts:

Make sure all packages are installed as listed in the BAG_framework documentation. The two needed, sqlitedict and openmdao are installed via pip, not anaconda, as they aren't on the conda repo (but are on Pypi repo)

lauch the setup.py file with "pip install .", while inside the folder. As stated online, it's better to avoid directly calling the setup.py file.


Create conda environment:
conda create --name bag

conda activate bag

Install in current env:
conda install .....

conda info


Getting the repository:
`git clone -b develop https://github.com/ucb-art/bag.git --recurse-submodules`


Figuring out what changes I've made to local:
git status
git log
git info


git fetch --dry-run
git fetch --dry-run --all
git remote update
git show-branch *develop

git config --global user.name "Kennedy Caisley"
git config --global user.email kcaisley@uni-bonn.de
git config --global core.editor vim

To copy down submodule, if forgot to do during cloning:
git submodule update --init --recursive --remote

ERROR:
Cloning into 'pybag'...
Permission denied (publickey).
fatal: Could not read from remote repository.

Please make sure you have the correct access rights
and the repository exists.
Clone of 'git@github.com:ucb-art/pybag.git' into submodule path 'pybag' failed





To reset all unstaged/uncommitted change:
git checkout .


git pull = git fetch + git merge


https://github.com/ucb-art/pybag.git


# August 27:

List of packages:

apipkg appdirs attrs backcall cycler decorator distlib execnet filelock h5py importlib-metadata ipython ipython-genutils jedi Jinja2 kiwisolver MarkupSafe matplotlib more-itertools networkx numpy packaging pandocfilters parso pexpect pickleshare pluggy prompt-toolkit ptyprocess py Pygments pyparsing PyQt5 PyQt5-sip pytest pytest-forked pytest-xdist python-dateutil pyzmq ruamel.yaml ruamel.yaml.clib scipy six sortedcontainers traitlets virtualenv wcwidth zipp zmq



# August 28:

I need to make sure that I use BAG_framework as my directory name, and not just BAG.


Delete the /designs/demo_ffmpt/ file and start over, by remaking a new empty one.

First, start a new project repo with these steps:
https://github.com/ucb-art/cds_ff_mpt-bag3

Then start up cadence and jupyter notebook with steps at the end of:
https://github.com/ucb-art/BAG2_cds_ff_mpt/

(This may not be 100% accurate.)



# Workspace setup phase:

Several differnt things need to be modified:

* Consult the bag2 ffmpt library to look at the configuration for Jupyter that is read in, before starting
  * `ipython_config.py` is stored inside the `.ipython\profile_default` directory. The bag3 ffmpt library was only the primitives directory on the lower level, but it does contain this file at `../../cds_ff_mpt/workspace_setup/ipython_config.py`. But the bag3 ffmpt library didn't have the xbase 
* the `ipython_config.py` file call

* `bag_config.yaml`
* `bag_submodules.yaml`
* `ipython_config.py`
* `leBindKeys`


## Needed changes:

In `./cds_ff_mpt/workspace_setup/ipython_config.py`, needed to a

```
## List of files to run at IPython startup.
c.InteractiveShellApp.exec_files = [
    os.path.join(os.environ['BAG_WORK_DIR'], 'bag_startup.py'),
]
```

This then calls `./bag_startup.py`, which I had to create, as is design specific to let Jupyter Notebook/Python know where to look. It's contents was:

```
# -*- coding: utf-8 -*-
import os
import sys

sys.path.append(os.environ['BAG_FRAMEWORK'])
sys.path.append(os.environ['BAG_TECH_CONFIG_DIR'])
sys.path.append(os.path.join(os.environ['BAG_WORK_DIR'], 'BAG2_TEMPLATES_EC'))
sys.path.append(os.path.join(os.environ['BAG_WORK_DIR'], 'BAG_XBase_demo'))
sys.path.append(os.path.join(os.environ['BAG_WORK_DIR'], 'bag_advanced_examples'))
sys.path.append(os.path.join(os.environ['BAG_WORK_DIR'], 'bag_testbenches'))
```

This, of course, then leads me to consider if I have all the necessary project files mentioned above put in place.
[x] BAG_FRAMEWORK (bag code base)
[x] BAG_TECH_CONFIG_DIR (BAG PDK primitives folder, containing PDK softlink, among other things)
[X] BAG2_TEMPLATES_EC ... had to grab this online, added via simple git clone: https://github.com/ucb-art/BAG2_TEMPLATES_EC.git
[X] BAG_XBase_demo.... https://github.com/ucb-art/BAG_XBase_demo/tree/master
[X] bag_advanced_examples... same, had to clone from https://github.com/ucb-art/bag_advanced_examples.git
[X] bag_testbenches... yep, got from https://github.com/ucb-art/bag_testbenches.git

This completed now, but I still have unanswered questions about several other files. Explaining everything below:

## Chronological origin of files in top level directory, during installation:
Following steps from: https://github.com/ucb-art/cds_ff_mpt-bag3

#### Manually making new git repo, and adding git modules, and updating them

BAG_framework           manually git moduled from my local copy

cds_ff_mpt-bag3         manually git moduled from local copy (this is primitives tech repo)

.gitmodules

.git

#### Running install.sh in workspace directory (many of these files had to be prepared)

`bag_submodules.yaml` copied from worksapce setup, via install.sh

`.cdsenv.personal` copied from worksapce setup, via install.sh

`.cdsinit.personal` copied from worksapce setup, via install.sh

`bag_config.yaml` link from workspace setup, via install.sh, multipurpose config file, used by `setup_submodules.py` during installation, and during BAG runtime.

`.bashrc` link from workspace setup, via install.sh

`.bashrc_bag` link from workspace setup, via install.sh

`.cdsenv` link from workspace setup, via install.sh

`.cdsinit` link from workspace setup, via install.sh

`cds.lib.core` link from workspace setup, via install.sh, included by `cds.lib` on startup

`.cshrc` link from workspace setup, via install.sh, unused

`.cshrc_bag` link from workspace setup, via install.sh, unused

`display.drf` link from workspace setup, via install.sh

`.gitignore` link from workspace setup, via install.sh

`models` link from workspace setup, via install.sh (is a directory)

`pvtech.lib` link from workspace setup, via install.sh

`leBindKeys.il` link from workspace setup, via install.sh

`start_tutorial.sh` link from workspace setup, via install.sh

`tutorial_files` link from workspace setup, via install.sh

`.ipython` created by install.sh (is a diretory, which contains ipython_config.py, which in turn is a link from workspace setup, via install.sh)

`gen_libs` created by install.sh

`cds.lib` created by install.sh (just points to cds.lib.core, which in turn points to )

`run_bag.sh` link from BAG framework, via install.sh, core script which actually runs BAG, called from core BAG scripts.

`setup_submodules.py` link from BAG framework, via install.sh, executed in the next step to actually 

`start_bag.il` link from BAG framework, via install.sh, written in SKILL, seems to call `virt_server.sh`, which in turn starts stuff in framework.

start_bag.sh link from BAG framework, via install.sh, very similar to `run_bag.sh` but appears unused

`virt_server.sh` link from BAG framework, via install.sh, called by `start_bag.il`, contains 1-line command to start server in BAG framework.

#### Running setup_submodules.py, which references bag_modules.yaml, both copied/link in the step above.

bag3_analog             automatic git module added by setup_submodules.py, from bag_modules.yaml

bag3_digital            automatic git module added by setup_submodules.py, from bag_modules.yaml

xbase                   automatic git module added by setup_submodules.py, from bag_modules.yaml

.bashrc_pypath          created by `setup_submodules.py`; contains `PYTHONPATH` env var python copies to sys.path on startup. Later exported by `run_bag.sh` and `start_bag.sh`.

bag_libs.def            created by `setup_submodules.py` with plaintext list of OA BAG libraries.

cds.lib.bag             created by `setup_submodules.py`, and included by cds.lib.core, which in turn is included by cds.lib.core

#### This finishes all the general BAG3 workspace setup, but for the tutorial, more was needed:

Following steps at at https://github.com/ucb-art/BAG2_cds_ff_mpt/

`BAG2_TEMPLATES_EC` manually git cloned from Github

`bag_advanced_examples` manually git cloned from Github

`bag_testbenches` manually git cloned from Github

`BAG_XBase_demo` manually git cloned from Github

`bag_startup.py` manually created, and made ipython_config.py call it, based on BAG2 example, adding libraries to pythonpath

#### Finally, starting up Virtuso

0. conda activate bag
1. source .bashrc
2. virtuoso &
3. ./start_tutorial.sh     this starts up iPython/Jupyter, which in turn calls the `.ipython/ipython_config` file, which then calls bag_startup.py

libManager.log          Log file created by Cadence Virtuoso on each startup.

## PYTHONPATH and sys.path understanding:
https://www.devdungeon.com/content/python-import-syspath-and-pythonpath-tutorial

## Changes to accomodate:
* renamed ~/eda/ to ~/packages/. Best to check for issues
* moved demo_ffmpt folder to ~/cadence/ folder, rather than /designs/. Check for issues.
* moved cds_ff_mpt-bag3 to ~/packages/ from ~/cadence/
* moved cds_ff_mpt_v_1.1 to ~/packages/ from ~/cadence/			so had to update PDK symlink.

## Potential outstanding problems:
* My reference to the cds_ff_mpd-bag module is broken in git, as it's still looking for an origin master in ~/cadence/. See above, as it's moved to ~/packages/
  * As a solution for now, I've just deleted the remote reference. It shouldn't really matter, as this is the only project I'll need which will use this cds_ff_mpt PDK
* Is anything calling `.bashrc_pypath`? I know `run_bag.sh` exports it; but I don't see the latter running anytime?
* Will the Jupyter notebook embedded in VScode read my `.ipython/profile_default/ipython_config.py` file on startup, like a standard Jupyter notebook would?


I may just delete all references to git, and move on with my life in this set of modules.


## Friday Sep 9
I need Jupyter to know where all my files are. Opening a Jupyter notebook in vscode will allow me to select a Anaconda environment, but it doesn't easily let me run the .ipython file, which calls the `bag_startup.py` to append to my

Once my Jupyter notebook in started in vscode, I can't simply call bash scripts to modify the environment variables. Plus, the sys.path has already been initialized by the integrated ipykernel upon startup, and no more interaction with the environement variable ipython

Jupyter comes with various components. The notebook server is language agnostic, and servers as the front end. iPython is a terminal only front end, which isn't used if I'm using the GUI jupyter notebook. The kernel is used by both, but is language specific.

I need to understand the difference between the notebook server and the jupyter kernel. It seems the kernel is what needs to be associated with my anaconda env, and not the notebook server?? These are shown in two different places, Kernel in the top left, and server in the bottom right.

I want to server to be started in a way that it is concious of all the environement variables I export when also starting cadence.

I think part of the problem I was facing before was that the local jupyter server was starting with it's home following the jupyter notebook symlink. And so this causes problems, becuase I 

To start jupyter in a certain environment, simple follow basic method here, before he introduces his package: http://stuartmumford.uk/blog/jupyter-notebook-and-conda.html

(as I don't need to switch my env dynamically)



## Monday Sep 12
Figure out why does pybag.core not exist? There is a core.pyi file and core.cpp file. Maybe it's pointing at a C function!
Seach 'How to import C function in 

An amazing note on relative imports:
https://stackoverflow.com/questions/14132789/relative-imports-for-the-billionth-time




## Tuesday Sep 13
My virtual env setup is really confusing the hell out of me. I decided to strip out Anaconda and just use Python -m venv.
This can can't cross versions though, and so I need to install the latest version of python on my machine, 3.10, as i only have 3.6 as the system python....
Actually, I tried following this tutorial: https://linuxstans.com/how-to-install-python-centos/    but it didn't work

A method that seemed to work istead was to create a local install of python:
https://codeghar.wordpress.com/2013/09/26/install-python-3-locally-under-home-directory-in-centos-6-4/

This works. `which python3.10` points in my PATH.

Except now, the version of OpenSSL that I have doesn't work with Python3.10, and so I need to instead install python 3.9.14 with this method.

Creating a venv: https://docs.python.org/3/library/venv.html
python3 -m venv /path/to/new/virtual/environment

activating a venv: source venv/bin/activate

installing packages: pip install -r ./requirements.txt

for some reason, numpy, scipy, matplotlib, and m5py needed to be installed manually, as they were needing compiling and crashing if included in the above file.

This all works now though, in my new venv.

## Wednesday Sep 14
No I'm going to copy over the bag version, and see if I can get this sorted out, with the pybag.core problem.

I tried installing the packages pybind11, into pybind_generics, into pybag into bag, in that order, but I started hitting compile errors about Cmake. My Cmake version is okay, but apparently GCC was also outdated:

https://stackoverflow.com/questions/47238577/target-requires-the-language-dialect-cxx17-with-compiler-extensions-but-cma

However, at the bottom of this document, it points out that Centos has a package called devtoolset-7. By checking the command 'scl -l' I found that I already have this package. Running 'scl enable devtoolset-7 bash' was enough to get the gcc version updated! I think it just applies to the current terminal though. This is explained here:

https://www.softwarecollections.org/en/scls/rhscl/devtoolset-7/

## Thursday 15 September
How can I deal with installing Pybag? Is it a wheel package?

## Friday 16 Sep
I inspected the logs from running `pip install -e .` and found complaints about the packages `fmt` and `spdlog` being missing. I installed the two of these from yum, and tried to proceed. CMake has stopped complaining about fmt, but still is asking for spdlog to be located.

A useful command for searching all files for some text: `grep -rnw '/path/to/somewhere/' -e 'pattern'` ... For example: `grep -rnw '.' -e 'CMAKE_PREFIX_PATH'`

Cleaned out my venv folder once again, and tried to follow the instructions [from yrrapt](https://github.com/yrrapt/bag/tree/develop)

I've recloned the bag3 develop branch on two separate machines, one with CentOS 7.9 and the other with Ubuntu 20.04. On each, I built a fresh python venv, and tried compiling the bag and pybag modules. In each case, the bag modules built properly, but the sub-module pybag is problematic. I've tried to read the CMakeLists.txt and follow the error build.log, to find clues about what packages might be missing or variables not configured, but no luck so far. My machines have the following:

* CentOS 7.9
* Python 3.9.14 (built from source)
* CMake 3.17.5
* fmt 8.22
* Boost 1.53.0
* gcc 7.3.1

* Ubuntu 20.04
* Python 3.8.10
* CMake 3.16.3
* fmt 8.30
* Boost 1.71.0
* gcc 9.4.0

Running `python -m pip install .` , I'm seeing build logs that contain the error below.

## After, Installed CMake with apt, wheel with pip, sudo apt install libboost1.71-all-dev, but still got:
```
  ERROR: Command errored out with exit status 1:
   command: /home/silab/delete_me_please/bag/venv/bin/python -u -c 'import sys, setuptools, tokenize; sys.argv[0] = '"'"'/tmp/pip-req-build-allzw648/setup.py'"'"'; __file__='"'"'/tmp/pip-req-build-allzw648/setup.py'"'"';f=getattr(tokenize, '"'"'open'"'"', open)(__file__);code=f.read().replace('"'"'\r\n'"'"', '"'"'\n'"'"');f.close();exec(compile(code, __file__, '"'"'exec'"'"'))' bdist_wheel -d /tmp/pip-wheel-2t7f35c2
       cwd: /tmp/pip-req-build-allzw648/
    CMake Error at cbag/CMakeLists.txt:94 (find_package):
      Could not find a package configuration file provided by "fmt" with any of
      the following names:
    
        fmtConfig.cmake
        fmt-config.cmake
    
      Add the installation prefix of "fmt" to CMAKE_PREFIX_PATH or set "fmt_DIR"
      to a directory containing one of the above files.  If "fmt" provides a
      separate development package or SDK, be sure it has been installed.
```

I think I need to point CMake toward my fmt and spdlog installs. Will investigate further.


## Some quick notes on setting ENV variables:

To set variable only for current shell:
`VARNAME="my value"`

To set it for current shell and all processes started from current shell:
`export VARNAME="my value"`      # shorter, less portable version

To set it permanently for all future bash sessions add such line above to your .bashrc file in your $HOME directory.

[Can be found here](https://askubuntu.com/questions/58814/how-do-i-add-environment-variables)

To add something to the beginning of a path variable:
`export CMAKE_PREFIX_PATH=____:${CMAKE_PREFIX_PATH}` where ___ is the thing you want to add


## To get libfmt:

find_package did not find the CMake package of fmt. It comes with the -dev variant of fmt's Ubuntu package. If you check the CI code, it installs libfmt-dev via apt:

`sudo apt install libfmt-dev`

Now it's pretty clear that I need the .cmake file from this package, and to figure out where it is I can use:

`dpkg -L libfmt-dev`

Yes! Now I can just get this file:

`/usr/lib/x86_64-linux-gnu/cmake/fmt/fmt-config.cmake`

I'm not sure what 'depth' I have to point it at, but I will try all the way to /fmt. (I was right)

Looks like I will also be missing spdlog, so I will installed the development flavor with:

`sudo apt install libspdlog-dev`
`dpkg -L libspdlog-dev` which gives: `/usr/lib/x86_64-linux-gnu/cmake/spdlog/spdlogConfig.cmake`

Will point at this below


## Let's try it with yrrapt's official repo, just making sure we enable OA:

* `git clone -b develop https://github.com/yrrapt/bag.git --recurse-submodules`
* From inside `bag` dir `python3.9 -m venv ~/designs/bag3_pll_verfication/venv`
* `source venv/bin/activate`
* `vim pybag/setup.cfg` and deleted line `openaccess-disable = True` so that it could build with open access
* `export PYBAG_PYTHON=$HOME/temp/bag/venv/bin/python`
* `python -m pip install wheel` to install wheel packages
* `python -m pip install .` to build bag package
* `export CMAKE_PREFIX_PATH=/usr/lib/x86_64-linux-gnu/cmake/fmt:${CMAKE_PREFIX_PATH}`
* `export CMAKE_PREFIX_PATH=/usr/lib/x86_64-linux-gnu/cmake/spdlog:${CMAKE_PREFIX_PATH}`
* `export CMAKE_PREFIX_PATH=/usr/lib/x86_64-linux-gnu/cmake/yaml-cpp:${CMAKE_PREFIX_PATH}`
* cd inside pybag dir, and `python -m pip install .` again to build pybag package

Nope, still errors:

```
WARNING: building without OpenAccess support.
  -- Found Boost: /usr/lib/x86_64-linux-gnu/cmake/Boost-1.71.0/BoostConfig.cmake (found version "1.71.0") found components: serialization
  CMake Error at pybind11_generics/CMakeLists.txt:46:
    Parse error.  Expected a command name, got unquoted argument with text
    "<<<<<<<".
```

Checking this file, we find that in fact, that should probably be deleted haha.


grep -rnw '.' -e 'CMAKE_PREFIX_PATH'


```
  CMake Error at pybind11_generics/pybind11/tools/pybind11Tools.cmake:17 (find_package):
    By not providing "FindPythonLibsNew.cmake" in CMAKE_MODULE_PATH this
    project has asked CMake to find a package configuration file provided by
    "PythonLibsNew", but CMake did not find one.
  
    Could not find a package configuration file provided by "PythonLibsNew"
    with any of the following names:
  
      PythonLibsNewConfig.cmake
      pythonlibsnew-config.cmake
  
    Add the installation prefix of "PythonLibsNew" to CMAKE_PREFIX_PATH or set
    "PythonLibsNew_DIR" to a directory containing one of the above files.  If
    "PythonLibsNew" provides a separate development package or SDK, be sure it
    has been installed.
  Call Stack (most recent call first):
    pybind11_generics/pybind11/tools/pybind11Common.cmake:201 (include)
    pybind11_generics/pybind11/CMakeLists.txt:169 (include)
```

Now it's asking me to find a .cmake file for PythonLibsNewConfig, but apt list doesn't reveal anything to install.

But this already lives at ..... `./pybag/pybind11_generics/pybind11/tools/FindPythonLibsNew.cmake`

Can I try to hack it?
`export CMAKE_PREFIX_PATH=/home/silab/temp/bag/pybag/pybind11_generics/pybind11/tools:${CMAKE_PREFIX_PATH}`

Okay... that's enough for today.


Compacting the lines from fefore: * `export CMAKE_PREFIX_PATH=/usr/lib/x86_64-linux-gnu/cmake/fmt:/usr/lib/x86_64-linux-gnu/cmake/spdlog:CMAKE_PREFIX_PATH=/usr/lib/x86_64-linux-gnu/cmake/yaml-cpp:${CMAKE_PREFIX_PATH}`

## Sat 17 Sep

Perfect. Building your modified repostory I was able to avoid the CMake issues, after I installed libspdlog-dev , fmt-config, and libyaml-cpp-dev to provide the necessary .cmake files) 

Simpler than manually adding them to the CMake path via, as I was doing before:
export CMAKE_PREFIX_PATH=/usr/lib/x86_64-linux-gnu/cmake/fmt:/usr/lib/x86_64-linux-gnu/cmake/spdlog:/usr/lib/x86_64-linux-gnu/cmake/yaml-cpp:${CMAKE_PREFIX_PATH}

* Case study to be [shared](https://ieeexplore.ieee.org/document/9576866)
* In above case sutdy did they get this working? Maybe check with Mirjana/Abassi first? Did they get the Open Access stuff?
* Ask yrrapt about "<<<<<<" HEAD" bug, and also about the FindPythonLibsNew.cmake bug.
* Ask yrrap how I can contribute, and if I should move discussions into the Git log tracker.

## Sunday 18 Sep
* I really want to apply for this competition: https://github.com/sscs-ose/sscs-ose-code-a-chip.github.io
* Its submission deadline is November 21, which would give me a perfect outlet for completing a functioning Jupyter notebook in a reasonable amount of time. I've already been here for 133 days, and I feel as though I haven't accomplished anything. For now though, don't tell Hans about this conference.
* I want to learn how to use BAG, because OpenFASOC isn't really meant to work with analog chip design. The issue is that BAG3 doesn't support open source tools, and that access for the necessary OpenAccess library is apparently very difficult to get anyways.
* I want to use BAG3, as BAG2 is not going to be further developed. My main question then is what are the major differences between the two? I'm meeting with Thomas tomorrow, and he seems to understand the better the status of BAG.
* So what if I did the following.... built a generator which is able to produce a functioning VCO layout.. or even PLL, and do it in a way that uses the toolchain of BAG3? If I accomplished this, I would be the first person to successfully use BAG3 outside of Berkeley. Other papers, few of which exist, have used BAG2 only.
* The issue now, is that I'm not sure if I can really build a functioning tool chain with BAG3. It doesn't support open source tools yet, and getting it to even work with Cadence seems nigh impossible for those outside Berkeley/BlueCheetah. I should confirm this by reading papers, tomorrow, of course. I think I can get through a lot of material by the time I meet with Thomas Parry at 3pm.
* One thing I'm realizing though is that a lot of the design process doesn't really require me to have a function BAG installation. XBase seems like it is very tied to BAG, but I think LayGO2 is less BAG-centric? I should really check with JD Han to figure out how I'm expected to produce a layout in 65nm if I don't have this special Cadence OpenAccess library. Perhaps I can w
* Mirjana is a member of the committee which decides the winners of the code-a-chip competition, and so if I were to develop a notebook with her guidance, then there is a *very* good chance of being accepted.
* Another note, I should consider giving a group presentation on Sep 29th, because I told Hans that I would. Maybe I should break this promise though. I should explain to Hans that understanding the status of all this open source code has taken significantly more time than I anticipated. Explain that I've made connections with two important people though!
* If I don't use BAG, then how do I work with the schematics needed to compare against LayGO layouts during LVS?
* If I want to design a process portable generator, do I target the layout constraints of a small-fill factor 28nm design, and then expect it to scale to a 65nm, or even 130nm process? I think this makes more sense, as there are less degrees of freedom in 28nm.
* Can this tool (LayGO2) be used in isolation, without BAG?  I think it can!
* One thing that is amazing about this, is that Laygo is written entirely in Python, and so I shouldn't have any huge problems getting it to run. No compilation required, etc. It's a 1-way path for generation.
* Also, much of the design work 'back of the envelope work' can be done in Python scripts, without any circuit simulation at all. But, then, once I get to circuit simulation, I wonder if I am able to run parasitic extraction with Magic on open source Tools on 65nm? If think seems to work well, then I think I can trust it enough to do large cell design without re-running a DRC/LVS ruleset in Calibrew. To be double sure, I can simply run a final Parasitic extraction and DRC and LVS test against Cadence.
* There's also no reason why my schematics would necessarily need to be be designed in cadence source tools, right? If I am looking for process portability though, I think that I need to use something like BAG, where I am am able to make schematic and test bench generators.
* So one question is: If I'm not using BAG... how do I achieve process portability in my schematics, such that I can quickly compare them against laygo? I think that the basic Laygo workflow uses hand-crafted primitives, which aren't process agnostic. On the other hand, I think that Lay
* I can slowly replace every part of the 65nm workflow in Cadence, with equivalents in 65nm technology.


## Monday 19 Sep
* I think the functionality is primarily good for the Analog Chip Bottom, where the SAR ADC, the Bandgap references, the Analog Multiplexer, and monitor ADCs, the Calibration Injection Voltages, the Serdes, and the CDR and TX/RX Circuits live. This is where documentation, reusability, comprehension, and testability are much, much more important that cutting edge performance.
* Generators are also best suited for instances where you will need to do many different iterations, in possilbly different
* BAG3 is a major upgrade, as it reworks the way layouts are generated in the tool. There is no AnalogBase/DigitalBase constructs anymore, just MOSBase.
* As long as devices share the same 'row' information, you can tile NMOs, PMOS, and TAPs right next to each other.
* Don't specify the width of each wire, have 'wire classes' which have preset widths.
* MOSBase just places the drawn transistors, and isn't necessarily DRC clean. MOSBase Wrapper then comes back and fill in the dummy devices, extension regions, and boundaries.
* In the YAML file, we have to define the properties of each row. It's more complicated in BAG3.
* The layouts may only have one type of tile, or you may have a more complicated multi-tile type layout.
* In BAG2 AnalogBase, you only have access to M3 and 4, (maybe more in Digital Base). But in BAG3
* Zhaokai Liu showed a BAG3 repository example on Github, but it's a private repo right now, and we can't see it.
* Bulk contacts are completed with TAP devices in BAG3.
* Different length devices are implemented with stacking devices, to increase effective channel length.
* To place transistors, you first specify the tile you are placing in, and then use XY coordinate (e.g.) within the tile. It defaults to position 0 for X and Y.
* BAG2 only supports ADEXL. BAG3 doesn't support any ADE package, Assembler, XL, or otherwise. Design variables are returned, but Stimuli and Data post processing must be done in Python, as we are just directly  calling Spectre.
* Notice how all the BAG developers are also using BAG to build real circuits, meaning they have real design cases.
* BAG3 includes BAG2 
* Behavioral models of base circuits are completed manually, but then the hierarchical arrangement of them is done automatically, tracking whatever is done at in the real schematic implementation.

#### Meeting with Thomas Parry
* Marco in Finland
* Marjana is moving to Infineon
* Infineon guys also putting money into
* Matthias is from Klayout, and he was able to implement a lot of the functions for BAG2 compatibility very quickly.


## Tuesday 20 Sep

#### continued with Ayan Biswas:
* Manually create leaf behavioural cells, and then allow BAg to generate the heirarchy. 
* One thing is that schematic and modeling hierarchy should be identical, but layout heirarchy my be different, as for example, a large chain of CS amplifiers would generated all the resistors in one heirarchy.
* 

#### Recap:
To be honest I have not produce much at all, but it hasn't been for lack of trying or time invested. It turns out that this is way harder than I thought.
I've worked on:
* BAG project repository organization and setup
* Python package management
* Review of OOP programming in Python (To understand BAG codebase)
* Jupyter Notebook Usage and Server Setup
* CMake, Make, and other build related tooling (for building Python, BAG, PyBAG, XBase, etc)
* Tools are 'complete' but not distributed in a complete form, so they have to be built

One thing that is a bit annoying is that I have several different places where I could develop my code. I think to submit to CAC23 I need to have a GitHub repo.
My personal Github account (kottenforst, or kennedycaisley, or kcaisley?)

Things to understand from Hans:
Can the models of TSMC65 be using in ngSPICE?

Can LayGO2 be used without BAG? 

I think that the goal of the MOSAIC group is to modify the BAG3 codebase such that it can be used with open source tools like Xschem/Magic/Klayout. This is different from the goals of my group.

My goal of my meeting with Mirjana is to figure out where my design work can overlap with the interests of MOSAIC. I don't have the time and the energy and 


You can use BAG3 for Measurements, without needing to have the openaccess library tooling. I think that I should maybe start here, and build a BAG3 test bench for my PLL is 65 nm.

Skill is signifigantly slower than OA, but Mario Weiss also pointed out that GDS based generation is available in BAG2/BAG3. Some flows work without Virtuoso, but some functions require OA layout.

#### Meeting with Marjana:
Programatic IC design is necessary
Talk to Chris Mayberry, BAG3, as he may be interested in helping
Watch his 'Cascode Labs Presentation'
UC Berkeley prof Vladamir S. it coming to Europe, Marjana may be able to talk with him

#### Meeting with Hans:
* Recap what I've been working on, and what I've learned:
	* Discovered a whole bunch of disorganized project folder for BAG2, BAG3, Xbase, Laygo, Laygo2
	* BAG project repository organization and setup (built my own repository)
	* Python package management (built my own environment)
	* Jupyter Notebook Usage and Server Setup
	* OOP programming in Python (To understand BAG codebase)
	* CMake, Make, and other build related tooling (for building Python, BAG, PyBAG, XBase, etc as Tools are not distributed built)
	* Got very stuck 2 weeks ago, as I had spent many weeks now reading the code base, and trying to debug. I understand how the tool worked alot better, but I couldn't actually 'run' it full on anything.
	* Went online (open source silicon slack channel), started connecting with people, and finding resources. I understand the lay of the land a lot better now, and the uses/limits of the tools, but I haven't made much progress on actual work (only basic prototyping of PLL specifications in Python).
	* What I need help with is technology evaluation, and where to focus my efforts? I'm am very serious about this programmatic IC design, but it's early days. We for some of the features, we would be the first externel adopters (not Laygo1/2 or Bag2 though, but for BAG3 yes.)

State of the art:

BAG2
Workflow: Schematic in Cadence with generic primitives, connects with Cadence over SKILL API. Allows use of Laygo or Xbase.
Status: Stable but slower, and no longer developed by UC berkeley. It does however has 

BAG3
Workflow: Allows use of up
Status: Streamlined, actively developed, several features improved, and many aspects of the workflow have bee 


People:

Chris Mayberry
Marjana
Thomas Parry

In git, what is main, origin, HEAD, 


origin is the default name given to the remote repository that a local repository is tied to. One can change this name, and can also add two different remotes to pull changes from. This is why we need aliases for remote repositories, so that we can distinguish between two remote codebases that are often nearly identical.


#BAG3 Thoughts:


I think the functionality is primarily good for the Analog Chip Bottom, where the SAR ADC, the Bandgap references, the Analog Multiplexer, and monitor ADCs, the Calibration Injection Voltages, the Serdes, and the CDR and TX/RX Circuits live. This is where documentation, reusability, comprehension, and testability are much, much more important that cutting edge performance.

BAG3 is a major upgrade, as it reworks the way layouts are generated in the tool. There is no AnalogBase/DigitalBase constructs anymore, just MOSBase.

As long as devices share the same 'row' information, you can tile NMOs, PMOS, and TAPs right next to each other.

Don't specify the width of each wire, have 'wire classes' which have preset widths.

MOSBase just places the drawn transistors, and isn't necessarily DRC clean. MOSBase Wrapper then comes back and fill in the dummy devices, extension regions, and boundaries.

In the YAML file, we have to define the properties of each row. It's more complicated in BAG3.

The layouts may only have one type of tile, or you may have a more complicated multi-tile type layout.

In BAG2 AnalogBase, you only have access to M3 and 4, (maybe more in Digital Base). But in BAG3
Zhaokai Liu showed a BAG3 repository example on Github, but it's a private repo right now, and we can't see it.


Hi Thomas and Mirjana,

After discussing with my co-workers + advisor, we've decided we want to identify and try acquiring, through official channels, the OpenAccess library used by BAG3 to interact with Virtuoso schematic and layout cellviews. If we succeed, we will document the steps we took to acquire the package, and share that knowledge with other groups. For those lacking the time or connections to acquire the dependency themselves, we would also be willing to take on the mantle of regularly compiling and distributing BAG3 with pybag/cbag binaries built against the OpenAccess component. Assuming it's legally allowed, I wonder if this would be useful for the subset of people primarily interested in just being users of BAG3 with Cadence.
As the above step could take considerable time with NDAs, in parallel, I want to figure out if the component of BAG3 responsible for launching SPECTRE/SPICE simulations and returning the results is able to be used without the OpenAccess component. If so, I will compile a version of BAG with this reduced-functionality. Assuming I manage to make this work, I want to then use this for a project:

My group invested significant time (4 revisions) designing this ^ 65nm clock-data recovery circuit for high radiation environments (total ionizing dose >1 Grad). The original design was done with a traditional industry workflow (Cadence Virtuoso, Calibre DRC/LVS/PEX, ADE XL testbenches, Spectre Simulation). Now that we have a silicon-verified design, though, we'd like to record that design knowledge in a BAG3 script for better documentation, modifications, and porting. Assuming BAG3's simulation component can be used as-in, I am going to start by re-implementing our verification framework for the PLL with the BAG3 API, and open source it.






# To Do

## Backlog

- [ ] Generate pre and post-extracted netlist of 65nm VCO
- [ ] Create a basic simulation of inverter, using tradition GUI Virtuoso Schematic/Layout -> PEX Extraction -> ADE XL -> Spectre -> ADE XL viewer.
- [ ] Reproduce basic INV simulation with SPICE netlist -> SPECTRE Command Line -> Flat File Output
- [ ] Reproduce basic INV simulation with: SPICE netlist -> Jupyter Notebook -> BAG3 -> SPECTRE -> BAG3 -> Jupyter Notebook.
- [ ] Start assembling list of tests to run on VCO.

## In Progress
- [ ] Identify what OpenAccess library is needed to properly compile and operate BAG3 (make issue of this)
- [ ] Move my venv over from my other venv, or just re-setup
- [ ] Figure out the ask to Ayan Biswas, Thomas Parry, or Marjana, to try and figure out exactly 'what' OpenAccess library is missing.

## Completed


# Notes
Should only have a vscode and firefox window open. Nothing more.
No readme file until done.
No figures or equations until done (just look in Razavi)


A decorator '@' is a design pattern in Python that allows a user to add new functionality to an existing object without modifying its structure. Decorators are usually called before the definition of a function you want to decorate. They support operations such as being passed as an argument, returned from a function, modified, and assigned to a variable. This is a fundamental concept to understand before we delve into creating Python decorators.
This tutorial explains it best: https://www.datacamp.com/tutorial/decorators-python

The class `SimProcessManager` an implementation of :class:`SimAccess` using :class:`SubProcessManager`
I'm not really even sure what this means.
`SubProcessManager` looks like it batches calls in an concurrent/asyncrhonous mannager, using the asyncio Python standard lib

But it looks like we would never call these latter two components, as they are lower level. Inside of the Spectre.py function, the 

# OpenAccess Dependency Research
A static library format for OA would require the rest of BAG be built with the the same version of build tools as it. Build tools are availabe from the CentOS software collections, in particular the devtoolset-7 through devltoolset-11 packages. These can be installed from yum, and examined with:

`sudo yum list devtoolset\*`

As each component is also available as it's own package, we can examine package contents via:

`sudo yum list devtoolset-8\*`

You can get started in three easy steps:

1. Install a package with repository for your system:
On CentOS, install package centos-release-scl available in CentOS repository:
$ sudo yum install centos-release-scl

On RHEL, enable RHSCL repository for you system:
$ sudo yum-config-manager --enable rhel-server-rhscl-7-rpms

2. Install the collection:
$ sudo yum install devtoolset-8

3. Start using software collections:
$ scl enable devtoolset-8 bash

At this point you should be able to use gcc and other tools just as a normal application. See examples below:

$ gcc hello.c
$ sudo yum install devtoolset-8-valgrind
$ valgrind ./a.out
$ gdb ./a.out

As Ayan points out, his .bashrc points to the locations of the various libraries. I notice that the version of OA is 22.60, which appears to be built against GCC 8.3, which is contained in devtoolset-8.

It looks like OA 22.60 is maybe the most recent version? https://si2.org/tag/oa-22-60/. In either case, it's obvious that the version matters.


## NEXT STEPS
Contact Thomas first thing, share what I learned from Ayan, including imports in .bashrc, and what version of GCC is necessary, and version of OA.
Next read the 6-7 tabs I have open about building from C++...

[link](https://gist.github.com/gubatron/32f82053596c24b6bec6)
[link](https://www.reddit.com/r/cpp_questions/comments/qmd5hf/whats_the_difference_between_include_directory/)
[link](https://www.learncpp.com/cpp-tutorial/introduction-to-the-compiler-linker-and-libraries/)
[link](https://www.learncpp.com/cpp-tutorial/header-files/)

## Work in October

oa_v22.60.063

Line 37 in this file: https://github.com/ucb-art/cds_ff_mpt-bag3/blob/master/workspace_setup/.bashrc



### Executables, Libaries, etc

Both libraries and executables are compiled non-human readable binaries, but the difference is that an executable will be intended to be used by itself and have a defined starting point, whereas code compiled as a library will have multiple extry points, and will be intended to be used as part of a larger project.

When linking in a library, whether or not is static vs dynamic matters. In either case though, code described as 'libraries' are not executible on their own.![img](https://miro.medium.com/max/537/1*QI-LJC2bVLwDMT9VTpnjtg.png)

A static library .a (or .lib on windows) is combined with compiled .c or .cpp machine .o in a process called linking (ld program), to produce an executible file with an .out (or .exe, on windows) extension.

Static libraries increase the size of the code in your binary. They're always loaded and whatever version of the code you compiled with is the version of the code that will run.

Dynamic libraries, with a .so (or .dll extension on Windows) are stored and versioned separately. It's possible for a version of the dynamic library to be loaded that wasn't the original one that shipped with your code **if** the update is considered binary compatible with the original version.

Additionally dynamic libraries aren't necessarily loaded -- they're usually loaded when first called -- and can be shared among components that use the same library (multiple data loads, one code load).

Dynamic libraries were considered to be the better approach most of the time, but originally they had a major flaw (google DLL hell), which has all but been eliminated by more recent Windows OSes (Windows XP in particular)



## Work in November

The OA binary libraries (.so) we have are for OA versions as recent as 22.60. In some instances we have their matching header (.h) files. But they have been compiled with GCC 4.4.x or older (probably corresponding to RHEL6).

Our use case for these libraries is to link to them in from some C++17 source code. 



Here is a link which talks about if it's possible to link in libraries that were built with a different version of GCC/ C++

https://stackoverflow.com/questions/46746878/is-it-safe-to-link-c17-c14-and-c11-objects

### Response from Ayan:
Hello Kennedy,

The oa_v22.60.s007 is available in the Cadence Virtuoso library (IC618 or ICADVM181 or ICADVM201), as you mentioned. But BAG3 also requires the OA C++ libraries compiled for the OS (RHEL7) and C++ compiler (gcc 8) as you can see on lines 34-36 of the .bashrc that you linked. We were hoping to get the updated version of those libraries (raw or compiled). But it looks like you hit the same problems as us while trying to work out the deal with Si2.

Some researchers in our group are trying to figure out ways to remove the OA dependence, or understand it a bit better by reading the available code base, in an effort to make BAG3 truly "open source" and accessible by people outside BWRC. I will let you know if those attempts converge to an acceptable solution. 

### Message from me:
This does match the stance on Si2's website, which says only "a license-keyed binary version is available for research and teaching purposes."

What new version of the OA C++ libraries are you trying to acquire? I see a reference to oa_v22.60.s007 in your workspace setup .bashrc file, and my understanding is OpenAccess 22.60 (DM6) is the latest release.

As an aside, do you know if the OA API dynamic library .so files included in the standard Cadence Virtuoso install (at ../IC618/tools.lnx86/lib/64bit/  and ../IC618/oa_v22.60.063/lib/linux_rhel60_64/opt) are essentially what we'd have by building C++ source or getting the binary library from Si2? The directories don't include associated header files or exact compiler toolchain, but the file names do match the target link library references in BAG3's CBAG CMakeLists.txt file.

### Message from Hans:
```
/cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa/22.43p006/include/oa/
/cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa/22.50p001/include/oa/
/cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa/2.2.6/include/oa/
/cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa/22.41.004/include/oa/
/cadence/mentor/ixl_cal_2016.1_14.11/shared/pkgs/icv_oa/22.43p006/include/oa/
/cadence/mentor/ixl_cal_2016.1_14.11/shared/pkgs/icv_oa/22.50p001/include/oa/
/cadence/mentor/ixl_cal_2016.1_14.11/shared/pkgs/icv_oa/2.2.6/include/oa/
/cadence/mentor/ixl_cal_2016.1_14.11/shared/pkgs/icv_oa/22.41.004/include/oa/
/cadence/mentor/ixl_cal_2012.4_25.21/shared/pkgs/icv_oa/2.2.6/include/oa/
/cadence/mentor/ixl_cal_2012.4_25.21/shared/pkgs/icv_oa/latest/include/oa/
```

I think the header files from the different versions (except the 2.x) are very similar. I just briefly checked a few and they only differ in adding an overloaded function here and there or changes to the include list. They might work for a wide range of lib versions.


## ETC

setup.cfg is a config file, which is read in by setup.py and contains infor that setup.py otherwise could. (Setup.py is a replacement for setuptools, as it is being deprecated)
config files like these oftentime also have the .ini file type or the the .conf file type.

## Building Pybag:

OA_LINK_DIR

To run CMake (make sure venv is active first)
`python -m pip install .`

### Reading setup.py and both CMakeLists.txt files

1. at bottom of setup.py, setup() function starts process, ext_modules and cmdclass looks to be important

setup.py is a older and more featured setup script, and setup.cfg and pyproject.toml are newer versions that are simpler and recommended unless you need the features of the older project.
Setuptools can build C/C++ extension modules. The keyword argument ext_modules of setup() should be a list of instances of the setuptools.Extension class.

So set the `ext_modules` keyword and inherit this class from the setuptools.Extension class, where we set a 

```
class CMakePyBind11Extension(Extension):
    def __init__(self, name, sourcedir=''):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = str(Path(sourcedir).resolve())

setup(
  package_dir{'': 'src'},     // fed to the ext_modules command below, as a base direcotory for extensions
  ext_modules=[CMakePyBind11Extension('all')],     // this lists the specifics of extensions what is to be built
  cmdclass={'build_ext': CMakePyBind11Build},   // this actually runs the build extension operation

)
```

Inside the CmakePyBind11Build object, there is a method called `build_extension`, which:

1. calculates output directory for the build
2. init cmake command w/: build source dir, temp build dir, output dir, build type, optional compiler launcher settings
3. build cmake command
4. run ./gen_stubs.sh


## Running setup.py in pybag library
"pip install ."

But build.sh appears to not follow this logic

Instead, run build.sh:

```
# this script builds the C++ extension

if [ -z ${OA_LINK_DIR+x} ]
then
    echo "OA_LINK_DIR is unset"
    exit 1
fi

if [ -z ${PYBAG_PYTHON+x} ]
then
    echo "PYBAG_PYTHON is unset"
    exit 1
fi

${PYBAG_PYTHON} setup.py build
```

The `if [ -z ${VAR} ]` command evaluates to true if VAR is null, which is what the -z does.

as [ ] is short for the `test` command in bash

the `${...}` construct is parameter expansion

Ah shit, it looks like this `+x` nonsense was deprecated as of Bash v4.3, which is why this isn't working. Let's just run `setup.py build` directly.



Therefore, it's obvious that we need `OA_LINK_DIR` and `PYBAG_PYTHON`

```
export PYBAG_PYTHON=.... /bin/python3

CMAKE_PREFIX_PATH used by CMake, and is set to fmt,Boost,yamp-cpp, spdlog directories. It normally set at a high level by the output tool in .bashrc files of BAG project.

OA_INCLUDE_DIR  used in cbag CMakeLists.txt, set in .bashrc
OA_LINK_DIR     used in cbag CMakeLists.txt, set in .bashrc

export OA_LINK_DIR=${OA_SRC_ROOT}/lib/linux_rhel70_gcc83x_64/opt

`sudo dnf install cmake`

`sudo dnf install fmt-devel boost-devel spdlog-devel yaml-cpp-devel`

```

to get the packages I want:

```
sudo yum install fmt-devel boost-devel spdlog-devel yaml-cpp-devel
```

You must do the setup in this order:

`python -m venv ~/designs/dmc65v2/.venv/`

`source /env/bin/activate` then `scl enable devtoolset-8 bash` otherwise, the venv will clear the scl env.
`export PYBAG_PYTHON=/faust/user/kcaisley/designs/dmc65v2/.venv/bin/python`
`export OA_SRC_ROOT=/cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa/22.50p001`
`export OA_LINK_DIR=${OA_SRC_ROOT}/lib/linux_rhel50_gcc44x_64/opt`                        #notice these are build for rhel5, with gcc4
`export OA_INCLUDE_DIR=${OA_SRC_ROOT}/include`

`export CMAKE_PREFIX_PATH=/faust/user/kcaisley/packages/spdlog-1.x/cmake:${CMAKE_PREFIX_PATH}`
`export CMAKE_PREFIX_PATH=/faust/user/kcaisley/packages/yaml-cpp-yaml-cpp-0.7.0:${CMAKE_PREFIX_PATH}`

Fist we will need to following libraries:
* Boost
* fmt
* spdlog  > 1.x
* yaml-cpp

To make them accessible to the CMake tool, we first need to make sure they are on our system (and of the devel variety), and then add something to the beginning of the CMake path variable:
`export CMAKE_PREFIX_PATH=____:${CMAKE_PREFIX_PATH}` where ___ is the thing you want to add

We are looking for the files of type:
`/usr/lib/x86_64-linux-gnu/cmake/fmt/fmt-config.cmake`

In this case, we would target the parent directory:
`export CMAKE_PREFIX_PATH=/usr/lib/x86_64-linux-gnu/cmake/fmt:${CMAKE_PREFIX_PATH}`

Okay, so this strategy of trying to use a bunch of manual downloads in not going to work...

Let's move to Fedora. Both the spdlog-devel and fmt-devel have their XXXConfig.cmake files right there.



# Trying again in Fedora:

inside /pybag, make sure you delete the `_build` folder, as it contains a cache of settings

NO, IT'S FINE, I JUST DIDN'T HAVE THE ENV VAR PROPERLY SET. `build.sh` run script is uses deprecated commands, so we will need to launch `setup.py` manually

You must do the setup in this order:

`sudo dnf install cmake`

`sudo dnf install fmt-devel boost-devel spdlog-devel yaml-cpp-devel`

`sudo dnf install gcc_c++`

`sudo dnf install python3.10`       as h5py doesn't work on python 3.11 yet

`python3.10 -m venv ~/designs/dmc65v2/.venv`   as h5py doesn't work on python 3.11 yet

`python -m pip install wheel`

`source .venv/bin/activate`  to activate environment

`export PYBAG_PYTHON=/faust/user/kcaisley/designs/dmc65v2/.venv/bin/python`

`export OA_SRC_ROOT=/cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa/22.50p001`

`export OA_LINK_DIR=${OA_SRC_ROOT}/lib/linux_rhel50_gcc44x_64/opt`          #notice these are build for rhel5, with gcc4

`export OA_INCLUDE_DIR=${OA_SRC_ROOT}/include`

`export CXX=g++`      from [here](https://stackoverflow.com/questions/17275348/how-to-specify-new-gcc-path-for-cmake)

### BAG

To install the top level BAG python lib simply navigate to this directory and execute:

`python -m pip install .`


### PyBAG + CBAG + pybind11

To install the lower level pybag package tools navigate to the pybag directory and execute:

`python -m pip install . --log build.log`

### Diff of stuff changed in cbag

```
diff --git a/CMakeLists.txt b/CMakeLists.txt
index 6ea5233..67896a4 100644
--- a/CMakeLists.txt
+++ b/CMakeLists.txt
@@ -202,7 +202,7 @@ set(SRC_FILES_LIB_CBAG_OA
   ${CMAKE_CURRENT_SOURCE_DIR}/src/cbag/oa/write.cpp
   )
 
-
+  
 if(DEFINED ENV{OA_LINK_DIR})
 message("OA include directory: " $ENV{OA_INCLUDE_DIR})
 message("OA link directory: " $ENV{OA_LINK_DIR})
@@ -226,6 +226,7 @@ target_link_libraries(cbag
   oaCommon
   oaPlugIn
   PRIVATE
+  spdlog::spdlog               #https://bugzilla.redhat.com/show_bug.cgi?id=1851497
   stdc++fs
   ${Boost_LIBRARIES}
   yaml-cpp
diff --git a/include/cbag/common/typedefs.h b/include/cbag/common/typedefs.h
index 7ce06b1..86dbba1 100644
--- a/include/cbag/common/typedefs.h
+++ b/include/cbag/common/typedefs.h
@@ -49,6 +49,9 @@ limitations under the License.
 
 #include <cstdint>
 #include <tuple>
+#include <limits>               //https://stackoverflow.com/questions/71296302/numeric-limits-is-not-a-member-of-std
+#include <optional>             //based on above comment
+#include <boost/geometry.hpp>   //https://github.com/pgRouting/pgrouting/issues/1825
 
 namespace cbag {
 
diff --git a/src/cbag/layout/path_util.cpp b/src/cbag/layout/path_util.cpp
index b9a0802..def66aa 100644
--- a/src/cbag/layout/path_util.cpp
+++ b/src/cbag/layout/path_util.cpp
@@ -46,6 +46,7 @@ limitations under the License.
 
 #include <fmt/core.h>
 #include <fmt/ostream.h>
+#include <fmt/format.h>     // trying to add this code
 
 #include <cbag/layout/path_util.h>
```


you make use `git clean -dfx`, that will remove all files not under source control. Be careful with this though, as it can delete newly created files if they haven't been added to source control yet.

this assumes an in-source build, of course, which is a bad habit

## Downgrading packages on Fedora:

### Error with {fmt} package during build

```
/usr/include/fmt/core.h:1757:7: error: static assertion failed: Cannot format an argument. To make type T formattable provide a formatter<T> specialization: https://fmt.dev/latest/api.html#udt
```

Solution: It looks like other people have have [problems with fmt](https://gitlab.com/mbunkus/mkvtoolnix/-/issues/3366)

To downgrade to fmt 8.1, we can use the koji build system: https://koji.fedoraproject.org/koji/buildinfo?buildID=1927503

looks like the newest version of spdlog (1.11) supports fmt 9.1, and so we need to downgrade to spdlog 1.10 to support fmt 8.1.1.

here's the fmt/fmt-devel packages: https://koji.fedoraproject.org/koji/buildinfo?buildID=1927503
here's the spdlog/spdlog-devel packages: 

If a package is still in the repos, here's how you find and target it:
https://unix.stackexchange.com/questions/266888/can-i-force-dnf-to-install-an-old-version-of-a-package

`dnf --showduplicates list <package>`

List packages that depend on the package of choice:
`dnf repoquery --installed --whatrequires qemu-kvm`

manually downgrade to a different package version downloaded from [this link](https://koji.fedoraproject.org)
`sudo dnf downgrade ~/Downloads/fmt-8.1.1-5.fc37.x86_64.rpm`


Had to remove gnome boxes, as it depends on fmt lib: `sudo dnf remove gnome-boxes`

`sudo dnf remove fmt fmt-devel spdlog spdlog-devel`  (march 02)

I knew I needed older version of spdlog to be compatible with my older fmt, based on [this](https://github.com/gabime/spdlog/releases)

```
wget https://kojipkgs.fedoraproject.org//packages/fmt/8.1.1/4.fc37/x86_64/fmt-8.1.1-4.fc37.x86_64.rpm https://kojipkgs.fedoraproject.org//packages/fmt/8.1.1/4.fc37/x86_64/fmt-devel-8.1.1-4.fc37.x86_64.rpm https://kojipkgs.fedoraproject.org//packages/spdlog/1.10.0/1.fc37/x86_64/spdlog-1.10.0-1.fc37.x86_64.rpm https://kojipkgs.fedoraproject.org//packages/spdlog/1.10.0/1.fc37/x86_64/spdlog-devel-1.10.0-1.fc37.x86_64.rpm -P ~/Downloads/
```

then simply manually install all of these rpms, assuming nothing else is in the download path
`sudo dnf install ~/Downloads/*.rpm`



### Error with Boost packages during build

```
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/src/cbag/spirit/range.cpp:53:1:   required from here
/usr/include/boost/spirit/home/x3/operator/detail/sequence.hpp:144:25: error: static assertion failed: Size of the passed attribute is bigger than expected.
  144 |             actual_size <= expected_size
      |             ~~~~~~~~~~~~^~~~~~~~~~~~~~~~
```

Let's try downgrading Boost and Boost devel:

```
> sudo dnf remove boost boost-devel

> wget https://kojipkgs.fedoraproject.org//packages/boost/1.76.0/10.fc37/x86_64/boost-1.76.0-10.fc37.x86_64.rpm https://kojipkgs.fedoraproject.org//packages/boost/1.76.0/10.fc37/x86_64/boost-devel-1.76.0-10.fc37.x86_64.rpm -P ~/Downloads/
```

Now I can't just manually install these now, because a couple core system components, namely `gnome-shell` require other boost libraries, like `boost-system` which an older version of `boost` wouldn't be compatible with.

# fmt and spdlog

fmt is a formatting library which provides a standardized, safe, fast way to construct strings. This is useful for output messages and dynamically generating filepaths in C++ code.

spdlog, pronounced 'speed log', is a library built on top of {fmt} which allows for the 


# putting more effor into understanding BAG:

the implementation of cbag is as a header only library. It uses 

# January 12: picking back up work

My current status ilss that I need to compile and install pybag, which depends on a bunch of different packages. Building the cbag subrepo though requires `fmt`, `spdlog`, and a collection of `boost` libs. The specific versions needed can't be accessed easily via the Fedora fedora dnf repos, and so I fear I'll just need to manually download and build the projects from source.

First, let's examine what we currently have installed, and specify exactly what we need to download.

# January 20: continuing with development

I think looking at how `cbag` and `cbag_polygon` are built first might be helpful in this case.

One must understand that CMake is a build system, in that it simple generates build files which are then compiles with a system's native build environment.

Running just the CMake build command gives me several clues:

In the CMakeLists.txt file, I see a control flow statement for:
`if(DEFINED ENV{OA_LINK_DIR})`

I've check it, and it's not evaluating, the else() statment below is instead.

#### Workflow:
```
[kcaisley@asiclab008 ~]$ cd designs/dmc65v2/
[kcaisley@asiclab008 dmc65v2]$ source setup.sh        
(.venv) [kcaisley@asiclab008 dmc65v2]$ cd bag/pybag/cbag/
(.venv) [kcaisley@asiclab008 cbag]$ rm -r _build
(.venv) [kcaisley@asiclab008 cbag]$ export BUILD_TYPE=${1:-Debug}
(.venv) [kcaisley@asiclab008 cbag]$ cmake -H. -Bbuild -DCMAKE_BUILD_TYPE=${BUILD_TYPE} -DCMAKE_CXX_COMPILER_LAUNCHER=ccache
```
Where
`-H` This internal option is not documented but widely used by community and Has been replaced in 3.13 with the official source directory flag of -S.
    there is no space place after for the directory, so the . is the local location
`-B` Starting with CMake 3.13, -B is an officially supported flag, can handle spaces correctly and can be used independently of the -S or -H options.
    again, there should be nospace, so `_build` is the build directory name
    
`-D` -D <var>:<type>=<value>
       Create a cmake cache entry.

       When cmake is first run in an empty build tree, it creates a CMakeCache.txt file and populates  it
       with  customizable  settings  for  the project.  This option may be used to specify a setting that
       takes priority over the project's default value.  The option may be repeated  for  as  many  cache
       entries as desired.
     Again, no space! There are hundreds of options in this file, but this comman above is specifically setting:
     CMAKE_BUILD_TYPE which is being set to 'Debug'
     CMAKE_CXX_COMPILER_LAUNCHER which passes the 'ccache' option to the makefiles generator, no idea relaly that this does
`|| exit` suffix should be removed, as this is being run on the command line, and this will cause the terminal to exit if the command fails

Now I just need to understand why the WARNING: building without OpenAccess support. path is running.....

I think the issue is that there is some complexity to CMake variable/environment variable scope system.

Yes, this is the issues. Those unix bash environment variables are not visible inside the CMake scope. Let's figure out how this can be set.

It's not being passed down from higher level CMake script, so it must be in the way that the command to build is called.

cmake -H. -B_build -DCMAKE_BUILD_TYPE=${BUILD_TYPE} -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DOA_LINK_DIR=/cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa/22.50p001/lib/linux_rhel50_gcc44x_64/opt

The CMakeCache.txt File

After the first configuration of a project, CMake persists variable information in a text file called CMakeCache.txt. Caches are used to improve. When CMake is re-run on a project the cache is read before starting so that some re-parsing time can be saved on CMakeLists.txt. Here is where passing parameters to CMake befuddles a beginner. If a variable is passed via the command line that variable is stored in the cache. Accessing that variable on future runs of CMake will always get the value stored inside the cache and new value passed through the command line are ignored. To make CMake take the new value passed through the command line the first value have to be explicitly undefined. Like so:

`cmake -U <previously defined variable> -D <previously defined variable>[=new value]`

(A better approach is to use CMake internal variables. For more information refer the CMake manual here.)

The syntax `if(DEFINED <name>|CACHE{<name>}|ENV{<name>})` is true if a variable, cache variable or environment variable with given <name> is defined. The value of the variable does not matter.


Environment Variables are like ordinary Variables, with the following differences:
* Environment variables have global scope in a CMake process. They are never cached.
* Variable References have the form $ENV{<variable>}, using the ENV operator.
* Initial values of the CMake environment variables are those of the calling process. Values can be changed using the set() and unset() commands. These commands only affect the running CMake process, not the system environment at large. Changed values are not written back to the calling process, and they are not seen by subsequent build or test processes.
* See the cmake -E env command-line tool to run a command in a modified environment.
* Source: https://cmake.org/cmake/help/latest/manual/cmake-language.7.html#cmake-language-environment-variables

This isn't working because I'm setting regular variables, but the check is for an environment variable.


Ohhhhh. If you set an vairable, just by writing it, it will only be valid in that shell. It's called a variable. If you write 'export' first though, it's now and 'environment variable' and will be active in all child processes.

Now, if it's inside a script (which is run as a child process), and if you want to access it inside another child process, you need to make sure that first you 'source' the script, so that the contents of the script re available in the parent bash session, but then you also need to add the 'export' command, if you want it to be available in a child pocess like CMake.
So in short the 'source' command makes bash script which would otherwise be child process, instead run in the parent bash session.
And 'export' makes all variables defined in the parent process also defined in the child processes.


# Fully documented build problems:

```
[kcaisley@asiclab008 ~]$ cd designs/dmc65v2/
[kcaisley@asiclab008 dmc65v2]$ source setup.sh        
(.venv) [kcaisley@asiclab008 dmc65v2]$ cd bag/pybag/cbag/
(.venv) [kcaisley@asiclab008 cbag]$ mkdir build
(.venv) [kcaisley@asiclab008 cbag]$ rm -r build/*
(.venv) [kcaisley@asiclab008 cbag]$ cd build
(.venv) [kcaisley@asiclab008 cbag]$ cmake ../
(.venv) [kcaisley@asiclab008 cbag]$ cd ..
(.venv) [kcaisley@asiclab008 cbag]$ cmake --build build
```

## Problem 1:

```
(.venv) [kcaisley@asiclab008 build]$ cmake --build .
[  1%] Building CXX object CMakeFiles/cbag.dir/src/cbag/common/box_collection.cpp.o
In file included from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/common/box_t.h:50,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/common/box_array.h:50,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/common/box_collection.h:23,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/src/cbag/common/box_collection.cpp:18:
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/common/typedefs.h:73:33: error: ‘numeric_limits’ is not a member of ‘std’
   73 | constexpr auto COORD_MIN = std::numeric_limits<coord_t>::min();
      |                                 ^~~~~~~~~~~~~~
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/common/typedefs.h:73:55: error: expected primary-expression before ‘>’ token
   73 | constexpr auto COORD_MIN = std::numeric_limits<coord_t>::min();
      |                                                       ^
compilation terminated due to -fmax-errors=2.
gmake[2]: *** [CMakeFiles/cbag.dir/build.make:76: CMakeFiles/cbag.dir/src/cbag/common/box_collection.cpp.o] Error 1
gmake[1]: *** [CMakeFiles/Makefile2:124: CMakeFiles/cbag.dir/all] Error 2
gmake: *** [Makefile:136: all] Error 2
```


When including files, if it's just a simple world like `#include <tuple>`, then this is probably a C++ standard lib component. If it is formatted like `#include <boost/geometry.hpp>`, then this is a good clue that the library isn't standard due to the .hpp suffix, and also that the libary is written in C++. If you have one like `#include <limits.h>`, we know this is written in C, and there is a good chance this is actually part of the C standard library, which is included in the C++ std lib but is deprecated and not advisable to use.

The fix was including the `<limits>` standard library header in the offending file, so that `std::numeric_limits` is defined. One thing I learned from the above error log is that we can see the trace of imports that lead to the offending file. We tried to compile `src/cbag/common/box_collection.cpp` but the error was in `cbag/include/cbag/common/typedefs.h`. We we read the "build line first", then the "In file included from" bottom to top", then finally the lowest section with the "error" to find our problem. In this case, our solution was adding a single line:

```
kcaisley@asiclab008 cbag]$ git diff include/cbag/common/typedefs.h
diff --git a/include/cbag/common/typedefs.h b/include/cbag/common/typedefs.h
index 7ce06b1..ed526cb 100644
--- a/include/cbag/common/typedefs.h
+++ b/include/cbag/common/typedefs.h
@@ -49,6 +49,7 @@ limitations under the License.
 
 #include <cstdint>
 #include <tuple>
+#include <limits>   //needed for std::numeric_limits

```

NOTE: I believe that `<cstdint>` defines primitive types like `int32_t`. Like the other std lib headers, `gcc` stores them at `/usr/include/c++/12`

## Problem #2
```
(.venv) [kcaisley@asiclab008 cbag]$ cmake --build build
[  1%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/main.cpp.o
In file included from /usr/include/spdlog/common.h:45,
                 from /usr/include/spdlog/spdlog.h:12,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/logging/spdlog.h:53,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/logging/logging.h:55,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/gdsii/read.h:58,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/src/cbag/gdsii/main.cpp:25:
/usr/include/spdlog/fmt/fmt.h:27:14: fatal error: spdlog/fmt/bundled/core.h: No such file or directory
   27 | #    include <spdlog/fmt/bundled/core.h>
      |              ^~~~~~~~~~~~~~~~~~~~~~~~~~~
compilation terminated.
gmake[2]: *** [CMakeFiles/cbag.dir/build.make:104: CMakeFiles/cbag.dir/src/cbag/gdsii/main.cpp.o] Error 1
gmake[1]: *** [CMakeFiles/Makefile2:124: CMakeFiles/cbag.dir/all] Error 2
```

As mentioned at [this link](https://bugzilla.redhat.com/show_bug.cgi?id=1851497) this error crops up if the CMakeLists.txt for a project doesn't correct set all the flags for spdlog and fmt. In this case, `spdlog` was erroneously omitted from the `target_link_libraries` section. A simple fix:

```
diff --git a/CMakeLists.txt b/CMakeLists.txt
index 6ea5233..e8f1408 100644
--- a/CMakeLists.txt
+++ b/CMakeLists.txt
@@ -201,8 +201,7 @@ set(SRC_FILES_LIB_CBAG_OA
   ${CMAKE_CURRENT_SOURCE_DIR}/src/cbag/oa/util.cpp
   ${CMAKE_CURRENT_SOURCE_DIR}/src/cbag/oa/write.cpp
   )
-
-
+  
 if(DEFINED ENV{OA_LINK_DIR})
 message("OA include directory: " $ENV{OA_INCLUDE_DIR})
 message("OA link directory: " $ENV{OA_LINK_DIR})
@@ -226,6 +225,7 @@ target_link_libraries(cbag
   oaCommon
   oaPlugIn
   PRIVATE
+  spdlog::spdlog               #https://bugzilla.redhat.com/show_bug.cgi?id=1851497
   stdc++fs
   ${Boost_LIBRARIES}
```

## Problem #3
```
(.venv) [kcaisley@asiclab008 cbag]$ cmake --build build
Interprocedural optimization disabled
-- Found Boost: /usr/lib64/cmake/Boost-1.78.0/BoostConfig.cmake (found version "1.78.0")  
Interprocedural optimization disabled
install prefix: /usr/local
install rpath: 
OA include directory: /cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa/22.50p001/include
OA link directory: /cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa/22.50p001/lib/linux_rhel50_gcc44x_64/opt
-- Found Boost: /usr/lib64/cmake/Boost-1.78.0/BoostConfig.cmake (found version "1.78.0") found components: serialization 
-- Configuring done
-- Generating done
-- Build files have been written to: /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/build
[  1%] Building CXX object CMakeFiles/cbag.dir/src/cbag/common/box_collection.cpp.o
[  2%] Building CXX object CMakeFiles/cbag.dir/src/cbag/common/transformation_util.cpp.o
[  3%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/main.cpp.o
[  4%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/math.cpp.o
[  5%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/parse_map.cpp.o
[  7%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/read.cpp.o
[  8%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/read_util.cpp.o
[  9%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/write.cpp.o
[ 10%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/write_util.cpp.o
[ 11%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/blockage.cpp.o
[ 12%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/boundary.cpp.o
[ 14%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/cellview.cpp.o
In file included from /usr/include/boost/geometry/index/rtree.hpp:30,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/cbag_polygon/include/cbag/polygon/geo_index.h:54,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/layout/cellview_fwd.h:59,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/layout/cellview.h:52,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/src/cbag/layout/cellview.cpp:55:
/usr/include/boost/geometry/strategies/relate/services.hpp: In instantiation of ‘struct boost::geometry::strategies::relate::services::default_strategy<boost::geometry::model::box<boost::geometry::model::point<int, 2, boost::geometry::cs::cartesian> >, cbag::polygon::rectangle_data<int>, boost::geometry::cartesian_tag, boost::geometry::cartesian_tag>’:
/usr/include/boost/geometry/algorithms/detail/disjoint/interface.hpp:92:21:   required from ‘static bool boost::geometry::resolve_strategy::disjoint<boost::geometry::default_strategy, false>::apply(const Geometry1&, const Geometry2&, boost::geometry::default_strategy) [with Geometry1 = boost::geometry::model::box<boost::geometry::model::point<int, 2, boost::geometry::cs::cartesian> >; Geometry2 = cbag::polygon::rectangle_data<int>]’
/usr/include/boost/geometry/algorithms/detail/disjoint/interface.hpp:129:21:   required from ‘static bool boost::geometry::resolve_dynamic::disjoint<Geometry1, Geometry2, IsDynamic, IsCollection>::apply(const Geometry1&, const Geometry2&, const Strategy&) [with Strategy = boost::geometry::default_strategy; Geometry1 = boost::geometry::model::box<boost::geometry::model::point<int, 2, boost::geometry::cs::cartesian> >; Geometry2 = cbag::polygon::rectangle_data<int>; bool IsDynamic = false; bool IsCollection = false]’
/usr/include/boost/geometry/algorithms/detail/disjoint/interface.hpp:231:21:   required from ‘bool boost::geometry::disjoint(const Geometry1&, const Geometry2&) [with Geometry1 = model::box<model::point<int, 2, cs::cartesian> >; Geometry2 = cbag::polygon::rectangle_data<int>]’
/usr/include/boost/geometry/algorithms/detail/intersects/interface.hpp:108:32:   required from ‘bool boost::geometry::intersects(const Geometry1&, const Geometry2&) [with Geometry1 = model::box<model::point<int, 2, cs::cartesian> >; Geometry2 = cbag::polygon::rectangle_data<int>]’
/usr/include/boost/geometry/index/detail/predicates.hpp:218:36:   required from ‘static bool boost::geometry::index::detail::spatial_predicate_intersects<G1, G2, Tag1, Tag2>::apply(const G1&, const G2&, const S&) [with S = boost::geometry::default_strategy; G1 = boost::geometry::model::box<boost::geometry::model::point<int, 2, boost::geometry::cs::cartesian> >; G2 = cbag::polygon::rectangle_data<int>; Tag1 = boost::geometry::box_tag; Tag2 = boost::geometry::box_tag]’
/usr/include/boost/geometry/index/detail/predicates.hpp:243:59:   [ skipping 5 instantiation contexts, use -ftemplate-backtrace-limit=0 to disable ]
/usr/include/boost/geometry/index/detail/rtree/visitors/spatial_query.hpp:87:21:   required from ‘boost::geometry::index::detail::rtree::visitors::spatial_query<MembersHolder, Predicates, OutIter>::size_type boost::geometry::index::detail::rtree::visitors::spatial_query<MembersHolder, Predicates, OutIter>::apply(const MembersHolder&) [with MembersHolder = boost::geometry::index::rtree<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int>, boost::geometry::index::quadratic<32, 16>, boost::geometry::index::indexable<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >, boost::geometry::index::equal_to<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >, boost::container::new_allocator<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> > >::members_holder; Predicates = boost::geometry::index::detail::predicates::spatial_predicate<cbag::polygon::rectangle_data<int>, boost::geometry::index::detail::predicates::intersects_tag, false>; OutIter = cbag::util::lambda_output_iterator<cbag::polygon::index::geo_index<int>::get_intersect<cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> > >(cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> >, const box_type&, coordinate_type, coordinate_type, bool, const cbag::polygon::transformation<int>&) const::<lambda(const cbag::polygon::index::geo_index<int>::tree_value_type&)> >; size_type = long unsigned int]’
/usr/include/boost/geometry/index/rtree.hpp:1861:27:   required from ‘boost::geometry::index::rtree<Value, Options, IndexableGetter, EqualTo, Allocator>::size_type boost::geometry::index::rtree<Value, Options, IndexableGetter, EqualTo, Allocator>::query_dispatch(const Predicates&, OutIter) const [with Predicates = boost::geometry::index::detail::predicates::spatial_predicate<cbag::polygon::rectangle_data<int>, boost::geometry::index::detail::predicates::intersects_tag, false>; OutIter = cbag::util::lambda_output_iterator<cbag::polygon::index::geo_index<int>::get_intersect<cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> > >(cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> >, const box_type&, coordinate_type, coordinate_type, bool, const cbag::polygon::transformation<int>&) const::<lambda(const cbag::polygon::index::geo_index<int>::tree_value_type&)> >; typename std::enable_if<(boost::geometry::index::detail::predicates_count_distance<Predicates>::value == 0), int>::type <anonymous> = 0; Value = std::pair<cbag::polygon::rectangle_data<int>, long unsigned int>; Parameters = boost::geometry::index::quadratic<32, 16>; IndexableGetter = boost::geometry::index::indexable<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; EqualTo = boost::geometry::index::equal_to<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; Allocator = boost::container::new_allocator<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; size_type = long unsigned int]’
/usr/include/boost/geometry/index/rtree.hpp:1083:30:   required from ‘boost::geometry::index::rtree<Value, Options, IndexableGetter, EqualTo, Allocator>::size_type boost::geometry::index::rtree<Value, Options, IndexableGetter, EqualTo, Allocator>::query(const Predicates&, OutIter) const [with Predicates = boost::geometry::index::detail::predicates::spatial_predicate<cbag::polygon::rectangle_data<int>, boost::geometry::index::detail::predicates::intersects_tag, false>; OutIter = cbag::util::lambda_output_iterator<cbag::polygon::index::geo_index<int>::get_intersect<cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> > >(cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> >, const box_type&, coordinate_type, coordinate_type, bool, const cbag::polygon::transformation<int>&) const::<lambda(const cbag::polygon::index::geo_index<int>::tree_value_type&)> >; Value = std::pair<cbag::polygon::rectangle_data<int>, long unsigned int>; Parameters = boost::geometry::index::quadratic<32, 16>; IndexableGetter = boost::geometry::index::indexable<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; EqualTo = boost::geometry::index::equal_to<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; Allocator = boost::container::new_allocator<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; size_type = long unsigned int]’
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/cbag_polygon/include/cbag/polygon/geo_index.h:212:21:   required from ‘void cbag::polygon::index::geo_index<T>::get_intersect(OutIter, const box_type&, coordinate_type, coordinate_type, bool, const cbag::polygon::transformation<T>&) const [with OutIter = cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> >; T = int; box_type = cbag::polygon::rectangle_data<int>; coordinate_type = int]’
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/cbag_polygon/include/cbag/polygon/geo_index.h:244:22:   required from ‘void cbag::polygon::index::apply_intersect(const geo_index<T>&, Fun, const typename geo_index<T>::box_type&, T, T, bool, const cbag::polygon::transformation<T>&) [with T = int; Fun = cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)>; typename geo_index<T>::box_type = cbag::polygon::rectangle_data<int>]’
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/src/cbag/layout/cellview.cpp:137:24:   required from here
/usr/include/boost/geometry/strategies/relate/services.hpp:36:5: error: static assertion failed: Not implemented for this Geometry's coordinate system.
   36 |     BOOST_GEOMETRY_STATIC_ASSERT_FALSE(
      |     ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
/usr/include/boost/geometry/strategies/relate/services.hpp:36:5: note: ‘std::integral_constant<bool, false>::value’ evaluates to false
In file included from /usr/include/boost/geometry/index/rtree.hpp:34:
/usr/include/boost/geometry/algorithms/detail/disjoint/interface.hpp: In instantiation of ‘static bool boost::geometry::resolve_strategy::disjoint<boost::geometry::default_strategy, false>::apply(const Geometry1&, const Geometry2&, boost::geometry::default_strategy) [with Geometry1 = boost::geometry::model::box<boost::geometry::model::point<int, 2, boost::geometry::cs::cartesian> >; Geometry2 = cbag::polygon::rectangle_data<int>]’:
/usr/include/boost/geometry/algorithms/detail/disjoint/interface.hpp:129:21:   required from ‘static bool boost::geometry::resolve_dynamic::disjoint<Geometry1, Geometry2, IsDynamic, IsCollection>::apply(const Geometry1&, const Geometry2&, const Strategy&) [with Strategy = boost::geometry::default_strategy; Geometry1 = boost::geometry::model::box<boost::geometry::model::point<int, 2, boost::geometry::cs::cartesian> >; Geometry2 = cbag::polygon::rectangle_data<int>; bool IsDynamic = false; bool IsCollection = false]’
/usr/include/boost/geometry/algorithms/detail/disjoint/interface.hpp:231:21:   required from ‘bool boost::geometry::disjoint(const Geometry1&, const Geometry2&) [with Geometry1 = model::box<model::point<int, 2, cs::cartesian> >; Geometry2 = cbag::polygon::rectangle_data<int>]’
/usr/include/boost/geometry/algorithms/detail/intersects/interface.hpp:108:32:   required from ‘bool boost::geometry::intersects(const Geometry1&, const Geometry2&) [with Geometry1 = model::box<model::point<int, 2, cs::cartesian> >; Geometry2 = cbag::polygon::rectangle_data<int>]’
/usr/include/boost/geometry/index/detail/predicates.hpp:218:36:   required from ‘static bool boost::geometry::index::detail::spatial_predicate_intersects<G1, G2, Tag1, Tag2>::apply(const G1&, const G2&, const S&) [with S = boost::geometry::default_strategy; G1 = boost::geometry::model::box<boost::geometry::model::point<int, 2, boost::geometry::cs::cartesian> >; G2 = cbag::polygon::rectangle_data<int>; Tag1 = boost::geometry::box_tag; Tag2 = boost::geometry::box_tag]’
/usr/include/boost/geometry/index/detail/predicates.hpp:243:59:   required from ‘static bool boost::geometry::index::detail::spatial_predicate_call<boost::geometry::index::detail::predicates::intersects_tag>::apply(const G1&, const G2&, const S&) [with G1 = boost::geometry::model::box<boost::geometry::model::point<int, 2, boost::geometry::cs::cartesian> >; G2 = cbag::polygon::rectangle_data<int>; S = boost::geometry::default_strategy]’
/usr/include/boost/geometry/index/detail/predicates.hpp:364:73:   [ skipping 4 instantiation contexts, use -ftemplate-backtrace-limit=0 to disable ]
/usr/include/boost/geometry/index/detail/rtree/visitors/spatial_query.hpp:87:21:   required from ‘boost::geometry::index::detail::rtree::visitors::spatial_query<MembersHolder, Predicates, OutIter>::size_type boost::geometry::index::detail::rtree::visitors::spatial_query<MembersHolder, Predicates, OutIter>::apply(const MembersHolder&) [with MembersHolder = boost::geometry::index::rtree<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int>, boost::geometry::index::quadratic<32, 16>, boost::geometry::index::indexable<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >, boost::geometry::index::equal_to<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >, boost::container::new_allocator<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> > >::members_holder; Predicates = boost::geometry::index::detail::predicates::spatial_predicate<cbag::polygon::rectangle_data<int>, boost::geometry::index::detail::predicates::intersects_tag, false>; OutIter = cbag::util::lambda_output_iterator<cbag::polygon::index::geo_index<int>::get_intersect<cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> > >(cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> >, const box_type&, coordinate_type, coordinate_type, bool, const cbag::polygon::transformation<int>&) const::<lambda(const cbag::polygon::index::geo_index<int>::tree_value_type&)> >; size_type = long unsigned int]’
/usr/include/boost/geometry/index/rtree.hpp:1861:27:   required from ‘boost::geometry::index::rtree<Value, Options, IndexableGetter, EqualTo, Allocator>::size_type boost::geometry::index::rtree<Value, Options, IndexableGetter, EqualTo, Allocator>::query_dispatch(const Predicates&, OutIter) const [with Predicates = boost::geometry::index::detail::predicates::spatial_predicate<cbag::polygon::rectangle_data<int>, boost::geometry::index::detail::predicates::intersects_tag, false>; OutIter = cbag::util::lambda_output_iterator<cbag::polygon::index::geo_index<int>::get_intersect<cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> > >(cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> >, const box_type&, coordinate_type, coordinate_type, bool, const cbag::polygon::transformation<int>&) const::<lambda(const cbag::polygon::index::geo_index<int>::tree_value_type&)> >; typename std::enable_if<(boost::geometry::index::detail::predicates_count_distance<Predicates>::value == 0), int>::type <anonymous> = 0; Value = std::pair<cbag::polygon::rectangle_data<int>, long unsigned int>; Parameters = boost::geometry::index::quadratic<32, 16>; IndexableGetter = boost::geometry::index::indexable<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; EqualTo = boost::geometry::index::equal_to<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; Allocator = boost::container::new_allocator<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; size_type = long unsigned int]’
/usr/include/boost/geometry/index/rtree.hpp:1083:30:   required from ‘boost::geometry::index::rtree<Value, Options, IndexableGetter, EqualTo, Allocator>::size_type boost::geometry::index::rtree<Value, Options, IndexableGetter, EqualTo, Allocator>::query(const Predicates&, OutIter) const [with Predicates = boost::geometry::index::detail::predicates::spatial_predicate<cbag::polygon::rectangle_data<int>, boost::geometry::index::detail::predicates::intersects_tag, false>; OutIter = cbag::util::lambda_output_iterator<cbag::polygon::index::geo_index<int>::get_intersect<cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> > >(cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> >, const box_type&, coordinate_type, coordinate_type, bool, const cbag::polygon::transformation<int>&) const::<lambda(const cbag::polygon::index::geo_index<int>::tree_value_type&)> >; Value = std::pair<cbag::polygon::rectangle_data<int>, long unsigned int>; Parameters = boost::geometry::index::quadratic<32, 16>; IndexableGetter = boost::geometry::index::indexable<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; EqualTo = boost::geometry::index::equal_to<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; Allocator = boost::container::new_allocator<std::pair<cbag::polygon::rectangle_data<int>, long unsigned int> >; size_type = long unsigned int]’
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/cbag_polygon/include/cbag/polygon/geo_index.h:212:21:   required from ‘void cbag::polygon::index::geo_index<T>::get_intersect(OutIter, const box_type&, coordinate_type, coordinate_type, bool, const cbag::polygon::transformation<T>&) const [with OutIter = cbag::util::lambda_output_iterator<cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)> >; T = int; box_type = cbag::polygon::rectangle_data<int>; coordinate_type = int]’
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/cbag_polygon/include/cbag/polygon/geo_index.h:244:22:   required from ‘void cbag::polygon::index::apply_intersect(const geo_index<T>&, Fun, const typename geo_index<T>::box_type&, T, T, bool, const cbag::polygon::transformation<T>&) [with T = int; Fun = cbag::layout::cellview::helper::get_ip_fill_intvs(const cbag::layout::geo_index_t&, const cbag::box_t&, cbag::coord_t, cbag::coord_t, int, cbag::offset_t)::<lambda(const auto:80&)>; typename geo_index<T>::box_type = cbag::polygon::rectangle_data<int>]’
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/src/cbag/layout/cellview.cpp:137:24:   required from here
/usr/include/boost/geometry/algorithms/detail/disjoint/interface.hpp:92:21: error: no type named ‘type’ in ‘struct boost::geometry::strategies::relate::services::default_strategy<boost::geometry::model::box<boost::geometry::model::point<int, 2, boost::geometry::cs::cartesian> >, cbag::polygon::rectangle_data<int>, boost::geometry::cartesian_tag, boost::geometry::cartesian_tag>’
   92 |             >::type strategy_type;
      |                     ^~~~~~~~~~~~~
compilation terminated due to -fmax-errors=2.
gmake[2]: *** [CMakeFiles/cbag.dir/build.make:230: CMakeFiles/cbag.dir/src/cbag/layout/cellview.cpp.o] Error 1
gmake[1]: *** [CMakeFiles/Makefile2:124: CMakeFiles/cbag.dir/all] Error 2
```

Solution was to include <boost/geometry.hpp>, as discussed in [this issues](https://github.com/pgRouting/pgrouting/issues/1825)

```
[kcaisley@asiclab008 cbag]$ git diff include/cbag/common/typedefs.h
diff --git a/include/cbag/common/typedefs.h b/include/cbag/common/typedefs.h
index 7ce06b1..86dbba1 100644
--- a/include/cbag/common/typedefs.h
+++ b/include/cbag/common/typedefs.h
@@ -49,6 +49,9 @@ limitations under the License.
 
 #include <cstdint>
 #include <tuple>
+#include <limits>               //https://stackoverflow.com/questions/71296302/numeric-limits-is-not-a-member-of-std
+#include <boost/geometry.hpp>   //https://github.com/pgRouting/pgrouting/issues/1825
```

NOTE: As you can see above, this is the second line we've had to add to this file.

## Problem #4

```
(.venv) [kcaisley@asiclab008 cbag]$ cmake --build build
[  1%] Building CXX object CMakeFiles/cbag.dir/src/cbag/common/box_collection.cpp.o
[  2%] Building CXX object CMakeFiles/cbag.dir/src/cbag/common/transformation_util.cpp.o
[  3%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/main.cpp.o
[  4%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/parse_map.cpp.o
[  5%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/read.cpp.o
[  7%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/read_util.cpp.o
[  8%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/write.cpp.o
[  9%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/write_util.cpp.o
[ 10%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/blockage.cpp.o
[ 11%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/boundary.cpp.o
[ 12%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/cellview.cpp.o
[ 14%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/cellview_poly.cpp.o
[ 15%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/cellview_util.cpp.o
[ 16%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/grid_object.cpp.o
[ 17%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/instance.cpp.o
[ 18%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/label.cpp.o
[ 20%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/len_info.cpp.o
[ 21%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/lp_lookup.cpp.o
In file included from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/src/cbag/layout/lp_lookup.cpp:51:
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/layout/lp_lookup.h:85:10: error: ‘optional’ in namespace ‘std’ does not name a template type
   85 |     std::optional<lay_t> get_layer_id(const std::string &layer) const;
      |          ^~~~~~~~
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/layout/lp_lookup.h:53:1: note: ‘std::optional’ is defined in header ‘<optional>’; did you forget to ‘#include <optional>’?
   52 | #include <cbag/common/typedefs.h>
  +++ |+#include <optional>
   53 | 
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/layout/lp_lookup.h:87:10: error: ‘optional’ in namespace ‘std’ does not name a template type
   87 |     std::optional<purp_t> get_purpose_id(const std::string &purpose) const;
      |          ^~~~~~~~
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/layout/lp_lookup.h:87:5: note: ‘std::optional’ is defined in header ‘<optional>’; did you forget to ‘#include <optional>’?
   87 |     std::optional<purp_t> get_purpose_id(const std::string &purpose) const;
      |     ^~~
compilation terminated due to -fmax-errors=2.
gmake[2]: *** [CMakeFiles/cbag.dir/build.make:328: CMakeFiles/cbag.dir/src/cbag/layout/lp_lookup.cpp.o] Error 1
gmake[1]: *** [CMakeFiles/Makefile2:124: CMakeFiles/cbag.dir/all] Error 2

```

The solution is described right there in the message, we forgot `std::optional` is defined in header `<optional>`; yep we forget to `#include <optional>` in `cbag/include/cbag/layout/lp_lookup.h`.

```
(.venv) [kcaisley@asiclab008 cbag]$ git diff include/cbag/layout/lp_lookup.h
diff --git a/include/cbag/layout/lp_lookup.h b/include/cbag/layout/lp_lookup.h
index 3f21bb9..cd6771d 100644
--- a/include/cbag/layout/lp_lookup.h
+++ b/include/cbag/layout/lp_lookup.h
@@ -48,7 +48,7 @@ limitations under the License.
 #define CBAG_COMMON_LP_LOOKUP_H
 
 #include <unordered_map>
-
+#include <optional>
 #include <cbag/common/typedefs.h>
```

## Problem #5
```shell
(.venv) [kcaisley@asiclab008 cbag]$ cmake --build build
[  1%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/main.cpp.o
[  2%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/parse_map.cpp.o
[  3%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/read.cpp.o
[  4%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/read_util.cpp.o
[  5%] Building CXX object CMakeFiles/cbag.dir/src/cbag/gdsii/write.cpp.o
[  7%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/cellview.cpp.o
[  8%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/cellview_poly.cpp.o
[  9%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/cellview_util.cpp.o
[ 10%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/grid_object.cpp.o
[ 11%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/instance.cpp.o
[ 12%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/lp_lookup.cpp.o
[ 14%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/path.cpp.o
[ 15%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/path_util.cpp.o
In file included from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/src/cbag/layout/path_util.cpp:47:
/usr/include/fmt/core.h: In instantiation of ‘constexpr fmt::v9::detail::value<Context> fmt::v9::detail::make_value(T&&) [with Context = fmt::v9::basic_format_context<fmt::v9::appender, char>; T = cbag::layout::vector45&]’:
/usr/include/fmt/core.h:1777:29:   required from ‘constexpr fmt::v9::detail::value<Context> fmt::v9::detail::make_arg(T&&) [with bool IS_PACKED = true; Context = fmt::v9::basic_format_context<fmt::v9::appender, char>; type <anonymous> = fmt::v9::detail::type::custom_type; T = cbag::layout::vector45&; typename std::enable_if<IS_PACKED, int>::type <anonymous> = 0]’
/usr/include/fmt/core.h:1901:77:   required from ‘constexpr fmt::v9::format_arg_store<Context, Args>::format_arg_store(T&& ...) [with T = {cbag::layout::vector45&}; Context = fmt::v9::basic_format_context<fmt::v9::appender, char>; Args = {cbag::layout::vector45}]’
/usr/include/fmt/core.h:1918:31:   required from ‘constexpr fmt::v9::format_arg_store<Context, typename std::remove_cv<typename std::remove_reference<Args>::type>::type ...> fmt::v9::make_format_args(Args&& ...) [with Context = basic_format_context<appender, char>; Args = {cbag::layout::vector45&}]’
/usr/include/fmt/core.h:3206:44:   required from ‘std::string fmt::v9::format(format_string<T ...>, T&& ...) [with T = {cbag::layout::vector45&}; std::string = std::__cxx11::basic_string<char>; format_string<T ...> = basic_format_string<char, cbag::layout::vector45&>]’
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/src/cbag/layout/path_util.cpp:123:48:   required from here
/usr/include/fmt/core.h:1757:7: error: static assertion failed: Cannot format an argument. To make type T formattable provide a formatter<T> specialization: https://fmt.dev/latest/api.html#udt
 1757 |       formattable,
      |       ^~~~~~~~~~~
/usr/include/fmt/core.h:1757:7: note: ‘formattable’ evaluates to false
gmake[2]: *** [CMakeFiles/cbag.dir/build.make:356: CMakeFiles/cbag.dir/src/cbag/layout/path_util.cpp.o] Error 1
gmake[1]: *** [CMakeFiles/Makefile2:124: CMakeFiles/cbag.dir/all] Error 2
gmake: *** [Makefile:136: all] Error 2
```

I think a similar problem is seen here: https://github.com/fmtlib/fmt/issues/3034

Seems I need to made a change to the function call, to meet this latest issue: https://fmt.dev/latest/api.html#udt

I simply commented out the line:
`throw std::invalid_argument(fmt::format("path segment vector {} not valid", p_norm));`

And it proceeded until 52% compilation


and finally an unused fix.....

```
diff --git a/src/cbag/layout/path_util.cpp b/src/cbag/layout/path_util.cpp
index b9a0802..3c62df2 100644
--- a/src/cbag/layout/path_util.cpp
+++ b/src/cbag/layout/path_util.cpp
@@ -46,6 +46,7 @@ limitations under the License.
 
 #include <fmt/core.h>
 #include <fmt/ostream.h>
+//#include <fmt/format.h>     // trying to add this code
 
 #include <cbag/layout/path_util.h>
```

## Problem #6
```shell
(.venv) [kcaisley@asiclab008 cbag]$ cmake --build build
[  1%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/path_util.cpp.o
[  2%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/pin.cpp.o
[  3%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/routing_grid.cpp.o
[  4%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/routing_grid_util.cpp.o
[  5%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/tech.cpp.o
[  7%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/tech_util.cpp.o
[  8%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/track_coloring.cpp.o
[  9%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/track_info.cpp.o
[ 10%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/track_info_util.cpp.o
[ 11%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/vector45.cpp.o
[ 12%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/via.cpp.o
[ 14%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/via_info.cpp.o
[ 15%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/via_lookup.cpp.o
[ 16%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/via_param.cpp.o
[ 17%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/via_param_util.cpp.o
[ 18%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/via_util.cpp.o
[ 20%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/via_wrapper.cpp.o
[ 21%] Building CXX object CMakeFiles/cbag.dir/src/cbag/layout/wire_width.cpp.o
[ 22%] Building CXX object CMakeFiles/cbag.dir/src/cbag/logging/logging.cpp.o
[ 23%] Building CXX object CMakeFiles/cbag.dir/src/cbag/netlist/cdl.cpp.o
[ 24%] Building CXX object CMakeFiles/cbag.dir/src/cbag/netlist/core.cpp.o
[ 25%] Building CXX object CMakeFiles/cbag.dir/src/cbag/netlist/lstream.cpp.o
[ 27%] Building CXX object CMakeFiles/cbag.dir/src/cbag/netlist/netlist.cpp.o
[ 28%] Building CXX object CMakeFiles/cbag.dir/src/cbag/netlist/nstream_output.cpp.o
[ 29%] Building CXX object CMakeFiles/cbag.dir/src/cbag/netlist/spectre.cpp.o
[ 30%] Building CXX object CMakeFiles/cbag.dir/src/cbag/netlist/verilog.cpp.o
[ 31%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/arc.cpp.o
[ 32%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/cellview.cpp.o
[ 34%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/cellview_info.cpp.o
[ 35%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/donut.cpp.o
[ 36%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/ellipse.cpp.o
[ 37%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/eval_text.cpp.o
[ 38%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/instance.cpp.o
[ 40%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/line.cpp.o
[ 41%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/path.cpp.o
[ 42%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/pin_figure.cpp.o
[ 43%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/pin_object.cpp.o
[ 44%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/polygon.cpp.o
[ 45%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/rectangle.cpp.o
[ 47%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/shape_base.cpp.o
[ 48%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/term_attr.cpp.o
[ 49%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/text_base.cpp.o
[ 50%] Building CXX object CMakeFiles/cbag.dir/src/cbag/schematic/text_t.cpp.o
[ 51%] Building CXX object CMakeFiles/cbag.dir/src/cbag/spirit/ast.cpp.o
[ 52%] Building CXX object CMakeFiles/cbag.dir/src/cbag/spirit/name.cpp.o
In file included from /usr/include/boost/spirit/home/x3/operator/sequence.hpp:12,
                 from /usr/include/boost/spirit/home/x3/operator.hpp:10,
                 from /usr/include/boost/spirit/home/x3.hpp:19,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/spirit/config.h:50,
                 from /faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/src/cbag/spirit/name.cpp:47:
/usr/include/boost/spirit/home/x3/operator/detail/sequence.hpp: In instantiation of ‘struct boost::spirit::x3::detail::partition_attribute<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:133&)> >, boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::sequence<boost::spirit::x3::uint_parser<unsigned int>, boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > > > > > > >, cbag::spirit::ast::range, boost::spirit::x3::context<boost::spirit::x3::error_handler_tag, const std::reference_wrapper<boost::spirit::x3::error_handler<__gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> > > >, boost::spirit::x3::unused_type>, void>’:
/usr/include/boost/spirit/home/x3/operator/detail/sequence.hpp:243:15:   required from ‘bool boost::spirit::x3::detail::parse_sequence(const Parser&, Iterator&, const Iterator&, const Context&, RContext&, Attribute&, AttributeCategory) [with Parser = boost::spirit::x3::sequence<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:133&)> >, boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::sequence<boost::spirit::x3::uint_parser<unsigned int>, boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > > > > > > > >; Iterator = __gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> >; Context = boost::spirit::x3::context<boost::spirit::x3::error_handler_tag, const std::reference_wrapper<boost::spirit::x3::error_handler<__gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> > > >, boost::spirit::x3::unused_type>; RContext = cbag::spirit::ast::range; Attribute = cbag::spirit::ast::range; AttributeCategory = boost::spirit::x3::traits::tuple_attribute]’
/usr/include/boost/spirit/home/x3/operator/sequence.hpp:46:42:   required from ‘bool boost::spirit::x3::sequence<Left, Right>::parse(Iterator&, const Iterator&, const Context&, RContext&, Attribute&) const [with Iterator = __gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> >; Context = boost::spirit::x3::context<boost::spirit::x3::error_handler_tag, const std::reference_wrapper<boost::spirit::x3::error_handler<__gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> > > >, boost::spirit::x3::unused_type>; RContext = cbag::spirit::ast::range; Attribute = cbag::spirit::ast::range; Left = boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:133&)> >; Right = boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::sequence<boost::spirit::x3::uint_parser<unsigned int>, boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > > > > > > >]’
/usr/include/boost/spirit/home/x3/directive/expect.hpp:54:41:   required from ‘bool boost::spirit::x3::expect_directive<Subject>::parse(Iterator&, const Iterator&, const Context&, RContext&, Attribute&) const [with Iterator = __gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> >; Context = boost::spirit::x3::context<boost::spirit::x3::error_handler_tag, const std::reference_wrapper<boost::spirit::x3::error_handler<__gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> > > >, boost::spirit::x3::unused_type>; RContext = cbag::spirit::ast::range; Attribute = cbag::spirit::ast::range; Subject = boost::spirit::x3::sequence<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:133&)> >, boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::sequence<boost::spirit::x3::uint_parser<unsigned int>, boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > > > > > > > >]’
/usr/include/boost/spirit/home/x3/operator/detail/sequence.hpp:253:34:   required from ‘bool boost::spirit::x3::detail::parse_sequence(const Parser&, Iterator&, const Iterator&, const Context&, RContext&, Attribute&, AttributeCategory) [with Parser = boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::sequence<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:133&)> >, boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::sequence<boost::spirit::x3::uint_parser<unsigned int>, boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > > > > > > > > > >; Iterator = __gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> >; Context = boost::spirit::x3::context<boost::spirit::x3::error_handler_tag, const std::reference_wrapper<boost::spirit::x3::error_handler<__gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> > > >, boost::spirit::x3::unused_type>; RContext = cbag::spirit::ast::range; Attribute = cbag::spirit::ast::range; AttributeCategory = boost::spirit::x3::traits::tuple_attribute]’
/usr/include/boost/spirit/home/x3/operator/sequence.hpp:46:42:   required from ‘bool boost::spirit::x3::sequence<Left, Right>::parse(Iterator&, const Iterator&, const Context&, RContext&, Attribute&) const [with Iterator = __gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> >; Context = boost::spirit::x3::context<boost::spirit::x3::error_handler_tag, const std::reference_wrapper<boost::spirit::x3::error_handler<__gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> > > >, boost::spirit::x3::unused_type>; RContext = cbag::spirit::ast::range; Attribute = cbag::spirit::ast::range; Left = boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>; Right = boost::spirit::x3::expect_directive<boost::spirit::x3::sequence<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:133&)> >, boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::sequence<boost::spirit::x3::uint_parser<unsigned int>, boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > > > > > > > > >]’
/usr/include/boost/spirit/home/x3/operator/detail/sequence.hpp:252:30:   [ skipping 44 instantiation contexts, use -ftemplate-backtrace-limit=0 to disable ]
/usr/include/boost/spirit/home/x3/nonterminal/detail/rule.hpp:240:42:   required from ‘static bool boost::spirit::x3::detail::rule_parser<Attribute, ID, skip_definition_injection>::parse_rhs_main(const RHS&, Iterator&, const Iterator&, const Context&, RContext&, ActualAttribute&, mpl_::true_) [with RHS = boost::spirit::x3::rule_definition<cbag::spirit::parser::name_rep_class, boost::spirit::x3::alternative<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::literal_string<const char*, boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > >, boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::alternative<boost::spirit::x3::sequence<boost::spirit::x3::rule<cbag::spirit::parser::name_unit_class, cbag::spirit::ast::name_unit, true>, boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> >, boost::spirit::x3::sequence<boost::spirit::x3::rule<cbag::spirit::parser::name_class, cbag::spirit::ast::name, true>, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > > > > > >, boost::spirit::x3::sequence<boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::literal_string<const char*, boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::rule<cbag::spirit::parser::name_unit_class, cbag::spirit::ast::name_unit, true> > > >, cbag::spirit::ast::name_rep, true, true>; Iterator = __gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> >; Context = boost::spirit::x3::context<boost::spirit::x3::error_handler_tag, const std::reference_wrapper<boost::spirit::x3::error_handler<__gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> > > >, boost::spirit::x3::unused_type>; RContext = cbag::spirit::ast::name_rep; ActualAttribute = cbag::spirit::ast::name_rep; Attribute = cbag::spirit::ast::name_rep; ID = cbag::spirit::parser::name_rep_class; bool skip_definition_injection = true; mpl_::true_ = mpl_::bool_<true>]’
/usr/include/boost/spirit/home/x3/nonterminal/detail/rule.hpp:267:34:   required from ‘static bool boost::spirit::x3::detail::rule_parser<Attribute, ID, skip_definition_injection>::parse_rhs_main(const RHS&, Iterator&, const Iterator&, const Context&, RContext&, ActualAttribute&) [with RHS = boost::spirit::x3::rule_definition<cbag::spirit::parser::name_rep_class, boost::spirit::x3::alternative<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::literal_string<const char*, boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > >, boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::alternative<boost::spirit::x3::sequence<boost::spirit::x3::rule<cbag::spirit::parser::name_unit_class, cbag::spirit::ast::name_unit, true>, boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> >, boost::spirit::x3::sequence<boost::spirit::x3::rule<cbag::spirit::parser::name_class, cbag::spirit::ast::name, true>, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > > > > > >, boost::spirit::x3::sequence<boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::literal_string<const char*, boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::rule<cbag::spirit::parser::name_unit_class, cbag::spirit::ast::name_unit, true> > > >, cbag::spirit::ast::name_rep, true, true>; Iterator = __gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> >; Context = boost::spirit::x3::context<boost::spirit::x3::error_handler_tag, const std::reference_wrapper<boost::spirit::x3::error_handler<__gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> > > >, boost::spirit::x3::unused_type>; RContext = cbag::spirit::ast::name_rep; ActualAttribute = cbag::spirit::ast::name_rep; Attribute = cbag::spirit::ast::name_rep; ID = cbag::spirit::parser::name_rep_class; bool skip_definition_injection = true]’
/usr/include/boost/spirit/home/x3/nonterminal/detail/rule.hpp:281:34:   required from ‘static bool boost::spirit::x3::detail::rule_parser<Attribute, ID, skip_definition_injection>::parse_rhs(const RHS&, Iterator&, const Iterator&, const Context&, RContext&, ActualAttribute&, mpl_::false_) [with RHS = boost::spirit::x3::rule_definition<cbag::spirit::parser::name_rep_class, boost::spirit::x3::alternative<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::literal_string<const char*, boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > >, boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::alternative<boost::spirit::x3::sequence<boost::spirit::x3::rule<cbag::spirit::parser::name_unit_class, cbag::spirit::ast::name_unit, true>, boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> >, boost::spirit::x3::sequence<boost::spirit::x3::rule<cbag::spirit::parser::name_class, cbag::spirit::ast::name, true>, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > > > > > >, boost::spirit::x3::sequence<boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::literal_string<const char*, boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::rule<cbag::spirit::parser::name_unit_class, cbag::spirit::ast::name_unit, true> > > >, cbag::spirit::ast::name_rep, true, true>; Iterator = __gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> >; Context = boost::spirit::x3::context<boost::spirit::x3::error_handler_tag, const std::reference_wrapper<boost::spirit::x3::error_handler<__gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> > > >, boost::spirit::x3::unused_type>; RContext = cbag::spirit::ast::name_rep; ActualAttribute = cbag::spirit::ast::name_rep; Attribute = cbag::spirit::ast::name_rep; ID = cbag::spirit::parser::name_rep_class; bool skip_definition_injection = true; mpl_::false_ = mpl_::bool_<false>]’
/usr/include/boost/spirit/home/x3/nonterminal/detail/rule.hpp:330:37:   required from ‘static bool boost::spirit::x3::detail::rule_parser<Attribute, ID, skip_definition_injection>::call_rule_definition(const RHS&, const char*, Iterator&, const Iterator&, const Context&, ActualAttribute&, ExplicitAttrPropagation) [with RHS = boost::spirit::x3::rule_definition<cbag::spirit::parser::name_rep_class, boost::spirit::x3::alternative<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::literal_string<const char*, boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > >, boost::spirit::x3::sequence<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::alternative<boost::spirit::x3::sequence<boost::spirit::x3::rule<cbag::spirit::parser::name_unit_class, cbag::spirit::ast::name_unit, true>, boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> >, boost::spirit::x3::sequence<boost::spirit::x3::rule<cbag::spirit::parser::name_class, cbag::spirit::ast::name, true>, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > > > > > >, boost::spirit::x3::sequence<boost::spirit::x3::optional<boost::spirit::x3::sequence<boost::spirit::x3::sequence<boost::spirit::x3::literal_string<const char*, boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type>, boost::spirit::x3::expect_directive<boost::spirit::x3::action<boost::spirit::x3::uint_parser<unsigned int>, cbag::spirit::parser::<lambda(auto:134&)> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::literal_char<boost::spirit::char_encoding::standard, boost::spirit::x3::unused_type> > > >, boost::spirit::x3::expect_directive<boost::spirit::x3::rule<cbag::spirit::parser::name_unit_class, cbag::spirit::ast::name_unit, true> > > >, cbag::spirit::ast::name_rep, true, true>; Iterator = __gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> >; Context = boost::spirit::x3::context<boost::spirit::x3::error_handler_tag, const std::reference_wrapper<boost::spirit::x3::error_handler<__gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> > > >, boost::spirit::x3::unused_type>; ActualAttribute = cbag::spirit::ast::name_rep; ExplicitAttrPropagation = mpl_::bool_<true>; Attribute = cbag::spirit::ast::name_rep; ID = cbag::spirit::parser::name_rep_class; bool skip_definition_injection = true]’
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/include/cbag/spirit/name_def.h:112:1:   required from ‘bool cbag::spirit::parser::parse_rule(boost::spirit::x3::detail::rule_id<name_rep_class>, Iterator&, const Iterator&, const Context&, boost::spirit::x3::rule<name_rep_class, cbag::spirit::ast::name_rep, true>::attribute_type&) [with Iterator = __gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> >; Context = boost::spirit::x3::context<boost::spirit::x3::error_handler_tag, const std::reference_wrapper<boost::spirit::x3::error_handler<__gnu_cxx::__normal_iterator<const char*, std::__cxx11::basic_string<char> > > >, boost::spirit::x3::unused_type>; boost::spirit::x3::rule<name_rep_class, cbag::spirit::ast::name_rep, true>::attribute_type = cbag::spirit::ast::name_rep]’
/faust/user/kcaisley/designs/dmc65v2/bag/pybag/cbag/src/cbag/spirit/name.cpp:53:1:   required from here
/usr/include/boost/spirit/home/x3/operator/detail/sequence.hpp:144:25: error: static assertion failed: Size of the passed attribute is bigger than expected.
  144 |             actual_size <= expected_size
      |             ~~~~~~~~~~~~^~~~~~~~~~~~~~~~
/usr/include/boost/spirit/home/x3/operator/detail/sequence.hpp:144:25: note: the comparison reduces to ‘(3 <= 2)’
gmake[2]: *** [CMakeFiles/cbag.dir/build.make:972: CMakeFiles/cbag.dir/src/cbag/spirit/name.cpp.o] Error 1
gmake[1]: *** [CMakeFiles/Makefile2:124: CMakeFiles/cbag.dir/all] Error 2

```

How I bulit containers to test the other versions of EL:

# Container Creation
sudo dnf install apptainer
apptainer build --sandbox cbag_centos7.sif docker://centos:7
apptainer shell --fakeroot --writable cbag_centos7.sif/

# For Centos7:
yum -y update && yum clean all
yum install centos-release-scl
yum install devtoolset-8
yum install epel-release
yum install which yaml-cpp yaml-cpp-devel fmt fmt-devel spdlog spdlog-devel cmake3 //note cmake3
source /opt/rh/devtoolset-8/enable

cd to folder and export CC and CXX
tried to build, but didn't work as spdlog wasn't new enough to include .cmake files

# For RockyLinux 8.7:
dnf -y update && dnf clean all
dnf install epel-release
dnf install which yaml-cpp yaml-cpp-devel fmt fmt-devel spdlog spdlog-devel cmake gcc gcc-c++ boost boost-devel

starts compiling after stting static boost to OFF, but then fails at compiling with boost...

# For RockyLinux 9.1:
dnf -y update && dnf clean all
dnf -y install epel-release
dnf -y install which yaml-cpp yaml-cpp-devel fmt fmt-devel spdlog spdlog-devel cmake gcc gcc-c++ boost boost-devel

same errors as fedora 37

# Email to Ayan:

If you have a moment, would it be possible for you to check what versions of gcc
and CMake are used to compile your copy of the CBAG submodule, and what versions
of the Boost, fmt, spdlog, and yaml-cpp libraries it is built against?

I have tried the following combinations of packages versions across various
distributions:

Distro      gcc/g++ CMake   Boost   fmt     spdlog  yaml-cpp
CentOS      7.9     8.3.1   3.17.0  1.53    6.2.1   0.10.0 0.5.1  (devtoolset-8)
RHEL        8.7     8.5.0   3.20.2  1.66    6.3.1   1.5.0 0.6.2
RHEL        9.1     11.3.1  3.20.2  1.75    8.1.1   1.10.0 0.6.3
Fedora 37   12.2.1  3.25.2  1.78    9.1.0   1.10.0  0.6.3
Fedora 37   12.2.1  3.25.2  1.81    9.1.0   1.11.0  0.6.3

In each case I have linked my copies of the OA binaies, have worked through
successfully generating make/build files with CMake, and compilation begins. But
in each case there are numerous compilation errors, primarily in the form of
static assertion failures originating from the fmt and Boost libraries. I've
made the most progress in the latter Fedora 37 configuration by editing the CBAG
source to be compatible with fmt >9.0, but am still stuck on a couple of the
more cryptic errors.

fmt     spdlog      yaml-cpp
8.1.1   1.10.0      0.6.3



export OA_SRC_ROOT=/cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa/22.50p001
export OA_LINK_DIR=${OA_SRC_ROOT}/lib/linux_rhel50_gcc44x_64/opt             
export OA_INCLUDE_DIR=${OA_SRC_ROOT}/include


I faced one last bug, which was simple to fix like Problem #1 above:

[ 87%] Building CXX object CMakeFiles/cbag.dir/src/cbag/oa/read_lib.cpp.o
In file included from /faust/user/kcaisley/packages/cbag/include/cbag/util/sorted_map.h:52,
                 from /faust/user/kcaisley/packages/cbag/include/cbag/schematic/cellview_fwd.h:53,
                 from /faust/user/kcaisley/packages/cbag/include/cbag/schematic/cellview.h:50,
                 from /faust/user/kcaisley/packages/cbag/src/cbag/oa/read_lib.cpp:47:
/faust/user/kcaisley/packages/cbag/include/cbag/util/sorted_vector.h: In member function ‘const cbag::util::sorted_vector<T, Compare>::value_type& cbag::util::sorted_vector<T, Compare>::at_front() const’:
/faust/user/kcaisley/packages/cbag/include/cbag/util/sorted_vector.h:107:24: error: ‘out_of_range’ is not a member of ‘std’
  107 |             throw std::out_of_range("Cannot get front of empty vector.");
      |                        ^~~~~~~~~~~~
/faust/user/kcaisley/packages/cbag/include/cbag/util/sorted_vector.h: In member function ‘const cbag::util::sorted_vector<T, Compare>::value_type& cbag::util::sorted_vector<T, Compare>::at_back() const’:
/faust/user/kcaisley/packages/cbag/include/cbag/util/sorted_vector.h:112:24: error: ‘out_of_range’ is not a member of ‘std’
  112 |             throw std::out_of_range("Cannot get back of empty vector.");
      |                        ^~~~~~~~~~~~
compilation terminated due to -fmax-errors=2.
gmake[2]: *** [CMakeFiles/cbag.dir/build.make:1210: CMakeFiles/cbag.dir/src/cbag/oa/read_lib.cpp.o] Error 1
gmake[1]: *** [CMakeFiles/Makefile2:124: CMakeFiles/cbag.dir/all] Error 2

So I think I'll just:

To use the std::out_of_range function in C++ code, you need to include the <stdexcept> header file in your code.

`#include <stdexcept>` in include/cbag/util/sorted_vector.h

cmake -H. -B_build -DHUNTER_STATUS_DEBUG=ON -DCMAKE_BUILD_TYPE=Release

cmake --build _build



Make sure, when installing from python top level build.sh, you need to have 'sudo dnf install python3.10 python3.10-devel`

## 22 March

I'd like to understand a number of concepts related to my Python/Pybind/CMake/C++ environment:

Duck typing
generics
    in C++ but not Python, due to it's typing
    in C++ done with templates
    avoids the need for function overloading


other C++ features that were added later:
garbage collector
shared pointer
metaprogramming
detailing


Searching for Pybind references:

[kcaisley@asiclab008 pybag]$ grep -r --exclude-dir={pybind11,_build} "PYBIND11_" 
src/pybag/core.cpp:PYBIND11_MODULE(core, m) {
src/pybag/tech.cpp:        PYBIND11_OVERLOAD_PURE(cbag::em_specs_t, cbag::layout::tech, get_metal_em_specs, layer,
src/pybag/tech.cpp:        PYBIND11_OVERLOAD_PURE(cbag::em_specs_t, cbag::layout::tech, get_via_em_specs, layer_dir,
src/pybag/enum_conv.h:    PYBIND11_OBJECT_DEFAULT(PyOrient2D, obj_base, true_check);
src/pybag/enum_conv.h:    PYBIND11_OBJECT_DEFAULT(PyOrient, obj_base, true_check);
src/pybag/enum_conv.h:    PYBIND11_OBJECT_DEFAULT(PyLogLevel, obj_base, true_check);
src/pybag/enum_conv.h:    PYBIND11_OBJECT_DEFAULT(PySigType, obj_base, true_check);
src/pybag/enum_conv.h:    PYBIND11_OBJECT_DEFAULT(PyDesignOutput, obj_base, true_check);
pybind11_generics/src/main.cpp:PYBIND11_MODULE(pyg_test, m) {
pybind11_generics/src/test_list.cpp:        PYBIND11_OVERLOAD_PURE(std::string, /* Return type */
pybind11_generics/include/pybind11_generics/dict.h:#ifndef PYBIND11_GENERICS_DICT_H
pybind11_generics/include/pybind11_generics/dict.h:#define PYBIND11_GENERICS_DICT_H
pybind11_generics/include/pybind11_generics/tuple.h:#ifndef PYBIND11_GENERICS_TUPLE_H
pybind11_generics/include/pybind11_generics/tuple.h:#define PYBIND11_GENERICS_TUPLE_H
pybind11_generics/include/pybind11_generics/list.h:#ifndef PYBIND11_GENERICS_LIST_H
pybind11_generics/include/pybind11_generics/list.h:#define PYBIND11_GENERICS_LIST_H
pybind11_generics/include/pybind11_generics/any.h:#ifndef PYBIND11_GENERICS_ANY_H
pybind11_generics/include/pybind11_generics/any.h:#define PYBIND11_GENERICS_ANY_H
pybind11_generics/include/pybind11_generics/any.h:    PYBIND11_OBJECT_DEFAULT(Any, any_base, true_check);
pybind11_generics/include/pybind11_generics/type_name.h:#ifndef PYBIND11_GENERICS_TYPE_NAME_H
pybind11_generics/include/pybind11_generics/type_name.h:#define PYBIND11_GENERICS_TYPE_NAME_H
pybind11_generics/include/pybind11_generics/optional.h:#ifndef PYBIND11_GENERICS_OPTIONAL_H
pybind11_generics/include/pybind11_generics/optional.h:#define PYBIND11_GENERICS_OPTIONAL_H
pybind11_generics/include/pybind11_generics/optional.h:    PYBIND11_OBJECT_DEFAULT(Optional, optional_base, optional_check);
pybind11_generics/include/pybind11_generics/custom.h:#ifndef PYBIND11_GENERICS_CUSTOM_H
pybind11_generics/include/pybind11_generics/custom.h:#define PYBIND11_GENERICS_CUSTOM_H
pybind11_generics/include/pybind11_generics/custom.h:    PYBIND11_OBJECT_DEFAULT(Custom, custom_base, true_check);
pybind11_generics/include/pybind11_generics/cast_input_iterator.h:#ifndef PYBIND11_GENERICS_CAST_INPUT_ITERATOR_H
pybind11_generics/include/pybind11_generics/cast_input_iterator.h:#define PYBIND11_GENERICS_CAST_INPUT_ITERATOR_H
pybind11_generics/include/pybind11_generics/iterator.h:#ifndef PYBIND11_GENERICS_ITERATOR_H
pybind11_generics/include/pybind11_generics/iterator.h:#define PYBIND11_GENERICS_ITERATOR_H
pybind11_generics/include/pybind11_generics/iterator.h:    PYBIND11_OBJECT_DEFAULT(PyIterator, iterator_base, PyIter_Check);
pybind11_generics/include/pybind11_generics/iterable.h:#ifndef PYBIND11_GENERICS_ITERABLE_H
pybind11_generics/include/pybind11_generics/iterable.h:#define PYBIND11_GENERICS_ITERABLE_H
pybind11_generics/include/pybind11_generics/iterable.h:    PYBIND11_OBJECT_DEFAULT(Iterable, iterable_base, iterable_check)
pybind11_generics/include/pybind11_generics/union.h:#ifndef PYBIND11_GENERICS_UNION_H
pybind11_generics/include/pybind11_generics/union.h:#define PYBIND11_GENERICS_UNION_H
pybind11_generics/include/pybind11_generics/cast.h:#ifndef PYBIND11_GENERICS_CAST_H
pybind11_generics/include/pybind11_generics/cast.h:#define PYBIND11_GENERICS_CAST_H
pybind11_generics/CMakeLists.txt:set(PYBIND11_GENERICS_MASTER_PROJECT OFF)
pybind11_generics/CMakeLists.txt:  set(PYBIND11_GENERICS_MASTER_PROJECT ON)
pybind11_generics/CMakeLists.txt:option(PYBIND11_GENERICS_TEST "Build pybind11_generics test suite?"
pybind11_generics/CMakeLists.txt:  ${PYBIND11_GENERICS_MASTER_PROJECT})
pybind11_generics/CMakeLists.txt:set(PYBIND11_CPP_STANDARD --std=c++1z)
pybind11_generics/CMakeLists.txt:if (PYBIND11_GENERICS_TEST)


Using CMake with external projects:

http://www.saoe.net/blog/using-cmake-with-external-projects/


https://www.scivision.dev/cmake-fetchcontent-vs-external-project/


git hashes: b6f4ceaed0a0a24ccf575fab6c56dd50ccf6f1a9 deps/fmt (8.1.1)
76fb40d95455f249bd70824ecfcae7a8f0930fa3 deps/spdlog (v1.2.1-2055-g76fb40d9)


# CMake workflow:

First, download and bootstrap vcpkg itself; it can be installed anywhere, but generally we recommend using vcpkg as a submodule for CMake projects.

$ git clone https://github.com/microsoft/vcpkg
$ ./vcpkg/bootstrap-vcpkg.sh

To install the libraries for your project, run:

$ ./vcpkg/vcpkg install [packages to install]

You can also search for the libraries you need with the search subcommand:

$ ./vcpkg/vcpkg search [search term]

In order to use vcpkg with CMake, you can use the toolchain file:

$ cmake -B [build directory] -S . "-DCMAKE_TOOLCHAIN_FILE=[path to vcpkg]/scripts/buildsystems/vcpkg.cmake"
$ cmake --build [build directory]




# Visual Studio Code with CMake Tools 
Adding the following to your workspace settings.json will make CMake Tools automatically use vcpkg for libraries:

{
  "cmake.configureSettings": {
    "CMAKE_TOOLCHAIN_FILE": "[vcpkg root]/scripts/buildsystems/vcpkg.cmake"
  }
}


# To enable versioning when running vcpkg
./vcpkg/vcpkg --feature-flags="versions" install

I should test this from just the cbag directory:

```
cmake -B_build -S. -DCMAKE_TOOLCHAIN_FILE=/home/kcaisley/packages/vcpkg/scripts/buildsystems/vcpkg.cmake
```


Step 1: Clone the vcpkg repo

```
git clone https://github.com/Microsoft/vcpkg.git
```

Make sure you are in the directory you want the tool installed to before doing this.

Step 2: Run the bootstrap script to build vcpkg

```
./vcpkg/bootstrap-vcpkg.sh
```

## Notes about building cbag with vcpkg

the errors with not finding compilers and make program only happen when running


fatal: path 'versions/baseline.json' exists on disk, but not in '664f8bb619b752430368d0f30a8289b761f5caba'

You can use the current commit as a baseline, which is:
        "builtin-baseline": "c9f906558f9bb12ee9811d6edc98ec9255c6cda5"
        
Adding the following before `project(cbag)`

```
set(CMAKE_MAKE_PROGRAM /usr/bin/make)
set(CMAKE_C_COMPILER /usr/bin/gcc)
set(CMAKE_CXX_COMPILER /usr/bin/g++)
```

Okay, that fixed it. Now the only error I'm seeing is:

```
error: Cannot resolve a minimum constraint for dependency boost-disjoint-sets from boost:x64-linux.
The dependency was not found in the baseline, indicating that the package did not exist at that time. This may be fixed by providing an explicit override version via the "overrides" field or by updating the baseline.
See `vcpkg help versioning` for more information.
```

These are the 
[two](https://devblogs.microsoft.com/cppblog/take-control-of-your-vcpkg-dependencies-with-versioning-support/)
[links](https://learn.microsoft.com/en-us/vcpkg/users/versioning.concepts)
needed for me to proceed in solving this error. Also, see `../../vcpkg/vcpkg help versioning`


This is how a manifest file should work:


{
    "name": "example",
    "version": "1.0",
    "builtin-baseline": "a14a6bcb27287e3ec138dba1b948a0cdbc337a3a",
    "dependencies": [
        { "name": "zlib", "version>=": "1.2.11#8" },
        "rapidjson"
    ],
    "overrides": [
        { "name": "rapidjson", "version": "2020-09-14" }
    ]
}



The boost components I probably need are:

container
container-hash
fusion
units
mpl
tokenizer
units
spirit



serialization (compiled, contains container_hash, and archive libraries)

spirit (header-only)
fusion
units
mpl
tokenizer


I give up for now. I can't install Boost with vcpkg. It's too frustrating. Boost 1.75 is the oldest I can install with a built-in baseline, and for some reason manually specifying the baseline with overrides requires me to write out each of the packages in Boost.


## Building on April 10
cp -r /cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa.aoi/22.50p001/ .

```
find . -type d -name "*example*"
```

This is the location of the binaries I want:
/mnt/md127/tools/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa.aoi/22.50p001

So, assuming it is mounted on my machine at `/cadence`, I can do:

```
cp -r /cadence/mentor/aoi_cal_2016.4_38.25/shared/pkgs/icv_oa.aoi/22.50p001/* .
```


## Multiple defenitions errors:

I'm finding some possible recommendations about how to figure out this multiple definitions issue:


https://stackoverflow.com/questions/69326932/multiple-definition-errors-during-gcc-linking-in-linux
https://stackoverflow.com/questions/37525922/how-to-handle-gcc-link-optionslike-whole-archive-allow-multiple-definition

The idea to hack it with `--allow-multiple-definition` in `target_link_libraries` doesn't work as `g++` doesn't support it.
