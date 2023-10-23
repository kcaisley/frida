Open source netlist:


schematic only has width and length
but layout has a bunch of other device level info per device, like pins, etc



TCL scripts are used for generating the Parameterized cells. You can set defaults for the additional devices parameters, which can't be automatically inferred from the layout (this is anything other than width and length) and then you can generated a mass of unconnected

You can only get port directions from the LEF file, not from the schematic, as spice netlists don't have direction.

you can run 'drc why' in Magic Tcl window

You should choose width of metal wires based on elecomigration and loading capacitance. Too small and electromigration is a problem, and too large and you are adding unecessary capacitance. Don't do routing too long on local interconnection, as it's high resistance.

Two questions:

As somebody who has only done analog design using Cadence tools where PCells which are normally in the OpenAcess format, could you explain a bit more on how the parametrized cells for Magic are written? Are they .tcl scripts, which are then read-in by Magic to flesh out the little 'params' GUI that we see? And are they provided as part of the SKY130 PDK in a standard format, or have they be translated from the PDK data into a Magic-specific TCL format?


## Both
* Harold Pretl has a Docker container, there is also efabless (foss-asic-tools i think) or from iic-jku (iic-osic-tools)?
* No gravity option
* Skywater PDK now has revision B (has support for ReRAM)
* Some device level parasitics are included in device models, if they are fully determined by W and L
* In SKY130, we have ti layer, which is titanium nitride, which is similar to poly, but about halfway between poly and metal in resistivity. It's how to local interconnect is done.
* In SKY130, for PVT and monte carlo, the models include all corners (both the standard process corners and monte carlo, which are separate things).
* To seperate analog and digital substrates, In the sky130 process in magic, there's an "isosub" layer that acts like sxcut.

## Magic VLSI
* In magic, there's a separate command for checking antenna rules.
* Klayout is unique because it doesn't have an internal database, and acts straight on GDS files.
* Magic supports online DRC, wheras klayout doesn't
* Only knowns what is 'one net' in layout via rules, and can't examing the schematic at all.
* for stretching, there is in fact the command is "stretch".
* 'drc where' to fin

## Klayout
* Supports Python and Ruby TCL PCells.
* You have to manually create each device from it's PCell form, and name everything to match Schematic.
* don't forget to set your own shortcut keys
