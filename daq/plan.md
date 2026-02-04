# Phase 1: Refactor DAQ directory structure

This is a summary of a conversation about reorganizing and implementing a data acquisition (DAQ) system for a FRIDA chip. The system uses:
- **Hardware**: Basil DAQ board (FPGA-based) with RGMII/Ethernet interface
- **Framework**: Basil (Python hardware abstraction layer)
- **Target**: FRIDA chip with 180-bit SPI configuration register and COMP_OUT signal

### How Components Fit Together

1. **daq.yaml** (FPGA hardware map)
   - Consumed by: `Dut()` from basil
   - Defines: FPGA modules (fifo, seq, spi, gpio, pulse_gen) and their bus addresses
   - Creates Python driver objects: `daq["spi"]`, `daq["gpio"]`, `daq["SEQ"]`, etc.
   - Must match Verilog address map in `daq_core.v`

2. **registers.yaml** (Chip register definitions)
   - Consumed by: `host.py` Frida class
   - Defines: 180-bit SPI shift register structure in FRIDA chip
   - Used by: `set_register()`/`get_register()` to pack/unpack named fields
   - No relation to FPGA or basil

3. **sequencer.py** (Waveform generation)
   - Consumed by: `host.py` via `_configure_sequencer()`
   - Pure Python - no hardware interaction
   - Returns: Dict of 4 lists (one per sequencer track) with 0/1 patterns

4. **host.py** (Frida class - chip controller)
   - Takes: Initialized `Dut` object
   - Methods:
     - `init()` - reset via gpio, load sequencer, write default SPI
     - `set_register()`/`write_spi()` - use registers.yaml + daq["spi"]
     - `run_conversions()` - configure seq, trigger pulse_gen, read fifo

### Data Flow
```
daq.yaml → Dut() → daq["seq"], daq["spi"], daq["gpio"], ...
                        ↑                    ↑
registers.yaml → Frida.set_register() → Frida.write_spi()
                                             ↑
sequencer.py → generate_conversion_sequence() → Frida._configure_sequencer()
```

## Planned Major Change: Replace Custom COMP_OUT Receiver

### Overview
Replace hand-rolled COMP_OUT shift register + FIFO (lines 256-349 in daq_core.v) with basil's `fast_spi_rx` module. Add two new sequencer tracks for capture clocking and framing.

### Signal Mapping
| fast_spi_rx port | Connection      | Notes                               |
|------------------|-----------------|-------------------------------------|
| SCLK             | seq_out[4]      | 5th sequencer track - capture clock |
| SDI              | COMP_OUT        | Comparator output from chip         |
| SEN              | seq_out[5]      | 6th sequencer track - frame enable  |
| FIFO_READ        | FIFO_READ_NEXT  | Existing bram_fifo read signal      |
| FIFO_EMPTY       | FIFO_EMPTY      | Existing bram_fifo empty flag       |
| FIFO_DATA        | FIFO_DATA_OUT   | Existing 32-bit data bus            |

### Why seq_out[4] as SCLK (not SEQ_CLK)
Round-trip propagation delay (FPGA → LVDS → chip → comparator → LVDS → FPGA) is unknown. Using a sequencer track lets the user shift the sampling edge in the sequencer pattern to compensate.

### Files to Modify

**1. daq_core.v**
- Add includes for basil modules (fast_spi_rx, cdc_syncfifo, generic_fifo)
- Add address space: `FAST_SPI_RX_BASEADDR = 32'h50000`
- Delete hand-rolled section 5 (lines 256-349)
- Instantiate `fast_spi_rx` module

**2. daq.yaml**
- Add fast_spi_rx driver at base_addr 0x50000
- Add sequencer tracks:
  - CLK_COMP_CAP (position 4)
  - SEN_COMP (position 5)

**3. daq_core_diagram.v**
- Replace comp_out_receiver stub with fast_spi_rx stub

## Planned Reorganization

### New File Structure
```
daq/
├── host/
│   ├── sequences.py      # (renamed from sequencer.py)
│   ├── host.py           # FPGA control abstraction
│   ├── test_dut.py       # pytest entry points
│   ├── map_fpga.yaml     # (renamed from daq.yaml)
│   └── map_dut.yaml      # (renamed from registers.yaml)
├── fpga/
│   ├── core.v            # (renamed from daq_core.v)
│   ├── diagram.v         # (renamed from daq_core_diagram.v)
│   └── top.v             # NEW: RGMII → TCP/IP → core + I2C
└── dut/
    └── [pcb files moved here]
```

### Missing Entry Point
Currently no script calls `Dut("daq.yaml"); daq.init()`. The `host.py` Frida class expects an already-initialized Dut object. This should be handled in `test_dut.py`.

### Reference Design
The obelix1-daq project at `/home/kcaisley/libs/obelix1-daq` follows the same basil pattern with its `DAQ.yaml` and should be consulted for the top-level FPGA module implementation.

## Key Implementation Notes

1. **daq.yaml is actively used** - Python loads it via `Dut("daq/daq.yaml")` and basil instantiates all hardware driver objects
2. **Both YAML additions are necessary**:
   - `hw_drivers` entry for fast_spi_rx (creates driver at 0x50000)
   - Two new sequencer tracks (positions 4 and 5)
3. **Sequencer pattern** (programmed in Python):
   - Cycle 0: CLK_INIT high (reset/init)
   - Cycles 1-2: CLK_SAMP high (sample)
   - Cycles 3+: CLK_COMP_CAP edges to sample COMP_OUT, SEN_COMP high for 17 capture cycles
4. **fast_spi_rx behavior**: 16-bit chunks → first 16 bits create one 32-bit FIFO word, remaining 1 bit → partial word on SEN falling edge

## Verification Steps
- Run Verilator lint on core.v
- Check basil transfer layer can read fast_spi_rx registers
- Verify sequencer pattern produces expected FIFO words in simulation


# Phase 2: Implement shared measurement infrastructure
