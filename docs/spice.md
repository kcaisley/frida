# SPICE netlists

- Spice standard netlist files should conventionally end in `.sp`, instead of the sometimes used `.spi`, `.ckt`, or `.net` extensions.
  - The combination of this extension and format allows portability between `spectre` and `ngspice`.
- The project supports multiple PDKs through symlinked `tech/` directories
- SPICE simulations output to `raw` binary format for broad tool compatibility
  - This is called `nutbin` by `spectre`


This doc provides notes how to correctly use SPICE netlists.

The the approve to generate differential clocks is:

```spice
VV5 syncn gnd! PULSE( log_VCC 0 -convtime/48  100p 100p convtime/24  convtime  )
VV6 syncp gnd! PULSE( 0 log_VCC -convtime/48  100p 100p convtime/24  convtime  )
VV7 clockn gnd! PULSE( log_VCC 0 0 100p 100p convtime/24  convtime/12 ) 
VV8 clockp gnd! PULSE( 0 log_VCC 0 100p 100p convtime/24  convtime/12 ) 
```

We can see there are two issues in the with the code above. Besides for the
initial transition, the new waveforms lag by 100ps. Next the waveforms
are seemly transitioning late.

Since `contime = 0.1u` we know that the period should be: 4.166 ns. This
indicates that the `pw` parameter in the `pulse(...)` function doesn't
include the rise or fall time in the width duration. Thus if we want a
waveform which has a pulse width measured from the half-maximum, we need
to shorten the pulse width by half the rise and half the fall time. Or
in the case that they are equal simply `pw = width - risefall`.

This solution exactly what we find upon inspecting the original old
waveform generator.

Not, you can't by default have independent params determined by others.
Also, you can't have spaces, and need quotes around expression. So
`pw=’(convtime/24)-100p’`



This statement may sometimes be needed, to ensure the simulator knows the size of devices:
*.SCALE micron
