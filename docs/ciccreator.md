# Workflow

To compile:

```bash
make clean
make all
```

To run:

```bash
cd /users/kcaisley/frida/build
cic SAR_ESSCIRC16_28N.json ../tech/tsmc65/tech.json SAR_ESSCIRC16_28N
cic-gui SAR_ESSCIRC16_28N.cic ../tech/tsmc65/tech.json

# Need to use full file path for output dir, so that relative links aren't put in the skill files
cicpy transpile --layskill SAR_ESSCIRC16_28N.cic ../tech/tsmc65/tech.json test_tsmc65
python ../src/replace_in_file.py test_tsmc65_lay.il test_tsmc65/skill/ /users/kcaisley/frida/build/test_tsmc65/skill/
```




```ciw
ddUpdateLibList()
load("/users/kcaisley/frida/build/test_tsmc65_lay.il")

or 

load("/users/kcaisley/frida/build/test_tsmc65/skill/NCHDL_lay.il")
load("/users/kcaisley/frida/build/test_tsmc65/skill/CAP_lay.il.il")
```

# outstanding bugs:


### Could not find the Qt platform plugin "wayland" in ""


upon starting cadence, while Wayland is active:

```
Qt Unknown Message Type: Warning: Ignoring XDG_SESSION_TYPE=wayland on Gnome. Use QT_QPA_PLATFORM=wayland to run on Wayland anyway.
```

Then also when trying to start `cic-gui`:

```
QFactoryLoader::QFactoryLoader() checking directory path "/users/kcaisley/ciccreator/release/platforms" ...
qt.qpa.plugin: Could not find the Qt platform plugin "wayland" in ""
This application failed to start because no Qt platform plugin could be initialized. Reinstalling the application may fix this problem.
```

The issue is that I compiled it using qt5 originally, but then I set a LD_LIBRARY_PATH  with the variables set by some Siemens tools:

```
ldd ~/ciccreator/release.bak/cic-gui
	linux-vdso.so.1 (0x00007fffa97a2000)
	libQt5Widgets.so.5 => /eda/Siemens/2024-25/RHELx86/HLVX_2409/HL2409/SDD_HOME/hldrc/linux64/bin/libQt5Widgets.so.5 (0x00007fb5211e7000)
	libQt5Gui.so.5 => /eda/Siemens/2024-25/RHELx86/HLVX_2409/HL2409/SDD_HOME/hldrc/linux64/bin/libQt5Gui.so.5 (0x00007fb5207e3000)
	libQt5Core.so.5 => /eda/Siemens/2024-25/RHELx86/HLVX_2409/HL2409/SDD_HOME/hldrc/linux64/bin/libQt5Core.so.5 (0x00007fb51ffd6000)
	libGL.so.1 => /lib64/libGL.so.1 (0x00007fb51ff3a000)
	libstdc++.so.6 => /lib64/libstdc++.so.6 (0x00007fb51fc00000)
	libm.so.6 => /lib64/libm.so.6 (0x00007fb51fe5d000)
	libgcc_s.so.1 => /lib64/libgcc_s.so.1 (0x00007fb51fe43000)
	libc.so.6 => /lib64/libc.so.6 (0x00007fb51f800000)
	libpthread.so.0 => /lib64/libpthread.so.0 (0x00007fb51fe3e000)
	libz.so.1 => /lib64/libz.so.1 (0x00007fb51fbe6000)
	libicui18n.so.56 => /eda/Siemens/2024-25/RHELx86/HLVX_2409/HL2409/SDD_HOME/hldrc/linux64/bin/libicui18n.so.56 (0x00007fb51f367000)
	libicuuc.so.56 => /eda/Siemens/2024-25/RHELx86/HLVX_2409/HL2409/SDD_HOME/hldrc/linux64/bin/libicuuc.so.56 (0x00007fb51efaf000)
	libicudata.so.56 => /eda/Siemens/2024-25/RHELx86/HLVX_2409/HL2409/SDD_HOME/hldrc/linux64/bin/libicudata.so.56 (0x00007fb51d5cc000)
	libdl.so.2 => /lib64/libdl.so.2 (0x00007fb51fe37000)
	libgthread-2.0.so.0 => /lib64/libgthread-2.0.so.0 (0x00007fb51fe32000)
	libglib-2.0.so.0 => /lib64/libglib-2.0.so.0 (0x00007fb51faac000)
	/lib64/ld-linux-x86-64.so.2 (0x00007fb521a4f000)
	libGLX.so.0 => /lib64/libGLX.so.0 (0x00007fb51fa7a000)
	libX11.so.6 => /lib64/libX11.so.6 (0x00007fb51d484000)
	libXext.so.6 => /lib64/libXext.so.6 (0x00007fb51fa65000)
	libGLdispatch.so.0 => /lib64/libGLdispatch.so.0 (0x00007fb51d3cc000)
	libpcre.so.1 => /lib64/libpcre.so.1 (0x00007fb51d354000)
	libxcb.so.1 => /lib64/libxcb.so.1 (0x00007fb51fa3a000)
	libXau.so.6 => /lib64/libXau.so.6 (0x00007fb51fa34000)
```

But after re-compiling, with all the Qt6 packages installing, the conflict no longer occurs since the EDA tools don't seem to use qt6 yet.

```
ldd ~/ciccreator/release/cic-gui.linux-latest 
	linux-vdso.so.1 (0x00007ffecfca0000)
	libQt6Widgets.so.6 => /lib64/libQt6Widgets.so.6 (0x00007fc34c800000)
	libQt6Gui.so.6 => /lib64/libQt6Gui.so.6 (0x00007fc34be00000)
	libQt6Core.so.6 => /lib64/libQt6Core.so.6 (0x00007fc34b600000)
	libGLX.so.0 => /lib64/libGLX.so.0 (0x00007fc34cfe1000)
	libOpenGL.so.0 => /lib64/libOpenGL.so.0 (0x00007fc34c7d5000)
	libstdc++.so.6 => /lib64/libstdc++.so.6 (0x00007fc34b200000)
	libm.so.6 => /lib64/libm.so.6 (0x00007fc34bd25000)
	libgcc_s.so.1 => /lib64/libgcc_s.so.1 (0x00007fc34c7bb000)
	libc.so.6 => /lib64/libc.so.6 (0x00007fc34ae00000)
	libEGL.so.1 => /lib64/libEGL.so.1 (0x00007fc34cfcd000)
	libfontconfig.so.1 => /lib64/libfontconfig.so.1 (0x00007fc34c76c000)
	libX11.so.6 => /lib64/libX11.so.6 (0x00007fc34b4b8000)
	libglib-2.0.so.0 => /lib64/libglib-2.0.so.0 (0x00007fc34b0c6000)
	libQt6DBus.so.6 => /lib64/libQt6DBus.so.6 (0x00007fc34ad2f000)
	libxkbcommon.so.0 => /lib64/libxkbcommon.so.0 (0x00007fc34bce0000)
	libpng16.so.16 => /lib64/libpng16.so.16 (0x00007fc34c735000)
	libharfbuzz.so.0 => /lib64/libharfbuzz.so.0 (0x00007fc34ac60000)
	libfreetype.so.6 => /lib64/libfreetype.so.6 (0x00007fc34ab9d000)
	libz.so.1 => /lib64/libz.so.1 (0x00007fc34bcc6000)
	libicui18n.so.67 => /lib64/libicui18n.so.67 (0x00007fc34a800000)
	libicuuc.so.67 => /lib64/libicuuc.so.67 (0x00007fc34a615000)
	libzstd.so.1 => /lib64/libzstd.so.1 (0x00007fc34b00f000)
	libsystemd.so.0 => /lib64/libsystemd.so.0 (0x00007fc34a538000)
	libdouble-conversion.so.3 => /lib64/libdouble-conversion.so.3 (0x00007fc34bcb0000)
	libb2.so.1 => /lib64/libb2.so.1 (0x00007fc34bca7000)
	libpcre2-16.so.0 => /lib64/libpcre2-16.so.0 (0x00007fc34ab0d000)
	libcrypto.so.3 => /lib64/libcrypto.so.3 (0x00007fc34a000000)
	/lib64/ld-linux-x86-64.so.2 (0x00007fc34d02a000)
	libXext.so.6 => /lib64/libXext.so.6 (0x00007fc34bc92000)
	libGLdispatch.so.0 => /lib64/libGLdispatch.so.0 (0x00007fc349f48000)
	libxml2.so.2 => /lib64/libxml2.so.2 (0x00007fc349dbf000)
	libxcb.so.1 => /lib64/libxcb.so.1 (0x00007fc34b48d000)
	libpcre.so.1 => /lib64/libpcre.so.1 (0x00007fc349d47000)
	libdbus-1.so.3 => /lib64/libdbus-1.so.3 (0x00007fc34b43a000)
	libgraphite2.so.3 => /lib64/libgraphite2.so.3 (0x00007fc349d26000)
	libbz2.so.1 => /lib64/libbz2.so.1 (0x00007fc34bc7f000)
	libbrotlidec.so.1 => /lib64/libbrotlidec.so.1 (0x00007fc34b42c000)
	libicudata.so.67 => /lib64/libicudata.so.67 (0x00007fc348200000)
	libcap.so.2 => /lib64/libcap.so.2 (0x00007fc34a52e000)
	libgcrypt.so.20 => /lib64/libgcrypt.so.20 (0x00007fc3480c4000)
	liblzma.so.5 => /lib64/liblzma.so.5 (0x00007fc348098000)
	liblz4.so.1 => /lib64/liblz4.so.1 (0x00007fc348074000)
	libgomp.so.1 => /lib64/libgomp.so.1 (0x00007fc34802e000)
	libXau.so.6 => /lib64/libXau.so.6 (0x00007fc34bc79000)
	libbrotlicommon.so.1 => /lib64/libbrotlicommon.so.1 (0x00007fc34800b000)
	libgpg-error.so.0 => /lib64/libgpg-error.so.0 (0x00007fc347fe5000)
```


### Detected locale "C"

why is this my locale??


```
$ cic-gui SAR_ESSCIRC16_28N.cic ../tech/tsmc65/tech.json 
Detected locale "C" with character encoding "ANSI_X3.4-1968", which is not UTF-8.
Qt depends on a UTF-8 locale, and has switched to "C.UTF-8" instead.
If this causes problems, reconfigure your locale. See the locale(1) manual
for more information.
Requested decoration  "adwaita"  not found, falling back to default
(.venv) [kcaisley@asiclab003 build]$ locale
LANG=C
LC_CTYPE="C"
LC_NUMERIC="C"
LC_TIME="C"
LC_COLLATE="C"
LC_MONETARY="C"
LC_MESSAGES="C"
LC_PAPER="C"
LC_NAME="C"
LC_ADDRESS="C"
LC_TELEPHONE="C"
LC_MEASUREMENT="C"
LC_IDENTIFICATION="C"
LC_ALL=
```

Something in my `workspace.sh` script is doing this. It's the assura setup file!


### *Error* dbCreateRect: Invalid layer/purpose - (34 0)

The following code can be used to export valid layers and purposes from Virtuoso's CIW:

```
techid=techGetTechFile(ddGetObj("tsmcN65"))
techGetMfgGridResolution(techid)
techGetDBUPerUU(techid "maskLayout")
let((laylist) foreach(layer techid->layers laylist=cons(list(layer->name layer->number) laylist)) laylist)
let((purplist) foreach(purp techid->purposeDefs purplist=cons(list(purp->name purp->number) purplist)) purplist)
let((vialist) foreach(via techid->viaDefs vialist=cons(list(via->name via->layer1Num via->layer2Num via->params) vialist)) vialist)
```


# ciccreator notes

- Q Which docs page is more up to date?
  - Looks like this one: https://analogicus.com/ciccreator/index.html

- **Q** Are are input schematics using generic transistors and other devices?
  - Yep. You can see between the IHP130 and SKY130 videos, that the `.spi` input files are essentially the same. Also the `.json` files are pretty much the same too, with like 1% differences.

- **Q** Do these input netlists support parameterization, maybe through placeholders or using SPICE parameters?
  - Parameterization is essentially adding extra transistors, so I think I can handle this by simply having different netlists! I can write a python script which converts 

- **Q** How to deal with digital stdcells? Can one wrap them with ciccreator, or perhaps even just FOSS digital flows? I saw in the post from the PhD student that there appeared to be some compiled logic.

- Make files for everything

- git submodules to connect PDK to design to flow, etc

- Magic and Xschem use their own plaint plain text formats, very easy to gen

- Using Xschem to produce the input netlists isn't a anti-pattern!

- "glue" code should be used for SIM, DRC, LVS, PEX, etc (Makefiles are good!)

- Design information should be encoded into the SPICE file, not schematic

- regarding Transistors
  - **Q**: In the SKY130 video it was shown that unit W xtors came in a single fl, but then in the IHP130 follow-up video, several dimensions of transistors were show?
  - What does the `DL` in `NCHDL` and `PCHDL` stand for, in the netlist base instance names. 
  - His XTORs appear to have horizontal poly, while TSMC have vertical
  - Bulk contacts are needed, and he puts them off to the side in each cell
  - Unit includes dummy poly, as <=28nm needs it for matching
  - Only PDK variable *should* then be X and Y lambda
  - only difference between NMOS and PMOS is implant layer.
  - **Q** Only unit transistors allowed. Parrallel for larger width is allowed. Is series for larger L allowed?
  - **Q** Can I rotate my layout to have vertical Poly, easily?

- regarding circuits
  -  Can "inherit" placement and routing, in the case of different drive strengths.
  - Devices are first placed, starting with top device in netlist, placed in top left. Then device of same type (P vs N) are placed in same columns, non-matching are placed to the right.
  - Routing comes next.
    - A routing pattern like `--|-` means over and then down, with a small over at the ends
    - A routing patten `-|` means  over and then down
    - A routing patten `-` or `|` means just down, or just over, respectively
    - directed routes, similar to Tikz:
      - Directed routes require that you specify the ports of which devices which will be connected by a specific metal using a specific strategy
      - `M1, Y, MN:D-|--MP:D` means "Using metal 1, route net Y, from MN port D to MP port D, using an over before down strategy"
      - This can't push or shove, or avoid other metals. It's completely blind and relies on you to actually route.

    - Connectivity based routing is the alternative, which already know the ports of which devices need to be connected by a net.
      - Therefore you can connect 3+ pins with a single command, simply stating a metal, a net, and the method.



- A symbol can be associated (xschem,skill,etc) for making Virtuoso/Xschem schematics
- A 'class' is supported. Base device are of type Gds, circuits are Layout, like LayoutDigitalCells, for example
- the SPICE netlist can live outside the JSON file
- `IVX1` means an inverter with a drive strength of (times) 1

  - **Q** I'm not sure what the `_CV` suffix stands for though?

- **Q** NMOS and PMOS unit XTORs include substrate contacts, but these seem to not appear in the higher level circuit blocks, and are only having taps?
- `.spi` and `.json` pairs include:

  - capacitor
  - components: analog blocks, i.e. transmission gate
  - dig(ital): flip flops, combinational logic, active pull up/downs (TIEH = tie high)
  - dmos (core): for transistors, which has no .spi file
  - resistors, which also only has .json, and no .spi file

- `.tech` one file per PDK

  - `layers` section provides mapping between generic M1, M2, M3 and PDK specific names for these layers, and how to move with a via on these layers
  - `technology` section contains

    - unit, grid size, technology name
    - devices w/ names, type, ports, **Q** what are `propertymap`s?

  - `symbol_lib` and `symbol_libs` which provide symbols for generating schematics

    - are mostly pdk generic

  - `rules`

    - metal routing, transistor ASCII -> unit nm equivalent, and via dimensions are different between PDKs, even in the same size
    - Other rules are mostly the same, in that they scale linearity with the tech Lamda dimensions



