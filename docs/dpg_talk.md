I# Stage of signal path, mechanistic models
Geant -> TCAD -> Allpix2 -> SPICE -> Digital

# stage has engineering details, which can be computationally modeled -> compared against experimental results
System Level (Chip Budget: constraints)             -> Database of known chips and their constraints
Block Level (Budget Allocation, behavioral models)  -> DB of detector specs/or, or project specific block level experimental data 
Circuit Level (Budget expenditure, mechanistic models) -> experimental results of chip, 
Implementation (the physical GDS and layout, or TCAD models. Requires lowering.)

# tools
Various tools are used to move between these representations. The are used to 'handle' the analysis, and modification of the different components.

I think the idea that the top level consists of constraints, which then don't get referenced below is incorrect. Specifications and constraints should both exist at the top, as any chip has, but are then both realized in the lower levels as the aggregate of each sub block.

Critically, the top-level may be inflexible (in some parameters) but in real design, not all constraints are propagated from the top down. Real designs are constantly moving all around the hierarchy, as specs + constraints are modified or discovered.


# But...
I think people will grow weary of my 'ideas'. So my focus should be on showing things of real value. I think the TB of an already designed amplifier is one option. But I don't have a good way (yet) of parsing in a schematic. So perhaps what I should focus on is generate the netlist for, and simulating, a basic self-design front end amplifier.

Then explain that parsing in existing netlists, for testbenches, and generating layouts is my next goal.
Is parsing in existing layouts also in the works? Do they just have to remain hard-macros, or could I learn something about their internals? Perhaps for netlists, you don't need to fully parse the netlist to simply wrap a DUT with a testbench.

Yes, this is good. I should show how to wrap the testbench for 1-2 existing designs. Perhaps the TJmonopix design, or the PLL design?

# Outline

Okay, so given that:

1. How analog design works (compared to digital)
2. Basic proposal: Use general purpose programming language to describe tasks that are methodological
3. First, bottom up approaches are good for generating netlists.
4. Also, top down can be use to evaluate (automating design decisions) and compare (against experimental data)



# External and internal DSLs

## external

notation can be close to that used by domain experts

big disadvantage of external DSLs is lack of 'symbolic intergration': the base language isn't aware of what we're doing. WE don't get benefits of modern IDEs. We don't get syntax highlighting, semantic editing (autocomplete), and debugging

another disadvantage of external DSLs is that there are too many languages, which can be overloading

## internal (embedded)

have full power of host language, but are limited by it's syntax
having clojures and macros can be helpful

most technologies which try to cater to 'lay programmers' actually end up forcing the domain expert to become a real developer.


effective lines of code (eLOC) is a metric used to measure the effectiveness of the language


Two ways of implementing it a host language:

- application library, with types and operators for the domain
- macro and subrouting preprocessing, where you use the languages features to first generate code at compile time
    - a special example of this is template meta-programming in C++


> To approximate domain-specific notations as closely as possible, the em-
bedding approach can use any features for user-definable operator syntax the
host language has to offer. For example, it is common to develop C++ class
libraries where the existing operators are overloaded with domain-specific se-
mantics. Although this technique is quite powerful, pitfalls exist in overloading
familiar operators to have unfamiliar semantics.

In addition to C++, we can benefit from functional language features such as lazy evaluation, higher-order functions,
and strong typing with polymorphism and overloading

Apparently *monads* can help a language adapt it's syntax?

> the recommended approach is to implement it by embedding, unless domain-specific
analysis, verification, optimization, parallelization,
or transformation (AVOPT) is required, a domain-specific notation must be
strictly obeyed, or the user community is expected to be large.

Some related terms: C++ meta-programmed, language oriented programming

SystemC overloads nearly every operator to the point of acting like a totally different language, but with all the pitfalls of CXX and TMP (template meta-programming) too

Python [supports](https://docs.python.org/3/reference/datamodel.html#special-method-names) overloading existing operators, but not adding new ones.

Rust supports something similar via traits, but doesn't support function overloading.

Operator overloading is good for linear algebra, tensor, vector math, List, stream concatenation, date comparison especially >=, BigDecimal math operations, c++ smart pointers, iterators, container types, python datetime classes, pathlib module, sqlalchemy, quartonians

macro examples include C preprocessor, TeX macros, C++ templates, 