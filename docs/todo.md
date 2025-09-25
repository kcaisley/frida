# demo gds issues found:
- asserts in synthesis give some issues, which were bypassed by commenting out line in scripts/synth.tcl
- position where vsub_vss_cup_pad should be is still a reset, need to remove reset pin and add power
- understand why 0.001 is needed for DBU scaling from DBU to micros to work properly. Even klayout gives a warning about the disagreement, but it's what works in practice for now?
- deleted frida_top.v, not sure if that's an issue yet
- pad dimensions in LEF are a bit complicated, one thing is that spacers need to be included between. WIP! Check cordia design for correct spacing. LVDS cells include one spacer, hence they need to take multiple positions? Maybe just flatten design into fixed positions, with no helpers.
- Is the adc .sdc file working now, with update syntax?
- Was the `localparam int BASE = 64 + i * 7;` syntax in the ADC generate actually problematic? I removed the `int` due to error from yosys, but I'm not sure if necessary?
- fully added ifdef USE_POWER_PINS at all levels, essentially removing them. IHP pdk does the same
- Modified platform pdn.tcl to mimic basic shape needed for frida, still needs 2 other domains though. Comment out design pdn.tcl for now
- Caparray LEF uses `CLASS BLOCK` with minimum size, issue of seeing it due to cell dimensions small around origin meaning it is out of frame easily when zooming
- Caparray LEF also needs M6 pins to be on LEF edge, to be accessible through blockages on M6!
- removed rtran and other statements in .v model of io cells
- passive cells has an I, O and PAD pin? That seems wrong.

# ADC issues:
- [x] Open road wouldn't build, even on Ubuntu 22.04 -> Solution was to install basic packages and rerun setup.sh
- [x] Resolve KLayout crash in build_macros - ADC LEF/LIB generation failing during GDS merge step -> Solution was to move to Ubuntu 22.04 (or RHEl 9!)
- [x] Solved issue of top level run not triggering ADC as BLOCK (solution was ADDITIONAL_LEFS += and placing them inside project config.mk)
- [x] Technology and stdcells should be seperated into different .LEFs
- [x] Pins must be track aligned, and meet minimum area, dimensions, and spacing as defined in technology LEF
- [x] I believe all design levels should just include *.v, and use (* blackboxes *) for non-synthesized macros
- [x] Error about double cut via -> For now out those rules from the the tech .LEF for now -> can also avoid those cells specifically
- [x] Lots of timing repair delay cells were being inserted -> (hacky) solution was to force DFF w/ enable cells to be used
- [ ] Can't figure out right syntax to generate multiple power domains, [ERROR PDN-1032] Unable to find DAC domain.
- [ ] Also don't know how to express supply names in the `.v` files without just totally omitting them
- [ ] SDC constraint pin names aren't being resolved correctly, giving error -> maybe use -hierarchy?
- [ ] global placement failing with error about RSZ-2001 (can I try disabling repair for now?)
- [ ] DRT failing, because not working for pins of comparator, claiming pins aren't found in the guide, even though it shows in the GUI
- [ ] Antenna diode insertion is failing, even got a crash at some point (skipping can't be final)
- [ ] placement not working for macros, they're just going to random locations, after changing my flow for heirachical design
- [ ] Klayout.lyt still doesn't have correct writer settings for DEF->GDS convesion for tsmc65, spacing is all messed up
- [ ] Macro placement with .tcl fails with 'caparray_p isn't a macro' and with .cfg just seems to ignore it and place as though no placement locations were specified
- [ ] PDN generation was failing with anything more than a basic VDD/VSS configuration. Need to re-implement.

# Chip-level issues:
- [ ] Top level timing constraints need to be completed, and also only be implemented from inside the pad-ring as we have no macro
- [ ] LEF files for IO pads are wrong, no blockages, missing pins (see ihp130 for better example?)
- [ ] Standard cells are appearing in the layout even during floorplanning?
- [ ] Verilog connections for the pad ring power level still aren't fully complete, need to replace 'connect by abutment'
- [ ] Pad placement script not really tested yet?

# Outstanding questions:
- [x] Does specifying the sub-block config.mk yield the same output as when it's built as a dependency? -> Looks like it, yes
- [ ] Should my blocks have power pins defined in verilog?
- [ ] we don't have .lib files for the pad ring at all, and for our macros, but I think I can do without this? Or I even specify capacitance with a basic lib file myself?
- [ ] which layers (drawing, pin, label, text) and objects (text, polygon, OA pin) should be used in .OA / .GDS files for input/outputs in my layouts?
- [ ] What's the correct way to use placement for ORFS? .cfg or .tcl?

# Outstanding Issues from Recent Work:
- [ ] Investigate power domain isolation - IHP-SG13G2 may not have dedicated power cut cells, need to ensure filler cells don't bridge different power domains (vdd_a vs vdd_d vs vdd_io vs vdd_dac)
- [x] Address "ERROR GPL-0001: clk_PAD toplevel port is not placed" during placement stage - **RESOLVED** by removing unused clk_PAD from design
- [x] Address "ERROR GPL-0001: vin_n_PAD/vin_p_PAD toplevel port is not placed" during placement stage - **RESOLVED** by blackboxing sg13g2_IOPadAnalog to prevent Yosys buffer insertion
- [ ] Address "WARNING ODB-0186: macro bondpad_70x70 references unknown site sg13g2_ioSite" during floorplan stage - bondpad may need proper site definition
- [ ] Address "WARNING ODB-0229: Error: library already exists" warnings during floorplan - multiple library loading causing conflicts
- [ ] Address "WARNING IFP-0028: Core area snapped to grid" during floorplan - core area coordinates not aligned to placement grid
- [ ] Address "WARNING PAD-0033: Could not find block terminal associated with IO corner power nets" during floorplan - power ring connectivity issues
- [ ] Address "WARNING RSZ-0062: Unable to repair all setup violations" during floorplan - timing issues that may need SDC constraint fixes
- [ ] Address "WARNING RSZ-0020: found 2 floating nets" during ADC placement - unconnected nets in ADC block
- [ ] Address "WARNING DRT-0349: LEF58_ENCLOSURE with no CUTCLASS not supported" during routing - technology LEF missing advanced via rules
- [ ] Address "WARNING DRT-6000: Macro pin has more than 1 polygon" during routing - ADC macro pin geometry causing routing issues
- [ ] Verify reset_b removal doesn't affect design functionality - removed reset_b_PAD from both TSMC65 and IHP-SG13G2 versions
- [ ] Confirm reserved pad functionality - added 5 reserved CMOS pads (cmos_reserved_0-4_PAD) for future expansion
- [ ] Validate macro spacing updates - increased ADC spacing from 160μm to 180μm to 190μm pitch, verify this resolves PDN conflicts
- [ ] Test FOOTPRINT_TCL vs IO_CONSTRAINTS usage - confirmed FOOTPRINT_TCL is correct for place_pad commands in IHP-SG13G2 flow
- [ ] Verify I/O power pad relocation - moved vdd_io_PAD and vss_io_PAD from NORTH edge to bottom of EAST/WEST edges
- [ ] Check pad layout symmetry - ensure 7 positions per side with proper power distribution balance
- [ ] Validate file path standardization - converted absolute paths to design variables throughout config files
- [ ] Test hierarchical vs flattened synthesis approach - ADC uses SYNTH_HIERARCHICAL=0, top-level uses SYNTH_HIERARCHICAL=1
- [ ] Verify cells_ihp_sg13g2.v file organization - moved from platform to source directory and updated all references

# Configuration and Flow Issues:
- [ ] Implement proper multi-domain PDN configuration - current simplified single VDD/VSS domain may not be sufficient for mixed-signal design
- [ ] Add power domain boundary definitions to prevent filler cell placement across domains
- [ ] Investigate FlowVariables.md documentation accuracy - added FOOTPRINT and FOOTPRINT_TCL variable documentation
- [ ] Consider implementing power cut isolation techniques since IHP-SG13G2 appears to lack dedicated power cut cells
- [ ] Review ADC macro LEF files for proper pin definitions to resolve DRT-6000 warnings about multi-polygon pins
- [ ] **FLOW BUG**: PWR_NETS_VOLTAGES and GND_NETS_VOLTAGES must be commented/uncommented in config.mk before each export - OpenROAD fails to parse dictionary format for power domain definitions, causing export to fail with parsing errors

# Design Deviations Between TSMC65 and IHP-SG13G2:
- [x] Document major architectural differences - TSMC65 uses explicit pad cell instantiation, IHP-SG13G2 uses OpenROAD automated placement
- [x] Verify differential signal handling differences - TSMC65 has LVDS receivers, IHP-SG13G2 uses manual logic conversion
- [ ] Confirm power distribution approach differences - TSMC65 uses explicit POWER_CUP_pad instances, IHP-SG13G2 relies on OpenROAD PDN

# Analog Pad Placement Issue - RESOLVED:
- [x] **Challenge**: sg13g2_IOPadAnalog cells causing "vin_n_PAD toplevel port is not placed" errors during global placement
- [x] **Root Cause**: Yosys synthesis tool was inserting digital buffers (sg13g2_buf_1) inside sg13g2_IOPadAnalog modules, breaking analog signal paths
- [x] **Investigation**: Found buffer instances sg13g2_IOPad_vin_n/_0_ and sg13g2_IOPad_vin_p/_0_ in synthesized netlist even though original platform definition was analog pass-through
- [x] **Solution**: Added sg13g2_IOPadAnalog to SYNTH_BLACKBOXES in config.mk to prevent Yosys from synthesizing analog cell internals
- [x] **Verification**: Confirmed analog pad terminals (vin_p_PAD, vin_n_PAD) now create successfully during floorplan stage
- [x] **Result**: Global placement proceeds without errors, analog signal integrity preserved

# Before submission don't forget:
- [ ] Complete ADC block hardening - Generate abstract files needed for hierarchical synthesis
- [ ] Don't forget to check if inverted signal in XOR gate in capdrive.v is right (I removed a ~)
- [ ] Check that the config pins on IO pads have been set correctly
- [ ] Run top-level synthesis - Test frida_top synthesis with ADC macros as black boxes
- [ ] Implement floorplanning - Place 16 ADC macros in 4×4 grid within 600×600μm core area
- [ ] Verify pad placement - Test IceWall pad.tcl script with 100μm pitch and power isolation
- [ ] Run placement and routing - Complete physical implementation of full chip
- [ ] Timing closure - Meet timing constraints across all four clock domains
- [ ] Generate final GDS - Complete chip layout with sealring integration
- [ ] Re-enable DRT in adc level
- [ ] Re-enable antenna cell insertion / checking
- [ ] Re-enable double/triple/quad cut via rules in the technology LEF
- [x] Create GDS for capacitor array
- [x] Create GDS for switches and comparator, from .OA views
- [x] Create .lef for capacitor, switches, and comparator
- [x] Manual positioning of top-level macros
- [ ] Set specific input wires for manual routing or unbuffered routing
- [x] Set how to place the pad ring automatically
- [ ] Double check what additional buffers and clock cells are being put on clock tree and data path (on top of the core synthesized netlist)
- [ ] Handle double or quad cut vias where OpenROAD doesn't support (make single cuts larger initially, then run find and replace operation in specific locations after the fact)
- [x] Connect to the 3 analog macros within each ADC channel (figure out proper positioning and apply correct pin/IO to each macro)
- [x] Get LEF files for the 3 analog blocks so tool can properly connect to them
- [x] Implement SPI Register
- [x] Implement output demultiplexer between the different channels
- [ ] Double check register count versus what I expect from synthesis result
- [ ] Make sure registers are minimum sized to minimize area
- [ ] Specify load capacitance for the different drivers so they are properly sized
- [ ] Add negative plate drivers for my try for a ray

# Behavioral modeling
- [ ] Actually build the model with python, following 'wreal' modeling.
- [ ] Understand DAC non-linearity from expected mismatch
- [ ] Understand calibratability condition vs mismathc and redundancy/radix
  - [ ] If M:N DEC logic is on chip, can you still use redundancy for calibration?
  
# ADC control logic
- [ ] Verify the calibration idea works (and compare against background error correction)
- [ ] Verify timing settling error can be measured with above method?
- [ ] Ensure all possible states of sample are possible with our 2-bit control

# Comparator
- [ ] Test bench for expected input referred noise and offset

# Capacitor array
- [x] Python script to generate layout
- [ ] Python script to generate schematic 

# Chip top level
- [x] Padring: 1mm x 1mm test chip, with 100um bump bond pitch. 28 pins in total.
- [ ] Decoupling MOSCAPs in periphery. Don't place them in-between as the real system won't have any room anyways
- [x] SPI 4-pin interface: SDI, SDO, SCLK, CS_B. Add more than one needs, and only use for static config
- [ ] Does the padring need to support 'higher voltages'?

# Verification
- [ ] block level DRC, don't forget antenna, wirebond, density rules

# Physical testing
- [ ] mini@sic will provide ~100 chips, all from a single wafer, but there are 3-4 total wafer produced for backup
- [ ] Fan out wires from chip pitch to PCB
  - [ ] Use exposed metal below chip, with normal epoxy to glue in place
  - [ ] But not copper as it will oxidize, use (nickel / gold?)
- [ ] Input path: test generator -> high quality op amp -> Vin+ and Vin-
- [ ] FPGA control system:
  - [ ] Provides a sequencer, to generate arbitrary control wavforms
  - [ ] Develop DEC correction output logic
- [ ] Don't forget fan-out of bonds

# Simulation and Analysis
- [ ] Why is ENOB calculation wrong? Thermal noise close to LSB should be -1.7 ENOB approximately
- [ ] Fix 5 variations of ADC - Get all simulating on TSMC65 using Dropbox files
- [ ] Get credible value for comparator noise in uV rms in Spectre at fixed speed (simulator bandwidth needs to be 10x circuit bandwidth)
- [ ] Fix LSB in terms of error
- [ ] Check the code to make sure it's correctly recombined
- [ ] Understand if shift vs subradix understanding is correct
- [ ] Test buffer and without buffer (depends on kickback)
