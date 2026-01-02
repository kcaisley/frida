I'm trying to plan ahead, and decide if SPICE it sufficient for testbenches, or if I really need the full Verilog-A functionality for testbenches. Here are the blocks for which I need to make test benches. Not that when I say 'to calculate', the actual calculation will be done in Python, but the stimulus needs to original from either spice or verilog-A.

1. Sampling switch: Will apply a stepping input, at 10 different input voltages, and check the Rds (which causes V error), Drain capacitance, and charge injection, and sampling delay. At each input voltage step we repeat 20 times to measure sampling noise. Then at the end of the test we turn off transient noise, and switch to a transient sinusoidal input which runs at 10 Mhz, 100Mhz, 200Mhz, 500Mhz, and 1Ghz, to measure the bandwidth of the switch (SFDR) so we can know the sampling time required for a certain n-bits of the device, as well as check to make sure the hold-mode feedthrough isn't too severe (characterized as amplitude in uV vs input frequency) Lastly, this will be wrapped by a spice MC top level run, which does 20 runs to measure variation due to mismatch.

2. Several custom digital logic gates: Will apply some digital signals, with transient noise enabled, to the logic inputs (eg INV, NAND, NOR, and some flip-flops) to calculate the jitter, setup/hold time, and propogation delay of cells. This is wrappped in a spice MC top-level sweep, which again lets device parameters vary, which will mainly be used to estimate timing varition caused by device mismatch.

3. Capacitive DAC with driver switches: Need to apply a set of digital control codes, and then monitor the voltage and charge on the various nodes of the network, to characterize the CDAC capacitance (both design and parasitic) and subsequently calculate the total power consumption, power supply noise sensitivity, linearity, and settling time. This is wrapped in a spice monte-carlo top-level sweep of 20 runs, which vary the capacitors using a stats block.

4. Comparator: Similar to the sampling switch, we need to apply in fixed static steps, 10 differential inputs, at 5 different common mode inputs. And perform 20 repetitions of the reset-compare cycle at each combination, to measure the input referred noise for various common mode inputs, power supply sensitivity, and kickback onto the sampling capacitnace. This is wrappped in a spice MC top-level sweep of 20, which again let's device parameters vary, which will mainly be used to estimate mismatch caused input referred offset.

5. Transimpedance amp:
Will apply DC current steps at 10 input levels to measure transimpedance and offset, 
then small-signal AC current sine waves at 5 frequencies (100kHz, 500kHz, 1MHz, 5MHz, 
10MHz) to measure bandwidth and gain via FFT post-processing. Finally runs long 
transient (100μs) with noise enabled to extract output noise PSD, input-referred 
noise density, and integrated RMS noise. Monitors output voltage, input voltage, and 
supply current throughout to calculate DC transimpedance, AC transimpedance vs 
frequency, 3dB bandwidth, GBW product, power consumption, and noise metrics across 
the signal bandwidth.

6. single-ended-to-diff converter amp
Will apply DC voltage steps at 10 input levels with fixed common-mode to measure DC 
differential gain and output swing, then small-signal AC sine sweeps at 5 frequencies 
(100kHz, 500kHz, 1MHz, 5MHz, 10MHz) to measure differential gain, bandwidth, and 
phase response via FFT. Additionally sweeps common-mode input across 5 levels to 
measure common-mode gain and CMRR, and injects AC noise on supply rails at the same 
5 frequencies to measure PSRR. Monitors differential outputs (VSOP, VSON), input, 
common-mode reference, and supply rails to calculate differential gain (dB), 
bandwidth, phase vs frequency, CMRR, PSRR, slew rate from step response, and 
settling time.

Can the testbenches for these all be implemented with pure SPICE? Some of the waveforms for the TIA, for 
example, would need to be a rather complicated PWL file with 10 or so different level



The current 


subckt = {
    'name': 'samp_tgate',
    'ports': {'in': 'I', 'out': 'O', 'clk': 'I', 'clk_b': 'I', 'vdd_a': 'B', 'vss_a': 'B'},
    'devices': [
        {
            'name': 'MN1',
            'type': 'nmos',
            'pins': {'d': 'out', 'g': 'clk', 's': 'in', 'b': 'vss_a'}
        },
            'name': 'MP1',
            'type': 'pmos',
            'pins': {'d': 'out', 'g': 'clk_b', 's': 'in', 'b': 'vdd_a'}
        }
    ]
}


Sweeps can parameterize the dimensions and types of the 

The json can completely describe a netlist, whether it's for a test bench or device, or heirarchical netlist. There's no true disctiontion between a template netlist or a finished netlist. The only difference is what detail is contained.


1. Some circuits only have a single topology, and so can specify the netlist inline. Other's have some form of parameters (in-line), which generates different templates returned as a list. This section must define a subckt

The next step is 


4. The last step is technology specification. This step fill in the vdd levels, (maybe load capacitances), 

Finally a parser can create the text output, based on the final json. This json must parse back-in as the final data structure, so that 







