# Lesson: A taxonomy of Electronics

Start with questions. How many of you:

FPGA. ASIC. Mixed Signal. VLSI. CMOS, HDL, SPICE, RFIC, RF, Combinational logic,

Passive vs active. Discrete va monolithic.

Overview and Scope of this conversation: What I want to help you understand. We’ll do it with no math. What we’ll ignore.

Paradigms, abstractions, disciplines. The fork between analog and digital. Symbols imply representation/model, model implies underlying maths.

A basic example: Common Source Amplifier?
Symbols, math, language, design method

A basic example: CMOS OR gate? INV? FF?
Symbols, math, word choice, design method

A combined example: Analog circuit into digital. Probably amplifier into inverter into flip flop.

Increasing levels of complexity/integration. Taking an example chip (RD53A?). 

———

I’d like to break down and categorize the ways in which we think about circuits. I want to provide a bit of historical context (mechanical switches, vacumm tubes, older transistors, and BJTs) and a bit of introduction to the fact that MEMS, microfluidics, integrated optics, integrated magnetics, antennas, photodiodes, and detectors, bio sensors, all exist as well. Pretty much any thing you can image can be ‘integrated’ on a chip. But for todays discussions we are going to restrict ourselves to:

- Basic ELECTRONICS devices. Transistors, resistors, capacitors, and inductors (sparingly, as they are large). In most systems, 

- Devices that can easily be integrated on a chip. So no power FETs, large inductors, super caps, etc.

- Devices as they stand today. (hasn’t and won’t always be this way)

Note: For a more complete introduction to these, I think would be to move chronologically, showing the progression of these devices, from their ancestors, and explain how they each devices has been refined, and customized for different purposes.






Don’t forget:

- Paradigms: when is what math used? Include discussion how frequency works.
- Design methods, leading from the math, there are different methods for designing. For analog, somebody figures out, from the math, what functionality they need. They draw the diagram, and run a simulation. And then they draw the physical implementation. Digital can be done exactly the same way. However, the sheer number of devices we can fit into a space, combined with the fact that these circuits are very repeated, means we can take advantage of automation.
- Abstraction and complexity: What diagrams are used to describe it? What language do we use? Cutoff frequency, gain, noise vs data rate, bitwise addition/multiplication, logical OR/AND, register, clock cycle, 
- Show the physical implementation: Notice how they look very similar?

- Physical packaging adds a layer of complexity on top, as it often doesn’t conform to the boundaries of mathematical/system abstraction.

- Should I discuss power vs signal processing circuits? Yes, I think so. As physicists, your main user of electronics will be in measurement and control in your experiments. However, not all features on a silicon chip are there because of signal processing. For example, consider LDOs, or decoupling caps, or ESD diodes, or calibration circuits, clock generators, clock distribution, configuration registers.

When do these abstractions break down?

When things become fast, big, performance critical, inteleaved with/connecting to, other domains.


Remember: Everthing is a model. All models are wrong. Some are useful. You can always examing something in finer detail, or from a different perspective. But you must keep your model tractable for human minds (and computers)!

Remember: You should use abstractions, even the pros do. But you must know know when your abstraction breaks down.

Addendum: RF design is a family of analog design where you think in the ‘frequency’ domain, as signals aren’t at baseband, and typically you’re modulating periodic signals. Not pulse based signals.


What are these words? What are these symbols. What are these diagrams. What are these disciplines and mode

Vertical axis is model abstraction level.

All models are wrong, some are useful, some of the time.

How do we determine the usefulness?

Symbolic and numerical tractabillity. (how much human and or human power/time do we have?)


Complexity (infer integration, and tools)
model (driven by appliction/fuction)


How fast, power consuming, old, hot, large/small complex, and how operating are the devices in these systems?
