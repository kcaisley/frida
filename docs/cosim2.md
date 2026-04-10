# Plan: Rewrite flow/scans/ with cocotb-native + cocotbext-ams

## Context

Rewriting the cosim infrastructure from basil-socket-based (scan in one process,
cocotb in simulator subprocess, IPC via socket) to cocotb-native (scan IS the
cocotb test, analog bridge via cocotbext-ams). This gives runtime analog control,
eliminates IPC complexity, and matches the cocotb-intended usage patterns.

## Dependencies

**cocotbext-ams** is added as a git submodule at `libs/cocotbext-ams/`
(already done: `git submodule add https://github.com/VLSIDA/cocotbext-ams.git libs/cocotbext-ams`).
We need to patch its netlist generator (`_netlist.py`) to support our subcircuit's
pin ordering, multiple supply pairs, and bracket bus naming. Having it as a submodule
lets us maintain these modifications and contribute them upstream later.

## Key decisions

1. **Keep daq_core in the testbench.** The existing `tb_integration.v` with
   `daq_core` (basil FPGA firmware) stays. cocotb drives the basil bus signals
   (`BUS_CLK`, `BUS_ADD`, `BUS_DATA`, `BUS_RD`, `BUS_WR`) directly. The basil
   `BasilBusDriver` already works with cocotb — that's what `Test.py` uses.
   The Frida class uses basil's bus driver to write SPI, load sequencer, etc.

2. **cocotbext-ams handles analog.** No spicebind, no `external` sources in
   hand-written .sp files. cocotbext-ams auto-generates the SPICE wrapper
   from the AnalogBlock definition. User provides only the `.subckt` files.

3. **Stub ports use plain `wire` + `output reg`.** For cocotbext-ams, the stub
   needs `output reg` (so bridge can `Force`) and `input wire` for analog-only
   signals. No `real`, no `wreal`. Add ifdef `COCOTBEXT_AMS` to `adc_stub.v`.

4. **Skip sediff in simulation for now.** The SE-to-diff conversion is unity
   gain — compute `vin_p = cm + diff/2`, `vin_n = cm - diff/2` in Python and
   set them directly on the ADC's analog inputs via `bridge.set_analog_input()`.
   Add sediff SPICE simulation as a second block later if needed.

5. **No hand-written wrapper subcircuit.** cocotbext-ams auto-generates a
   SPICE wrapper deck internally (`_netlist.py`). However, its generator has
   three limitations that don't match our `.subckt adc` pin order:
   - It puts all inputs before outputs, but `comp_out` is at position 5
     in `.subckt adc` (between inputs).
   - It generates one vdd/vss pair, but our subcircuit has three
     (`vdd_a/vss_a`, `vdd_d/vss_d`, `vdd_dac/vss_dac`).
   - `_bit_node_name()` uses underscores (`dac_astate_p_15`) but the
     subcircuit uses brackets (`dac_astate_p[15]`).
   **Fix: Patch cocotbext-ams** (`libs/cocotbext-ams/src/cocotbext/ams/_netlist.py`)
   to support a `port_order` parameter on `AnalogBlock` that explicitly
   specifies the `.subckt` instantiation order, multiple supply pairs,
   and bracket-style bus naming. This keeps the user's SPICE netlist
   unchanged and makes cocotbext-ams more generally useful.

6. **Move flow/host/ contents into flow/scans/.** No separate host directory.
   map_dut.yaml, sequences logic, Frida class all live in flow/scans/.

## Files to create

### `flow/scans/chip.py` (~350 lines)
Frida class with `self.peripherals` namespace:

```python
class Frida:
    def __init__(self, dut, peripherals: SimpleNamespace):
        self.dut = dut                          # cocotb DUT handle
        self.spi_bits = bitarray(180)           # silicon state
        self.peripherals = peripherals          # .awg, .psu
```

**Silicon state methods** (pure Python, from host.py):
- `set_register(name, value)`, `get_register(name)`
- `enable_adc(n)`, `disable_all_adcs()`, `select_mux(n)`, `set_dac_state(...)`

**Operations** (use basil bus via cocotb):
- `async write_spi()` — uses BasilBusDriver to write SPI register
- `async reset()` — GPIO bit 0 (`rst_b`) toggle via basil bus
- `async run_conversion(n=1)` — loads sequencer via basil, triggers pulse_gen
- `async sample_and_compare()` — simpler sequence, just seq_samp + seq_comp
- `async read_comp_out()` — reads fast_spi_rx FIFO via basil bus

**Peripheral dispatch:**
- `async set_vin(diff, cm)` → `self.peripherals.awg.set_differential(diff, cm)`
- `async set_vdd(v)` → `self.peripherals.psu.set_voltage(v)`

**Private sequencer helpers** (from sequences.py, pure math):
- `_generate_conversion_sequence(clk_mhz)`
- `_generate_samp_comp_sequence()`

### `flow/scans/peripherals.py` (~120 lines)
Abstract interfaces + hardware backends:

```python
class PowerSupply(ABC):
    async def set_voltage(self, v): ...
    async def on(self) / off(self): ...

class FunctionGenerator(ABC):
    async def set_differential(self, diff, cm): ...
    async def start_sin(self, amplitude, offset, freq_hz): ...

class BasilPSU(PowerSupply):     # SCPI over basil Serial/Visa
class BasilAWG(FunctionGenerator)  # SCPI to Agilent 33250A
```

### `flow/scans/sim.py` (~200 lines)
Simulation backends + cocotbext-ams bridge setup:

```python
class SimAWG(FunctionGenerator):
    # set_differential → bridge.set_analog_input("i_chip.adc_inst", "vin_p/vin_n")
    # start_sin → cocotb.start_soon(coroutine updating bridge periodically)

class SimPSU(PowerSupply):
    # VDD fixed in SPICE; log warning if changed

def create_adc_block(vdd=1.2) -> AnalogBlock:
    # Returns AnalogBlock for adc_cosim subcircuit
    # digital_pins: seq_*, en_*, dac_*_N, comp_out
    # analog_inputs: vin_p, vin_n
    # extra_lines: PDK models, stdcell SPICE, subcircuit includes

def verilog_sources() -> list[Path]:
    # tb_integration.v, frida_core_1chan.v, spi_register.v,
    # adc_stub.v, daq_core.v, RAMB16_S1_S9_sim.v
```

### `flow/scans/scan_adc.py` (~120 lines)

```python
@cocotb.test()
async def scan_adc_simple(dut):
    bridge = MixedSignalBridge(dut, [create_adc_block()], max_sync_interval_ns=1.0)
    await bridge.start(duration_ns=..., analog_vcd="scan_adc.vcd")

    chip = Frida(dut, SimpleNamespace(awg=SimAWG(bridge), psu=SimPSU()))
    await chip.reset()
    chip.enable_adc(0)  # all init bits high
    chip.set_dac_state(astate_p=0xFFFF, astate_n=0xFFFF)
    await chip.write_spi()

    for diff in np.arange(-1.2, 1.2, 0.05):  # 50mV steps
        await chip.set_vin(diff=diff, cm=0.6)
        bits = await chip.run_conversion()

    await bridge.stop()
```

Runner at bottom: `get_runner("icarus")`, `runner.build()`, `runner.test()`.

### `flow/scans/scan_comp.py` (~100 lines)

```python
@cocotb.test()
async def scan_comp_threshold(dut):
    # Same setup but:
    # - en_init=False, en_update=False (only samp + comp)
    # - Sweep -5mV to +5mV in 0.5mV steps
    # - chip.sample_and_compare() instead of chip.run_conversion()
```

## Files to modify

### `design/hdl/adc_stub.v`
Add `COCOTBEXT_AMS` ifdef branch: `output reg comp_out`, `input wire` for
analog ports. No `real`, no `wreal`.

### `design/hdl/tb_integration.v`
May need minor adjustments for the cocotbext-ams flow (e.g., removing
`$dumpvars` that conflict, ensuring analog ports are plain `wire`).

## Files to move

- `flow/host/map_dut.yaml` → `flow/scans/map_dut.yaml`
- `flow/host/map_fpga.yaml` → `flow/scans/map_fpga.yaml`
- Sequencer logic from `flow/host/sequences.py` → absorbed into `flow/scans/chip.py`

## Files to delete

- `flow/scans/drivers/` (DriveAnalog, DriveSeqClock — replaced by sim.py)
- `flow/scans/spi.py` (absorbed into chip.py)
- `flow/scans/map_sim.yaml` (not needed with cocotbext-ams)
- Current `flow/scans/scan_adc.py` contents (complete rewrite)

## How basil bus works with cocotb

The existing basil `BasilBusDriver` is a cocotb `BusDriver` that drives
`BUS_CLK`, `BUS_RST`, `BUS_ADD`, `BUS_DATA`, `BUS_RD`, `BUS_WR` signals.
basil's `Test.py` uses it via socket IPC. In our new approach, we can either:

**Option A:** Use `BasilBusDriver` directly from the `@cocotb.test()` function
(it's a cocotb class, no socket needed). Load the basil YAML config with
`Dut(conf)` in-process. This means the basil register drivers (seq_gen, spi,
gpio, etc.) work unchanged — they just talk to the bus driver directly instead
of through a socket.

**Option B:** Write a thin `CocotbDaq` that duck-types basil's `Dut["spi"]`
interface but drives VPI directly. More work but cleaner separation.

**Recommendation: Option A.** basil's `BasilBusDriver` already runs inside
cocotb. The socket indirection in `Test.py` was only needed because the scan
ran in a separate process. Since our scan IS the cocotb test, we can call
`BasilBusDriver.write()` directly. We just need to initialize it and start
the bus clock.

## Two analog block question

The sediff (THS4541 PCB amp) and adc are separate SPICE subcircuits.
cocotbext-ams calls `sim.load_circuit()` once per block. For ngspice,
this uses `ngSpice_Circ()` which may or may not support multiple circuits.

**Decision: Skip sediff for now.** Set vin_p/vin_n directly on the ADC
analog inputs. The sediff is unity gain — Python computes `cm ± diff/2`.
Add sediff as a second block later after validating single-block flow.

## Verification

1. Compile `tb_integration.v` with `check_hdl.sh` (existing)
2. Run `scan_adc_simple` with Icarus — verify comp_out bits change with voltage
3. Run `scan_comp_threshold` — verify transition near 0mV
4. Check `scan_adc.vcd` for analog waveforms
5. Parse ngspice output for internal nodes (vdac_p, vdac_n)

## Risks

1. **SPICE pin order** — wrapper subcircuit `adc_cosim.sp` needed (confirmed)
2. **ngspice speed** — gate-level adc_digital is slow. Accept for now.
3. **BasilBusDriver in-process** — may need initialization without socket.
   Test.py does `bus = get_bus()(dut); await bus.init()`. We replicate this.
4. **Sync interval** — must be ≤1ns for 2.5ns sequencer steps.
