- Netlist to verilog, verilog to netlist
- SPICE support for transient noise, and verilog-A behavioral models
- Netlists generators (using spice params? Find and replacement?)
- Parasitic extraction tool and configuration
- Pin legalization and routing grid in klayout
- GDS to LEF abstract generation (would need to be in klayout, since gds database parse is complex and klayout is really only game in town)
- LEF abstract checking
- Analog block implementation using openroad, from netlist
    - Create library of basic devices with legal pin locations (manually?)
    - Partition spice netlist into unit devices
    - Convert spice netlist to verilog netlist
    - Specify device placement. Can just do it based order in netlist, which I can map with comments in netlist. Should also take advantage of symmetry in netlist. 
    - Can two half circuits be re-assembled without hardening? I think so, we can somehow modify and invert the DEF database!, and then run back through routing again. So we would just select a sub-set of the device and then mirror the placement in the database, and the finally route the remaining nets.
    - either include taps in power strips, or manually add tap cells?
    - pin placement should also be inferred
    - NOTE: I suppose each step here can be done essentially manually, to verify the process. A LLM-tool might be sufficiently good at generating this!
    - The steps would be:
        - Create verilog netlist from spice netlist
        - spice netlist can include one track heigh of standard cells
        - read LEFs
        - Generate floorplan, routing grid, and tracks
        - Manual pin and device placement
        - Device placement could also use half partitioning with blockage, and then mirroring
        - Select half of nets to route, with routing blockage over other half
        - Manually mirror and add routes from previous step
        - Add final route which link two halves
        - Power grid straps on side, to power block?


- Openroad:
  - Support for multicut vias
  - LEF abstract checker
  - Better way to specify that a macro doesn't create FEOL blockage


- Klayout:
  - Pins and connectivity labeling nets
  - Routing grids per technology? Maybe can just use normal grids