# Capacitor Types

## MOM Capacitors (Metal-on-Metal)
- Structure: Multi-layer metal fingers with interdigitated layout
- Variations: RTMOM (rotated top metal-on-metal) with finger rotation between layers
- Fringe Layout: Interdigitated fingers with vias between layers or vias only at edges
- Capacitance Density (65nm process):
  - 1 layer: 0.31 fF/μm²
  - 2 layers: 0.62 fF/μm²  
  - 3 layers: 0.93 fF/μm²
- Matching: σ(ΔC/C) = 0.85% × √C[fF] (Pelgrom coefficient)
- Advantages: Best matching characteristics, no voltage dependence
- Layout Tips: Can stack on top of device capacitors (connect in parallel, not series)

## MIM Capacitors (Metal-Insulator-Metal)
- Structure: Special insulator layer between metal plates (Si₃N₄ or Ta₂O₅)
- Capacitance Density: 
  - Regular MIM: 1.7 fF/μm²
  - UHD MIM: 2.8 fF/μm²
  - UHD Stacked: 5.6 fF/μm²
- Trade-off: Using MIM caps sacrifices the top copper layer (1 out of 6 layers)
- ITRS 2011: 5-7 fF/μm² typical range

## MOSCAP/Varactor Capacitors  
- Structure: Poly gate over n-well (MOS capacitor)
- Capacitance Density: 7-11 fF/μm² (ITRS 2011)
- Voltage Dependence: Capacitance varies with applied voltage
- Applications: Primarily used in RF applications where voltage tuning is needed

## POD/Accumulation Capacitors
- Structure: Poly-over-diffusion with accumulation mode operation
- Capacitance Density: ~5 fF/μm²
- Operation: Channel doping keeps device in accumulation even at zero gate voltage
- Connection: Uses gate-to-bulk capacitance with source/drain tied together

## POP Capacitors (Poly-over-Poly)
- Structure: Two large rectangles on separate poly layers
- Requirement: Needs poly2 layer availability
- Layout: Simple parallel plate structure
- Density: Lower than other options but good for large value capacitors

## NIC Capacitors (N-Implant Capacitor)
- Structure: N-implant based capacitor (Tower Semiconductor specific)
- Usage: Available in Tower processes as alternative to standard options