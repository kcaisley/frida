The way that a generator is parameterized is important.

If it's parameterized on it's physical construction, is it generally 'incomplete' from a design perspective, and is best incorporated within a higher level routine.

Like a differential pair, for example. It likely will be nested inside of a multistage amplifier to the point that it's performance is not well isolated in a vacuum.

As another example though, consider a ring oscillator. While it very well may be used subsequently inside of a higher level routine, it also can be considered very cleanly at it's own boundaries.

You input a desired nominal frequency, a power supply voltage and power consumption(or current, same thing) and you can get out a design?

One thing to note, is that because we want to restrict ourselves to a subset of allowed devices sizes, and to a grid-based layout, it might make sense to pregenerate a set of primitives.

These can be intelligently back annotated with ideal capacitances representing major loading, such that they are fairly precise in simulation.

In other words, I don't think it make sense to let something like a PLL generator individually control the sizing of each transistor.

What I'm intuitively describing is the difference between a bottom up vs top down design pattern. Good designs patterns dictate both should exist in a design.

Starting with a bottom-up approach, a designer should start to develop an understanding of the technology, and begin producing a range of basic cell designers which are useful.

While a designer may choose to match the cell height of the digital standard cells in a process, I think it's unwise to actually rely on the library for design.

This is because it totally wrecks process portability. In fact, one probably shouldn't rely on the standard cells at all, as matching cell heights benefits little but could be designed sub-optimally.

Another benefit of having a regularized transistor structure is the ability to standardize the power delivery network. Design should be like LEGOs.

Okay, so therefore, when starting in a process, once should construct a bottom up library of primitives. These should never go more than 5-10 transistors in size, but they needn't.

The benefit is in locking down the transistor sizing and spacing (and resistors and capacitors too) so that everything is composable from a physical perspective.

Once you have these primitives generated, however, it's important to then move to the top level of the block design (i.e. PLL) and process with a top-down flow.

Identify top level specifications that are necessary, and try to identify using design equations what the specifications of the various sub blocks might be.

Next, create a couple of naive (bottom up? no that would be structural) top down sub block generators which given a set of behavioral parameters, will convert into a structural design.

Finally, once should revise the sub-block generator until I really does truly yield the performance desirable.


In summary do that following:

1) Run a library characterization script and subjective analysis. Create a library of transistor parameters, and develop a grid-based abstraction for the transistor rules. Export the valid layouts and BSIM parameters for all the transistor sizes we may need to use. Run device gm, ids, etc simulations, so we have a `numpy`` database with all of our data of interest. This is 'write once'. You shouldn't be rerunning this step frequently. And it should only be queried when doing cell level design. At the system level you shouldn't be querying it.

2) Design a set of bottom generators which will yield a broad library of cells, all physically composable. This can be entirely structural, as the cells shouldn't have too many transistor in them, and we are not willing to sacrifice composability for the extra 10% of performance that might come from full custom optimization of device sizes. Therefore, simply restrict oneself to all the useful sizes of transistors, which are composable, and then simply generate a complete static library of modules which follow those rules. The runtime used to generate these shouldn't be subsequently be run every time their needed. It's a compile stage, which then shouldn't be re-run by the 'end user'. Of course, we will need a characterization routines, so that we know the parameters of the cells. This should include everything from propagation delay and jitter of inverters/delay cells, to the gain and noise figure of amplifiers. One thing to note, is that while cells like inverters should be approached using a structural generation approach (since we know plenty of rules for sizing, so there aren't that many good combos) on the other hand a differential pair generator should use the device properties database to try and compute what would make a set of useful amplifiers. Since we will mainly be interconnecting with devices in our own library, we can make some assumptions about the characteristics of the circuit driving our block, and those loading it.

2.b) Enough data about the physical process should have been previously characterized such that the schematic generator, and subsequently layout generation about both individually feedforward steps. As best as possible, we want to avoid iteratively optimization feedback in these generators. This is because that feedback would have to include 3rd party tools. I want portions of my scripts to be able to be run without leaving the python environment. Therefore we can use these tools, but we should unroll any potential runtime loops that could exist. Dependencies on 3rd party tools should be buffered using 'caches' of their output which we can later query without having to re-run them. Another work around, for tools like DRC, is to simply use the tools to verifying the design methodology is 'correct by construction'. That way, upon subsequent runs, as long our methodology for building a layout doesn't, we can continue to build without worry we need to check DRC after every cell is placed.

2c) Enough parameters should be extracted about these low level blocks that we can then start to compose them while being able to predict the performance at the system level. I'm thinking things like power consumption (per transition or steady state) area consumption, propagation delay, etc. This is useful because these are numbers that we can mathematically combine to compute the optimal implementation of the system, without needing to run a system level parasitic simulation. This system level simulation will still need to be run for verification, but not initially for optimization.

3) Only after completing the previous stages should a designer change to a 'top down` approach. Otherwise you will find yourself with too many parameters to optimize, and you will get lost. Additionally, building the primitives first allows you to develop a degree of abstraction from the process. The top-down system-level generators will simply optimize the architecture given the primitives that are provided.

3b) This has the added benefit, as it will allow the designer to have some division between where they should be applying the 'circuit level design' discipline and when they should change to analyzing something more from a system-level signal processing perspective. Things like power and area will still be reported of course, but more as a by product of selecting between different pre-existing primitives.


# Applied

In an applied vein, I will take the PLL generator example as a trial run of my design methodology. I won't be trying to achieve state-of-the-art performance with the PLL, and it will give me the chance to test the entire flow on a design that is well documented and done. I have a full textbook to follow, and other people who are also developing PLLs.

After succeeding in this project, and submitting a tape-out, I should proceed to my real thesis work, which is a generator and FOM based approach to pixel front end design. I think there may be more room for improvement there than people realize.