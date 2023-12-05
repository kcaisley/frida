# Rust basics

'vectors' store memory adjacently, whereas a linked lists/linked structres stores data in a disparate manner. This is bad for performance, and not necessarily even helpful when inserting values.

https://isocpp.org/blog/2014/06/stroustrup-lists
https://www.programmingtalks.org/talk/keynote-goingnative-2012


metaprogramming? 

interfaces

python: protocols, abstract base classes, collections

c++: standard template classes

Rust: 
Structs: data structure grouping data
Enum: data structure defining a set of options
Collections: more data structures, sequeces(vectors,linked lists) strings, maps(hash maps, b-tree), sets(hashset, btreeset

Generics: generic data types which provide a definition for functions or structs, which a concrete data type can then implement

Generics give a way for one function to work on multiple types — generic types and generic functions — are just things that take types as arguments. In these examples, though, we haven't specified what sorts of types we'd like to accept, and so we accept any type. This is where traits come in. Traits give you a way to describe a bunch of related types by describing what methods the type must define.

Traits: 

Trait bounds + objects

Attributes	#[meta]	#[derive()]	#[inline]	#[cfg(test)]

Macros


The levels of organization are modules -> files -> crates -> workspaces?


# questions for Substrate devs

So first, I guess I could summarize my research project. I'm building a readout IC (28nm bulk CMOS) for a 1 Mpixel, 80kHz frame rate transmission electron camera. Each column-parallel readout channel should probably fit within the 60 µm pixel pitch and measure the column current at 10 Ms/s with a 8+ bit resolution. The data from each channel will then be buffered, seralized, and transmitted out over short (25 cm) wireline links. I'd like to try different configurations of ADC speed, ADC resolution, buffer size, serializer ratio, wireline link speed, and number of links. I'm hoping the generation of these narrow 60 µm channel slices, to be then arranged in parallel, is an appropriate use case for Substrate.

1. I'm still wrapping my head around the Substrate API, and how Rust modules, crates (and workspaces?) are used to organize it. If I understand correctly: The `substrate` crate is the top-level API which user written generators import and interface with, with the exception of "plugin" crates for connection to external tools like DRC, LVS, and ngspice/spectre simulation. And rust crates for a PDK.

2. If I remember correctly, the layout engine of Substrate2 isn't done, but i'm Developing Xbase-like device primitives? bag/xbase/bag3_generators are sort of a vertical mess, so I'm wrondering what the strategy here would be?

3. BAG2 uses nutbin and for 

4. Parsing in SPECTRE and ngspice netlists?

5. User would write then a rust crate which imports and calls this 

I'd really like to help with documentation and examples,






    
has functionality of both BAG (layout, DRC, LVS, etc) and Hdl21 (schematic generation)

Poor process portability. But maybe I can just write generators in both.
I know that Substrate is very much a bottom-up generator, but is it possible to implement procedural sizing defined by a simulation result? This isn't the focus of Hdl21, as it sorta imagines that you already have

A high level user would simply have a commandline utility called `droic`.

https://crates.io/crates/substrate2 appears to not be recieving updates in line with github?

Good generators 'unroll' the design problem:
- Don't symbolically solve an expression in code, solve it on paper, so it is directly computable.
- Don't require incremental optimization/design centering. Refine your generator so that it can produce a design on the first run through.
- Then simple run simulations at the end. This is harder, but runs faster.



# problems with BAG

dependency fetching requires like 5 different sources, and still doesn't cover external EDA tools
depends on system package versions, whi
dependency versions are poorly defined, conda .yml can't be locked, and so can't be updated
building system is outdated (setup.py), no pyproject.toml support
cbag/pybag/bag/xbase/bag3_generators/workspace is a mess with git submodules nesting and config
very dependent on Cadence/Skill
API is poorly documented, and abstraction is violated, and 
usage is undocumented
dependency on skill/cadence
still includes OA code base
has no unit tests, and no integration tests
Has no CI/CD and github actions
No dependabot
No precommit hooks, for code style or static code analysis
dual python/C++ makes debugging very dificult, and will cause high level generators to be slow
users are developers, so C++ extension building is hell for debug.
no original developers are available
currently developers are scattered and divided
Config is done in YAML, and netlists are parsed into YAML, which makes understanding/validating data types hard.
Schematics, netlists, and tests are seperated by type, rather than by cell. Therefore associations are difficult.
Schematics must start from a SPICE/Virtuoso template, and then can only size circuits.
xbase build on top of BAG API cleanly, but nobody uses BAG without it. And generators call code from both XBase and BAG intermixed.
How do you proceed in these cases? Pehaps XBase are considered 'templates'? Both 'template' and 'base' are overloaded though.
To build the extension modules, we can use pyproject.toml, scikit-build, PyBind11, CMake, and setup.py (not deprecated, but calling it directly and disutils are)
Fetching C++ dependencies could come with vcpkg, Conan, or Hunter, or Conda/Miniconda.
We won't vendor or advise the installation of GUI tools. But therefore BAG needs to be able to at least *run* without BAG.
