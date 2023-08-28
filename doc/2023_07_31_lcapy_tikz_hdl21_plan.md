# July 31, 2023

Considering all of the different things that I do during my work, I starting to think I should use Python for more. Consider:

HTML/CSS for websites
Markdown for notes + pandoc for conversion
Powerpoint or markdown + marp for slides
Latex for reports and theses
Mermaid and tikz/circuitkz and inkscape for diagram creation
SPICE netlists

The features that I need are:

- Code snippets w/ syntax highlighting
- Figures and plots
- Diagrams
- Tables
- Equations/math
- Images with sizing control
- Citations (references to references.bib)
- links (to other files and online)
- Slides segmentation formatting, with column support
 
# circuit schematics and diagrams and plots

- there are a lot of custom figures I will want to create for my thesis, think:
    - Circuit diagrams, with annotations for equations, waveform shapes, and net 'highlighting'
    - Simulated and ideal modeled waveforms
    - ideal modeled and simulated/measured INL/DNL or transfer functions or bode plots
    - System block diagrams


What I would like is to be able to hold behavior descriptions, simulation results, and raw measurement data all in the same general purpose programming language. Then, I can use one set of infrastructure to write that homogenized data out to plots.

I would like a similar sort of thing with circuit netlists and diagrams. It would save so much work for my design schematics to be produced with the same representation as my communication schematics. Since my netlists are in this protobuf format, perhaps there is a straightforward way in which I could 


# Python over julia

My group knows it, and I know it better. To both contribute to existing code, and get other to use mine, I should stay the course.
If I hope to homogenize plots from SiLab BASIL/BDAQ with HDL21, I should use the same language
HDL21 contains my schematic data, and it's in python, so I should learn it
Symbolic representation of equations is a killer feature, for plotting and exporting to latex, but it's actually better support in python at the moment, and Julia actually in some use cases depends on this SymPy package.

For plots, it looks like I want the option to export to pgfplots, which is a set of macros for Tikz for plot creation:
https://www.overleaf.com/learn/latex/Pgfplots_package

Creating this file format, though, should be accomplished via a GP programming language:

In Python: https://github.com/nschloe/tikzplotlib

In Julia: https://github.com/KristofferC/PGFPlotsX.jl

Let's now examine schematics. Similarly, there exists Cicuitkz as a Tikz macro package for circuit diagrams:

Lcapy in Python is an amazing library solution: https://lcapy.readthedocs.io/en/latest/schematics.html#schtex

What I need is a way to pipe together Hdl21 and Lcapy. I don't see any good for to include Verilog-D or Verilog-A in this work flow, which would allow for complete simulation of the system, but I think that's okay?

When dealing with complex systems, I find a purely simulator-driven methodology to not be satisfying from a research perspective. In other words, I don't want to spend too much time creating a complicated verification model in a Cadence environment. Instead, I would like to use a simulator to extract parameters of the system, but then use these parameters to optimize behavioral models of the system which I've build. This is the language that engineers think in; see for example the Razavi textbook. There is little non-linearity in the book; where it occurs naturally it is avoided using clever work-arounds and techniques.

We need to turn to books like Razavi to understand how to make things like noise and non-linearity tractable when they significantly arise in the systems we're building.

For layout, check this out:

https://github.com/DrPiBlacksmith/icLayoutRender

Alternatively, perhaps there is some export features in Layout21 that supports 

# Game plan

Next I will start building a library of bottom up generators, including flip-flops, gates, and a basic VCO. I need complete testbenches for these, so that I have characterized versions which can be used in higher level design scripts.

