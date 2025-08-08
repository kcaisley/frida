# Analog CAD algorithms and methods




There are two ways to organize this, by design step, or by method type. Sometimes methods are useful for multiple design steps, so but I will organize it it instead by design step since this matches the flow. Also note that performant designs typically creates feedback from later steps to earlier steps, to improve 

## Topology generation

## Device sizing
Can use the following global optimization approaches, most (EA, SA, BO) are model free (no model of environment, meaning a bblack box)
- evolutionary algorithm (EA) i.e. genetic algorithms
- simulated annealing (SA)
- particle swarm
- Baysian optimization, uses a probablistic surrogate mode (normally a gaussian process) and an acquision function either (expected improvement (EI), probability of improvement (PI), entropy search (ES) and Thompson sampling (TS))


## Placement

## Routing




Model

I want to fit in the following terms:
Djisstrak's algorithms
Steiner tree
multi-objective optimization
objective function vs cost function vs acquisition function
MIP - mixed integer programming (optimization when some variables are integers, and others are linear)
integer linear programming (note: programming means optimization)

objective functions: MIN: loss = cost, MAX reward = profit = utility = fitness function


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


# Relevance of Discrete Mathematics List to ASIC Design:

    Integer Linear Programming (ILP) → Used for placement, routing, and resource allocation (e.g., assigning logic to FPGA/ASIC tiles).

    Network Flows → Key for wire routing, congestion minimization, and buffering.

    Matching → Applies to pin assignment, clock-tree synthesis, and technology mapping.

    NP-Completeness & Approximation → Crucial for understanding hardness of layout, timing closure, and partitioning problems.

    TSP/Steiner Trees → Directly used in global routing, clock-tree synthesis, and minimizing wirelength.

    Combinatorial Optimization → Core to logic synthesis, gate sizing, and voltage-island partitioning.

Potential Additions for ASIC-Specific Optimization:

    Graph Partitioning / Clustering

        Critical for hierarchical design, floorplanning, and voltage-island formation.

        Tools: METIS, spectral partitioning.

    Dynamic Programming

        Used in technology mapping (e.g., DAG covering for LUTs), timing optimization.

    Satisfiability (SAT/SMT Solvers)

        Key for formal verification, timing analysis, and logic optimization.

        Modern EDA tools heavily use SAT solvers (e.g., ABC, Cadence Conformal).

    Multi-Objective Optimization

        ASIC design trades off power, performance, area (PPA)—Pareto-optimal fronts are essential.

    Physical Design-Specific Algorithms

        Force-directed placement (simulated annealing, genetic algorithms).

        Global/detailed routing (A*, maze routing).

        Clock-tree synthesis (geometric matching, delay balancing).

    Statistical Methods for Variability

        Monte Carlo methods for process variation analysis.

        Robust optimization for PVT (Process-Voltage-Temperature) corners.

    Hardware-Aware Heuristics

        Retiming, pipelining, and parallelism extraction (e.g., loop unrolling in HLS).

        Memory/register-file optimization (e.g., bank partitioning).


# Inverse problems: optimization, sensitivity analysis, parameter estimation, regression

## Classical Optimization

The alternative problem type is an [inverse problem](https://en.wikipedia.org/wiki/Inverse_problem), where you work backward from desired analysis outputs, to compute ideal parameters. The most common example in engineering is optimization: when you're working from analysis outputs, to find ideal parameters of the model. Types include Mathematical(linear programming, non-linear programminag, mixed integer, semidefinite, conic, etc) and Baysian statistical optimization (which is very sample efficient, and good in cases of treating the inside as a black box.) The systems to be optimized can be discrete/continuous, singular or multi-variable, constrained/unconstrained, static/dynamic (time-varying?), and deterministic/stochastic.). Theories: finite dimensional derivatives, convexity, optimality, duality, and sensitivity. Methods: simplex and interior-point, gradient, Newton, and barrier.

This [course](https://web.stanford.edu/group/sisl/k12/optimization/#!index.md) explains in detail a lot of optimization concepts.

## Parameter estimators
In models without 'signal inputs' like stochastic processes, the parameters are PDF variables. [Estimators] are the statistic method for estimating the parameter from data. In more traditional physics based systems, which have input and output signals

When you have lots of data from the output of a forward simulation, or from a real experimental measurements, inverse methods overlap with machine learning and provide methods for producing estimators:

![Estimators](https://scikit-learn.org/stable/_static/ml_map.png)

## Inverse Sensitivity Analysis

In recent years however, due to an increasing interest in incorporating uncertaintyinto models and in ascertaining the sensitivity of parameter estimates withrespect to data measurements, the uses of sensitivity have broadened significantly [7, 26]. 
So on the other hand, investigators’ attention has also recently turned to the sensitivity of the solutions to inverse problems with respect to data, in a quest for optimal selection of data measurements in experimental design. 

Another inverse problem example is [sensitivity analysis](https://en.wikipedia.org/wiki/Sensitivity_analysis). Problem inversion is an unstable process: noise and errors can be tremendously amplified making a direct solution hardly practicable. With the advent of computers in the 70s, the least-squares and probabilistic approaches came in and turned out to be very helpful for the determination of parameters involved in various physical systems.

Sensitivity analysis consists in computing derivatives of one or more quantities (outputs) with respect to one or several independent variables (inputs). Although there are various uses for sensitivity information, our main motivation is the use of this information in gradient-based optimization
