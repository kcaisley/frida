People to contact:

28nm forum
brown bag seminar berkekely
Email CERN people for flow advice
Email Openlane2 devs for flow advice
Email 



Tasks to do:

I need a setup, which doesn't rely on any specific PDK, which can:
Clone down repository
Pulling dependencies
building on EL7, EL8, EL9, Ubuntu 20.04. Perhaps use a set of containers for this.
Run smoke test, unit testing for BAG


I don't want to rely on a Virtuoso, Spectre, etc being in the environment, in a specific fashion
as this wouldn't be something in common with BWRC.

What sort of tests could be meaningfully build agnostic of BWRC vs Uni-Bonn vs CERN infrastructure?
What repository should this test system be built in? Maybe a new top level repository? Or a branch of the BAG one?
How can the repositories be best refactored?


bag keyword on command line vs bash. And entry points should be python, not bash script.

Use skill bridge library fro connection to Cadence

Try to turn many things into a "plugin".

Design generators are good integration tests. Unit tests aren't helpful at this stage, before refactoring.

PDK, Virtuoso, Klayout, Ngspice, etc, are all limiting as they take up a lot of space.

Running Openlane2 on github takes 4 cumulative hours on github actions. 33 hours is the limit per month (2000 mins)


environment variables should be avoided
running bag should be done with 
Is YAML okay? How can we make it more structured?


build
install
test
run
