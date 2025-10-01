// ADC Module - with configurable resolution

module adc (
   
    // Sequencing signals
    input  wire seq_init,                     // Initialization sequence timing
    input  wire seq_samp,                     // Sampling sequence timing
    input  wire seq_comp,                     // Comparator sequence timing
    input  wire seq_update,                   // Logic sequence timing

    // Enable control signals
    input  wire en_init,                      // Enable initialization
    input  wire en_samp_p,                    // Enable sampling positive side
    input  wire en_samp_n,                    // Enable sampling negative side
    input  wire en_comp,                      // Enable comparator
    input  wire en_update,                    // Enable update logic

    // DAC config - positive side
    input  wire dac_mode,                     // DAC mode control (shared for both sides)
    input  wire [15:0] dac_astate_p,          // DAC A state positive side
    input  wire [15:0] dac_bstate_p,          // DAC B state positive side
    
    // DAC config - negative side
    input  wire [15:0] dac_astate_n,          // DAC A state negative side
    input  wire [15:0] dac_bstate_n,          // DAC B state negative side

    // DAC diff caps (for unit length caps!)
    input wire dac_diffcaps,                  // Enable differential capacitor mode.
    
    // Analog inputs
    inout  wire vin_p,                        // Analog input positive
    inout  wire vin_n,                        // Analog input negative
    
    
    // Output
    output wire comp_out                      // Comparator output

    // Power supply signals
`ifdef USE_POWER_PINS
    ,inout wire vdd_a, vss_a,                 // Analog supply
    inout wire vdd_d, vss_d,                  // Digital supply
    inout wire vdd_dac, vss_dac               // DAC supply
`endif
);

    // Internal wires
    wire vdac_p, vdac_n;                      // DAC voltages (positive and negative)
    wire comp_out_p, comp_out_n;              // Comparator differential outputs
    wire vsamp_p, vsamp_n;                    // Sampling switch output voltages
    wire clk_init;                            // Initialization clock
    wire clk_samp_p_raw, clk_samp_n_raw;      // Raw sampling clock signals from clkgate
    wire clk_samp_p, clk_samp_n;              // Buffered sampling clock signals
    wire clk_samp_p_b, clk_samp_n_b;          // Complementary sampling clock signals
    wire clk_comp;                            // Comparator clock
    wire clk_update;                          // Logic clock signal
    wire [15:0] dac_state_p, dac_state_n;     // SAR logic output buses
    
    // Four 16-bit capacitor driver outputs (keeping same signal names at top level)
    wire [15:0] dac_drive_botplate_main_p; // Positive capacitor driver outputs
    wire [15:0] dac_drive_botplate_diff_p; // Positive capacitor driver outputs, difference caps
    wire [15:0] dac_drive_botplate_main_n; // Negative capacitor driver outputs
    wire [15:0] dac_drive_botplate_diff_n; // Negative capacitor driver outputs, difference caps

    // Clock gate module - generates all gated clocks
    clkgate clkgate(
        // Sequencing inputs
        .seq_init(seq_init),
        .seq_samp(seq_samp),
        .seq_comp(seq_comp),
        .seq_update(seq_update),

        // Enable inputs
        .en_init(en_init),
        .en_samp_p(en_samp_p),
        .en_samp_n(en_samp_n),
        .en_comp(en_comp),
        .en_update(en_update),

        // Clock outputs
        .clk_init(clk_init),
        .clk_samp_p(clk_samp_p_raw),
        .clk_samp_n(clk_samp_n_raw),
        .clk_comp(clk_comp),
        .clk_update(clk_update)

        // Power supplies
`ifdef USE_POWER_PINS
        ,.vdd_d(vdd_d),
        .vss_d(vss_d)
`endif
    );

    // SAR Logic - Consolidated dual-channel
    salogic salogic_dual (
        .clk_init(clk_init),                  // Initialization clock
        .clk_update(clk_update),              // Update clock
        .dac_astate_p(dac_astate_p),          // DAC A state positive
        .dac_bstate_p(dac_bstate_p),          // DAC B state positive
        .dac_mode(dac_mode),                  // DAC mode (shared for both sides)
        .comp_p(comp_out_n),                  // Use negative comp output for P-side logic
        .dac_astate_n(dac_astate_n),          // DAC A state negative
        .dac_bstate_n(dac_bstate_n),          // DAC B state negative
        .comp_n(comp_out_p),                  // Use positive comp output for N-side logic
        .dac_state_p(dac_state_p),            // Output to positive DAC state
        .dac_state_n(dac_state_n)             // Output to negative DAC state

        // Power supplies
`ifdef USE_POWER_PINS
        ,.vdd_d(vdd_d),
        .vss_d(vss_d)
`endif
    );


    // Four Capacitor Drivers (4×16-bit instances)

    // The dac_drive_invert signal, when low, causes that bank of 16x drivers to output a drive level opposite from the dac_state input signals
    // This feature isn't needed on the two _main drivers, so this control input is tied high
    // However, it should be available via dac_diffcaps on the two _diff drivers. It's active low.

    // P-side main capacitor driver (active low: 1 = no invert)
    capdriver capdriver_p_main (
        .dac_state(dac_state_p),              // SAR logic positive output
        .dac_drive_invert(1'b1),              // Main drivers: no inversion (active low)
        .dac_drive(dac_drive_botplate_main_p) // To positive main capacitor array
`ifdef USE_POWER_PINS
        ,.vdd_dac(vdd_dac),
        .vss_dac(vss_dac)
`endif
    );

    // P-side diff capacitor driver (active low: 1 = no invert)  
    capdriver capdriver_p_diff (
        .dac_state(dac_state_p),              // SAR logic positive output
        .dac_drive_invert(dac_diffcaps),      // No inversion for positive side diff caps (active low)
        .dac_drive(dac_drive_botplate_diff_p) // To positive diff capacitor array
`ifdef USE_POWER_PINS
        ,.vdd_dac(vdd_dac),
        .vss_dac(vss_dac)
`endif
    );

    // N-side main capacitor driver (active low: 1 = no invert)
    capdriver capdriver_n_main (
        .dac_state(dac_state_n),              // SAR logic negative output  
        .dac_drive_invert(1'b1),              // Main drivers: no inversion (active low)
        .dac_drive(dac_drive_botplate_main_n) // To negative main capacitor array
`ifdef USE_POWER_PINS
        ,.vdd_dac(vdd_dac),
        .vss_dac(vss_dac)
`endif
    );

    // N-side diff capacitor driver (active low: 0 = invert)
    capdriver capdriver_n_diff (
        .dac_state(dac_state_n),              // SAR logic negative output
        .dac_drive_invert(dac_diffcaps),      // Invert diff caps for negative side (active low)
        .dac_drive(dac_drive_botplate_diff_n) // To negative diff capacitor array
`ifdef USE_POWER_PINS
        ,.vdd_dac(vdd_dac),
        .vss_dac(vss_dac)
`endif
    );




    // Sampling clock drivers - generate complementary clock pairs
    sampdriver sampdriver_p (
        .clk_in(clk_samp_p_raw),              // Input raw gated sampling clock positive
        .clk_out(clk_samp_p),                 // Buffered output clock positive
        .clk_out_b(clk_samp_p_b)              // Inverted output clock positive
`ifdef USE_POWER_PINS
        ,.vdd_d(vdd_d),
        .vss_d(vss_d)
`endif
    );
    
    sampdriver sampdriver_n (
        .clk_in(clk_samp_n_raw),              // Input raw gated sampling clock negative
        .clk_out(clk_samp_n),                 // Buffered output clock negative
        .clk_out_b(clk_samp_n_b)              // Inverted output clock negative
`ifdef USE_POWER_PINS
        ,.vdd_d(vdd_d),
        .vss_d(vss_d)
`endif
    );

    // ! ANALOG MACRO ! Capacitor arrays (CDACs)
    caparray caparray_p (
        .cap_topplate_in(vsamp_p),            // Positive sampling input from sampling switch
        .cap_topplate_out(vdac_p),            // Positive DAC voltage output to comparator
        .cap_botplate_main(dac_drive_botplate_main_p), // Positive main capacitor bottom plates
        .cap_botplate_diff(dac_drive_botplate_diff_p)  // Positive diff capacitor bottom plates
    );

    caparray caparray_n (
        .cap_topplate_in(vsamp_n),            // Negative sampling input from sampling switch
        .cap_topplate_out(vdac_n),            // Negative DAC voltage output to comparator
        .cap_botplate_main(dac_drive_botplate_main_n), // Negative main capacitor bottom plates
        .cap_botplate_diff(dac_drive_botplate_diff_n)  // Negative diff capacitor bottom plates
    );
    // ! ANALOG MACRO ! Sampling switches with complementary clocks
    sampswitch samp_p (
        .vin(vin_p),                          // Positive analog input
        .vout(vsamp_p),                       // Positive sampling output
        .clk(clk_samp_p),                     // Positive sampling clock
        .clk_b(clk_samp_p_b)                  // Complementary positive sampling clock
`ifdef USE_POWER_PINS
        ,.vdd_a(vdd_a),                       // Analog power
        .vss_a(vss_a)                         // Analog ground
`endif
    );

    sampswitch samp_n (
        .vin(vin_n),                          // Negative analog input
        .vout(vsamp_n),                       // Negative sampling output
        .clk(clk_samp_n),                     // Negative sampling clock
        .clk_b(clk_samp_n_b)                  // Complementary negative sampling clock
`ifdef USE_POWER_PINS
        ,.vdd_a(vdd_a),                       // Analog power
        .vss_a(vss_a)                         // Analog ground
`endif
    );

    // ! ANALOG MACRO ! Comparator
    comp comp (
        .vin_p(vdac_p),                       // Positive comparator input
        .vin_n(vdac_n),                       // Negative comparator input
        .dout_p(comp_out_p),                  // Positive comparator output
        .dout_n(comp_out_n),                  // Negative comparator output
        .clk(clk_comp)                        // Comparator clock
`ifdef USE_POWER_PINS
        ,.vdd_a(vdd_a),                       // Analog power
        .vss_a(vss_a)                         // Analog ground
`endif
    );

    // Output assignment
    // NOTE: Should maybe add an output driver cell here!
    assign comp_out = comp_out_p;             // Transmit out the positive comparator output

endmodule
