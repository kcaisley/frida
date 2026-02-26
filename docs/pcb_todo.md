## PCB Schematic:

- [x] RJ45 connector (J3) updated to Molex 446200002 with datasheet.
- [x] Molex Mini-Fit Jr connector (J5) updated to part 469990014 (2x2, 4 circuits).
- [x] SMA connectors J1/J2 updated to Molex 733910070 vertical SMA.
- [x] Pin headers updated from 2x04 to 2x02 where applicable.
- [x] TXV0106-Q1 level shifter (U2) added to schematic.
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

## PCB Layout:

- [x] RJ45 connector (J3) mapped to local footprint + 3D model for Molex 446200002.
- [x] Molex Mini-Fit Jr connector (J5) mapped to local footprint + 3D model for part 469990014.
- [x] SMA connectors J1/J2 mapped to local Molex 733910070 footprint/model.
- [x] DisplayPort connector footprint fixed (zero-sized pad corrected).
- [x] THS4541 (U3) footprint switched to local Texas RUN0010A WQFN-10 copy.
- [x] TXV0106-Q1 level shifter (U2) mapped to local footprint + 3D model.
- [x] All footprints and 3D models self-contained in `daq/dut/frida.pretty`.
- [x] Stale library references removed from `fp-lib-table` (`silab`, `dmaps`, `import`).
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

## Ordering Checklist:
- [ ] Request impedance control from Multi-CB at order time (+/- 10% or +/- 5% tolerance available on request)
