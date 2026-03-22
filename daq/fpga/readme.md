# FRIDA-1 FPGA Firmware

FPGA design for the FRIDA ADC test chip DAQ, targeting the BDAQ53 base board
with Enclustra Mercury KX1 or KX2 modules (Kintex-7).

## Usage

Run commands from the project root (`~/frida/`)

```bash
# 1. source vivado
source /eda/local/scripts/vivado_2025.2.sh

# 2. download SiTCP (only needed once)
python daq/fpga/manage.py --get_sitcp

# 3. compile
python daq/fpga/manage.py --compile BDAQ53_KX1

# 4. program FPGA via JTAG
python daq/fpga/manage.py --flash daq/fpga/bit/frida_bdaq53_kx1.bit      # volatile (SRAM)
python daq/fpga/manage.py --flash daq/fpga/bit/frida_bdaq53_kx1.mcs      # persistent (SPI flash)

# if JTAG device not found, install cable drivers and replug USB:
sudo /eda/xilinx/2025.2/Vivado/data/xicom/cable_drivers/lin64/install_script/install_drivers/install_drivers
```

## Files

- `frida1.v` — top-level: PLL, SiTCP Ethernet, RGMII, LVDS I/O, core
- `frida1_core.v` — DAQ core: sequencer, SPI, GPIO, pulse gen, comp capture
- `run.tcl` — Vivado synthesis/P&R/bitgen (called by manage.py)
- `manage.py` — CLI for downloading SiTCP, compiling, and JTAG programming
- `bdaq53_kx1.xdc` — pin constraints for BDAQ53 + Mercury KX1 (xc7k160t-1)
- `bdaq53_kx2.xdc` — pin constraints for BDAQ53 + Mercury+ KX2 (xc7k160t-2)

## Build targets

- `BDAQ53_KX1` — xc7k160tfbg676-1, BDAQ53 + Mercury KX1
- `BDAQ53_KX2` — xc7k160tffg676-2, BDAQ53 + Mercury+ KX2

## Dependencies

- Vivado 2025.2 — synthesis and programming
- Python packages — `uv sync --extra daq` (pexpect, gitpython, basil-daq, pyyaml, bitarray)
- basil — ~/libs/basil, provides Verilog firmware modules
- SiTCP — downloaded by `manage.py --get_sitcp`
