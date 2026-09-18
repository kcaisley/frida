# FRIDA-1 FPGA Firmware

FPGA design for the FRIDA ADC test chip DAQ, targeting the BDAQ53 base board
with Enclustra Mercury KX1 or KX2 modules (Kintex-7).

## Usage

Run commands from the project root (`~/frida/`)

```bash
# 0. install python dependencies (only needed once)
#    if design libs (hdl21, vlsir) are not on this machine,
#    comment out [tool.uv.sources] in pyproject.toml first
uv sync --extra daq

# 1. source vivado
source /eda/local/scripts/vivado_2025.2.sh

# 2. download SiTCP (only needed once)
uv run python design/fpga/manage.py --get_sitcp

# 3. compile
uv run python design/fpga/manage.py --compile BDAQ53_KX1 \
  --verilog design/fpga/daq_top.v --top daq_top \
  --xdc design/fpga/bdaq53_kx1.xdc \
  --xdc design/fpga/SiTCP/EDF_SiTCP.xdc \
  --edif design/fpga/SiTCP/SiTCP_XC7K_32K_BBT_V110.edf \
  --include-dir design/fpga --include-dir design/fpga/SiTCP \
  --include-dir libs/basil/basil/firmware/modules \
  --name frida_bdaq53_kx1 --out-dir design/fpga

# 4. program FPGA via JTAG
uv run python design/fpga/manage.py --flash design/fpga/bit/frida_bdaq53_kx1.bit      # volatile (SRAM)
uv run python design/fpga/manage.py --flash design/fpga/bit/frida_bdaq53_kx1.mcs      # persistent (SPI flash)

# if JTAG device not found, install cable drivers and replug USB:
sudo /eda/xilinx/2025.2/Vivado/data/xicom/cable_drivers/lin64/install_script/install_drivers/install_drivers
```

## Custom firmware inputs and outputs

To build another chip's firmware on BDAQ, supply the inputs and output name:

```bash
uv run python design/fpga/manage.py --compile BDAQ53_KX2 \
  --verilog /path/to/firmware/top.v --top my_top \
  --xdc /path/to/firmware/pins.xdc \
  --include-dir /path/to/firmware/include \
  --name my_chip --out-dir /path/to/output
```

Repeat `--verilog`, `--xdc`, `--edif`, and `--include-dir` for multiple inputs.
Compilation requires an explicit board, HDL and XDC files, top module, image
name, and output directory. No SiTCP, Basil, or other source/include paths are
added automatically; supply any required dependencies explicitly. SiTCP is
only downloaded by `--get_sitcp`. Flashing always requires an explicit image.
Paths resolve from the invocation directory. Outputs go to `build/`, `bit/`,
and `reports/` beneath `--out-dir`; matching files are overwritten without
deleting other builds. Program an image with
`uv run python design/fpga/manage.py --flash /path/to/output/bit/my_chip.bit`
(`.mcs` for persistent SPI flash).

The same overrides are available directly in Tcl, after the FPGA part and flash size:

```bash
vivado -mode batch -source design/fpga/run.tcl -tclargs \
  xc7k160tffg676-2 64 \
  --verilog /path/to/firmware/top.v --top my_top \
  --xdc /path/to/firmware/pins.xdc \
  --name my_chip --out-dir /path/to/output
```

Use `--help` on `manage.py`, or `tclsh design/fpga/run.tcl --help`, for all options.

## Opening the design in Vivado GUI

After compiling, the project file is at `build/frida_bdaq53_kx1.xpr`.
Open it directly to inspect the implemented design, view schematics, run
timing analysis, or use the hardware manager:

```bash
source /eda/local/scripts/vivado_2025.2.sh
cd design/fpga
vivado build/frida_bdaq53_kx1.xpr -log build/vivado_gui.log -journal build/vivado_gui.jou
```

This opens the full project with synthesis and implementation results intact.

## Running hardware checks

After compiling and flashing, use the serializer/sequencer check to inspect the
current raw 64-bit pattern packing and capture the output waveforms:

```bash
uv run pytest -q -s -m hw flow/scans/test_serdes.py
```

Run one explicitly selected ADC hardware campaign with:

```bash
uv run python -m flow.scans.runner adc_sample_rate
```

Both commands require the FPGA hardware and instruments described by the Basil
maps in `flow/scans/`.

## Files

- `daq_top.v` — top-level: PLL, SiTCP Ethernet, RGMII, LVDS I/O, core
- `daq_core.v` — DAQ core: sequencer, SPI, GPIO, pulse gen, comp capture
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
- basil — supplies Verilog firmware modules; pass its module directory with `--include-dir`
- SiTCP — downloaded by `manage.py --get_sitcp`

## Comparator input delay

COMP_OUT uses two calibrated IDELAYE2 stages in series. The first receives
IBUFDS; the second uses its fabric DATAIN port. KX1 constraints place the
second stage at IDELAY_X0Y173 beside the native input site IDELAY_X0Y172.
The FPGA does not rotate ADC controls or shift the FastRX clock.

GPIO1 is now 16 bits: [5:0] combined tap request, [6] load, [7] IDELAYCTRL
ready, [8] reserved zero, [14:9] actual sum of both delay counters, and [15]
two-stage ABI marker. Total 0..62 maps to floor(N/2), ceil(N/2); raw code 63
saturates to 62 and host software rejects it. Both stages load together on
BUS_CLK. Stop acquisition before changing taps. The host must use the updated
map_fpga.yaml; the old eight-bit GPIO1 interface is incompatible.

Nominal adjustment span is 4.84375 ns plus intrinsic and routed delay.
IDELAYCTRL does not calibrate the connecting fabric route. Hardware scope
validation and a new board capture profile are required after programming.

The 2026-09-18 optimized image has been programmed and checked on ADC00–15
with two sequences at 320/960/1600 MBd. Six corresponding profiles are stored
in `flow/scans/map_board.yaml`; the measurement manifest and limitations are
in `build/diagnostics/fastrx_capture_validation/README.md`. The 800 MHz
serializer clock still fails its BUFG minimum-period check by 0.350 ns;
successful acquisition is not full timing signoff.

The editable [CircuitikZ datapath diagram](../../docs/diagrams/adc_datapath.tex)
shows both PCBs, cable, clocks, primitives, delays and tuning ranges.
See its [build instructions and timing evidence](../../docs/diagrams/readme.md).
