# Helena

Frame-based radiation detectors with integrating front-ends are especially well-suited for applications like electron microscopy and X-ray imaging where hit-rates are high, spatial resolution should be maximized with simple pixels, and energy resolution is needed, but particles need not be individually discriminated in time, space, or spectrum. In an experimental setting, fast frame rates allow for real time in-situ observations. Potential subjects include rapid chemical processes, molecular dynamics of proteins, crystal nucleation and growth, material phase transitions, thermal conductivity, charge transfer, and mechanical strain.

This project pursues the possibility of a single-reticle array larger than 1 Mpixel with a continuous frame-rate surpassing 100,000 fps. For the conjunction of these two specifications to be met, one must have a compact and power efficient bank of column-parallel data converters, which at 10-12 bit resolution churn out data at a rate in excess of 1000 Gbps. To fit within the constraints of a chip bottom, the converter fabric must respect a restricted metric of 1 W/cm^2 while exceeding a 5 ksps/µm^2 sampling rate density. Successive-approximation ADCs are identified as the optimal choice, and various topologies and techniques will be analyzed to meet our goals.

Research question: How do we best allocate the quantity and weighting of SA bit positions, in order to yeild the highest resolution (in ENOB) for a given power, area, and power budget, and with a given amount of power supply noise.

## Workflow

![](/docs/talks/workflow.svg)

## Design targets

| Design                  | EDET DCD    | CoRDIA     | pre-Helena | Helena      |
|-------------------------|-------------|------------|------------|-------------|
| ADC resolution          | 8-bit       | 10-bit     | 8-bit      | 10-bit      |
| Conversion rate         | 10 MHz      | 2.5MHz     | 5 MHz      | 10 MHz      |
| Area of one ADC         | 100x200 μm² | 80x330 μm² | 60x800 μm² | 20x100 μm²  |
| Power of one ADC        | 1800 μW     | 30 μW      | 700 μW     | 100 μW      |
| FOM_csa (conv/sec/area) | 500 Hz/μm²  | 95 Hz/μm²  | 105 Hz/μm² | 5000 Hz/μm² |
| FOM_epc (energy/conv)   | 180 pJ      | 12 pJ      | 155 pJ     | 10 pJ       |
| FOM_ppa (power/area)    | 9.0 W/cm²   | 0.11 W/cm² | 1.45 W/cm² | 5.0 W/cm²   |
| ADC qty Mpix @ 100 KHz  | 10000       | 40000      | 20000      | 10000       |
| ADCs total pixel rate   | 100 Gpx/s   | 100 Gpx/s  | 100 Gpx/s  | 100 Gpx/s   |
| ADCs total data rate    | 800 Gb/s    | 1 Tb/s     | 800 Gb/s   | 1 Tb/s      |
| ADCs total area         | 2.0 cm²     | 10.5 cm²   | 9.6 cm²    | 0.2 cm²     |
| ADCs total power        | 35.0 W      | 1.2 W      | 14 W       | 1.0 W       |

NOTE: EDET DCD 1800 μW seems high, does it erroneously includes input amp?

## Tasks

In direct pursuit of the above research question.

- [x] Verilog-A model of comparator
- [x] Replace active input with passive
- [x] Replace re-analog with external block
- [x] Verilog-A model of vstepping input voltage
- [ ] Fix Spectre compatibility (necessary for multi machine runs)
    - [ ] Replace waveform sources with either VA or SPECTRE supported AnalogLib parts
    - [ ] Benchmark SPICE vs Spectre, profile CPU
- [ ] Where are the asserts defined? Not in PDK or v2common...
- [ ] Benchmark lt177 vs jupiter vs asiclab0## workstations (necessary to know where to run)
- [ ] Verilog-A model of logic (to try and speed up simulation)
- [ ] Implement PyTables backend of simulation (for sane logging of data)
    - [ ] Append simulation meta data to results
- [ ] Identify reason for shifted output values
- [ ] Identify reason for non-monotonic sections
- [ ] Understand if monotonic/BSS conversions are properly understood (can we use last conversion?)
- [ ] Implement multiple conversions
    - [ ] Add syntax for repeated bit positions
    - [ ] Generate different capacitor arrays, from params
    - [ ] Generate N-bit sequencer (perhaps Verilog-A, can we remove bus width on top level?)
    - [ ] Figure out correct expresions for multi bit (can we just re-normalize?)
- [ ] Pass parameters to top level .params file, which can be written by python (necessary for multi param runs)