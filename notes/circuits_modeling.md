# Models

- Modeling is the set of deterministic and stochastic, numerical (approximate) and symbolic (analytic), ideas that we use to explain and predict the world.
- Models are built following data observations (normally automatically with computation), system models are composed from building blocks using frameworks like SPICE/TCAD/EM/Signal flow tools.
- Predictions about behavior can be made, either on pen+paper, or on computers. (Both can be can be numeric of symbolic)
- And systems can be optimizatized for a purpose, either using (look at opt types)


# Circuit Theory, Design, Analysis, Optimization, etc

While watching Elad Alon's videos, I came to a realization: Circuit theory is more about analyzing circuits as they are, and not about 'design'. Design is an optimization problem, and I find myself hopelessly overwhelmed by informal/uintuitive methods. I prefer to frame my work as a formal design problem.

Looking at the Sci-ML website, they partition their tools into: modeling, solvers, analysis, and machine learning. Ignoring the latter of theses (partitioned into ), we can focus on the first three:

1. Modeling: Model Languages, Libraries, Tools, Array Libraries, Symbolic Tools
2. Solvers: Equation Solvers, PDE Solvers, Inverse Problem/Estimation, Optimization
3. Analysis: Plotting, Uncertainty Quantification, Parameter Analysis
4. ML: Computery tricks to approximate the modeling, solving, and analysis steps (Function Approximation, Symbolic Learning, Implicit Layer Deep Learning, and Differential Tooling)

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


Compact modeling:

Needs to balance accurate modeling across physical and technology variation, while still remaining mathematically tractable (poisson, stochastic LLG, schrodinger, Boltzmann Transport)

There are basically three types of compact models:

* Macro models, using lumped element circuit devices to mimic device behavior
* Table lookup, {I,Q} = F{L,W,T,VD,VG,VD,VB..}, this is of limited value early in device evaluation
* Physics based analytic model, computationally effici






# The Mathematics of Electrical Engineering

I want to better understand and classify the types of mathematical models that most often arise in electronics, and how they can be classified and solved. This includes stochasticity (arising from measurement error, system noise, and environmental noise), boundaries conditions, linearity/nonlinearity, partial differential equations, etc. Then I will study how numerical methods can be applied to solving the equations.

Remember the difference between numerical (approximate) and symbolic (analytic) solutions. Wow many symbolic manipulations are done on paper, there is actually symbolic computation:

> These distinctions, however, can vary. There are increasingly many theorems and equations that can only be solved using a computer; however, the computer doesn't do any approximations, it simply can do more steps than any human can ever hope to do without error. This is the realm of "symbolic computation" and its cousin, "automatic theorem proving." There is substantial debate as to the validity of these solutions -- checking them is difficult, and one cannot always be sure the source code is error-free. Some folks argue that computer-assisted proofs should not be accepted. 

> Nevertheless, symbolic computing differs from numerical computing. In numerical computing, we specify a problem, and then shove numbers down its throat in a very well-defined, carefully-constructed order. If we are very careful about the way in which we shove numbers down the problem's throat, we can guarantee that the result is only a little bit inaccurate, and usually close enough for whatever purposes we need.

> Numerical solutions very rarely can contribute to proofs of new ideas. Analytic solutions are generally considered to be "stronger". The thinking goes that if we can get an analytic solution, it is exact, and then if we need a number at the end of the day, we can just shove numbers into the analytic solution. Therefore, there is always great interest in discovering methods for analytic solutions. However, even if analytic solutions can be found, they might not be able to be computed quickly. As a result, numerical approximation will never go away, and both approaches contribute holistically to the fields of mathematics and quantitative sciences.

> Although the terms "modeling" and "simulation" are often used as synonyms within disciplines applying M&S exclusively as a tool, within the discipline of M&S both are treated as individual and equally important concepts. Modeling is understood as the purposeful abstraction of reality, resulting in the formal specification of a conceptualization and underlying assumptions and constraints. M&S is in particular interested in models that are used to support the implementation of an executable version on a computer. The execution of a model over time is understood as the simulation. While modeling targets the conceptualization, simulation challenges mainly focus on implementation, in other words, modeling resides on the abstraction level, whereas simulation resides on the implementation level. Conceptualization and implementation – modeling and simulation – are two activities that are mutually dependent, but can nonetheless be conducted by separate individuals

Benefits of simulation:

1. cheaper
2. more accurate, as no environment
3. faster than realtime
4. coherent synthetic environment



## Symbolic regression

is the finding of a mathematical analytic expression which best matches data, using numerical methods:

https://astroautomata.com/SymbolicRegression.jl/stable/


Older

These videos are primarily targeted at electrical engineering students and professionals. When I graduated from my undergraduate program I had been exposed to all the concepts I'll be covering in this video

-When should I be using a Fourier transform vs a Laplace transform in the analysis of a circuit?
-What is the fundemental difference between the equations that arise from circuit with and without non-liner devices?


The purpose of this video series is to develop an understanding of the mathematical techniques used in circuit analysis. This video will not be explicitly analyzing the design or performance of specific circuits.

Given a circuit, the objective of circuit analysis is to find the approximate functions for the voltage and current wave forms/signals. Depending on the complexity of the circuit, the devices present in it, and the tools available to us (pen/paper vs computer), we will see that varying levels of detail in our analysis are possible. After watching these videos, you should be to identify what analysis techniques are necessary/available, by visual inspection of the circuit's elements/configuration.

1) Our first task is to appreciate the limitations of circuit theory. It is important to understand that circuit theory is an approximation of Maxwell's equations, called the 'lumped circuit discipline' is only valid with these assumptions, compare an electromagnetic simulation to the circuit analysis. In general, the smaller the dimensions of your physical devices, and the higher frequency your exciting signal, the worse our lumped circuit model will perform. At a certain threshold, typically in the single digit GHz region for circuit board level designs

This of course depends on your tolerance for error. The more accuracy you demand, the sooner you'll be making that switch 

Electromagnetics is perhaps the best defined/understood fundemental force. Without this appoximation, however, we would never be able to compute. Explain how ideal circuit schematics differ from those meant for for fabrication

2) Linear circuit devices, give rise to directly linear equations. In this model the voltage and current in the circuit instantaneusly would change with the forcing function. In order for this model to be valid, you must keep the forcing function constant or changing slowly. Show how you can solve this on paper with hand solutions (DC opt as well as transiet, if the input is definable by  and also how you can use numerical solutions. Then show how to place in

3) Introduce non-linear devices. Basic square laws. Equations are still quite simple. Yet this still yields incredibly complicated simulations. The main challenge in this case is that the operation of the transistor, across all terminal voltages can not be defined by a single equation. This peicewise definition causes our

4) Differential circuits with energy storage (inductors and capacitors)

Explain that you need to keep rising edges slow for all of this to be valid.

If we start speeding up this circuit with transistors, we start to see non Non-linear differential equations. 

Show a transistion






# Math
There exists a relationship between

Differential Equations
Exponentials		Natural Log	Comple
Laplace transforms
Fourier Transforms	cos and sin
Eigen Functions
Linear Systems of Equations
Eigenvectors and Eigevalues
Linear Algebra


Bui  Linear Combination of Complex Time Exponentials

Holomorphic Functions
Cauchy Riemann @ Differentiability

Notes from Major Prep's Laplace transforms
Laplace transforms are comprised of slices 2D fourier transforms at varying alpha values
Laplace transforms have a region of convergence

If poles are on the imaginary access, then the original function has only sinusoidals
	The values equate to the frequecies of the sinusoidals
	Symmetric about the 
If poles are on the real access, then the 

If you start manipulating the damping and oscilating coefficients in the differential equation, you will be strengethening and weakening the eponential and sinusoidal terms in the solution (system impulse response.) The movement of these poles, to optimise something (rise/fall times, minimize oscillations) I think is the basis of the Root locus plots.

So then what is a dominant pole?

Holomorphic Functions
Cauchy Riemann @ Differentiability



## Computing

Numerical/approximate methods existed before Computer science and programming. Older methods, like analog computers/slides rules are approximate because of error accumulation from mechanical tolerances and electronic noise. And so the methods explored by them accumulate error in a different manner. Digital computers instead accumulate error through quantization. Herein lies the beauty of digital; after conversion, it suppress analog noise/error with noise margin, at the expense of quantization error. Note: Computers drastically accelerate numerical **AND** symbolic methods. Therefore, make sure you don’t confuse numerical(approximate) methods are being the exclusive or sole domain of digital computers. Humans can also do numerical and symbolic computation. (Is analog computation a third type?)


## Euler

Sinusoids, Trigonometric Functions, Trigonometric Identities

Rational Expression: fraction of two polynomials/monomials

Exponents

Logarithms: how many times must $x$ be multiplied by itself to get $y$? i.e. $log_{x}y$

Natural Logarithm

Euler's Formula/Identity:

$$
e^{ix}=cos(x)+isin(x)
$$
For the special case of $x=\pi$:

$$
e^{i\pi}+1=0
$$

Math is the pure study of numbers, symbols, spaces, and geometries. We can apply it for the construction of models, as well as the optimization of systems described and explained by those models. The relevant fields are 

- calculus (vector, multivariable, sequences and series)
- differential equations (ordinary and PDEs, Fourier series is solving 2nd order ODE, basic theory of Fourier series is infinite dimensional vector spaces)
- linear algebra (vector spaces)

On applying mathematics to engineering: https://www.jstor.org/stable/2309339

My primary goal in understanding math is to provide an template for reusable models, optimizations, frameworks, etc. I'm focused on applied math here.

I should delve deeply enough to understand the math I see in my electronics, devices, and physics books. The focus is on my understanding and being able to speak and think in this language.

- Calculus and Differential Equations
- Statistics, Probability, and Randomness
- Linear Algebra
- Optimization


"Math needed for CS:""

1. Boolean algebra
2. Numeral systems
3. Floating points
4. Logarithms
5. Set Theory
6. Combinatorics
7. Graph Theory
8. Complexity Theory
9. Statistics
10. Linear Algebra

A free math/CS book: **Operating Systems: Three Easy Pieces** https://pages.cs.wisc.edu/~remzi/OSTEP/


# Verilog-A

Verilog-A is the analog component of Verilog-AMS, and can be understood by the SPICE kernel in a AMS simulator.


One important thing to know, is that in Virtuoso, if you was a graphical representation of your system, you need to have “SPICE on top”, with the Verilog-A as only “leaf modules.” I think, as least?

`<+` contribution operators assign (and only assign) values/relations to branch potentials or flows.

starting with ` means something is a compiler directive


functions with $ start are not synthesizable?

base units of time, and the time precision are specified like this:

```
`timescale 1s / 1ns
```

It isn't mandatory to use a base of 1 second, but since Verilog-AMS allows SI uni suffixes, we normally stick to this.
The second unit is used for rounding/quantization of the time
And for the output of the $realtime function


Wires:
Must be driven, continous or discrete, continous has a 'discipline' like a voltage/current
'Nets' are wires that move between modules. They can be implicitely created, or explicitely.
Can also be named 'tri' for tristate, and this syntax should just be used to explain that it's a wire that probably can have bus contentions or high-impedance outputs.


Spectre-AMS Course -> about the AMS Designer Virtuoso Use Model (AVUM)

Discipline Resolution and signals crossing A/D domain boundaries
Unified Netlister (UNL) in Virtuoso ADE Explorer w/ Xrun executible
AMSD Flex option allows mixing and matching digital and analog kernels

HED - Heirarchy Editor

AMS Designer simulator can be invoked from either Virtuoso/Spectre or Xcelium

Using the Spectre/Virtuoso option:
Spectre is highly accurate for small designs,APS is for larger designers
Support for Verilog, Verilog-AMS, ANSI-C/C++, and SV Design and Assertion (but no Real number modeling)

SystemVerilog and Verilog-AMS both have support for real number modeling (called real/wreal, respectively). This is faster, but less performant that SPICE or more complex Verilog-AMS models, because real/wreal models don't require 'solvers'. The IO behavior is simply defined by a function, and is evaluted with simple discrete event solver. Therefor it does not behave well for models that involve feedback.

Unified/Commond Power Format (https://www.techdesignforums.com/practice/guides/unified-power-format-upf/)


Spectre AMS connect connects the uniform timestep SPICE/Spectre Simulator with an event based Xcelium simulator.

Spectre AMS Simulator/Design is not just an interprocess communication between two separate kernels, but instead a pair of tightly coupled enginge which access a shared memory storing the state of the circuit during simulation.


Two ways to run AMS Design/Simulator:
1) AVUM for GUI
2) AXUM for command line

In the Virtuoso USe model, config views are used to select the cellview for each cell.

normal: ac, dc, noise sp, stb, xf, tran
hb:     ac, noise, sp, stb, xf
p:	ac, noise, sp, ss, stb, xf
qp:	ac, noise, sp, ss, xf

the hb, p, and qp analysis flavors aren't available in AMS Designer

## Digital Simulation

modelsim
questa
nc-sim
xcelium (most modern from Cadence?)

some are use by fpga
cocotb used questa with bdaq

vivado uses modelsim?

synonpsys uses another?

## Hierarchical Structures

Hierarchical structures are a Verilog concept that allow interconnection of modules at different levels of hierarchy. This is essentially the same function as the netlist but defined within a Verilog-A module.

In this phase-locked loop example, all modules and the top level module interconnecting them are in the same file. However this isn't necessary and it is possible to have each Verilog-A module in its own file. In this case a .LOAD statement must be included in the netlist to load all Verilog-A module accessed in the instance statements

#### The main two uses for a AMS language are simulation and synthesis

But the latter isn't really possible with Verilog-AMS. The prior though can be broken down:

1. To model components: Unlike traditional SPICE simulation libraries which only support a limited number of devices, model SPICE simulators which support Verilog-AMS can describe 
   1. Basic devices (R, L, C)
   2. Compact models like Gummel-Poon BJT, VBIC BJT, Mextram BJT, MOS3, BSIM3+4, and EKV MOS. BSIM4 is written in a bunch of C files. BSIM-Bulk, the newest version of BSIM is instead a single Verilog-A model.
   3. Functional blocks like ADCs, de/modulators, samplers, filters, etc
   4. Multi-disciplinary components such as sensors, actuators, transducers, etc.
   5. Logic components
   6. Test bench components like sources and monitors?
2. To create testbenches: testbench devices will often not be ideal, so this is perfect for Verilog-A
3. To accelerate simulation: replacing non-examined blocks in each simulation with a more abstract representation. In end, this is part of the testbench, as the  
4. To verify mixed-signal simulation
5. To support the top-down design process


# Spice and BSIM

Digital IR drop, power domiains, timing closure

Level 1 16 params, bsim6 has 1200

Additions beyond the core spice:
Fast spice
Simulation corners and Monte Carlo
Extraction




15.4.2 batch versus interactive mode
.meas analysis may not be used in batch mode (-b command line option), if an output file (rawfile) is given at the same time (-r rawfile command line option).


recall there a two design pattern for Simulations

Either you Create a `Sim` object immediately
s = Sim(tb=MyTb)

And add all the same attributes as above
p = s.param(name="x", val=5)


Or you create a Sim class, and then decorae it with the @sim function, to get an object.

I want to have an object, and I wnat to know what can be put inside the .save() attribute.

So I shoul look at the class definition.

It has a `attr`, which is a list made from `SimAttr`, which in turm is a Union of

```
SimAttr = Union[Analysis, Control, Options]
```
And I'm interested in the control element

## Spice-Sim Attribute-Union
Control = Union[Include, Lib, Save, Meas, Param, Literal]:

This finally leads us to:

```
class SaveMode(Enum):
    """Enumerated data-saving modes"""

    NONE = "none"
    ALL = "all"
    SELECTED = "selected"


# Union of "save-able" types
SaveTarget = Union[
    SaveMode,  # A `SaveMode`, e.g. `SaveMode.ALL`
    Signal,  # A single `Signal`
    List[Signal],  # A list of `Signal`s
    str,  # A signal signale-name
    List[str],  # A list of signal-names
]


@simattr
@datatype
class Save:
    """Save Control-Element
    Adds content to the target simulation output"""

    targ: SaveTarget
```





# ML optimization

From Infineon's anagen program

## Schematic optimization

there's not one best design, as there are multiple objectives. This is a parento front problem.
We use evolutinary algorithms, which is a stochastic optimization algorithm
This is sample inefficient, and simulation has high sample cost
Gaussian processes vs baysian optimization
Baysian isn't true multi object model -> it compresses to a single point

evalution methods used: constraint violation (how far away violating the constraints), alternative hypervolume

GDE3, MODEBI, MACE, EBO (evolutional baysian optimization)
3 of these use machine learning models (surrogate only)

GDE3 is common standard, MACE is another publication,o

## Layout optimization

Analog layout ML optimization:
Slicing: floorplan from repetiviely currting the floorplan in horizontal and vertical slices (normalized polish expression)
non slidcing: The opposite. Implemented by non-sequeunce pair algorithm

Key optimization algorithms:
Simulated annealing: stochastic optimization, using hill-climibing approach. Non-zero probability of moving from one local minim, to another, better one. Hopefully global.
Reinforcement learning: agent interacts with environment, and gets reward. Super sample inefficient.
evolutionary algorithm
integer linear programming
Graph neural netowork: a graph placement methodology for fast chip design. Mirhoseini, et al. 2021.

Analog routing ML optimization:
Most common/basic method: A* search, pathfinding algorithm.*
Pattern routing: predefine patterns of wiring. L-shaped (one bend) Z-shaped (2 bend)
To space apart, estimate congestion.
Then use rectilinear steiner minimum tree.

Papers: Liao 2019, 2020: Global and local routing algorithms, using Deep neural networks

In conclusion: stochastic methods like SA for floorplans, graph pathfinding like A-star search for routing


# Statistics

Concerning the collection, organisation, analysis, interpretation, and presentation of data. The opposite of mechanistic modelling. Used to learn, describe, and predict the behaviour of systems after empirical data has been collected. Statistical or correlation studies often bypass the need for causality and focus exclusively on prediction, and not mechanistic explanations of “why?”. As most data is computer generated (Ninety per cent of the world's data have been generated in the last 5 years), these methods are often closely intertwined with computer algorithms. Permutations and combinations, allow us to work with simple discrete known populations and directly calculate probability from it. Random variables. Intersections and unions of sets. Multiplication rule. Bayes’ theorem, the central limit theorem and the law of large numbers, co-variance and correlation, and maximum likelihood estimation (MLE). Probability density functions and cumulative design functions

# Jitter Modeling

'Understanding and Characterizing Timing Jitter' - Primer by Tektronix

* Jitter is short term variation w/ frequencies above 10 Hz, other it is called "wander"
* Must be characterized w/ statistics (mean, standard deviation $\sigma$, and confidence interval)
* High pass filter is useful for physical measurement, to cancel "wander"
* This can be a PLL, which is "nice" because it mimics a real system
* Ideal sinusoid is ideal reference, most often (with same freq. and $\phi$), found via min $\Sigma(error)^2$

$$
A*\sin(\omega_c*t+\phi_c)
$$

where $\omega_c$ and $\phi_c$ are constants chosen to minimize timer error of positions.

## Sampling

Samples in the measurement of jitter can be acquired in three way:

1. Periodic Jitter $J_p$ : Just a histogram of signal periods of a persistent period, measured often in persistence mode (trigger on one edge/peak of waveform, and then measure 'width' on the subsequent edge/peak)

3. Cycle-to-Cycle $J_{c2c}$: First order difference of period jitter, which show dynamics from cycle-to-cycle, for a PLL, etc

$$
J_{c2c}=J_{P_{n+1}}-J_{P_{n}}
$$

3. Time-Interval Error (TIE): uses deviation from ideal reference. Difficult to observe directly with oscilloscope in experimental setup, but is good as it reveals cumulative effect of jitter

$$
TIE_n = \sum\limits_{0}^{n}(J_{p_{n}}-t_{ideal_{n}})
$$

where $n$ is the cumulative edge number, in time. The more cycles go by, the further we will likely find ourselves from the ideal

## Jitter Statistics

Mean of the distribution is the reciprocal of the frequency of the signal.

Next, regardless of which method you use to measure timing error, the statistical PDF can either be characterised by it's standard deviation (RMS), or by a more stringent metric tied to a BER. For example, 68% percent of distribution is within one standard deviation, but a BER of 0.32 would be unacceptable, so

$$
J_{pp} = α * Jitter_{rms}
$$
The reason for this peak-to-peak concept is that Gaussian random processes technically have an unbounded peak-to-peak value - one theoretically just needs to take enough samples.

|BER|α|
|---|---|
|10-3|6.180|
|10-4|7.438|
|10-5|8.530|
|10-6|9.507|
|10-7|10.399|
|10-8|11.224|
|10-9|11.996|
|10-10|12.723|
|10-11|13.412|
|10-12|14.069|


## Random vs Determinisitc

The convolution of random data with a deterministic waveform jitter, will create a non-gaussian PDF. For example, in a system with different rise and fall times, the PDF will be Bimodal:

![](img/jitter_pdf.png)

It's instead convolved with a sinusoidal waveform, then you will have a normal area in the middle, with sharp rising gaussian components on the edges.


# Signal Sampling Theorem

Whittaker-Shannon-Nyquist sampling theorem says there is no info loss when digitizing band-limited analog signals, if sampling rate is at least twice that of highest frequency in the signal.

The sampling theorem is worst case though, as it assuming that highest frequency is always present.

> Recent developments in alternative sampling schemes such as compressive sensing [6], finite rate of innovation [7], and signal-dependent time-based samplers [8]–[10] are promising. These approaches combine sensing and compression into a single step by recognizing that useful information in real world signals is sparser than the raw data generated by sensors. The focus of this paper is on processing of pulse trains created by a special type of analog to pulse converter named integrate and fire converter (IFC), which converts an analog signal of finite bandwidth into a train of pulses where the area under the curve of the analog signal is encoded in the time difference between pulses [10]. The IFC is inspired by the leaky integrator and fire neuron model [11]. It takes advantage of the time structure of the input,enabling users to tune the IFC parameters for sensing specific regions of interest in the signal; therefore, it provides a compressed representation of the analog signal, using the  charge time of the capacitor as the sparseness constraint [12]–[14].

The key idea here is designing a sampling and compression scheme which are integrated together, and tailored to the signal of interest. The quote "approaches combine sensing and compression into a single step by recognizing that useful information in real world signals is sparser than the raw data generated by sensors."


Looking at a pulse signal, we can imagine that there is some algorithm that given a list of samples 

[Online vs offline algorithm implementations.](https://en.wikipedia.org/wiki/Online_algorithm)

If we want to know the area under the curve of a pulse (and the time that it arrives, but we'll address that later) what is the most efficient 'online' scheme for sampling it, if we don't know it's time of arrival. We need to minimize output data for a given desired precision, and make sure we can reject false positives coming from noise.

We can assume an output bandwidth per chip of around 5 GHz, in the highest hit rate sections. That corresponds to around 3 GHz per cm^2.