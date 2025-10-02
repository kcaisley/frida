// ADC Digital Module - Digital portion only, analog macros factored out

module adc_digital (

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

    input  wire comp_out_p, comp_out_n,      // Comparator differential outputs - from comparator

    // Digital clock outputs - to sampling switches
    output wire clk_samp_p, clk_samp_p_b,    // Positive sampling clocks (normal and complementary)
    output wire clk_samp_n, clk_samp_n_b,    // Negative sampling clocks (normal and complementary)

    // Digital clock output - to comparator
    output wire clk_comp,                     // Comparator clock

    // DAC state outputs - buffered to four separate signals (64 bits total)
    output wire [15:0] dac_state_p_main,         // Positive DAC state main (16 bits)
    output wire [15:0] dac_state_p_diff,         // Positive DAC state diff (16 bits)
    output wire [15:0] dac_state_n_main,         // Negative DAC state main (16 bits)
    output wire [15:0] dac_state_n_diff,         // Negative DAC state diff (16 bits)

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
    wire clk_init;                            // Initialization clock
    wire clk_samp_p_raw, clk_samp_n_raw;      // Raw sampling clock signals from clkgate
    wire clk_update;                          // Logic clock signal

    // Internal DAC state signals from SAR logic
    wire [15:0] dac_state_p;                  // Positive DAC state
    wire [15:0] dac_state_n;                  // Negative DAC state

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

    // DAC state buffering - create four separate outputs from SAR logic
    assign dac_state_p_main = dac_state_p;   // Buffer to main positive output
    assign dac_state_p_diff = dac_state_p;   // Buffer to diff positive output
    assign dac_state_n_main = dac_state_n;   // Buffer to main negative output
    assign dac_state_n_diff = dac_state_n;   // Buffer to diff negative output

    // Output assignment
    // NOTE: Should maybe add an output driver cell here!
    assign comp_out = comp_out_p;             // Transmit out the positive comparator output

endmodule