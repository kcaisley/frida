# Circuit Theory, Design, Analysis, Optimization, etc

While watching Elad Alon's videos, I came to a realization: Circuit theory is more about analyzing circuits as they are, and not about 'design'. Design is an optimization problem, and I find myself hopelessly overhwhelmed by informal/uintuitive methods. I prefer to frame my work as a formal design problem.

Looking at the Sci-ML website, they partition their tools into: modeling, solvers, analysis, and machine learning. Ignoring the latter of theses (partitioned into Function Approximation, Symbolic Learning, Implicit Layer Deep Learning, and Differential Tooling), we can focus on the first three:

1. Modeling: Model Languages, Libraries, Tools, Array Libraries, Symbolic Tools
2. Solvers: Equation Solvers, PDE Solvers, Inverse Problem/Estimation, Optimization
3. Analysis: Plotting, Uncertainty Quantification, Parameter Analysis
4. ML: Computery tricks to approximate the modeling, solving, and analysis steps

Now, I shouldn't take these as the 'holy grain' of mapping out the field of applied maths, but I think that these partititions are something I hadn't really thought through before.

Note how Optimization is part of the 'solvers' section. It's a different type of problem though. You aren't simulating a given system, with fixed parameters, to find the response, you are detailing a 'cost function' which formally specifies what you want to have as the output, and then changing the system parameters in order to best minimize the cost function. What's interesting is that if the system is simple and has 'one output', then the cost function to minimize is the function that models the system itself. However, if there any many outputs, then it's up to the user to 'overlay' a synthetic cost function to be minimized, which compresses all the outputs down to a single parameter to minimize.

## In the past

In the past, I believe the thing I've struggled with the most is design, not the 'analysis' part of circuits. Design is an optimization problem, and I find myself hopelessly overhwhelmed by informal/uintuitive methods. I prefer to frame my work as a formal design problem. This is what PhD students should be doing.

# My interests

I'm realizing that I'm very interested in the intersection between electronics design, computing, numerical methods, mathematic (analytic) and stochastic modeling, (the intermediate simulation step), mathematic and statistical analysis, and the wide world of optimization. I'm not particularly interested in manufacturing real systems on any fast time scale. I still want to work in a applied sense, but with long lead times, for high confidence in the design space, decisions, and process. I love documentation, not rushing, and understanding what I'm doing. I take great pleasure in going slowly.

# Spice, schematics, and mathematical modeling, analysis, and optimization

When you draw a schematic in EDA software, you are essentially defining the arrangement of a system model but you aren't speciying everything. For example:

1. You aren't specifying the device model, or other macro models. These are provided by vendors or by yourself, and may range in complexity from simple V=IR for an ideal resistors, to sophisticated numerical models, and even idealized digital circuits with only discrete outputs (macro models). This is tightly coupled to the simulator. Often models will only work for a certain type of analysis (i.e. needing RF transistor models for high-frequency AC). One important type of simulation is embedded noise statistical analysis. Mathematical and statistical modeling occurs simultaneously and can be very difficult.

2. You aren't specifying the simulation type/evaluation type. These can range from transient numerical simulations all the way to symbolic solutions of problems that are reduced in complexity and can be evalutated analytically.

3. You aren't specifying the stimulus to the circuit. This can be tightly coupled to the simulation type and model type, like with (maybe symbolic) linear/small-signal AC analysis, or it can be less coupled, like in the case of a numerical transient simulation, where you are free to input arbitraty time-domain (sampled) waveforms (as long as they don't change too fast relative to the simulation time step.

4. When you complete the schematic, it may be exported as a netlist in the case of most numerical simulator, of if you're working with your own simplified toy model, it maybe be evaluated analytically be hand or by simple feedforward numerical calculation (if the system is linear and time-invariant).

5. An intermediate step which must be completed is a layout generator, which produces a DRC valid layout from a template and transistor sizes, and then which extracts it to get a more complex (but same class) PEX netlist for simulation. This generator is necessary for trusting our models, but isn't needed for every optimization setp.

### Next Steps (Analysis and Optimization)

6. Once you have a mathematic model which is generalizable across different types of simulations, you need to create a parameterizable workflow where you can check this feedforward simulation against many different factors like choice of device sizing, process, voltage, and temperature variation, local and global device mismatch, radiation damage, etc. These may not be part of core simulation routine, but must be accounted for during optimization.

6.5: One high level type of analysis is 'sensitivity analysis'. This can be classfied as a [invers problem approach](https://en.wikipedia.org/wiki/Inverse_problem)

7. Finally, the top level is optimization. There are many kind of optimization, including Mathematical(linear programming, non-linear programminag, mixed integer, semidefinite, conic, etc) and Baysian statistical optimization (which is very sample efficient, and good in cases of treating the inside as a black box.) The systems to be optimized can be discrete/continuous, singular or multi-variable, constrained/unconstrained, static/dynamic (time-varying?), and deterministic/stochastic.). The way an optimization problem is posed is therefore very importantto how it is solved, and also relates to 

8. NOTE: While optimization is the top level routine, that doesn't mean it only occurs on the top level parameters. Low level blocks can be modeled and optimized (and SHOULD in most cases) before moving to high level blocks. This helps improve one's understanding of the block itself, and understand the limitations of it's construction.

This [course](https://web.stanford.edu/group/sisl/k12/optimization/#!index.md) explains in detail a lot of optimization concepts.

9. Another note: Notice how there is a transition between system modeling, system solving, and analysis, and then finally optimization? This parallels what we see on the [SciML](https://docs.sciml.ai/Overview/stable/overview/#overview) page. I'm primarily working at the analysis and optimization stage, but I want to understand how the prior two work as well.



# Circuit Modeling

Analog work-group 
April 18, Sadayuki Yoshitomi

In the tape out stage, we are increasingly needing large design margins at high speed, as real silicon is far from actual PDK models.

PDK models are correct in the sense that they are extracted from Si during development, and yet why do designers claim SPICE models are inaccurate?

![image-20230418181857736](image-20230418181857736.png)

There are many different ground-source-ground (GSG) test structures used for calibration of the different properties of the devices, including

1) dielectric constants/well resistance
2) metal conductivity
3) fringe capacitances/metal
4) fringe capacitances/ via

![image-20230418183246467](image-20230418183246467.png)



Compact modeling:

Needs to balance accurate modeling across physical and technology variation, while still remaining mathematically tractable (poisson, stochastic LLG, schrodinger, Boltzmann Transport)

There are basically three types of compact models:

* Macro models, using lumped element circuit devices to mimic device behavior
* Table lookup, {I,Q} = F{L,W,T,VD,VG,VD,VB..}, this is of limited value early in device evaluation
* Physics based analytic model, computationally effici
