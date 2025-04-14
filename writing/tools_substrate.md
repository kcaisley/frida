# Analysis of `strongarm` project

- atoll and tb `pub mod`
- Create IO struct for diffcomp, with a handful of impls, where `Io` is custom-defined via procedural macro, the rest are built-in
- Create 


Do I not need the spice parser, if I want to use the ngspice plugin?


# Outstanding questions

What is the appropriate way to organize the project? I was thinking something like:

```
project/
|-- src/
|   |-- amp.rs      // contains code describing hardware itself
|   |-- amp_tb.rs   // contains code that can TB, simulate, evaluate, and size devices?
|   |-- inv.rs
|   |-- inv_tb.rs
|   |-- lib.rs      // has top level declaration of different elements, and libraries to import.

```

:: is the path seperator, but can also be part of the turbofish `instance.method::<SomeThing>()`

In other words: 

. is used when you have a value on the left-hand-side. It's for value access.
:: is used when you have a type or module. It's for namespace member access.

# Info

Hdl21 is opinionated, and doesn't really support the use-case of generating a schematic, with sizing determined by:
- a set of iterated values
- a deterministic expression (closed-form solution, found by analytic methods)
- a set of instances, filtered by numerical simulation result (choosing the best of several)

This could be either done at runtime, or potentially before with preprocessers, macros, or other metaprogramming types. But I think for the 'plain old data' approach, these more abstract tools should be reserved for the function which produce and manipulate block, and not be used by the block definitions themselves.

One idea from Hdl21 is that modules, i.e. the equivalent representation of a SPICE netlist, should be represent-able by a serialized format. This generic representation can then be transpiled to the necessary format.

Laygo2 adds the same idea for layouts, with a generic interchange format. But it goes one step further, with 'templates' for layouts, which are 

Rust and Substrate the following system packages:
`sudo dnf install gcc protobuf protobuf-compiler sqlite sqlite-devel`

gcc is for the `cc` linker

# IOs

How does this `Default` attribute work? It should be adding a trait to the struct...?
IO is a schematic interface, and all implement the `Directed` trait, and each component of IO has a default of `InOut<Signal>.` These can be expanded to be made an array, and can be configured as `Input` or `Output`. This can happen at the single signal level or at the level of an entire collection, because composite type IOs are flattenable 
`VdividerIo::default()` is an example of an associated function, not a method?
The `Default` attribute creates a trait which is a 'default' constructor for the Type
    where each basic type is initialized to it's default (ints are zero, etc)
    and where compound types behave specially, like enums, where the first  varients is selected.
So it's like a default version of a constructor, e.g. `InverterTb::new()`.
    Just like the above, it's an associated function not a method, as it doesn't take `self` aka not acting on an object

You can create an instance of a certain type with:
1. An associated function like `let myinst = MyType::new(10,20)`, which you've manually defined
2. The default trait `let myinst::default()` which is applied to the type definition via the derive attribute `#[derive(Default)]`
3. By direct instantiation `let myinst = MyType{x:10, y:20};`

Where 
```
struct MyType {
    x: i32,
    y: i32,
}
```

One you have the schematic netlist representation of IOs, you can connect it easily to other IOs that have the same type (aka the same IO struct). If it's a compound (aka composite) of IO types, aka a bundle, then it is first flattened, and then connected in order. If the types don't match, then you would need to self-write a custom `Connect` Marker Trait.

But doing this directly isn't advisable, and so instead the better approach is the  

In the 

# Blocks

Blocks are like modules/cells, and are paired with a corresponding Io. Blocks can automatically implement the `Block` trait via derive attributes, but it's often better to manually define it.

I don't really grok what the params inside the block struct should be? Should they always be physical dimensions, and when can they be under specified? I guess the `impl Schematic for Inverter` is how one actually maps out the netlist contents of a block.




# Rust Book Chapter 2:

```rust
use std::io;
use rand::Rng;
use std::cmp::Ordering;


fn main() {
    println!("Guess the number!");

    // originally this was inferred as i32, but now with the guess u32 and the later cmp, rustc knows to infer u32
    let secret_number = rand::thread_rng().gen_range(1..=100);

    println!("The secret number is: {secret_number}");  // Just for debugging!

    loop {
        println!("Please input your guess.");

        let mut guess = String::new();

        // Result is an enum of Ok and Error. The options of an enum are called Variants.
        io::stdin()
            .read_line(&mut guess)
            .expect("Failed to read line");

        // This is shadowing, where we reuse a variable name by overwriting.
        // parse returns an error type, in case an unparsable value is entered
        // just like before, if we get 'Ok' expect passes the value, if 'Err' expect panics
        let guess: u32 = match guess.trim().parse() {
            Ok(num) => num,
            Err(_) => continue  // _ means match all error values; continue means skip to next loop iteration
        };

        println!("You guessed: {guess}");

        /*
        match expression gives the => cases notation
        */

        match guess.cmp(&secret_number) {
            Ordering::Less => println!("Too small!"),       // Ordering is an enum from the standard library
            Ordering::Greater => println!("Too big!"),
            Ordering::Equal => {
                println!("You win!");
                break;
            }
        }
    }
}
```


# Chapter 3, 

- scalar types are int, float, bool, and char
- (primitive) compound types: tuple, array
    - .... struct, enum? user defined?
    - `tuples` have mixed types, `arrays` have one type
    - `tuples` and `arrays` can't be increased in size.
    - more complex compound types can come from collections, like `vector`
    - tuples indexed with `.` or deaggregagted, arrays indexed with `[]`
    - you can make tuples of array (and maybe arrays of tuples?)
    - Are strings compound types of `chars`?
- functions have args and return
    - last term can be returned implicitly, without return or ;
- control flow:
  - if, else, if else need a bool input
  - loops, while, for. Break statement exists for all; necessary for 'loop'


static methods — methods that belong to a type itself are called using the :: operator.

instance methods — methods that belong to an instance of a type are called using the . operator.



traits are collections of functions defined for a certain type
macros are grouping of functions which act as one


- The elements of an enum are called 'variants'


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

to summarize my research project. I'm building a readout IC (28nm bulk CMOS) for a 1 Mpixel, 80kHz frame rate transmission electron camera. Each column-parallel readout channel should probably fit within the 60 µm pixel pitch and measure the column current at 10 Ms/s with a 8+ bit resolution. The data from each channel will then be buffered, seralized, and transmitted out over short (25 cm) wireline links. I'd like to try different configurations of ADC speed, ADC resolution, buffer size, serializer ratio, wireline link speed, and number of links. I'm hoping the generation of these narrow 60 µm channel slices, to be then arranged in parallel, is an appropriate use case for Substrate.

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



# Questions

How do you guys minimize build times, and have you thought about how build times affect interactivness?

usability concerns: DSL, embedded DSLs, REPLs, build systems, plotting, IDE interactivness, Unix command line, speed of local hardware for simulation vs remote systems/mounts

features: analog behavioral modeling, analog synthesis, layout synthesis, feedback based optimization

As interactiveness is a critical component of using the tool quickly, we must think about how certain dependencies will signifigantly decrease productivity, and so we should custom write (with a reduce scope) those dependencies which we need features from but don't want to have to build.

# substrate review

https://github.com/substrate-labs

trait objects, essentially refers to using structs as types!

If I understand correctly, this is a holdover from the preview name?
This is need to use substrate as a dependency, but it's outdate right now, right?

Also, it shouldn't be used for development, correct? Just git clone, and get rolling?


Is there a reason why `psfparser` isn't in tree with the rest of substrate?

quickstart.md

22
Perhaps mention that cc (from gcc), protobuf, protobuf-compiler, and sqlite, and sqlite-devel are needed?


io.md

IO must implement the 

Io struct - template (interface) for instantiation of of Io. Must implement Io trait (potentially via derive)

line 62
Comment on the hardwaretype vs schematictype alias

66
<!-- What is the above link supposed to point at? I can't find this SchematicType Trait. -->

104
<!-- Perhaps adding some mention of how the From and Into traits work in this case, plus their associate methods? -->
<!-- Also, this code, and the code above it, are presented in an incomplete 'non-compilable' fashion. -->


schematics.md
23
<!--You don't need the `#[derive(NestedData)]` if you have the manual impl, right?   -->
<!-- All blocks that have a schematic implementation must export nodes? -->

24
<!-- What is the difference between ExportsNestedData and HasNestedView and #[derive(NestedData)] -->



contributing.md
I think the link into the subtrrate docs is wrong

double check I can build the docs and the main tools?



readme.md

check in general.
