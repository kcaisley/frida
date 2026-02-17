# FRIDA: Fast Radiation Imaging Digitizer Array

This project focuses on improving analog to digital converters (ADCs) in CMOS image sensors, the chip design discipline with arguably the most stringent constraints on silicon design density. A design flow built on open source EDA tools enables comparison across different circuit topologies and process nodes including 180, 130, 65, and 28 nm. So far, we've fabricated a prototype ASIC in 65 nm using this methodology, which targets a state-of-the-art 2500 um^2 area and 100 uW power budget, with a performance of 12-bit resolution at 10 Msps performance.

Frame-based radiation detectors with integrating front-ends are especially well-suited for applications like electron microscopy and X-ray imaging, where hit rates are high and spatial resolution should be maximized with simple pixels. This project also pursues a single-reticle array larger than 1 Mpixel with a continuous frame rate above 100,000 fps. To meet those array-level goals, the converter fabric must deliver aggregate throughput above 1000 Gbps while staying within a 1 W/cm² chip-bottom power-density budget and exceeding 5 ksps/µm² sampling-rate density. Successive-approximation ADCs are the primary architecture under study.

![ADC used in example system](docs/images/arch.png)

Seen below is the initial prototype, designed in 65nm and measuring 1x1 mm. On the prototype are 16 ADCs, each measuring 60x60um. The tapeout was submitted in Oct 2025, and will be tested upon arrival this Spring 2026.

> [!NOTE]
> For some more detailed information about the submitted prototype, see [design.pdf](docs/design.pdf).

![FRIDA chip Level](docs/images/frida_65A.png)

## Past Designs vs Current Target

The table below compares previous ADC designs with the current FRIDA target, highlighting improvements in resolution, speed, area, and energy efficiency. Notable advancements include higher conversion rates and lower power consumption per ADC, supporting the project's goal of scalable, high-performance digitizer arrays.

| Design  | [DCD-E](https://doi.org/10.1016/j.nima.2019.162544) | [CoRDIA](https://doi.org/10.1088/1742-6596/3010/1/012141) | M  | H  | FRIDA |
|-------------------------|-------------|------------|------------|-------------|-------------|
| Design resolution       | 8-bit       | 10-bit     | 8-bit      | 10-bit      | 12-bit      |
| ENOB                    | 8.3         | 8.8        | 8.0        | 9.5 ?       | 11.0 ?      |
| Conversion rate         | 6.25 MHz    | 2.5 MHz    | 4.5 MHz    | 10 MHz      | 10 MHz      |
| Dimensions of one ADC   | 40×55 μm²   | 80×330 μm² | 60×800 μm² | 15×100 μm²  | 50×50 μm²   |
| Area of one ADC         | 0.002 mm²   | 0.026 mm²  | 0.048 mm²  | 0.0015 mm²  | 0.0025 mm²  |
| Power of one ADC        | 960 μW      | 30 μW      | 700 μW     | 100 μW      | 200 μW ?    |
| FOM_csa (conv/sec/area) | 3125 Hz/μm² | 95 Hz/μm²  | 105 Hz/μm² | 5000 Hz/μm² | 5000 Hz/μm² |
| FOM_wal (J/conv-step)   | 487 fJ      | 26 fJ      | 608 fJ     | 14 fJ       | 10 fJ       |


# Usage

FRIDA exposes three flow modes via pytest:

- `netlist`: generate netlists only
- `simulate`: generate netlists and run simulation
- `measure`: reserved for measurement post-processing (currently unimplemented)

Run from the repo root:

```bash
source .venv/bin/activate
pytest flow/comp/test_comp.py -v --tech=ihp130 --flow=netlist --mode=min
```

## Flow Options

### `--flow=netlist`

Supported options:

- `--tech={generic,ihp130,tsmc65,tsmc28,tower180}`
- `--mode={min,max}`
- `--fmt={spectre,ngspice,yaml,verilog}` (`spice` accepted as alias)
- `--clean={yes,no}`

Notes:

- `--fmt=spectre` writes DUT-only Spectre netlists (`.scs`).
- `--fmt=ngspice` writes DUT-only SPICE netlists (`.sp`).
- `--fmt=yaml` writes DUT-only hierarchical YAML netlists.
- `--fmt=verilog` writes DUT-only structural Verilog netlists.

Examples:

```bash
# DUT-only YAML netlists
pytest flow/comp/test_comp.py -v --flow=netlist --mode=min --tech=ihp130 --fmt=yaml

# DUT-only Verilog netlists
pytest flow/comp/test_comp.py -v --flow=netlist --mode=min --tech=ihp130 --fmt=verilog
```

### `--flow=simulate`

Supported options:

- `--tech={generic,ihp130,tsmc65,tsmc28,tower180}`
- `--mode={min,max}`
- `--simulator={spectre,ngspice,xyce}`
- `--montecarlo={yes,no}`
- `--sim-server=<host[:port]>` (optional remote execution)
- `--clean={yes,no}`

Notes:

- `--fmt` is invalid for `simulate` flow.
- In simulate flow, `--simulator` determines netlist dialect/runtime backend.

Example:

```bash
pytest flow/comp/test_comp.py -v --flow=simulate --mode=min --tech=ihp130 --simulator=spectre
```

### `--flow=measure`

Status:

- Flow hook exists, but measurement logic is currently unimplemented in block tests.

Supported options currently mirror simulate setup:

- `--tech`, `--mode`, `--simulator`, `--montecarlo`, `--sim-server`, `--clean`

`--fmt` remains invalid here as well.


# Installation

## Spectre

FRIDA uses Cadence Spectre for signoff-oriented analog simulations. Ensure it
is installed and visible on `PATH` on whichever host runs the simulations.

```bash
which spectre
spectre -W
```

## Ngspice

FRIDA can also use `ngspice` for open-source simulation flows. The commands
below build from source; use either the Ubuntu path or the RHEL path depending
on your OS.

```bash
# Ubuntu 24.04 dependency install
sudo apt-get update
sudo apt-get install -y \
  build-essential autoconf automake libtool bison flex \
  libx11-6 libx11-dev libxaw7 libxaw7-dev libxmu6 libxmu-dev \
  libxext6 libxext-dev libxft2 libxft-dev \
  libfontconfig1 libfontconfig1-dev libxrender1 libxrender-dev \
  libfreetype6 libfreetype-dev libreadline8 libreadline-dev

# RHEL 9 dependency install
sudo dnf install -y epel-release
sudo dnf install -y \
  gcc gcc-c++ make autoconf automake libtool bison flex \
  libX11 libX11-devel libXaw libXaw-devel libXmu libXmu-devel \
  libXext libXext-devel libXft libXft-devel \
  fontconfig fontconfig-devel freetype freetype-devel \
  libXrender libXrender-devel readline-devel

# Clone and build
mkdir -p ~/libs
git clone https://git.code.sf.net/p/ngspice/ngspice ~/libs/ngspice
cd ~/libs/ngspice
./autogen.sh
mkdir -p release
cd release
../configure --with-x --enable-xspice --enable-cider --enable-openmp --with-readline=yes
make -j"$(nproc)"
sudo make install
sudo ldconfig

# Verify
which ngspice
ngspice --version
```

For waveform viewing, [`gaw`](https://www.rvq.fr/linux/gaw.php) is useful.
When producing raw binary files, ensure `utf_8` encoding is used for the
plaintext section.

## OpenROAD

FRIDA's digital implementation flow uses OpenROAD tooling. The commands below
follow OpenROAD's upstream local build method described in the
[OpenROAD Build Guide](https://openroad.readthedocs.io/en/latest/user/Build.html#build-locally).
`DependencyInstaller.sh -base` handles Ubuntu vs RHEL package installation
internally.

```bash
# Clone
mkdir -p ~/libs
git clone --recursive https://github.com/The-OpenROAD-Project/OpenROAD.git ~/libs/OpenROAD
cd ~/libs/OpenROAD

# Install dependencies + build
sudo ./etc/DependencyInstaller.sh -base
./etc/DependencyInstaller.sh -common -local
./etc/Build.sh
./etc/Build.sh -build-man

# Verify
./build/bin/openroad -version
./build/bin/openroad -help
```

## Remote SpiceServer Setup (for `--sim-server`)

Use this when FRIDA runs on one machine and simulations run on a remote host
through `spice_server`.

Detailed build/ runtime instructions and known-issue notes are in:

- [`docs/spice_server.md`](docs/spice_server.md)
