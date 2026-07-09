# SPICE Simulation Runtimes

Rough wall-clock costs for FRIDA ADC simulations (TSMC 65 nm, Spectre 24.10, asiclab003).

A PEX-extracted transient with no noise (154.88 µs sweep, 121 ADC conversions) takes about 1h 25m wall time — roughly 33 wall seconds per µs of simulated time, or 42 seconds per conversion. The equivalent transient-noise PEX run takes 22h 22m — roughly 520 wall seconds per µs, or 11 minutes per conversion. Transient noise is about 16× more expensive than a noiseless PEX sweep.

As a rough rule of thumb: budget ~30 wall seconds per µs for PEX noiseless transients, and ~500 wall seconds per µs for PEX transient-noise. Schematic-level runs (no parasitics) are much cheaper — a comparator transient over 11 µs finishes in ~12 seconds, and a small delay sim over 36 ns finishes in ~1 second.
