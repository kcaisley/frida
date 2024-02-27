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