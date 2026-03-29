# Plan: Mixed-Signal Co-Simulation Framework for FRIDA

## Context

FRIDA needs a unified framework where the **same scan code** drives both physical
hardware measurement and transistor-level mixed-signal simulation. Today, simulation
uses standalone SPICE (HDL21 generates self-contained netlists with embedded sources,
run via Spectre/ngspice). Hardware measurement uses basil + the `Frida` class. These
two paths share no code.

The new architecture uses cocotb + spicebind to bridge Icarus Verilog (digital) with
ngspice (analog), driven by basil scan code through the SiSim transfer layer — the
same pattern used by tj-monopix2-daq and bdaq53 for FPGA firmware verification.

**Note:** Verilator appears to support `wreal` and `vpiRealVal` in its VPI layer,
but spicebind is only tested with Icarus Verilog. We start with Icarus; Verilator
can be validated later if simulation speed becomes a concern.

## Architecture

```
flow simulate -c comp --scan scurve    flow measure -c comp --scan scurve
         │                                      │
    Same scan code (Python)                Same scan code (Python)
         │                                      │
    Frida class (flow/scans/host.py)        Frida class
         │                                      │
    basil Dut(map_sim.yaml)                basil Dut(map_fpga.yaml)
         │                                      │
    TL: SiSim ──► cocotb Test.py           TL: SiTcp ──► real FPGA
         │              │                       │
    SerialSim ─► SIMULATION_MODULE         TL: Serial ──► real AWG
         │         (AwgSim, PsuSim)             │
         │              │                  TL: Visa ──► real scope
    fpga_core.v   drives real ports
    frida_core.v       │
    analog stubs ──► spicebind ──► ngspice (transistor models)
```

## Simulation Hierarchy

The spicebind boundary sits at the ADC level — everything inside the ADC
(clkgate, salogic, capdriver, sampswitch, caparray, comp) runs in ngspice.
The PCB amplifier (THS4541) also runs in ngspice. Only the FPGA firmware
and chip-level digital logic (SPI register, comp MUX) run in Icarus.

### Icarus Verilog side (sim/tb.v)

```
tb
├── real VIN_P, VIN_N, VDD          ← driven by cocotb AnalogDriver (SerialSim)
├── BUS_CLK/RST/ADD/DATA/RD/WR     ← driven by cocotb BasilSbusDriver (SiSim)
│
├── i_fifo : bram_fifo              ← basil firmware module
│
├── i_daq_core : daq_core                       ← design/daq/daq_core.v
│   ├── inst_seq_gen : seq_gen                  ← basil firmware module
│   ├── inst_spi : spi                          ← basil firmware module
│   ├── inst_gpio : gpio                        ← basil firmware module
│   ├── inst_pulse_gen : pulse_gen              ← basil firmware module
│   └── inst_fast_spi_rx : fast_spi_rx          ← basil firmware module
│       .SDI(comp_out) ◄────────────────────────────────┐
│                                                       │
└── i_chip : frida_core                         ← design/hdl/frida_core.v
    ├── spi_reg : spi_register                  ← design/hdl/spi_register.v
    ├── comp_mux : compmux                      ← design/hdl/compmux.v
    │   .comp_out ──────────────────────────────────────┘
    │
    └── adc_array[0].adc_inst : adc             ← stub (adc.v with real ports)
        ├── input wire  seq_init/samp/comp/update
        ├── input wire  en_init/samp_p/samp_n/comp/update
        ├── input wire  [15:0] dac_astate_p/bstate_p/astate_n/bstate_n
        ├── input wire  dac_mode, dac_diffcaps
        ├── input real  vin_p, vin_n            ← from ngspice THS4541
        └── output wire comp_out                ← to ngspice, back via threshold
                 │
═════════════════╪══════ spicebind boundary ═══════════════════════════
                 │
```

### ngspice side (tb_adc.sp)

```
.lib tsmc65_models tt                   ← PDK transistor models
.include adc.sp                         ← HDL21: full ADC (salogic + capdriver
.include design/pcb/ths4541.sp             │  + clkgate + samp + cdac + comp)

PCB input stage:
  Vawg_p awg_p 0 0 external            ← cocotb VIN_P (from AnalogDriver)
  Vawg_n awg_n 0 0 external            ← cocotb VIN_N
  Xamp ... THS4541                      ← differential amp + feedback network
    awg_p/n → vin_p/vin_n

Supplies:
  Vvdd vdd 0 0 external                ← cocotb VDD (from AnalogDriver, set by scan code)
  Vvss vss 0 0

Clock/config (from Icarus via spicebind):
  Vseq_init seq_init 0 0 external
  Vseq_samp seq_samp 0 0 external
  Vseq_comp seq_comp 0 0 external
  Vseq_update seq_update 0 0 external
  Ven_init en_init 0 0 external
  Ven_samp_p en_samp_p 0 0 external
  ... (all digital control signals)

ADC instance (entire analog + digital internals):
  Xadc vin_p vin_n seq_init ... comp_out vdd vss ADC
    ├── Xclkgate_init, _samp_p, _samp_n, _comp, _update
    ├── Xsa_logic (SAR logic — transistor level)
    ├── Xcapdrv_p, Xcapdrv_n (cap drivers — transistor level)
    ├── Xsamp_p, Xsamp_n (sampling switches)
    ├── Xcdac_p, Xcdac_n (cap arrays)
    └── Xcomp (comparator)
         comp_out → spicebind threshold → back to Icarus

  .tran 100p 100u

Post-simulation: dump.raw contains all internal node voltages
  v(xadc.xcomp.vlatch_p), v(xadc.xcdac_p.vbot[3]), ...
```

## What Already Exists

| Asset | Location | Notes |
|-------|----------|-------|
| FPGA firmware | `design/daq/daq_core.v` | basil modules: seq_gen, spi, gpio, pulse_gen, fast_spi_rx |
| Chip digital RTL | `design/hdl/frida_core.v` | SPI register, 16 ADCs, comp MUX |
| Analog blackboxes | `design/hdl/comp.v`, `sampswitch.v`, `caparray.v` | `(* blackbox *)` stubs |
| PCB amplifier model | `design/pcb/ths4541.sp` | TI fully differential amp (SPICE behavioral) |
| HDL21 generators | `flow/comp/subckt.py`, `flow/samp/`, `flow/cdac/` | Produce transistor-level SPICE netlists |
| Frida host class | `flow/scans/host.py` | init, SPI config, run_conversions, data parsing (moved from daq/host/) |
| Basil SiSim | `libs/basil/basil/TL/SiSim.py` | TCP socket TL replacing SiTcp |
| Basil sim infra | `libs/basil/basil/utils/sim/Test.py` | cocotb socket server + SIMULATION_MODULES |
| SpiceBind | `libs/spicebind` | VPI bridge: Icarus ↔ ngspice, supports `real` ports |
| Flow CLI | `flow/cli.py` | `flow netlist`, `flow simulate`, `flow measure` commands |

## CLI Design

Two new `flow` subcommands replace the old `flow simulate`:

```bash
# Generate netlists (existing, add --scope cosim)
flow netlist -c comp -t tsmc65 -f ngspice --scope cosim

# Run mixed-signal simulation via cocotb+spicebind
flow simulate -c adc -t tsmc65 --scan transfer

# Run physical measurement via basil+FPGA
flow measure -c adc --scan transfer
```

Both `flow simulate` and `flow measure` run the same scan function. The difference
is which basil YAML config they load (SiSim vs SiTcp) and whether they launch
the simulator.

---

## Step 1: Add spicebind submodule + install dependencies

```bash
cd /local/frida
git submodule add https://github.com/themperek/spicebind libs/spicebind
```

**Modify** `pyproject.toml`:
```toml
[dependency-groups]
simulate = [
    "cocotb",
    "cocotb-bus",
    "spicebind",
]

[tool.uv.sources]
spicebind = { path = "libs/spicebind", editable = true }
```

**Verify:** `uv sync --group sim && python -c "import cocotb; import spicebind"`

---

## Step 2: Standalone comparator co-simulation

Prove spicebind works with FRIDA's transistor-level comp, driven by cocotb
directly (no basil, no FPGA). This validates the ngspice + TSMC model stack.

### Files to create

**`sim/comp/comp_stub.v`** — Verilog shell replacing the `(* blackbox *)` in
`design/hdl/comp.v`. SpiceBind binds this to ngspice:

```verilog
`timescale 1ns/1ps

module comp(
    input  real vin_p,
    input  real vin_n,
    output real dout_p,
    output real dout_n,
    input  wire clk
);
    // SpiceBind maps these ports to ngspice external sources / nodes
endmodule
```

**`scratch/tb_comp.sp`** — generated by `flow netlist -c comp -f ngspice --scope cosim`.
HDL21 produces this automatically from the `Comp` module's port list. Example output:

```spice
* Comparator co-simulation wrapper (generated by HDL21)
.lib /eda/kits/TSMC/65LP/.../hspice/toplevel.l tt
.include comp.sp

* Inputs driven by spicebind (from Verilog real ports)
Vvin_p vin_p 0 0 external
Vvin_n vin_n 0 0 external
Vclk   clk   0 0 external

* Supplies driven by spicebind (from AnalogDriver)
Vvdd vdd 0 0 external
Vvss vss 0 0

* DUT instance
Xdut vin_p vin_n dout_p dout_n clk vdd vss Comp

.tran 100p 100u
.end
```

**`sim/comp/test_comp_standalone.py`** — cocotb test (direct, no basil):

```python
import math
import cocotb
from cocotb.triggers import Timer
import numpy as np

@cocotb.test()
async def test_comp_scurve(dut):
    """Drive differential sweep, read comparator decisions."""
    results = []
    vcm = 0.6

    for vdiff_mv in range(-10, 11, 2):
        vdiff = vdiff_mv * 1e-3
        dut.vin_p.value = vcm + vdiff / 2
        dut.vin_n.value = vcm - vdiff / 2

        # Run 20 clock cycles at this operating point
        for _ in range(20):
            dut.clk.value = 0
            await Timer(5, units="ns")
            dut.clk.value = 1
            await Timer(5, units="ns")
            results.append((vdiff, dut.dout_p.value))

    dut._log.info(f"Collected {len(results)} samples")
```

**`sim/comp/Makefile`**:

```makefile
SPICEBIND_DIR := $(shell spicebind-vpi-path)
COMP_DUT      := ../../scratch/comp.sp  # from: flow netlist -c comp --scope dut -f ngspice

all: run

compile:
	iverilog -g2005-sv -o comp_tb.vvp comp_stub.v

run: compile
	SPICE_NETLIST=tb_comp.sp \
	HDL_INSTANCE=comp \
	MODULE=test_comp_standalone \
	vvp -M $(SPICEBIND_DIR) -m spicebind_vpi comp_tb.vvp

clean:
	rm -f *.vvp *.vcd *.raw
```

**Prerequisite:** `flow netlist -c comp -t tsmc65 -f ngspice --scope dut -o scratch`

**Verify:** `cd sim/comp && make` — ngspice runs transistor comp, cocotb reads
outputs, confirms S-curve shape.

---

## Step 3: Basil contributions (SerialSim + AnalogDriver + modern runner)

Three additions to basil's simulation infrastructure:

1. **`SerialSim`** — new TL that mocks Serial/Visa instruments in simulation
2. **`AnalogDriver`** — new SIMULATION_MODULE that drives `real` Verilog ports
3. **`runner.py`** — new launcher using cocotb's Python-native `Runner` API

### Modern cocotb runner

Basil's existing `cocotb_compile_and_run()` generates a Makefile and calls
`make`, passing configuration via exported environment variables. cocotb added
a Python-native `Runner` API in January 2022 (PR #2634) that eliminates
Makefiles entirely. We add a thin wrapper in basil that uses it:

**`libs/basil/basil/utils/sim/runner.py`** (~25 lines):

```python
"""Modern cocotb runner for basil simulation.

Uses cocotb's Python-native Runner API (added 2022, PR #2634) instead
of the legacy Makefile-based cocotb_compile_and_run(). Configuration
is passed via extra_env dict on the subprocess — no Makefile generation,
no os.environ pollution.
"""

from pathlib import Path
from cocotb.runner import get_runner


def cocotb_run(
    sim="icarus",
    sources=(),
    top_level="tb",
    test_module="basil.utils.sim.Test",
    includes=(),
    sim_args=(),
    extra_env=None,
):
    runner = get_runner(sim)
    runner.build(
        sources=[str(s) for s in sources],
        hdl_toplevel=top_level,
        includes=[str(i) for i in includes],
        always=True,
    )
    runner.test(
        hdl_toplevel=top_level,
        test_module=test_module,
        test_args=list(sim_args),
        extra_env=extra_env or {},
    )
```

This replaces the need for `cocotb_compile_and_run()` and `cocotb_makefile()`
in `utils.py`. Existing basil code can continue using the old functions.

### The instrument mocking problem

In hardware, the AWG is on its own `Serial` TL — completely separate from the
FPGA's `SiTcp` bus. In simulation, `SiSim` only mocks the FPGA bus. There is
no simulation equivalent of `Serial` or `Visa`.

### The solution

A new basil TL `SerialSim` that connects to a `SIMULATION_MODULE` via a
dedicated TCP socket. The module drives `real` ports in the Verilog testbench.

Three files are added to basil:

**`libs/basil/basil/utils/sim/Protocol.py`** — add `AnalogSetRequest` alongside
existing `WriteRequest`/`ReadRequest`/`ReadResponse` (this is where pickle
message types live, so both `SerialSim` and `AnalogDriver` can import it):

```python
class AnalogSetRequest(ProtocolBase):
    """Request to set an analog signal value in simulation."""
    def __init__(self, signal, value):
        self.signal = signal
        self.value = value

    def __str__(self):
        return "AnalogSetRequest: %s = %f" % (self.signal, self.value)
```

**`libs/basil/basil/TL/SerialSim.py`** (~50 lines):

```python
"""Simulation replacement for Serial/Visa TLs.

Connects to a SIMULATION_MODULE that drives real-valued Verilog ports.
Intercepts SCPI byte strings, extracts values, and sends structured
AnalogSetRequest messages over a TCP socket.

Note: The SCPI parsing is minimal — it matches command substrings like
'VOLT:HIGH', 'VOLT:LOW', 'OUTP'. This covers the agilent33250a and
common power supply drivers. Other instruments may need additional
patterns added here.
"""

import socket
import time
from basil.TL.SiTransferLayer import SiTransferLayer
from basil.utils.sim.Protocol import PickleInterface, AnalogSetRequest

class SerialSim(SiTransferLayer):
    def __init__(self, conf):
        super().__init__(conf)
        self._sock = None
        self._signal_map = conf.get('init', {}).get('signal_map', {})

    def init(self):
        super().init()
        host = self._init.get('host', 'localhost')
        port = self._init.get('port', 12346)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        for _ in range(60):
            if self._sock.connect_ex((host, port)) == 0:
                break
            time.sleep(0.5)
        else:
            raise IOError("Cannot connect to SerialSim server")
        self._iface = PickleInterface(self._sock)

    def write(self, data):
        """Parse SCPI commands and forward as AnalogSetRequest."""
        text = bytes(data).decode().strip()
        if 'VOLT:HIGH' in text.upper():
            value = float(text.split()[-1])
            signal = self._signal_map.get('voltage_high', 'VIN_P')
            self._iface.send(AnalogSetRequest(signal, value))
        elif 'VOLT:LOW' in text.upper():
            value = float(text.split()[-1])
            signal = self._signal_map.get('voltage_low', 'VIN_N')
            self._iface.send(AnalogSetRequest(signal, value))
        elif 'OUTP' in text.upper():
            enabled = 'ON' in text.upper()
            signal = self._signal_map.get('enable', 'VIN_EN')
            self._iface.send(AnalogSetRequest(signal, 1.0 if enabled else 0.0))

    def close(self):
        if self._sock:
            self._sock.close()
        super().close()
```

**`libs/basil/basil/utils/sim/AnalogDriver.py`** — SIMULATION_MODULE (~40 lines).
Not a `BusDriver` subclass (it doesn't bind to any bus signals). Just a plain
class with a `run()` coroutine, matching the interface `Test.py` expects:

```python
"""cocotb simulation module that receives AnalogSetRequest messages
and drives real-valued Verilog ports on the DUT.

Registered as a SIMULATION_MODULE alongside Test.py.
Listens on a separate TCP port for SerialSim connections.
"""

import os
import socket
from basil.utils.sim.Protocol import PickleInterface, AnalogSetRequest
from cocotb.triggers import Timer

class AnalogDriver:
    def __init__(self, entity, port=None):
        self._entity = entity
        self._port = port or int(os.getenv("ANALOG_SIM_PORT", "12346"))

    async def run(self):
        """Listen for analog set requests and drive real ports."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("localhost", self._port))
        s.listen(1)
        s.setblocking(False)

        clientsocket = None
        iface = None

        while True:
            if clientsocket is None:
                try:
                    clientsocket, _ = s.accept()
                    iface = PickleInterface(clientsocket)
                except BlockingIOError:
                    pass

            if iface is not None:
                try:
                    req = iface.try_recv()
                    if req is not None and isinstance(req, AnalogSetRequest):
                        getattr(self._entity, req.signal).value = req.value
                except EOFError:
                    clientsocket.close()
                    clientsocket = None
                    iface = None

            await Timer(100, units="ps")
```

### YAML config for simulation

**`flow/scans/map_sim.yaml`** (relevant TL section):

```yaml
transfer_layer:
  - name: intf
    type: SiSim
    init:
      host: localhost
      port: 12345

  - name: awg_sim
    type: SerialSim
    init:
      host: localhost
      port: 12346
      signal_map:
        voltage_high: VIN_P
        voltage_low: VIN_N
        enable: VIN_EN
```

**Verify:** Unit test that starts AnalogDriver in cocotb, connects SerialSim,
sends `set_voltage_high(0.6)`, confirms `dut.VIN_P.value == 0.6`.

---

## Step 4: Co-sim netlist generation (flow netlist --scope cosim)

Each block's `testbench.py` already generates the DUT and testbench wrapper
using HDL21. For cosim mode, the same generator is used but with `Vexternal`
sources replacing `Vpwl`/`Vpulse`/`Vdc`. This keeps cosim logic next to the
existing sim logic — no separate wrapper generator needed.

### Netlist scope definitions

| Scope | Produces | Purpose |
|-------|----------|---------|
| `dut` | `comp.sp` | Subcircuit definitions only |
| `sim` | `comp.sp` + `tb_comp.sp` | Self-contained SPICE sim (Vpwl/Vpulse sources, .tran) |
| `cosim` | `comp.sp` + `tb_comp.sp` + `comp.v` | Spicebind co-sim (Vexternal sources + Verilog stub) |

### New HDL21 primitive: Vexternal

Add to HDL21 primitives. Emits `0 external` in ngspice netlisting:

```python
# In hdl21/primitives.py
Vexternal = _add(
    prim=Primitive(
        name="ExternalVoltageSource",
        desc="External voltage source for co-simulation (spicebind)",
        port_list=copy.deepcopy(PassivePorts),
        paramtype=NoParams,
        primtype=PrimitiveType.IDEAL,
    ),
    aliases=["Vext", "Vexternal"],
)
```

And in the ngspice netlister (`vlsirtools/netlist/spice.py`):

```python
elif name == "vexternal":
    self.write(f"+ 0 external \n")
```

### Testbench conditional pattern

Each block's `testbench.py` gains a `scope` parameter. Three types of sources
get the conditional — supplies, clocks, and input stimulus. Passive components
(load caps, source impedances) and the DUT instantiation stay identical.

**Example: comp testbench** (`flow/comp/testbench.py`):

```python
@h.generator
def CompTb(params: CompTbParams, scope: str = "sim") -> h.Module:
    supply = SupplyVals.corner(params.pvt.v)

    @h.module
    class CompTb:
        vss = h.Port(desc="Ground")
        vdd = h.Signal()
        vin_p_src = h.Signal()
        vin_n_src = h.Signal()
        in_p = h.Signal()
        in_n = h.Signal()
        clk = h.Signal()
        clk_b = h.Signal()
        out_p = h.Signal()
        out_n = h.Signal()

    # Supply — external in cosim (driven by power supply mock)
    if scope == "cosim":
        CompTb.vvdd = Vexternal()(p=CompTb.vdd, n=CompTb.vss)
    else:
        CompTb.vvdd = Vdc(dc=supply.VDD)(p=CompTb.vdd, n=CompTb.vss)

    # Source impedance — same in both modes (models DAC/SHA output)
    CompTb.rsrc_p = R(r=1000)(p=CompTb.vin_p_src, n=CompTb.in_p)
    CompTb.rsrc_n = R(r=1000)(p=CompTb.vin_n_src, n=CompTb.in_n)
    CompTb.csrc_p = C(c=100 * f)(p=CompTb.in_p, n=CompTb.vss)
    CompTb.csrc_n = C(c=100 * f)(p=CompTb.in_n, n=CompTb.vss)

    # Clocks — external in cosim (driven by FPGA sequencer via spicebind)
    if scope == "cosim":
        CompTb.vclk = Vexternal()(p=CompTb.clk, n=CompTb.vss)
        CompTb.vclkb = Vexternal()(p=CompTb.clk_b, n=CompTb.vss)
    else:
        CompTb.vclk = Vpulse(
            v1=0, v2=supply.VDD, period=10*n, width=4*n,
            rise=100*p, fall=100*p, delay=500*p,
        )(p=CompTb.clk, n=CompTb.vss)
        CompTb.vclkb = Vpulse(
            v1=supply.VDD, v2=0, period=10*n, width=4*n,
            rise=100*p, fall=100*p, delay=500*p,
        )(p=CompTb.clk_b, n=CompTb.vss)

    # Output loading — same in both modes
    CompTb.cload_p = C(c=10 * f)(p=CompTb.out_p, n=CompTb.vss)
    CompTb.cload_n = C(c=10 * f)(p=CompTb.out_n, n=CompTb.vss)

    # DUT — same in both modes
    CompTb.dut = Comp(params.comp)(
        inp=CompTb.in_p, inn=CompTb.in_n,
        outp=CompTb.out_p, outn=CompTb.out_n,
        clk=CompTb.clk, clkb=CompTb.clk_b,
        vdd=CompTb.vdd, vss=CompTb.vss,
    )

    # Input stimulus — external in cosim (driven by AWG mock via spicebind)
    if scope == "cosim":
        CompTb.vvin_p = Vexternal()(p=CompTb.vin_p_src, n=CompTb.vss)
        CompTb.vvin_n = Vexternal()(p=CompTb.vin_n_src, n=CompTb.vss)
    else:
        # ... existing PWL staircase generation ...
        CompTb.vvin_p = Vpwl(wave=pwl_points_to_wave(points_p))(...)
        CompTb.vvin_n = Vpwl(wave=pwl_points_to_wave(points_n))(...)

    return CompTb
```

**Example: cdac testbench** (`flow/cdac/testbench.py`):

```python
@h.generator
def CdacTb(params: CdacTbParams, scope: str = "sim") -> h.Module:
    supply = SupplyVals.corner(params.pvt.v)
    n_bits = get_cdac_n_bits(params.cdac)

    @h.module
    class CdacTb:
        vss = h.Port(desc="Ground")
        vdd = h.Signal()
        top = h.Signal()
        dac_bits = h.Signal(width=n_bits)

    # Supply
    if scope == "cosim":
        CdacTb.vvdd = Vexternal()(p=CdacTb.vdd, n=CdacTb.vss)
    else:
        CdacTb.vvdd = Vdc(dc=supply.VDD)(p=CdacTb.vdd, n=CdacTb.vss)

    CdacTb.cload = C(c=100 * f)(p=CdacTb.top, n=CdacTb.vss)

    CdacTb.dut = Cdac(params.cdac)(
        top=CdacTb.top, dac=CdacTb.dac_bits,
        vdd=CdacTb.vdd, vss=CdacTb.vss,
    )

    # DAC bit inputs
    if scope == "cosim":
        for bit in range(n_bits):
            setattr(CdacTb, f"vdac_{bit}",
                    Vexternal()(p=CdacTb.dac_bits[bit], n=CdacTb.vss))
    else:
        # ... existing PWL code generation ...
        for bit in range(n_bits):
            points, _ = _build_pwl_points(bit_values[bit], t_step, t_rise)
            wave = pwl_points_to_wave(points)
            setattr(CdacTb, f"vdac_{bit}",
                    Vpwl(wave=wave)(p=CdacTb.dac_bits[bit], n=CdacTb.vss))

    return CdacTb
```

### Verilog stub generator

A small utility in `flow/circuit/netlist.py` generates the Verilog stub
mechanically from the HDL21 module port list. This is the same for all blocks:

```python
def generate_verilog_stub(module_name: str, ports: dict[str, str], output_path: Path):
    """Generate Verilog stub for spicebind binding.

    Args:
        module_name: Verilog module name (e.g. "comp")
        ports: {"vin_p": "real", "clk": "wire", "dout_p": "real", ...}
               Direction is inferred from the HDL21 port direction.
        output_path: Where to write the .v file
    """
    lines = ["`timescale 1ns/1ps", "", f"module {module_name}("]
    port_lines = []
    for name, info in ports.items():
        direction = "input" if info["dir"] == "input" else "output"
        vtype = "real" if info["analog"] else "wire"
        port_lines.append(f"    {direction} {vtype} {name}")
    lines.append(",\n".join(port_lines))
    lines.append(");")
    lines.append("endmodule")
    output_path.write_text("\n".join(lines))
```

### CLI changes

**Modify:** `flow/cli.py` — replace scope choices:

```python
p.add_argument(
    "--scope",
    default="sim",
    choices=["dut", "sim", "cosim"],
    help="dut: subcircuit only; sim: self-contained SPICE testbench; "
         "cosim: spicebind co-sim (external sources + Verilog stub)",
)
```

### HDL21/VLSIR changes

| File | Change |
|------|--------|
| `libs/Hdl21/hdl21/primitives.py` | Add `Vexternal` primitive |
| `libs/Vlsir/VlsirTools/vlsirtools/primitives.py` | Add `vexternal` ExternalModule |
| `libs/Vlsir/VlsirTools/vlsirtools/netlist/spice.py` | Handle `vexternal` → `0 external` |

**Verify:** `flow netlist -c comp -t tsmc65 -f ngspice --scope cosim -o scratch`
produces `scratch/comp.sp` + `scratch/tb_comp.sp` + `scratch/comp.v`.

---

## Step 5: Scan definitions

Define scan classes that work identically for simulation and hardware.
Each scan knows what stimulus to apply and what data to collect.

**Create:** `flow/scans/__init__.py`, `flow/scans/base.py`:

```python
class ScanBase:
    """Base class for FRIDA scans.

    A scan defines:
    - How to configure the chip (SPI registers, ADC selection)
    - What stimulus to apply (voltage sweep via AWG/sim)
    - How many conversions to run at each point
    - How to collect and return results
    """
    scan_id = None

    def configure(self, frida, daq, **kwargs):
        """Set up chip for this scan. Override in subclass."""
        raise NotImplementedError

    def run(self, frida, daq, **kwargs):
        """Execute the scan. Override in subclass."""
        raise NotImplementedError
```

**Create:** `flow/scans/scan_comp_scurve.py`:

```python
import numpy as np
from .base import ScanBase

class CompScurveScan(ScanBase):
    """Comparator S-curve: sweep Vdiff at multiple Vcm, measure decisions.

    Works identically on hardware (AWG + FPGA) and simulation (SerialSim + cocotb).
    """
    scan_id = "comp_scurve"

    default_config = {
        "cm_voltages": [0.3, 0.4, 0.5, 0.6, 0.7],
        "diff_range_mv": (-10, 10, 2),   # start, stop, step in mV
        "n_conversions": 20,              # conversions per operating point
        "adc_num": 0,
    }

    def configure(self, frida, daq, **kwargs):
        cfg = {**self.default_config, **kwargs}
        frida.enable_adc(cfg["adc_num"])
        frida.select_adc(cfg["adc_num"])
        return cfg

    def run(self, frida, daq, **kwargs):
        cfg = self.configure(frida, daq, **kwargs)

        diff_voltages = np.arange(*cfg["diff_range_mv"]) * 1e-3
        results = []

        for vcm in cfg["cm_voltages"]:
            for vdiff in diff_voltages:
                vin_p = vcm + vdiff / 2
                vin_n = vcm - vdiff / 2

                # This calls agilent33250a on hardware, SerialSim in simulation
                daq["awg"].set_voltage_high(vin_p)
                daq["awg"].set_voltage_low(vin_n)

                bits = frida.run_conversions(
                    n_conversions=cfg["n_conversions"]
                )
                results.append({
                    "vcm": vcm, "vdiff": vdiff,
                    "vin_p": vin_p, "vin_n": vin_n,
                    "bits": bits,
                })

        return results
```

**Create:** `flow/scans/scan_adc_transfer.py`:

```python
import numpy as np
from .base import ScanBase

class AdcTransferScan(ScanBase):
    """ADC transfer function: ramp differential input, record codes."""
    scan_id = "adc_transfer"

    default_config = {
        "vcm": 0.6,
        "vdiff_start": -0.3,
        "vdiff_stop": 0.3,
        "n_points": 1000,
        "n_conversions": 10,
        "adc_num": 0,
    }

    def configure(self, frida, daq, **kwargs):
        cfg = {**self.default_config, **kwargs}
        frida.enable_adc(cfg["adc_num"])
        frida.select_adc(cfg["adc_num"])
        frida.set_dac_state(
            astate_p=0xFFFF, bstate_p=0x0000,
            astate_n=0xFFFF, bstate_n=0x0000,
        )
        return cfg

    def run(self, frida, daq, **kwargs):
        cfg = self.configure(frida, daq, **kwargs)

        vdiffs = np.linspace(cfg["vdiff_start"], cfg["vdiff_stop"], cfg["n_points"])
        all_codes = []

        for vdiff in vdiffs:
            daq["awg"].set_voltage_high(cfg["vcm"] + vdiff / 2)
            daq["awg"].set_voltage_low(cfg["vcm"] - vdiff / 2)

            bits = frida.run_conversions(n_conversions=cfg["n_conversions"])
            all_codes.append(bits)

        return {"vdiffs": vdiffs, "codes": np.array(all_codes)}
```

---

## Step 6: Simulation testbench (design/daq/daq_tb.v)

Verilog testbench for Icarus that instantiates `daq_core` (the FPGA firmware)
plus `frida_core` (the chip digital RTL) plus the cocotb bus bridge. Lives
alongside `daq_core.v` and `daq_fpga.v` in `design/daq/` — same core module,
different wrappers for synthesis vs simulation.

**Create:** `design/daq/daq_tb.v`:

```verilog
`timescale 1ns/1ps

`include "daq_core.v"
`include "frida_core.v"         // chip digital (uses only ADC[0] in sim)
`include "bram_fifo/bram_fifo.v"
`include "bram_fifo/bram_fifo_core.v"

module tb(
    output wire        BUS_CLK,
    input wire         BUS_RST,
    input wire  [31:0] BUS_ADD,
    input wire  [31:0] BUS_DATA_IN,
    output wire [31:0] BUS_DATA_OUT,
    input wire         BUS_RD,
    input wire         BUS_WR,
    output wire        BUS_BYTE_ACCESS
);

    // Bus bridge (same pattern as basil tests)
    wire [7:0] BUS_DATA;
    assign BUS_DATA = BUS_WR ? BUS_DATA_IN[7:0] : 8'bz;
    assign BUS_DATA_OUT = {24'b0, BUS_DATA};
    assign BUS_BYTE_ACCESS = (BUS_ADD < 32'h8000_0000) ? 1'b1 : 1'b0;

    // Clocks
    reg CLK40;       // BUS_CLK (driven by cocotb)
    reg SEQ_CLK;     // Sequencer clock (generated locally)
    reg SPI_CLK;     // SPI clock

    assign BUS_CLK = CLK40;

    // Generate SEQ_CLK from BUS_CLK (4x for simulation)
    initial SEQ_CLK = 0;
    always #1.25 SEQ_CLK = ~SEQ_CLK;  // 400 MHz

    initial SPI_CLK = 0;
    always #25 SPI_CLK = ~SPI_CLK;    // 20 MHz

    // Analog input (driven by AnalogDriver SIMULATION_MODULE)
    real VIN_P, VIN_N;
    real VIN_EN;

    // Wires between FPGA core and chip
    wire clk_init, clk_samp, clk_comp, clk_logic;
    wire spi_sclk, spi_sdi, spi_sdo, spi_cs_b;
    wire rst_b, ampen_b;
    wire comp_out;

    // FIFO interface
    wire [31:0] fifo_data;
    wire fifo_read_next, fifo_empty;

    // FPGA DAQ core (same RTL as real hardware)
    daq_core i_daq_core(
        .bus_clk(CLK40),
        .bus_rst(BUS_RST),
        .bus_add(BUS_ADD),
        .bus_data(BUS_DATA),
        .bus_rd(BUS_RD),
        .bus_wr(BUS_WR),
        .seq_clk(SEQ_CLK),
        .clk_init(clk_init),
        .clk_samp(clk_samp),
        .clk_comp(clk_comp),
        .clk_logic(clk_logic),
        .spi_clk(SPI_CLK),
        .spi_sclk(spi_sclk),
        .spi_sdi(spi_sdi),
        .spi_sdo(spi_sdo),
        .spi_cs_b(spi_cs_b),
        .rst_b(rst_b),
        .ampen_b(ampen_b),
        .fifo_data_out(fifo_data),
        .fifo_read_next(fifo_read_next),
        .fifo_empty(fifo_empty),
        .comp_out(comp_out),
        .reset(BUS_RST),
        .seq_pattern_out(),
        .seq_pattern_addr(6'b0)
    );

    // BRAM FIFO (replaces sitcp_fifo for bus-accessible readback)
    bram_fifo #(
        .BASEADDR(32'h8000),
        .HIGHADDR(32'h9000 - 1),
        .BASEADDR_DATA(32'h8000_0000),
        .HIGHADDR_DATA(32'h9000_0000),
        .ABUSWIDTH(32)
    ) i_fifo(
        .BUS_CLK(CLK40),
        .BUS_RST(BUS_RST),
        .BUS_ADD(BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD(BUS_RD),
        .BUS_WR(BUS_WR),
        .FIFO_READ_NEXT_OUT(fifo_read_next),
        .FIFO_EMPTY_IN(fifo_empty),
        .FIFO_DATA(fifo_data),
        .FIFO_NOT_EMPTY(),
        .FIFO_FULL(),
        .FIFO_NEAR_FULL(),
        .FIFO_READ_ERROR()
    );

    // FRIDA chip digital model (only ADC[0] active)
    frida_core i_chip(
        .seq_init(clk_init),
        .seq_samp(clk_samp),
        .seq_comp(clk_comp),
        .seq_logic(clk_logic),
        .spi_sclk(spi_sclk),
        .spi_sdi(spi_sdi),
        .spi_sdo(spi_sdo),
        .spi_cs_b(spi_cs_b),
        .reset_b(rst_b),
        .comp_out(comp_out)
        // Note: vin_p, vin_n, power pins excluded (no USE_POWER_PINS)
        // Analog inputs arrive at the analog stubs via spicebind
    );

endmodule
```

**Note:** The analog stubs inside `adc.v` (comp, sampswitch, caparray) are the
spicebind binding points. The `VIN_P`/`VIN_N` real signals on the testbench top
level are driven by the `AnalogDriver` SIMULATION_MODULE and feed into the SPICE
netlist as external sources connected to the sampling switch inputs.

**DAQ Verilog file naming:**

```
design/daq/
├── daq_fpga.v    # FPGA top: SiTcp, PLLs, LVDS (Vivado synthesis)
├── daq_core.v    # Basil modules: seq_gen, spi, gpio, pulse_gen, fast_spi_rx
├── daq_tb.v      # Simulation top: cocotb bus + bram_fifo + frida_core
└── ...
```

`daq_fpga.v` includes `daq_core.v` for synthesis. `daq_tb.v` includes
`daq_core.v` for simulation. Same core, different wrappers.

**Verify:** `iverilog -g2005-sv -I ... -o design/daq/daq_tb.vvp design/daq/daq_tb.v` compiles.

---

## Step 7: Basil simulation config

**Create:** `flow/scans/map_sim.yaml`:

```yaml
name: frida-sim
version: 0.1.0

transfer_layer:
  - name: intf
    type: SiSim
    init:
      host: localhost
      port: 12345
      timeout: 10000

  - name: awg_sim
    type: SerialSim
    init:
      host: localhost
      port: 12346
      signal_map:
        voltage_high: VIN_P
        voltage_low: VIN_N
        enable: VIN_EN

hw_drivers:
  - name: fifo
    type: bram_fifo
    interface: intf
    base_addr: 0x8000
    base_data_addr: 0x80000000

  - name: seq
    type: seq_gen
    interface: intf
    base_addr: 0x10000
    mem_bytes: 8192

  - name: spi
    type: spi
    interface: intf
    base_addr: 0x20000
    mem_bytes: 1024

  - name: gpio
    type: gpio
    interface: intf
    base_addr: 0x30000

  - name: pulse_gen
    type: pulse_gen
    interface: intf
    base_addr: 0x40000

  - name: fast_spi_rx
    type: fast_spi_rx
    interface: intf
    base_addr: 0x50000

  - name: awg
    type: agilent33250a
    interface: awg_sim

registers: []  # DUT registers loaded from map_dut.yaml by Frida class
```

---

## Step 8: flow simulate / flow measure CLI commands

**Modify:** `flow/cli.py`:

```python
# ==== Simulate (mixed-signal co-simulation) ====
p = sub.add_parser("simulate", help="Run mixed-signal co-simulation")
p.add_argument("-c", "--cell", required=True,
               choices=["samp", "comp", "cdac", "adc"])
p.add_argument("-t", "--tech", default="tsmc65", choices=list_pdks())
p.add_argument("--scan", required=True,
               choices=["scurve", "transfer", "settling"])
p.add_argument("--mc", type=int, default=1,
               help="Monte Carlo runs (re-launches simulator with fresh agauss seeds)")
p.add_argument("-o", "--out", default="scratch", type=Path)

# ==== Measure (physical measurement) ====
p = sub.add_parser("measure", help="Run physical measurement")
p.add_argument("-c", "--cell", required=True,
               choices=["samp", "comp", "cdac", "adc"])
p.add_argument("--scan", required=True,
               choices=["scurve", "transfer", "settling"])
p.add_argument("--channels", type=str, default="0",
               help="Comma-separated ADC channels to measure (e.g. 0,1,2,3)")
p.add_argument("-o", "--out", default="scratch", type=Path)
```

**Create:** `flow/scans/simulate.py` — orchestrates the co-simulation:

```python
"""Mixed-signal simulation runner.

Uses basil's modern cocotb runner (basil.utils.sim.runner.cocotb_run)
which wraps cocotb's Python-native Runner API (added Jan 2022, PR #2634).
No Makefiles, no os.environ pollution — all config is passed as extra_env
on the simulator subprocess.

For Monte Carlo, re-launches the entire simulator for each run. ngspice
re-seeds agauss()/gauss() in the PDK models on restart.
"""

from pathlib import Path

import yaml
import numpy as np
import spicebind
from basil.dut import Dut
from basil.utils.sim.runner import cocotb_run

from flow.scans.host import Frida

# Basil simulation config passed to the simulator subprocess
_SIM_ENV = {
    "SIMULATION_HOST": "localhost",
    "SIMULATION_PORT": "12345",
    "SIMULATION_BUS": "basil.utils.sim.BasilSbusDriver",
    "SIMULATION_END_ON_DISCONNECT": "1",
    "SIMULATION_MODULES": yaml.dump({"basil.utils.sim.AnalogDriver": {}}),
    "ANALOG_SIM_PORT": "12346",
}


def setup_simulation(cell: str, tech: str, outdir: Path):
    """Launch simulator and return (frida, daq) pair."""

    cosim_netlist = outdir / f"tb_{cell}.sp"
    if not cosim_netlist.exists():
        raise SystemExit(
            f"Co-sim netlist not found: {cosim_netlist}\n"
            f"Run: flow netlist -c {cell} -t {tech} -f ngspice --scope cosim"
        )

    # Build env for the simulator subprocess
    sim_env = {
        **_SIM_ENV,
        "SPICE_NETLIST": str(cosim_netlist),
        "HDL_INSTANCE": "tb.i_chip.adc_array[0].adc_inst",
    }

    # Launch Icarus + cocotb + spicebind (non-blocking — runs in background)
    cocotb_run(
        sim="icarus",
        sources=[Path("design/daq/daq_tb.v")],
        top_level="tb",
        includes=[
            Path("libs/basil/basil/firmware/modules"),
            Path("design/daq"),
            Path("design/hdl"),
            outdir,  # generated stubs (.v) live here
        ],
        sim_args=["-M", spicebind.get_lib_dir(), "-m", "spicebind_vpi"],
        extra_env=sim_env,
    )

    # Connect to simulator via basil
    yaml_path = Path(__file__).parent / "map_sim.yaml"
    daq = Dut(str(yaml_path))
    daq.init()

    frida = Frida(daq)
    frida.init()

    return frida, daq


def run_sim(cell: str, tech: str, scan_name: str, outdir: Path, mc_runs: int = 1):
    """Run a scan, optionally with Monte Carlo repetitions.

    Each MC run launches a fresh simulator instance, which causes ngspice
    to re-seed agauss()/gauss() in the PDK models. The scan code is
    agnostic — it sees one run. Stacking happens here.
    """
    from flow.scans import SCAN_REGISTRY
    scan_cls = SCAN_REGISTRY[scan_name]

    all_results = []
    for i in range(mc_runs):
        if mc_runs > 1:
            print(f"Monte Carlo run {i+1}/{mc_runs}")

        frida, daq = setup_simulation(cell, tech, outdir)
        scan = scan_cls()
        result = scan.run(frida, daq)
        all_results.append(result)
        daq.close()

    # Stack results
    if mc_runs == 1:
        np.savez(outdir / f"{cell}_{scan_name}.npz", **all_results[0])
    else:
        stacked = {}
        for key in all_results[0]:
            stacked[key] = np.stack([r[key] for r in all_results])
        stacked["mc_runs"] = np.array(mc_runs)
        np.savez(outdir / f"{cell}_{scan_name}_mc{mc_runs}.npz", **stacked)
```

**Verify:** `flow simulate -c comp -t tsmc65 --scan scurve` runs end-to-end.

---

## Step 9: Adapt host.py for dual-mode operation

**Modify:** `flow/scans/host.py`

The main change: `time.sleep()` calls in `init()` and `run_conversions()` are
no-ops in simulation (simulation time only advances via bus transactions).

```python
def _sleep(self, seconds):
    """Sleep in hardware mode, no-op in simulation."""
    if not isinstance(self.daq._transport_layer, SiSim):
        time.sleep(seconds)
```

Replace all `time.sleep(...)` calls with `self._sleep(...)`.

Everything else (SPI writes, sequencer config, FIFO readback) uses the basil
API which works transparently with both SiTcp and SiSim.

---

## File Summary

| File | Action | Step |
|------|--------|------|
| `libs/spicebind/` | Add as git submodule | 1 |
| `pyproject.toml` | Merge all deps into main dependencies list | 1 |
| `libs/basil/basil/utils/sim/runner.py` | Create: modern cocotb runner wrapper | 3 |
| `libs/basil/basil/utils/sim/Protocol.py` | Modify: add `AnalogSetRequest` class | 3 |
| `libs/basil/basil/TL/SerialSim.py` | Create: new basil TL | 3 |
| `libs/basil/basil/utils/sim/AnalogDriver.py` | Create: SIMULATION_MODULE | 3 |
| `flow/circuit/netlist.py` | Modify: add `generate_verilog_stub()` utility | 4 |
| `flow/*/testbench.py` | Modify: add `scope` param, `Vexternal` conditionals | 4 |
| `libs/Hdl21/hdl21/primitives.py` | Add `Vexternal` primitive | 4 |
| `libs/Vlsir/VlsirTools/vlsirtools/netlist/spice.py` | Handle `vexternal` → `0 external` | 4 |
| `flow/cli.py` | Modify: add `--scope cosim`, `simulate`, `measure` commands | 4, 8 |
| `flow/scans/__init__.py` | Create: ScanBase class + scan registry | 5 |
| `flow/scans/scan_comp_scurve.py` | Create: comp S-curve scan | 5 |
| `flow/scans/scan_adc_transfer.py` | Create: ADC transfer scan | 5 |
| `flow/scans/simulate.py` | Create: launch cocotb+spicebind, setup sim, MC loop | 5 |
| `flow/scans/measure.py` | Create: setup Dut(map_fpga.yaml) | 5 |
| `flow/scans/host.py` | Move from `daq/host/` (Frida class + sequences) | 5 |
| `design/daq/daq_tb.v` | Create: Icarus simulation testbench | 6 |
| `design/daq/daq_core.v` | Rename from `frida1_core.v` | prereq |
| `design/daq/daq_fpga.v` | Rename from `frida1.v` | prereq |
| `flow/scans/map_sim.yaml` | Create: basil sim config (SiSim + SerialSim) | 7 |
| `flow/scans/map_fpga.yaml` | Move from `daq/host/` | 7 |
| `flow/scans/map_dut.yaml` | Move from `daq/host/` | 7 |
| `design/pcb/` | Rename from `daq/dut/`, add `ths4541.sp` | prereq |

## Instrument Mocking: End-to-End Signal Path

This section traces how a voltage set by scan code reaches the SPICE simulation.
The same pattern applies to the AWG (input stimulus) and power supply (VDD).

### Hardware path

```
scan code: daq["awg"].set_voltage_high(0.6)
    → agilent33250a.set_voltage_high(0.6)      (basil HL driver)
        → self._intf.write("VOLT:HIGH 0.6")    (SCPI string)
            → Serial.write(bytes)               (basil TL: USB-RS232)
                → physical AWG changes output
                    → BNC cable → THS4541 amp → chip vin_p pad
```

### Simulation path

```
scan code: daq["awg"].set_voltage_high(0.6)     ← identical call
    → agilent33250a.set_voltage_high(0.6)        (same basil HL driver)
        → self._intf.write("VOLT:HIGH 0.6")      (same SCPI string)
            → SerialSim.write(bytes)              (basil TL: new, replaces Serial)
                → parses "VOLT:HIGH" → extracts 0.6
                → sends AnalogSetRequest("VIN_P", 0.6) via TCP socket
                    → AnalogDriver (SIMULATION_MODULE in cocotb)
                        → dut.VIN_P.value = 0.6  (Verilog real port)
                            → spicebind reads VIN_P
                                → ngspice: Vawg_p source returns 0.6V
                                    → THS4541 subcircuit → vin_p node
```

### YAML config swap (the only difference)

```yaml
# map_fpga.yaml (hardware)          # map_sim.yaml (simulation)
transfer_layer:                      transfer_layer:
  - name: awg_serial                   - name: awg_serial
    type: Serial                         type: SerialSim
    init:                                init:
      port: /dev/ttyUSB0                   host: localhost
      baudrate: 9600                       port: 12346
                                           signal_map:
                                             voltage_high: VIN_P
                                             voltage_low: VIN_N

  - name: psu_serial                   - name: psu_serial
    type: Serial                         type: SerialSim
    init:                                init:
      port: /dev/ttyUSB1                   host: localhost
      baudrate: 9600                       port: 12347
                                           signal_map:
                                             voltage: VDD
```

The HL drivers (`agilent33250a`, power supply SCPI driver) are unchanged.
The scan code is unchanged. Only the YAML selects hardware or simulation.

## Data Flow and Observability

### Primary data path (same for simulation and hardware)

Scan data (comparator decisions, ADC codes) flows live through the basil FIFO,
identical in both modes:

```
Simulation:  ngspice comp_out → spicebind threshold → Icarus digital 0/1
             → frida_core MUX → daq_core fast_spi_rx → bram_fifo
             → SiSim socket → basil get_data() → numpy array → .npz

Hardware:    FRIDA chip comp_out → LVDS → BDAQ53 fast_spi_rx → sitcp_fifo
             → SiTcp Ethernet → basil get_data() → numpy array → .npz
```

No intermediate files. `run_conversions()` returns numpy arrays directly.
Both paths save results as `.npz` files in `scratch/`.

### Simulation-only debug data

SpiceBind produces two additional output files for debugging:

- **`dump.raw`** — ngspice raw file, written at simulation end. Contains all
  internal SPICE node voltages/currents at every timestep. Access internal
  signals like comparator latch voltages, DAC settling waveforms, etc.
  These are not visible through cocotb — they only exist in the ngspice domain.
  Parse with `spyci` or ngspice ASCII mode after simulation:

  ```python
  # Post-simulation analysis of internal analog nodes
  from spyci import load_raw
  raw = load_raw("scratch/dump.raw")
  time = raw["time"]
  vlatch = raw["v(xtop.xdut.xcomp.vlatch_p)"]  # SPICE hierarchical names
  ```

  Note: HDL21 does not provide Python-object-to-SPICE-node mapping. Internal
  node access uses raw SPICE hierarchical name strings.

- **`*.vcd`** — Icarus VCD file (if `$dumpvars` is in the testbench). Contains
  digital signals only. Useful for viewing bus transactions and sequencer timing
  in GTKWave. Not part of the data pipeline.

### cocotb runtime signal access

cocotb can read **any signal in the Verilog hierarchy** at runtime via VPI,
not just top-level ports. This includes internal digital signals:

```python
# During a scan, from a SIMULATION_MODULE or extended Test.py:
dut.i_chip.spi_reg.spi_bits.value           # 180-bit SPI register
dut.i_chip.adc_array[0].adc_inst.dac_state_p.value  # SAR logic state
dut.i_daq_core.inst_fast_spi_rx.SCLK.value  # FPGA-side signals
```

However, signals inside spicebind-bound analog blocks (internal SPICE nodes)
are **not** accessible through cocotb. cocotb sees the analog stub ports
(`real` values at the spicebind boundary) but nothing inside the SPICE
subcircuit. For those, use `dump.raw`.

### Summary

| Data type | Access method | Available in |
|-----------|--------------|-------------|
| ADC codes / comp_out bits | basil FIFO → numpy | Both sim & hardware |
| Digital internals (SPI, SAR, clocks) | cocotb `dut.path.value` | Simulation only (runtime) |
| Analog stub ports (vin, vdac, etc.) | cocotb `dut.path.value` (real) | Simulation only (runtime) |
| Analog internals (latch nodes, etc.) | `dump.raw` (SPICE names) | Simulation only (post-sim) |
| Scope waveforms | `daq["scope"].get_waveform()` | Hardware only |

---

## Risks

1. **TSMC hspice models in ngspice**: The 15MB model file may have syntax ngspice
   can't parse. Validated early in Step 2.
2. **SEQ_CLK speed**: Each sequencer edge triggers spicebind sync. 400 MHz may be
   slow. The testbench uses a local clock that can be slowed down — the sequencer
   is step-based, not time-based.
3. **bram_fifo vs sitcp_fifo**: Different FIFO types but same basil Python API.
   `run_conversions()` data parsing may need minor adjustments for word ordering.
4. **spicebind multi-instance**: The ADC has 3 analog blocks (comp, samp, cdac).
   SpiceBind needs `HDL_INSTANCE` to list all three, comma-separated.
5. **frida_core.v generates 16 ADCs**: For simulation, compile with a parameter
   or ifdef to instantiate only ADC[0]. Others tie comp_out to 0.
