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
    input  wire en_update_p,                  // Enable update positive side
    input  wire en_update_n,                  // Enable update negative side (NOTE: is this necessary?)

    // DAC control - positive side
    input  wire dac_mode_p,                   // DAC mode control positive
    input  wire [15:0] dac_astate_p,          // DAC A state positive side
    input  wire [15:0] dac_bstate_p,          // DAC B state positive side
    
    // DAC control - negative side
    input  wire dac_mode_n,                   // DAC mode control negative
    input  wire [15:0] dac_astate_n,          // DAC A state negative side
    input  wire [15:0] dac_bstate_n,          // DAC B state negative side

    // DAC diff caps (for unit length caps!)
    input wire dac_diffcaps,                  // Enable differential capacitor mode. (Unused for now, reserved for diffcaps)
    
    // Analog inputs
    inout  wire vin_p,                        // Analog input positive
    inout  wire vin_n,                        // Analog input negative
    
    // Reset
    input  wire rst,                          // Reset signal, currently unused (might use for salogic reset)
    
    // Output
    output wire comp_out                      // Comparator output
);

    // Internal wires
    wire vdac_p, vdac_n;                      // DAC voltages (positive and negative)
    wire clk_init;                            // Initialization clock
    wire clk_samp_p, clk_samp_n;              // Sampling clock signals
    wire clk_comp;                            // Comparator clock
    wire clk_update_p, clk_update_n;          // Logic clock signals
    wire comp_out_p, comp_out_n;              // Comparator differential outputs
    wire [15:0] dac_state_p, dac_state_n;     // SAR logic output buses
    wire [15:0] dac_cap_botplate_p, dac_cap_botplate_n; // Capacitor driver output buses

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
        .en_update_p(en_update_p),
        .en_update_n(en_update_n),
        
        // Clock outputs
        .clk_init(clk_init),
        .clk_samp_p(clk_samp_p),
        .clk_samp_n(clk_samp_n),
        .clk_comp(clk_comp),
        .clk_update_p(clk_update_p),
        .clk_update_n(clk_update_n)
    );

    // SAR Logic - Positive branch
    salogic salogic_p (
        .clk_init(clk_init),                  // Initialization clock
        .clk_update(clk_update_p),            // Update clock positive
        .dac_astate(dac_astate_p),            // DAC A state positive
        .dac_bstate(dac_bstate_p),            // DAC B state positive
        .dac_mode(dac_mode_p),                // DAC mode positive
        .comp(comp_out_n),                    // Use negative comp output for P-side logic
        .dac_state(dac_state_p)               // Output to positive DAC state
    );

    // SAR Logic - Negative branch
    salogic salogic_n (
        .clk_init(clk_init),                  // Initialization clock
        .clk_update(clk_update_n),            // Update clock negative
        .dac_astate(dac_astate_n),            // DAC A state negative
        .dac_bstate(dac_bstate_n),            // DAC B state negative
        .dac_mode(dac_mode_n),                // DAC mode negative
        .comp(comp_out_p),                    // Use positive comp output for N-side logic
        .dac_state(dac_state_n)               // Output to negative DAC state
    );

    // Capacitor Drivers
    capdriver capdriver_p (
        .dac_state(dac_state_p),              // SAR logic positive output
        .dac_drive_invert(1'b0),              // No inversion as the caps aren't inverted
        .dac_drive(dac_cap_botplate_p)        // To positive capacitor array
    );

    capdriver capdriver_n (
        .dac_state(dac_state_n),              // SAR logic negative output
        .dac_drive_invert(1'b0),              // No inversion as the caps aren't inverted
        .dac_drive(dac_cap_botplate_n)        // To negative capacitor array
    );

    // ! DUMMY ! Sampling switches
    sampswitch samp_p (
        .vin(vin_p),                          // Positive analog input
        .vout(vdac_p),                        // Positive DAC voltage
        .clk(clk_samp_p)                      // Positive sampling clock
    );

    sampswitch samp_n (
        .vin(vin_n),                          // Negative analog input
        .vout(vdac_n),                        // Negative DAC voltage
        .clk(clk_samp_n)                      // Negative sampling clock
    );

    // ! DUMMY ! Capacitor arrays (CDACs)
    caparray caparray_p (
        .cap_topplate(vdac_p),                // Positive DAC voltage
        .cap_botplate(dac_cap_botplate_p)     // Positive capacitor bottom plates
    );

    caparray caparray_n (
        .cap_topplate(vdac_n),                // Negative DAC voltage
        .cap_botplate(dac_cap_botplate_n)     // Negative capacitor bottom plates
    );

    // ! DUMMY ! Comparator
    comp comp (
        .vin_p(vdac_p),                       // Positive comparator input
        .vin_n(vdac_n),                       // Negative comparator input
        .vout_p(comp_out_p),                  // Positive comparator output
        .vout_n(comp_out_n),                  // Negative comparator output
        .clk(clk_comp)                        // Comparator clock
    );

    // Output assignment
    // NOTE: Should maybe add an output driver cell here!
    assign comp_out = comp_out_p;             // Transmit out the positive comparator output

endmodule
