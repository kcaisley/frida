## Connectors & Footprints

- [x] RJ45 connector (J5) updated to Molex 446200002 with 3D model and datasheet
- [x] Molex Mini-Fit Jr connector (J13) updated to part 469990014 (2x2, 4 circuits) with 3D model
- [x] SMA connectors J2/J3 updated to Molex 733910070 vertical SMA with local footprint/model
- [x] Pin headers J1 and J12 changed from 2x04 to 2x02 (4 pins each)
- [x] DisplayPort connector footprint fixed (zero-sized pad corrected)
- [x] THS4541 (U3) footprint switched to local Texas RUN0010A WQFN-10 copy
- [x] TXV0106-Q1 level shifter added to schematic as U2
- [x] All footprints and 3D models self-contained in daq/dut/frida.pretty
- [x] Stale library references removed from fp-lib-table (silab, dmaps, import)

### Library file inventory

Local symbols in `frida:`, local footprints in `frida:`, KiCad built-in libraries prefixed accordingly.
Naming convention: `Company_Type_PartNum`.

| ID | Component | Symbol | Footprint | 3D Model |
|---|---|---|---|---|
| J2 | Input SMA P (Molex 733910070) | `frida:Molex_SMA_733910070` | `frida:Molex_SMA_733910070` | `Molex_SMA_733910070.stp` |
| J3 | Input SMA N (Molex 733910070) | `frida:Molex_SMA_733910070` | `frida:Molex_SMA_733910070` | `Molex_SMA_733910070.stp` |
| J5 | RJ45 (Molex 446200002) | `Connector:RJ45` | `frida:Molex_RJ45_446200002` | `Molex_RJ45_446200002.stp` |
| J13 | Molex Mini-Fit Jr 2x02 (469990014) | `frida:Molex_MiniFitJr_469990014` | `frida:Molex_MiniFitJr_469990014` | `Molex_MiniFitJr_469990014.stp` |
| DP1 | DisplayPort (Molex 472720024) | `frida:Molex_DisplayPort_472720024` | `frida:Molex_DisplayPort_472720024` | `Molex_DisplayPort_472720024.stp` |
| U3 | THS4541 diff amp | `frida:TI_DiffAmp_THS4541` | `frida:TI_DiffAmp_THS4541` | `Texas_RUN0010A_WQFN-10_2x2mm_P0.5mm.step` |
| U2 | TXV0106-Q1 level shifter | `frida:TI_LevelShifter_TXV0106Q1` | `Package_DFN_QFN:WQFN-16-1EP_4x4mm_P0.5mm_EP2.6x2.6mm` | `TI_LevelShifter_TXV0106Q1.stp` |
| U1 | FRIDA ASIC | `frida:FRIDA_ASIC_Pad` | `frida:FRIDA_ASIC_Pad` | *(none)* |

## Power & Voltage Management

- [ ] Level shifter: specify voltage requirements (source and target voltages)
- [ ] Forward VDD_FPGA voltage on one of the extra pins
- [ ] Buffer negative rail: make configurable with negative supply or ground (add jumper)
- [ ] TVS diode for reverse polarity protection (not for transients)

## Analog Input Path

- [ ] Input devices/switching for buffer
- [ ] Clamp diodes to protect FRIDA chip from external/buffer sources (VIN_P and VIN_N, use solder/pin jumper, check ENOB impact, clamp to VDD_DAC and GND)
- [ ] Share input connector pins but have headers to measure current
- [ ] Add test point on VIN_N

## Feedback Network

- [ ] Cap feedback: specify values and frequency response requirements

## Reset Circuit

- [ ] Add pulldown for reset using NMOS with 20k resistor connected to chip reset pin

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

## High-Speed Signals

- [ ] LVDS TX traces: design for 100 ohm differential impedance
- [ ] LVDS RX traces: design for 100 ohm differential impedance

## Research & Component Selection

- [ ] Check for new application notes on Analog Devices (AD) website
- [ ] Check for new application notes on Texas Instruments (TI) website
