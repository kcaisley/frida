# frida-scc-2p0

The FRIDA single-chip card, revision 2.0: the test board for the FRIDA-1 ADC, written in
[Zener](https://docs.pcb.new/pages/spec.md). The `.zen` files are the source; the `pcb` tool makes
the netlist, the KiCad schematic and the KiCad board from them. The previous board is
`../frida-scc-1p1.kicad_pro`.

## Flow

```bash
# KiCad 10 for the pcb tool (the pinned AppImage, unpacked by tools/check.py install kicad)
export KICAD_APPDIR=$PWD/../../../build/tools/kicad-10.0.8/AppDir  # in the main checkout
export KICAD_CLI=$KICAD_APPDIR/bin/kicad-cli KICAD_PCBNEW=$KICAD_APPDIR/bin/pcbnew
export KICAD_PYTHON_INTERPRETER=$PWD/../kicad-python  # a wrapper that keeps pcb's PYTHONPATH

pcb build frida-scc-2p0.zen                       # check the design, write the netlist
pcb apply schematic --no-open frida-scc-2p0.zen   # eda/frida-scc-2p0.kicad_sch
pcb layout --no-open frida-scc-2p0.zen            # eda/frida-scc-2p0.kicad_pcb
```

The board file owns the geometry (placement, routing, outline); later `pcb layout` runs keep it
and place only new parts.

## Structure

| File | What it holds |
| --- | --- |
| `frida-scc-2p0.zen` | The board: rails, buses, one instance of each module |
| `modules/Asic.zen` | The FRIDA-1 die, its clock terminations, decoupling and reset pull-up |
| `modules/FpgaLink.zen` | DisplayPort (clocks, COMP_OUT) and RJ45 (SPI, reset) to the BDAQ53, the level shifter |
| `modules/InputAmp.zen` | SMAs, jumper network, THS4541, output filter, clamps |
| `modules/LvdsTap.zen` | One LVDS pair's 20:1 resistive pick-off for the probe matrix |
| `components/` | Parts with their own symbol and footprint, carried over from frida-scc-1p1 |

## Changes from frida-scc-1p1

- The chip symbol's pin 13 is `COMP_OUT_N` (was spelled `COUP_OUT_N`).
- Q1 is a BSS84 on a SOT-23 footprint the libraries resolve.
- The probe headers on the LVDS lines, the amplifier and the SPI bus are gone; a probe matrix
  replaces them (in progress).
- Passives are the standard library's generic resistors and capacitors.

## Open questions

- Chip selects for the new SPI devices: every RJ45 wire and DisplayPort lane is in use.
- The level shifter's direction straps: both groups pulled to A-to-B on frida-scc-1p1, with SDO
  in the second group.
- The board thermistor's value.
