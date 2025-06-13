# ciccreator notes

- Q Which docs page is more up to date?
  - Looks like this one: https://analogicus.com/ciccreator/index.html

- **Q** Are are input schematics using generic transistors and other devices?
  - Yep. You can see between the IHP130 and SKY130 videos, that the `.spi` input files are essentially the same. Also the `.json` files are pretty much the same too, with like 1% differences.

- **Q** Do these input netlists support parameterization, maybe through placeholders or using SPICE parameters?
  - Parameterization is essentially adding extra transistors, so I think I can handle this by simply having different netlists! I can write a python script which converts 

- **Q** How to deal with digital stdcells? Can one wrap them with ciccreator, or perhaps even just FOSS digital flows? I saw in the post from the PhD student that there appeared to be some compiled logic.

- Make files for everything

- git submodules to connect PDK to design to flow, etc

- Magic and Xschem use their own plaint plain text formats, very easy to gen

- Using Xschem to produce the input netlists isn't a anti-pattern!

- "glue" code should be used for SIM, DRC, LVS, PEX, etc (Makefiles are good!)

- Design information should be encoded into the SPICE file, not schematic

- regarding Transistors
  - **Q**: In the SKY130 video it was shown that unit W xtors came in a single fl, but then in the IHP130 follow-up video, several dimensions of transistors were show?
  - What does the `DL` in `NCHDL` and `PCHDL` stand for, in the netlist base instance names. 
  - His XTORs appear to have horizontal poly, while TSMC have vertical
  - Bulk contacts are needed, and he puts them off to the side in each cell
  - Unit includes dummy poly, as <=28nm needs it for matching
  - Only PDK variable *should* then be X and Y lambda
  - only difference between NMOS and PMOS is implant layer.
  - **Q** Only unit transistors allowed. Parrallel for larger width is allowed. Is series for larger L allowed?
  - **Q** Can I rotate my layout to have vertical Poly, easily?

- regarding circuits
  -  Can "inherit" placement and routing, in the case of different drive strengths.
  - Devices are first placed, starting with top device in netlist, placed in top left. Then device of same type (P vs N) are placed in same columns, non-matching are placed to the right.
  - Routing comes next.
    - A routing pattern like `--|-` means over and then down, with a small over at the ends
    - A routing patten `-|` means  over and then down
    - A routing patten `-` or `|` means just down, or just over, respectively
    - directed routes, similar to Tikz:
      - Directed routes require that you specify the ports of which devices which will be connected by a specific metal using a specific strategy
      - `M1, Y, MN:D-|--MP:D` means "Using metal 1, route net Y, from MN port D to MP port D, using an over before down strategy"
      - This can't push or shove, or avoid other metals. It's completely blind and relies on you to actually route.

    - Connectivity based routing is the alternative, which already know the ports of which devices need to be connected by a net.
      - Therefore you can connect 3+ pins with a single command, simply stating a metal, a net, and the method.



- A symbol can be associated (xschem,skill,etc) for making Virtuoso/Xschem schematics
- A 'class' is supported. Base device are of type Gds, circuits are Layout, like LayoutDigitalCells, for example
- the SPICE netlist can live outside the JSON file
- `IVX1` means an inverter with a drive strength of (times) 1

  - **Q** I'm not sure what the `_CV` suffix stands for though?

- **Q** NMOS and PMOS unit XTORs include substrate contacts, but these seem to not appear in the higher level circuit blocks, and are only having taps?
- `.spi` and `.json` pairs include:

  - capacitor
  - components: analog blocks, i.e. transmission gate
  - dig(ital): flip flops, combinational logic, active pull up/downs (TIEH = tie high)
  - dmos (core): for transistors, which has no .spi file
  - resistors, which also only has .json, and no .spi file

- `.tech` one file per PDK

  - `layers` section provides mapping between generic M1, M2, M3 and PDK specific names for these layers, and how to move with a via on these layers
  - `technology` section contains

    - unit, grid size, technology name
    - devices w/ names, type, ports, **Q** what are `propertymap`s?

  - `symbol_lib` and `symbol_libs` which provide symbols for generating schematics

    - are mostly pdk generic

  - `rules`

    - metal routing, transistor ASCII -> unit nm equivalent, and via dimensions are different between PDKs, even in the same size
    - Other rules are mostly the same, in that they scale linearity with the tech Lamda dimensions



