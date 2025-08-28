# Todo list
- [ ] Create GDS for capacitor array
- [ ] Create GDS for switches and comparator, from .OA views
- [ ] Create .lef for capacitor, switches, and comparator
- [ ] Manual positioning of top-level macros
- [ ] Set specific input wires for manual routing or unbuffered routing
- [ ] Set how to place the pad ring automatically
- [ ] Double check what additional buffers and clock cells are being put on clock tree and data path (on top of the core synthesized netlist)
- [ ] Handle double or quad cut vias where OpenROAD doesn't support (make single cuts larger initially, then run find and replace operation in specific locations after the fact)
- [ ] Connect to the 3 analog macros within each ADC channel (figure out proper positioning and apply correct pin/IO to each macro)
- [ ] Get LEF files for the 3 analog blocks so tool can properly connect to them
- [ ] Implement SPI Register
- [ ] Implement output demultiplexer between the different channels
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
- [ ] Python script to generate layout
- [ ] Python script to generate schematic 

# Chip top level
- [ ] Padring: 1mm x 1mm test chip, with 100um bump bond pitch. 28 pins in total.
- [ ] Decoupling MOSCAPs in periphery. Don't place them in-between as the real system won't have any room anyways
- [ ] SPI 4-pin interface: SDI, SDO, SCLK, CS_B. Add more than one needs, and only use for static config
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
