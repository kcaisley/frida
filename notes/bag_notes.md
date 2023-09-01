# Bag 3 Install

# Container
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


