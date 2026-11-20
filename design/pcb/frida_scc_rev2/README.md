# frida_scc_rev2

The FRIDA single-chip card, revision 2.0: the test board for the FRIDA-1 ADC, written in
[Zener](https://docs.pcb.new/pages/spec.md). The `.zen` files are the source; the `pcb` tool makes
the netlist, the KiCad schematic and the KiCad board from them. The previous board is
`../frida-scc-1p1.kicad_pro`.

This is a first sketch: it builds (236 components) and generates. The board has frida-scc-1p1's
outline, stack-up and, for the 92 parts both boards have, its placement; the 144 new parts are
placed around them. Routing is in progress, nothing is simulated yet, and the items under "Open
questions" are undecided.

## Flow

```bash
# KiCad 10 for the pcb tool (the pinned AppImage, unpacked by tools/check.py install kicad)
export KICAD_APPDIR=$PWD/../../../build/tools/kicad-10.0.8/AppDir  # in the main checkout
export KICAD_CLI=$KICAD_APPDIR/bin/kicad-cli KICAD_PCBNEW=$KICAD_APPDIR/bin/pcbnew
export KICAD_PYTHON_INTERPRETER=$PWD/../kicad-python  # a wrapper that keeps pcb's PYTHONPATH

pcb build frida_scc_rev2.zen                       # check the design, write the netlist
pcb bom frida_scc_rev2.zen                         # the bill of materials, generics matched to parts
pcb apply schematic --no-open frida_scc_rev2.zen   # eda/frida_scc_rev2.kicad_sch and its pages
pcb layout --no-open frida_scc_rev2.zen            # eda/frida_scc_rev2.kicad_pcb
$KICAD_APPDIR/bin/python3.11 place_from_1p1.py    # frida-scc-1p1's outline and shared placement
$KICAD_APPDIR/bin/python3.11 place_new.py         # the new parts, around them
$KICAD_APPDIR/bin/python3.11 route_from_1p1.py    # frida-scc-1p1's tracks and ground plane for the shared parts
```

The board file owns the geometry (placement, routing, outline); later `pcb layout` runs keep it
and place only new parts, so the board and its project file in `eda/` are committed. The schematic is kept the same
way: the tool repairs only what no longer matches the design, and leaves the drawing alone.

`place_from_1p1.py` copies the outline and, for each part named in its table, the position,
rotation and side of the part it replaces on frida-scc-1p1 (the tap resistors sit on the pads of
the 1 kohm loads they replace). It also checks that the two boards' nets correspond one to one
over those parts, and moves every other part beside the outline. `place_new.py` then places
those: the supplies and the signal source left of the chip, the four probe channels and the
second RJ45 right of it, each small part beside the pin it serves. `route_from_1p1.py` copies frida-scc-1p1's tracks and vias onto the nets that are on the same
pads here, drops what a new part or a changed pad is in the way of, removes the loose ends that
led to parts that are gone, and gives the inner layers its ground plane: the LVDS pairs and the
analog input keep the routing that was measured. Run the three in this order to lay the board
out again from nothing.

Autorouting runs FreeRouting on this machine, driven directly (the `pcb` tool's own `route`
command was removed after release 0.4.60): KiCad writes the board as a Specctra design,
FreeRouting routes it, KiCad reads the result back. FreeRouting and its Java runtime are pinned
in `pyproject.toml` and fetched on first use.

```bash
uv run --no-project --python 3.12 python ../freeroute.py eda/frida_scc_rev2.kicad_pcb --minutes 30
```

## Schematic

Page 1 is frida-scc-1p1's sheet as it was drawn (its wires, notes and jumper pictures), with the
values and nets of this design; the parts that are new are on pages 2 to 5, in a block per
function, each pin with the tool's stub and net label (connections there are by net name, between
pages by global labels). `arrange_schematic.py` made it that way and says how in its heading; it
runs again when parts are added. `kicad-cli sch export pdf eda/frida_scc_rev2.kicad_sch` prints
all pages.

## Structure

| File | What it holds |
| --- | --- |
| `frida_scc_rev2.zen` | The board: rails, buses, one instance of each module, the probe matrix's node map |
| `modules/Asic.zen` | The FRIDA-1 die, its clock terminations, decoupling and reset pull-up |
| `modules/FpgaLink.zen` | DisplayPort (clocks, COMP_OUT) and RJ45 (SPI, reset) to the BDAQ53, the level shifter |
| `modules/AuxLink.zen` | A second RJ45: an SPI bus for the DAC and the probe matrix |
| `modules/InputAmp.zen` | SMAs, jumper network, THS4541, output filter, clamps |
| `modules/Supplies.zen` | +-5 V in; seven rails, each from its own regulator; external-rail jumpers |
| `modules/Regulator.zen`, `NegRegulator.zen` | One LT3045 or LT3094 rail |
| `modules/SignalSource.zen` | 2.5 V reference, 16-bit DAC, follower, two-pole filter |
| `modules/LvdsTap.zen` | One LVDS pair's resistive pick-off |
| `modules/ProbeChannel.zen` | One oscilloscope SMA: RF switch, slow multiplexer, select register |
| `components/` | Parts with their own symbol and footprint |

## What is new against frida-scc-1p1

**Supplies.** One raw +5 V and one raw -5 V come in on the Mini-Fit Jr. An LT3045 each makes
VDD_A, VDD_D, VDD_DAC and VDD_IO (1.2 V), 3.3 V for the analog parts and 2.5 V for the control
logic; an LT3094 makes -1 V. Each chip rail has a jumper that takes it from a lab supply
instead, as before. Each chip rail's regulator reports its load current (3 mV per mA) to the
probe matrix.

**Signal source.** An AD5541A 16-bit DAC on an ADR4525 2.5 V reference, a follower and a
145 kHz two-pole filter, with half the reference as the negative leg (+-1.25 V differential),
into the input network through jumpers beside the SMAs. It is for
ramps, DC levels and sines up to tens of kHz. Tones near the Nyquist frequency still come in on
the SMA.

**Probe matrix.** Four SMAs, one per oscilloscope channel. Each is switched by an ADG904
(DC-coupled, absorptive, 2 GHz) to one of three LVDS tap legs or to an 8:1 multiplexer of slow
nodes; four chained shift registers on the second RJ45 hold the selection. The taps replace the
1 kohm-to-ground resistors and the header pins that sat on the LVDS lines.

| Channel | Fast legs | Slow nodes (after the four chip rails) |
| --- | --- | --- |
| CH1 | INIT+, COMP_OUT-, SAMP- | VIN+, amplifier OUT+, source / 2, SPI_CS_B |
| CH2 | COMP+, INIT-, LOGIC- | VIN-, amplifier OUT-, VOCM, SPI_SCLK |
| CH3 | LOGIC+, COMP- | I(VDD_A), I(VDD_DAC), V3P3A / 2, SPI_SDI |
| CH4 | COMP_OUT+, SAMP+ | I(VDD_D), I(VDD_IO), (V3P3A + VS_N) / 2, SPI_SDO |

**Label.** The top silkscreen reads "FRIDA SCC / Rev 2.0" in the corner by mounting hole H4
(`place_new.py`'s `LABEL`; `place_new.py label` adds it to a board placed before it existed).

**Corrections.** The chip symbol's pin 13 is `COMP_OUT_N` (was spelled `COUP_OUT_N`); Q1 is a
BSS84 on a SOT-23 footprint the libraries resolve; the DisplayPort cable's power pin no longer
joins a supply rail. The RJ45 jack's footprint has the two plated holes its shield's solder
tabs need (frida-scc-1p1's had none), on the connectors' shell net.

**Kept.** The parts frida-scc-1p1 drew itself keep its symbols and footprints, and their 3-D
models are its files in `../frida.pretty`.

## Where the numbers come from

Read from the manufacturers' datasheets (copies in the main checkout's `build/datasheets`, not
committed): LT3045, LT3094, AD5541A, ADR4525, TMUX1108, ADG904. Several are older revisions from
distributor copies; check them against the current ones before ordering.

Not yet checked against a datasheet: the followers (OPA365), the select register (SN74LVC595A),
the THS4541's and BAV99's order codes.

## Open questions

- The second RJ45: which BDAQ53 port and FPGA pins it gets (or the PMOD header instead).
- The amplifier's positive supply: 3.3 V here (the negative one is frida-scc-1p1's -1 V); its
  bench value on frida-scc-1p1 is not recorded.
- The level shifter's direction straps: both groups are pulled to A-to-B on frida-scc-1p1, with
  SDO in the second group.
- The amplifier's output filter (499 ohm, 100 nF across: 1.6 kHz) passes ramps and DC but no
  sine test; fixed, or selectable?
- The COMP_OUT tap loads the chip's own driver (2.49 kohm per leg to ground when watched or not).
- The board thermistor's value.
- The six 47 uF bulk capacitors keep frida-scc-1p1's 0402 footprint, for which no part is found;
  what was fitted there?
- Not designed yet: a filtered square wave for tones near Nyquist, a fast step between two DAC
  levels, trimming the chip rails from the FPGA, a differential amplifier per SMA (each leg goes
  out single-ended), the stack-up.
- Not carried over from frida-scc-1p1 yet: its routing, ground pours, silkscreen labels and logos.
