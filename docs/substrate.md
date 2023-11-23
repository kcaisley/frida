# Rust basics

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

I guess the best place to start might be first for me to outline what my use case for Substrate would be, and then see where we can find some common ground where I could contribute.

My task over the next 2-3 years is to project design a readout ICs for a 1 megapixel image sensor with a 60 µm pixel pitch, at a ~80kHz full frame rate (12.8 us). The end application is for a high-performance transmission electron microscopy camera.

The corresponding ROICs are placed around the periphery of the sensor array, and bump bonded to substrate. Each is only responsible for reading a subsection of the array with 256 column x 128 rows, with one ADC per column. Based on the frame time ADC must capture the drain current in less than 100ns, at 10bit resolution. The area per ADC should be around 0.0576 mm² area (240µm * 240µm, assuming it's square).

The minimum requirement is the full frame needs to be readout at 80kHz, with at least 10 bit resolution.



Like I mentioned earlier, I've taken a long look at BAG3, Laygo2, and Hdl21. I like some of the features from each, but the the complexity of the

 of work that would be necessary to get BAG3 to a place where it's usable


I was hoping to ask some questions about the substrate API:




What is the outward facing API of substrate? It must be the substrate + simulation plugins crates? 


As I understand it right now, the basic intented interface for 



Access to git repository
Add as a guest to BAR Slack?

Developing Xbase-like device primitives?
Developing generators on top? (How will it be packaged?)
Providing assitance for PDK integration (DRC, LVS, SPICE decks?) Skill hooks to stream in GDS?
Parsing SPECTRE netlists? 
Layout interface is not implemented yet
Good first issues?
your docs look great
My plan is to make a column parrallel image sensor ROIC, with 10bit ADC, SRAM (for buffering), PLL, digital core, and SERDES interface
    All the components will be medium performance, medium area, medium power
    I need to target TSMC 28nm, but would like to have a public version which works in 130 nm
    I'd like to make the individual components
    
has functionality of both BAG (layout, DRC, LVS, etc) and Hdl21 (schematic generation)

Poor process portability. But maybe I can just write generators in both.
I know that Substrate is very much a bottom-up generator, but is it possible to implement procedural sizing defined by a simulation result? This isn't the focus of Hdl21, as it sorta imagines that you already have

A high level user would simply have a commandline utility called `droic`.

https://crates.io/crates/substrate2 appears to not be recieving updates in line with github?

Do you envision others being able to depend directly on your library?

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
