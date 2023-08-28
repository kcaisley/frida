




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



## Symbolic regression, is the finding of a mathematical analytic expression which best matches data, using numerical methods:

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
