# Summary

Electronics design is based on modeling + solving/optimization + analysis, just like most fields of engineering and science

# Overview

While watching Elad Alon's videos, I came to a realization: Circuit theory is more about analyzing circuits as they are, and not about 'design'. Design is an optimization problem, and I find myself hopelessly overwhelmed by informal/uintuitive methods. I prefer to frame my work as a formal design problem.

From [SciML](https://docs.sciml.ai/Overview/stable/overview/#overview) :

1. Modeling: Model Languages, Libraries, Tools, Array Libraries, Symbolic Tools
2. Problem Solvers: Equation Solvers, PDE Solvers, Inverse Problem/Estimation, Optimization
3. Analysis: Plotting, Uncertainty Quantification, Parameter Analysis
4. ML: Computery trickery to approximate the modeling, solving, and analysis steps (Function Approximation, Symbolic Learning, Implicit Layer Deep Learning, and Differential Tooling)

Now, I shouldn't take these as the 'holy grain' of mapping out the field of applied maths, but I think that these partititions are something I hadn't really thought through before.

Note how Optimization is part of the 'solvers' section. It's a different type of problem though. You aren't simulating a given system, with fixed parameters, to find the response, you are detailing a 'cost function' which formally specifies what you want to have as the output, and then changing the system parameters in order to best minimize the cost function. What's interesting is that if the system is simple and has 'one output', then the cost function to minimize is the function that models the system itself. However, if there any many outputs, then it's up to the user to 'overlay' a synthetic cost function to be minimized, which compresses all the outputs down to a single parameter to minimize.

# Models

- Modeling is the set of abstractions for explaining and predicting physical phenomenon: deterministic and stochastic, numerical (approximate) and symbolic (analytic)

- Models are the functions which predict outputs from given inputs, but all models also imply or enforce certain forms and constraints on the inputs signal. Therefor the system model is both the abstraction of the system and the signals. Consider statistic models, like the Markov Chain stochastic processes which don't have 'input signals' in the traditional sense, do but have outputs.

- Models are built following data observations (often automatically with computation), system models are composed from building blocks using frameworks like SPICE/TCAD/EM/Signal flow tools.
- Predictions about behavior can be made, either on pen+paper, or on computers. (Both can be can be numeric of symbolic)
- And systems can be optimizatized for a purpose, either using (look at opt types)

When you draw a schematic in EDA software, you are essentially defining the arrangement of a system model but you aren't specifying everything. For example:

## Compact modeling:

Needs to balance accurate modeling across physical and technology variation, while still remaining mathematically tractable (poisson, stochastic LLG, schrodinger, Boltzmann Transport)

There are basically three types of compact models:

* Macro models, using lumped element circuit devices to mimic device behavior
* Table lookup, {I,Q} = F{L,W,T,VD,VG,VD,VB..}, this is of limited value early in device evaluation
* Physics based analytic model, computationally effici

1. You aren't specifying the device model, or other macro models. These are provided by vendors or by yourself, and may range in complexity from simple V=IR for an ideal resistors, to sophisticated numerical models, and even idealized digital circuits with only discrete outputs (macro models). This is tightly coupled to the simulator. Often models will only work for a certain type of analysis (i.e. needing RF transistor models for high-frequency AC). One important type of simulation is embedded noise statistical analysis. Mathematical and statistical modeling occurs simultaneously and can be very difficult.

2. You aren't specifying the simulation type/evaluation type. These can range from transient numerical simulations all the way to symbolic solutions of problems that are reduced in complexity and can be evalutated analytically.

3. You aren't specifying the stimulus to the circuit. This can be tightly coupled to the simulation type and model type, like with (maybe symbolic) linear/small-signal AC analysis, or it can be less coupled, like in the case of a numerical transient simulation, where you are free to input arbitraty time-domain (sampled) waveforms (as long as they don't change too fast relative to the simulation time step.

4. When you complete the schematic, it may be exported as a netlist in the case of most numerical simulator, of if you're working with your own simplified toy model, it maybe be evaluated analytically be hand or by simple feedforward numerical calculation (if the system is linear and time-invariant).

5. An intermediate step which must be completed is a layout generator, which produces a DRC valid layout from a template and transistor sizes, and then which extracts it to get a more complex (but same class) PEX netlist for simulation. This generator is necessary for trusting our models, but isn't needed for every optimization setp.


# Forward problem solutions: simulations, etc

Once you have a mathematic model which is generalizable across different problems, we solve these problems. Some problems, like standard simulations in DC, AC, or transient analaysis modes, are 'forward problems'.

Forward problem solutions includes stochasticity (arising from measurement error, system noise, and environmental noise), boundaries conditions, linearity/nonlinearity, partial differential equations

Numerical/approximate methods for solving problems existed before Computer science and programming. Older methods, like analog computers/slides rules are approximate because of error accumulation from mechanical tolerances and electronic noise. And so the methods explored by them accumulate error in a different manner. Digital computers instead accumulate error through quantization. Herein lies the beauty of digital; after conversion, it suppress analog noise/error with noise margin, at the expense of quantization error. Note: Computers drastically accelerate numerical **AND** symbolic methods. Therefore, make sure you don’t confuse numerical(approximate) methods are being the exclusive or sole domain of digital computers. Humans can also do numerical and symbolic computation. (Is analog computation a third type?)

Monte-carlo methods are a stochastic forward solution to understanding variance

# Inverse problems: optimization, sensitivity analysis, parameter estimation, regression

## Classical Optimization

The alternative problem type is an [inverse problem](https://en.wikipedia.org/wiki/Inverse_problem), where you work backward from desired analysis outputs, to compute ideal parameters. The most common example in engineering is optimization: when you're working from analysis outputs, to find ideal parameters of the model. Types include Mathematical(linear programming, non-linear programminag, mixed integer, semidefinite, conic, etc) and Baysian statistical optimization (which is very sample efficient, and good in cases of treating the inside as a black box.) The systems to be optimized can be discrete/continuous, singular or multi-variable, constrained/unconstrained, static/dynamic (time-varying?), and deterministic/stochastic.).

This [course](https://web.stanford.edu/group/sisl/k12/optimization/#!index.md) explains in detail a lot of optimization concepts.

## Parameter estimators
In models without 'signal inputs' like stochastic processes, the parameters are PDF variables. [Estimators] are the statistic method for estimating the parameter from data. In more traditional physics based systems, which have input and output signals

When you have lots of data from the output of a forward simulation, or from a real experimental measurements, inverse methods overlap with machine learning and provide methods for producing estimators:

![Estimators](https://scikit-learn.org/stable/_static/ml_map.png)

## Sensitivity Analysis
Another inverse problem example is [sensitivity analysis](https://en.wikipedia.org/wiki/Sensitivity_analysis). Problem inversion is an unstable process: noise and errors can be tremendously amplified making a direct solution hardly practicable. With the advent of computers in the 70s, the least-squares and probabilistic approaches came in and turned out to be very helpful for the determination of parameters involved in various physical systems.


## Regression

Estimating the relation/function between inputs and outputs, given the dependent outcome variables. The most common is a linear regression. Symbolic is the finding of a mathematical analytic expression which best matches data, using numerical methods. A common library:

https://astroautomata.com/SymbolicRegression.jl/stable/

## Machine learning optimization

From Infineon's anagen program.

For analog schematics: there's not one best design, as there are multiple objectives. This is a parento front problem.
We use evolutinary algorithms, which is a stochastic optimization algorithm
This is sample inefficient, and simulation has high sample cost
Gaussian processes vs baysian optimization
Baysian isn't true multi object model -> it compresses to a single point

evalution methods used: constraint violation (how far away violating the constraints), alternative hypervolume

GDE3, MODEBI, MACE, EBO (evolutional baysian optimization)
3 of these use machine learning models (surrogate only)

GDE3 is common standard, MACE is another publication,o

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

# The Mathematics of Electrical Engineering

Remember the difference between numerical (approximate) and symbolic (analytic) solutions. Wow many symbolic manipulations are done on paper, there is actually symbolic computation:

> These distinctions, however, can vary. There are increasingly many theorems and equations that can only be solved using a computer; however, the computer doesn't do any approximations, it simply can do more steps than any human can ever hope to do without error. This is the realm of "symbolic computation" and its cousin, "automatic theorem proving." There is substantial debate as to the validity of these solutions -- checking them is difficult, and one cannot always be sure the source code is error-free. Some folks argue that computer-assisted proofs should not be accepted. 

> Nevertheless, symbolic computing differs from numerical computing. In numerical computing, we specify a problem, and then shove numbers down its throat in a very well-defined, carefully-constructed order. If we are very careful about the way in which we shove numbers down the problem's throat, we can guarantee that the result is only a little bit inaccurate, and usually close enough for whatever purposes we need.

> Numerical solutions very rarely can contribute to proofs of new ideas. Analytic solutions are generally considered to be "stronger". The thinking goes that if we can get an analytic solution, it is exact, and then if we need a number at the end of the day, we can just shove numbers into the analytic solution. Therefore, there is always great interest in discovering methods for analytic solutions. However, even if analytic solutions can be found, they might not be able to be computed quickly. As a result, numerical approximation will never go away, and both approaches contribute holistically to the fields of mathematics and quantitative sciences.

> Although the terms "modeling" and "simulation" are often used as synonyms within disciplines applying M&S exclusively as a tool, within the discipline of M&S both are treated as individual and equally important concepts. Modeling is understood as the purposeful abstraction of reality, resulting in the formal specification of a conceptualization and underlying assumptions and constraints. M&S is in particular interested in models that are used to support the implementation of an executable version on a computer. The execution of a model over time is understood as the simulation. While modeling targets the conceptualization, simulation challenges mainly focus on implementation, in other words, modeling resides on the abstraction level, whereas simulation resides on the implementation level. Conceptualization and implementation – modeling and simulation – are two activities that are mutually dependent, but can nonetheless be conducted by separate individuals

Benefits of simulation:

1. cheaper
2. more accurate, as no errors/noise
3. faster than realtime
4. coherent synthetic environment





# Not sure what seciton this is?

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

# Statistics

Concerning the collection, organisation, analysis, interpretation, and presentation of data. The opposite of mechanistic modelling. Used to learn, describe, and predict the behaviour of systems after empirical data has been collected. Statistical or correlation studies often bypass the need for causality and focus exclusively on prediction, and not mechanistic explanations of “why?”. As most data is computer generated (Ninety per cent of the world's data have been generated in the last 5 years), these methods are often closely intertwined with computer algorithms. Permutations and combinations, allow us to work with simple discrete known populations and directly calculate probability from it. Random variables. Intersections and unions of sets. Multiplication rule. Bayes’ theorem, the central limit theorem and the law of large numbers, co-variance and correlation, and maximum likelihood estimation (MLE). Probability density functions and cumulative design functions


# Jitter

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

## Jitter Sampling

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


## Random vs Determinisitc Jitter

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

Euler

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


