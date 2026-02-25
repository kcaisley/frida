## Connectors & Footprints

- [x] RJ45 connector (J3) updated to Molex 446200002 with 3D model and datasheet
- [x] Molex Mini-Fit Jr connector (J5) updated to part 469990014 (2x2, 4 circuits) with 3D model
- [x] SMA connectors J1/J2 updated to Molex 733910070 vertical SMA with local footprint/model
- [x] Pin headers updated from 2x04 to 2x02 where applicable
- [x] DisplayPort connector footprint fixed (zero-sized pad corrected)
- [x] THS4541 (U3) footprint switched to local Texas RUN0010A WQFN-10 copy
- [x] TXV0106-Q1 level shifter (U2) added to schematic with local footprint + 3D model mapping
- [x] All footprints and 3D models self-contained in daq/dut/frida.pretty
- [x] Stale library references removed from fp-lib-table (silab, dmaps, import)

### Library file inventory

Local symbols in `frida:`, local footprints in `frida:`, KiCad built-in libraries prefixed accordingly.
Naming convention: `Company_Type_PartNum`.

| ID | Component | Symbol | Footprint | 3D Model |
|---|---|---|---|---|
| J1 | Input SMA P (Molex 733910070) | `frida:Molex_SMA_733910070` | `frida:Molex_SMA_733910070` | `Molex_SMA_733910070.stp` |
| J2 | Input SMA N (Molex 733910070) | `frida:Molex_SMA_733910070` | `frida:Molex_SMA_733910070` | `Molex_SMA_733910070.stp` |
| J3 | RJ45 (Molex 446200002) | `Connector:RJ45` | `frida:Molex_RJ45_446200002` | `Molex_RJ45_446200002.stp` |
| J4 | DisplayPort (Molex 472720024) | `frida:Molex_DisplayPort_472720024` | `frida:Molex_DisplayPort_472720024` | `Molex_DisplayPort_472720024.stp` |
| J5 | Molex Mini-Fit Jr 2x02 (469990014) | `frida:Molex_MiniFitJr_469990014` | `frida:Molex_MiniFitJr_469990014` | `Molex_MiniFitJr_469990014.stp` |
| J6 | Generic header 2x06 | `Connector_Generic:Conn_02x06_Top_Bottom` | *(unassigned in schematic)* | *(none)* |
| U1 | FRIDA ASIC | `frida:FRIDA_ASIC_Pad` | `frida:FRIDA_ASIC_Pad` | *(none)* |
| U2 | TXV0106-Q1 level shifter | `frida:TI_LevelShifter_TXV0106Q1` | `frida:TI_LevelShifter_TXV0106Q1` | `TI_LevelShifter_TXV0106Q1.stp` |
| U3 | THS4541 diff amp | `frida:TI_DiffAmp_THS4541` | `frida:TI_DiffAmp_THS4541` | `TI_DiffAmp_THS4541.stp` |

## Test Point Placement

Reference section for future TP additions in the schematic:

- Place TP symbols on a single horizontal row at `y = 114.3 mm`.
- Use `x` pitch of `12.7 mm` between adjacent TP symbols.
- For example, some TP row anchor points are `x = 25.4, 38.1, 50.8, 63.5, 76.2, 88.9, 101.6, 114.3, 127.0, 139.7 mm` (TP1..TP10).
- Place each net label at the exact same coordinate as its TP symbol anchor (delta `x = 0`, delta `y = 0`).
- Set TP label text angle to `270 deg` with `justify right bottom` so text runs downward.
- Draw no connecting wire between TP and label (line length `0 mm` because both are coincident).
- Hide the `Value` field on TP symbols.

## PCB Stackup & Impedance

4-layer stackup from Multi-CB (FR4, 1.6mm nominal):

![4-layer Multi-CB stackup](images/4L_multicb_stackup.png)

- Estimated final thickness (+/- 10%): 1.6mm
- Prepreg thicknesses after pressing, at approx. 80% copper utilization on the inner layers.
- Loss Tangent / Dissipation factor (Df): ca. 0.02
- Dielectric constant Er for 1x Prepreg 1080: 3.95

### Differential trace geometry

| Type              | Impedance | Signal layer | Reference layer | Width  | Space  |
|-------------------|-----------|--------------|-----------------|--------|--------|
| Single ended      | 50 Ohm    | TOP          | IN2             | 245um  | -      |
| Differential pair | 90 Ohm    | TOP          | IN2             | 180um  | 120um  |
| Differential pair | 100 Ohm   | TOP          | IN2             | 120um  | 115um  |

- [ ] Request impedance control from Multi-CB at order time (+/- 10% or +/- 5% tolerance available on request)

## Schematic Checklist

- [x] Add input devices/switching for the buffer.
- [x] Add a test point on `VIN_N`.
- [x] Add extra feedback capacitors.
- [x] Add series measurement resistors.
- [x] Switch the `VOCM` voltage divider supply from `VDD_IO` to `VDD_DAC`.
- [x] Switch clamps to the amplifier output.
- [x] Switch transistor polarity of `AMP_PD_EXT`.
- [x] Add pull-up/ pull-down control on `AMP_EN_EXT_B`.
- [x] Switch `BDAQ` supplied voltage naming to `BDAQ` instead of `DAQ`.
- [x] Change clock differential pair pull-downs to `1k`.
- [x] Forward `VDD_BDAQ` on one extra pin.
- [x] Add clamp diodes to protect FRIDA from external/buffer sources on `VIN_P` and `VIN_N`, with solder/pin jumper options; check ENOB impact and clamp to `VDD_DAC` and `GND`.
- [x] Share input connector pins and add headers for current measurement.
- [x] Add feedback and forward filter capacitors to amplifiers (two stage low-pass).
- [x] Reverse the `PD_N` pull-down to a pull-up with `VDD_BDAQ`.
- [x] Add pin-8 supply for `VDAQ`.
- [x] Rename `VDD_DAQ`/ `VDD_DAC` to `VDD_BDAQ` where applicable.
- [x] Change `RJ45` pin 7 to provide ground reference.
- [x] Flip pin orders of differential pairs, to match DP connector to DUT pinout
- [x] Update part for level-shifter to `SN74AXC8T245RJWR`
- [x] Add pull-up for the frida `rst_b`, to ensure it's enabled by default

## PCB Checklist

- [x] Keep amp test-point placement as-is (good).
- [ ] Route `LVDS_TX` as `100 ohm` differential.
- [ ] Route `LVDS_RX` as `100 ohm` differential.
- [ ] Add a solid silkscreen field for batch numbers.
- [ ] Add logos.
- [ ] Add more headers, including doubled ground headers.
- [ ] Add text labels for header names.
- [ ] Name test points by signal net instead of test-point number.
- [ ] Keep routing out from under the DisplayPort connector.
- [x] Add electrical connection for chip back plane (via down).
- [x] Name the jumpers.
- [x] Add ground plane to the FRIDA footprint.
- [ ] Place pull-up resistors on the backside.
- [ ] Connect all FRIDA ground pads to footprint ground to reduce ground impedance.
- [ ] Place differential resistors equidistant from the chip.
- [ ] Float mounting holes instead of tying to earth/ ground.
- [ ] Add lot-number marking area.
