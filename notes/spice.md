# Spice History:

Digital IR drop, power domiains, timing closure

Level 1 16 params, bsim6 has 1200

Additions beyond the core spice:
Fast spice
Simulation corners and Monte Carlo
Extraction




15.4.2 batch versus interactive mode
.meas analysis may not be used in batch mode (-b command line option), if an output file (rawfile) is given at the same time (-r rawfile command line option).


recall there a two design pattern for Simulations

Either you Create a `Sim` object immediately
s = Sim(tb=MyTb)

And add all the same attributes as above
p = s.param(name="x", val=5)


Or you create a Sim class, and then decorae it with the @sim function, to get an object.

I want to have an object, and I wnat to know what can be put inside the .save() attribute.

So I shoul look at the class definition.

It has a `attr`, which is a list made from `SimAttr`, which in turm is a Union of

```
SimAttr = Union[Analysis, Control, Options]
```
And I'm interested in the control element

# Spice-Sim Attribute-Union
Control = Union[Include, Lib, Save, Meas, Param, Literal]:

This finally leads us to:

```
class SaveMode(Enum):
    """Enumerated data-saving modes"""

    NONE = "none"
    ALL = "all"
    SELECTED = "selected"


# Union of "save-able" types
SaveTarget = Union[
    SaveMode,  # A `SaveMode`, e.g. `SaveMode.ALL`
    Signal,  # A single `Signal`
    List[Signal],  # A list of `Signal`s
    str,  # A signal signale-name
    List[str],  # A list of signal-names
]


@simattr
@datatype
class Save:
    """Save Control-Element
    Adds content to the target simulation output"""

    targ: SaveTarget
```
