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
