## Tasks

In direct pursuit of the above research question.

- [x] Verilog-A model of comparator
- [x] Replace active input with passive
- [x] Replace re-analog with external block
- [x] Verilog-A model of vstepping input voltage
- [x] Fix Spectre compatibility (necessary for multi machine runs)
    - [x] Replace waveform sources with either VA or SPECTRE supported AnalogLib parts
    - [x] Benchmark SPICE vs Spectre, profile CPU
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
- Figure out the expression for what input signal swing is, depending on total capacitance and parasitic capacitance!

### Run plans:

SPICE comparator characterization
SPICE 8 bins of ADC for comparison, just binary 8-bit to verify noise at tripping points

behavioral simulation of ADC which compares different bit combos and values:
	8 steps binary
	12 steps binary
	12 steps non-binary
	12 steps


Chip submission
Deadlines for PhD
Taking courses in optimization

Questions:

How do I optimize the weights of the capacitors?
How do I model the noise of the capacitors? (cap noise, area, power, and switching noise)
How can I model


Other assumptions:
networks are only composed of units caps, with monotonic switching
No modeling of clock-feedthrough / kick-back, discharge from leakage

We will compute area, power and ENOB for different configs
We calculate ENOB as a degradation above the quantization eror calculated from the non-linearity + base QN

Now how do we will out the capacitors?
Do I start from a total or unit capacitance?

Note that the