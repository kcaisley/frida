cad design essentially consists of a bunch on interelated tasks, with feedfoward functions inpdependanlty, but which come together in feedback loops

when designing the independant steps, we would like the ability to have fast developer experiences, with short feedback loops. We want interactive usage speeds, where the output can be constantly checked as the function is built up. Many different approaches of implementation have been used, to various degrees of success.

however, when we then arrange that function in part of a larger system, where we typicaly rely on iterative optimization, the slower than step it, and the more unique it's implementation is (more cognitive load from different languages) the slower and more confusing our system will be.

Let's examine some different design approaches to understand how we might built these indidivudal functions, with different benefits and draw backs. We'll take for exaple the layout Pcell example, in a batch workflow

# laygo2
unix shell -> python intepreter -> python script+YAML -> 2 python library -> write GDS

# substrate
unix shell -> cargo test -> rust script -> rust library -> write GDS

# openpcells
unix shell -> embedded lua interpreted in compiled C bin -> lua script -> compiled C bin -> write GDS

# gdsfactory
unix shell -> python interp -> python script|YAML -> 2 python library -> compiled C++ extension -> write GDS

# BAG3
unix shell -> bash script -> python interpreter -> python script+YAML -> 3 python library -> C++

# BAG2



A good system is one which minimizes the aggregate of all time. Run time is developer time, etc:

learn language + write script + run script + evaluate output + extend library/runtime

Using a GPPL for the language is okay, but you should never require the user to use any 3rd party librarys in their 'script'. Any 3rd party library, if used at all, should be wrapped by your library, so that you can present a uniform and well documented API.

writing in a GPPL may save time, as it will allow multiple system components to be expressed in the same language

GPPLs are 

The more times a users uses this system, the better benefit a GPPL will have, at it's primitives are foundational to a language. To avoid the spiriling complexity of a GPPL, though, it's essentially that the 'library' component has a strongly defined API. Else you have a arbitrary code execution of


# composing the system

When you go to compose the system, there's a couple things that matter

- api used in batch operation should be able to be alternatively called as a library import
- package should be modular so that modules boundaries match how people interactively used them. There should be no inter-dependencies. Anything in the library that in feedback depends on another should instead be monolithi (python does this well)
- we should ideally be able to debug/trace program execution, all in one language. This is also applies to 'jump to defenition'. For a field as small as this, tool users inevitabley become tool developers.
- using an embedded scripting language instantly degrades composbility, as you won't be able to access the language from same environment as you use for plotting and data analysis, as well as whatever optimization strategies you're using.
- if the tool has a command line interface for interactive use, you shouldn't then need to continue to use it when composing the system. The commandline is great for people, but annoying for GPPL intergration as now you need a library for command lines


# frameworks comparison
oceane		1700k C, but this included device generators
substate	39k Rust
openpcells	43k C, 35k lua generators
bag3		37k C++, 50k python, 40k python generators, SO MUCH YAML
laygo2		15k python, 5k python generators
mosaic bag2	25k of core BAG framework, without generators
hdl21		31k python
layout21	12k rust

ALIGN
MAGICAL
GDSFactory	63k python, 20k YAML (but it's an alternate approach)
GDStk		32k C++, 5k python wrapper

# the rust-based Substrate environment is the best compromise for my PhD
- It's all integrated, with schematic, layout, and test benching in one place. We can write and debug in one language.
- It's not super easy for others to read, but the next best options, i.e. python with hdl21, python with Laygo2,python with Gdstk, or lua with openpcells are also relatively complicated. And frankly I'm doing it for my own satisfaction and learning; I'm not making 'product'.
- It doesn't support plotting, but I will be downsampling and plotting with pgfplot/tex anyways.
- It isn't quite as good for prototyping, but I'd like to improve my software engineering anyways
- It doesn't have integration with numerical simulation, optimization frameworks, and machine learning, but I don't want to get into those things anyways
- I doesn't have a library of existing designs, but the ones from Laygo2 aren't plentiful, the ones from BAG don't run, and the ones in openpcells are something I can always use for reference. Plus, as a designer, I need to *do* the designs anyways.
- It has great tooling, good libraries, good documentation, resonable compile times (compared to C++), a good build system, libraries, packaging
- It doesn't read as easily as Mojo, but it's ready now, and we don't even know if Mojo will succeed. It mojo does succeed, then I can simply rewrite, as there are so many similarities.
- It doesn't 'integrate' with Klayout or Cadence, but neither do Openpcells, and the latter doesn't it doesn't seem to be an issue for me when I think of it in my head.



# Presentation
Discuss the fundamental steps the exist in EDA, and how these can be mapped into a general purpose programming languages. I should show some nice example layouts, which I can manually draw to explain how things should be constructed.

What I won't be talking about:
- Introducing a new framework. This field is super fractured, as few designers can program, and those that can, always want to start their own project.
- Automatic circuit synthesis. This is a very broad unsolved problem, with many niche solutions. We may get there one day, but not
- DRC, LVS, PEX, graphical user interfaces, interaction with Klayout / 


Question: What are the core procedures/components of analog design?
- transistor device models. These are mapped to certain PDKs and provided by the foundary, but aren't virtuoso specific (like the pcells are). Recreating pcells isn't that hard, LVS will later tell us if we messed up, and
- Heirachical arrangement of schmetaics. We can do that pretty easily. And if we want to do parameterization, code can do this way better. You might say we need graphical representations. Well verilog systems are way more complicated, and we don't need them there? Also, the LVS tools can graphically show you the netlists, and some [people](https://github.com/gen-alpha-xtor/GenAlphaXtorSchematics) are working on adding schematics to vscode.
- Simulation running. We don't need cadence. We can view sims in a waveform viewer, and Spectre/Ngspice work fine over the command line. Plus we can better track how the testbenching and results are produced.
- Analysis: Cadence's post processing abiliies are limited anyways, and we normally pull this out into a script.
- Documentation: Cadence sucks at this. We can just use comments.
- Layout of cells: We can fairly easily recreate transistor pcells. And for other devices, like caps and guard rings, we end up often manually creating our own pcells anyways. In smaller processes our layouts are fairly regular.
- Heirachical layout: Building up tiles and arrays is natural in programming languages. And we can use some basic templating and grid structures, with basic routing algorithms to manually connect. We can track width classes. End caps, etc.
- library management is simply done via packages.

Of course, design isn't a pipeline. It's interactive, so we need to make sure that our code can be run in an ad-hoc manner. This is where unit-testing is a perfect fit. We also have to make sure that we manage dependencies in the language, to keep build times relatively short. And we can use the vscode IDEs features.

Issues: manual design is tedious, poor/no documentation, no integration with testing software, 
design isn't a pipeline, it's building of contraints, and tools help us exchange
implementing in language systems (classes), trade-offs (composability, runtime)

compare Analog design (vs digital, TCAd, or system level) but then focus in
explain that DRC, LVS, PEX, are necessary, but not 

We won't be including any 'optimization' routines in the code. Instead with manually constrain the design, and then generate variations within the constraints. Essentially we just build Pcells, where layouts are correct by construction. Optimizations may happen later, but they best occur on top of constrained (pcells).

Process portability is still essential. But I think it's doable, if we abstract the design rules.

Aside from assiting others on the occasional tapeout, and teaching my courses, don't stray too far beyond my work, like taking Math classes, etc. If I simply share what I'm working on frequently, the collaborations will occur.

# next

Continue dev work on schematic level/simulation work Substate in TSMC65nm and TSMC28nm, and get in contact with devs about layout strategies.