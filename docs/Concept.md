---
created: 2023-09-13T16:48:06+02:00
modified: 2023-09-16T17:57:22+02:00
---

# Concept

Two places analog performance matters is IO and FE. Show a generator can work in both of these.


In an AFE, generator is best used for design exploration, and optimization against accurate models. Aim is to ensure the entire design space has been checked, which a human can’t normally do well. Layout models are mostly useful for modeling, as the layout will always benefit from the human touch in optimization. (A constraint based layout optimizer could work here, but it’s far too complex for my background.)


For IO, we are less space or power constrained, but we do want to be able to generate a family of proven medium performance and reliable blocks. This approach would have a sweeping design based method for netlist creation, and then a straightforward template-based approach for layout generation. These then would be arranged by the designer at the block level, to fit their need.

At the core of both approaches is a cell based approach where a library of components is designed with a set of bottom up design scripts, for a particular PDK. The necessary blocks are characterized by regression and equivalent Verilog-A models are made. Then, whether doing design exploration or straight forward generation, the HDL21 netlist tool can simply **hierarchically assemble the circuit**.  This is how process portability is achieved.

Beyond design reuse/speed and widened exploration coverage of the design space, this code based approach also allows designers and testers to use the same detector characterization tooling as testers.

06.09.2023

Creation of the netlists is where I should be focusing my attention at this point. Learn to run simulations, generate different netlists, and get the netlist as close as easily possible to post layout simulation. Hdl21 is the tool for this.

Later on, I can the focus on translating this netlist to layouts, either either Laygo2, ALIGN, GDSFactory, GDSTk, or even just manual layout in Klayout.

Rust is fast, but complicated, with few EDA tools, and with no mindshare. Julia is composable, but only really with numerical/mathematical libraries. It has no mindshare for EDA. Use Python. It isn’t sexy, but that’s a good thing. Everybody in my group and in EDA uses it. It’s a glue language, essentially acting as a fancy config file for faster compiled tools.
