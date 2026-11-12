# Thesis outline (draft, 2026-11-12)

The thesis is about the electronics: how small a converter of a given resolution and speed can be
made, and how to find that design by optimization across circuits, layouts and process nodes. The
imaging application comes first, once, and only to set the targets: resolution and frame rate from
the physics, area and power from the way the readout is built and packaged.

## 1 Applications (`applications.md`)

From the physics to four numbers: resolution, conversion rate, area and power per converter.

1. Frame rate is time resolution: 4D-STEM, CW-FEL and synchrotron X-ray imaging, stroboscopic and in-situ EM
2. Counting and integrating pixels: hit rate against fluence, pile-up against levels per frame; why multi-bit
3. Sensor and readout arrangements: monolithic and hybrid, interconnect and pixel pitch
4. Where the converters go: pixel-parallel, column-parallel and periphery conversion, multiplexing
5. Budgets: aggregate rate and channel count, power density and cooling, area per converter, data off-chip

## 2 Analog-to-digital converters (`adcs.md`)

The field broken down, the architectures, the survey that points to SAR, and the specification derived from Chapter 1.

1. Metrics: resolution and ENOB, energy and the Walden figure of merit, area and sampling-rate density
2. Architectures: flash, single-slope, SAR, pipeline, pipelined SAR, delta-sigma, time-based
3. Survey of architectures and process nodes, with area added to the comparison
4. Why SAR: resolution–speed fit, compactness, dynamic power, multiplexing; where area goes (CDAC, comparator, logic)
5. Specification, derived from Chapter 1, and the earlier detector ADCs it builds on

## 3 Design space and optimization

How the smallest design is found rather than hand-picked.

1. Block decomposition and the characterization pipeline (netlist, simulation, layout, extraction, post-layout simulation)
2. Objectives and constraints: energy, noise, area (floorplan, not gate area), per-resolution bounds
3. Search across sizes, topologies and process nodes (180, 130, 65, 28 nm)

## 4 Sampling switch

On-resistance and bandwidth, kT/C noise, input-dependent settling; area against settling error.

## 5 Dynamic comparator

Architectures, noise, offset, metastability, kickback; energy-optimal designs per resolution and their area.

## 6 Compact capacitive DAC

Capacitor styles and density, unit-length and difference capacitors, mismatch, switching scheme, drivers; the dominant area term.

## 7 The complete SAR ADC

Redundancy and calibration, timing budget, system noise and linearity, power; area of the assembled channel.

## 8 Layout generation and verification

Placement, routing and assembly with open tools across PDKs; DRC, LVS, extraction; dense tiling.

## 9 FRIDA-1: a 65 nm prototype and its measurements

Implementation, DAQ, sampling, comparator, CDAC, linearity, noise, rate, timing optimization.

## 10 FRIDA-2: the revised design

What the measurements and the optimization changed.

## 11 Conclusions

Area reached against the survey; what scales to finer nodes; open problems.
