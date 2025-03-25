# Diagramming needs:

- Adding arrows and annotations easily (anything native to insscape will support that)
- MUX, ADC, Blocks
- text in Latex roman font
- Ability to animate by revealing layers (have to do it in inkscape)


# Comparison of schematic drawing packages:
Standard circuitikz: Complicated but well documented and has all of the symbols I needs. The issue is if I want to add arrows or block diagrams or waveforms I can't easily tack that on. Also I can easily additively animate layers, and will need inkscape for that anyways.

https://svg-schematic.readthedocs.io/en/latest/examples.html: Neither latex not inkscape. Alignment will be an issue. Also doesn't support every symbol and I can take the time to learn to use it.

https://github.com/medwatt/circuitikz_symbols/blob/main/circuitikz_0.5mm_grid.svg:Looks nice, but doesn't support all symbols from circuitikz.

https://github.com/fsmMLK/inkscapeCircuitSymbols?tab=readme-ov-file#changelog: I will go with this, as it has a style I actually think I prefer over circuitikz with thicker likes, and it's graphical in inkscape. Any missing symbols I can just draw myself in inkscape or later learn to implement in the library. Also it supports latex text and it has a wide array of partner packages for other stuff.

https://github.com/patrickschulz/integrated-circuits-tikz/: Same issues as Circuitikz with many fewer symbols. No docs


# Inkscape config

Set canvas to FHD 1920x1080, but set grid and rulers to mm.

>Edit >Preferences >Behaviour >Transforms
Once there tick or un-tick "Scale stroke width" and Under "Store Transformation"

To set default stroke width to 1mm, double click on the pen/bezier tool, and then set "use last used style"

gpl files go in Edit > Preferences > System: User palettes
