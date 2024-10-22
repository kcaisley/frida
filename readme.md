# Current design progress

### Legacy 'flat' design
![alt text](docs/images/helena_before.png)

### SAR ADC sub-circuits (SASC)
![alt text](docs/images/helena_top.png)

# Basic Simulation

![alt text](docs/images/helena_sim.png)

# Design targets

| Design                  | EDET DCD    | CoRDIA     | pre-Helena | Helena      |
|-------------------------|-------------|------------|------------|-------------|
| ADC resolution          | 8-bit       | 10-bit     | 8-bit      | 10-bit      |
| Conversion rate         | 10 MHz      | 2.5MHz     | 5 MHz      | 10 MHz      |
| Area of one ADC         | 100x200 μm² | 80x330 μm² | 60x800 μm² | 20x100 μm²  |
| Power of one ADC        | 3500 μW     | 30 μW      | 700 μW     | 100 μW      |
| FOM_csa (conv/sec/area) | 500 Hz/μm²  | 95 Hz/μm²  | 105 Hz/μm² | 5000 Hz/μm² |
| FOM_epc (energy/conv)   | 350 pJ      | 12 pJ      | 155 pJ     | 10 pJ       |
| FOM_ppa (power/area)    | 17.5 W/cm²  | 0.11 W/cm² | 1.45 W/cm² | 5.0 W/cm²   |
| ADCs for 1Mpix@100Khz   | 10000       | 40000      | 20000      | 10000       |
| ADCs total area         | 2.0 cm²     | 10.5 cm²   | 9.6 cm²    | 0.2 cm²     |
| ADCs total power        | 35.0 W      | 1.2 W      | 14 W       | 1.0 W       |

# Column-parrallel ADC FOM

murmann 2022


# Design techniques

- ✅ Unary, double conversion, and non-binary steps (typically x1.8 smaller)
- ✅ RDAC for powering lower voltage LSBs vs attenuating cap
- ❕ MoM != MIM, and POD is best  @ 4fF in μm², with ~5% variation
- ❌ MoM caps are only 0.6-0.8 fF in the same μm², with worse variation
- ✅ Double sample, and use differential cap array
- ✅ Auto-zero comparator, and use a basic dynamic/clocked latch design
- ❌ Async jeapordizes stability of neighbors
- ✅ Share sequencer across all ADCs
- ❌ Interleaving typically not worth it
- ✅ 7-8 Gbps JESD204B w/ 8b/10b encoding

# Compiling/simulating against PDKs

- TSMC 65nm (✅ Working)
- Tower 180nm (✅ working on tsl018)
- TSMC 180nm (tsmc018)
- Tower 65nm (tpsc65)

# Needs

- [ ] tpsco65
- [ ] Siemens AFS license (just 50EUR!)
- [ ] 