# Scope

Understanding of chip scale electronics, including sensors, circuits, and the microwave design theory needed to characterize IO.

But this repository needs to be build with a purpose: Designing a PLL and VCO front end in 28nm/65nm + teaching/designing the lab component of a detector signal processing course.
This repo isn't my research, but instead serve as a supporting repo for all the prerequiresit background knowledge and theory needed to be productive in the field.
Knowledge should be partition by theory/discipline, and application.
This repo makes the assumption the reader is familiar with: physics (devices, particle, EM), math (calc, stats, linear algebra, DEQ, optimization), and computing (programming, Unix).

*Put differently, this is all the stuff I won't talk about in my Thesis, as it's out of scope. Explaining it would make my document too large.*

# Modeling Disciplines

*Note: (try to think of just what's written in equations on the page, anything beyond that is more application than theory)*

Review of widely applicable, generalizable and composable models/theory used in electronics engineering.

*Put differently, this is material that should only appear in the first chapter of my thesis, if at all. I need to arrange and pick the information that is necessary to 'drill down', such that chapter two can start applying the theory to the system of interest.*

[Devices](./devices.md) Built on semiconductor physics and EM, from junctions to useful devices, i.e. MOSFET, PIN diode, detectors. Ending with accurate bu complicated non-linear models of devices. Don't forget to also build models of basic inductors, capacitors, and resistors. Describe basic nanofabrication process and result. Make sure to describe limitations, including noise and distortion temperature and radiation damage on these devices. For more accuracy, explain computational simulation: FEM, process sims, dynamic charge sims, etc.

[Lumped Element Circuits](./circuits.md) Looking at devices, use assumptions like small signal, low frequency, opt point, small dimensions so ignore propagation time (but not too small), to linearize. Starting from Ohm's law, KVL, KCL, L+C equations, Nodal and Mesh, Circuit reduction, Open/Short circuit tests, AC circuits and phasors, work to time and frequency domain representations of circuits. Not sure if the laplace transform should be covered here. Also, I feel that 'Op Amps' are outside the scope.

[Distributed Element Circuits](./microwave.md) Don't go into this really at all, for now, as it's tangential. Microwave and Optics Primarily useful for knowing when lumped element and linear electronics breakdown. Waveguides, transmission lines, etc. Also not applicable to quantized particle models. Distributed Circuits Models (due to ratio of wavelength to circuit dimensions, wave propagation time can't be ignored). Used in Microwave and Optics, etc. S-parameters. Z-Parameters. Waveguides, coupled lines, stubs, cascaded lines, impedance discontinuities, power divider, filter, circulator, active amplifiers.

[Digital Circuits](./digital.md) Give extremely light weight introduction to INV, NAND, NOR (no noise margin, rise/fall/ or loading) perhaps with propagation delay and setup/hold time added. Noise margin eliminates noise. Logic gates, expressions, truth tables, state machines, combinational and sequential, Kanaugh maps. Meely and moore state machines. Can use HDLs. Critically, don't start getting into any sort of cell design or loading concepts.

[Signal and Systems](./signals.md) - Linear Continuous/Discrete Time-Invariant systems. An extension/abstraction of lumped element and digital circuit theory. Voltage and current are  normalized to abstract inputs and outputs. No concept of operating point (addressed only in non-linear systems/control theory). S-Domain/Laplace transform, Dirac delta, is covered. Filters, feedback, state space. For discrete LTIs, abstraction of digital, assuming prop delay and other timing violations won't be an issue.

# Design Application:

This is where we apply general theory to the specific application, to solve and formalize the problem of interest. This should be inline with my thesis statement:

> 'Time-based processing feasible and useful for pulse-based signals in radiation detector.'

*Note: I don't want to talk about ATLAS, Belle, CMS, etc really at all. I also don't want to talk about particle physics. I just want to explain the signals that are being processed, the information that needs to be extracted, the design constraints, and then walk through the process of explaining when time-based processing would be a good choice, and how one could design a circuit implementing such a scheme.*

Chapter two should generalize the problem, comparing various applications/implementations of pulse signal processing elemectronics, and show where and why they are located on the design space.


At the macroscopic systems level, most blocks can't be properly defined by any one of these models alone. This is because of various sources of nonlinearity, noise, and time-variance. For example:

- ADCs and DACs are often wildly nonlinear, and so have various specs like INL, DNL, gain error, offset error, etc.
- RF blocks will have Noise Figure (NF), IP2, IP3, etc to characterize power saturation (gain compression, not tied to frequency, and IM2 and IM3 which are intermodulation for harmonic distortion.
- PLL will have phases noise, jitter, etc.
- Pixel detectors have ENC, time walk, dead time, etc!

Notice also here how once the word "design" enters our vocabulary, we are implying that optimization and constraints are overlayed on top of our models, to allow us to make decisions.

In short though, this is the material that needs to be built in conjunction with real simulations, but isn't my actual "research contribution". They are applications of basic models, which I need to learn by heart in order to do anything original. It's also useful as the scope of what I could teach in a course.
