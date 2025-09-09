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
