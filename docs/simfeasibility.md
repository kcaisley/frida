## Simulation feasibility:

Each measurement of the ADC requires rougly:

20 waveforms * 1000 time steps * 8bits per sample = 160,000 bytes

A 12-bit ADC, requires for mismatch roughly:

4096 levels (aka bins) * 20 samples per bin * 1000 MC runs for cap mismatch = 81,920,000 runs

A single sample and convert function took 0.000109 seconds.

Therefore we can calculate the total time to be:

81,920,000 runs * 0.0001 second = 9011 seconds, or 2.5 hours, not including overhead of analysis, saving data etc.

But these runs would produce: 81920000*160000/1e9 = 13100 GB, or 13.1 TB.

The overhead of initilizating the simulation is likely large, for both my behavioral SIM and also SPICE, so a better method is to run through the simulation all the way across the input range of the ADC. In this case, we'd run 1000 runs, each with a time of 8.2 seconds. Each run would then produce 20*4096*160000 = 13.1GB data file.