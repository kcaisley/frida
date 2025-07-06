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