// Clock Gate Module - Generates gated control 'clock' signals
// Combines sequencing signals with enable controls

module clkgate (
    // Sequencing signals
    input  wire seq_init,       // DAC initialization sequence timing
    input  wire seq_samp,       // Sampling sequence timing
    input  wire seq_comp,       // Comparator sequence timing
    input  wire seq_update,     // DAC update logic sequence timing

    // Enable control signals
    input  wire en_init,        // Enable initialization
    input  wire en_samp_p,      // Enable sampling positive side
    input  wire en_samp_n,      // Enable sampling negative side
    input  wire en_comp,        // Enable comparator
    input  wire en_update,      // Enable update logic

    // Output gated clocks
    output wire clk_init,       // Gated initialization clock
    output wire clk_samp_p,     // Gated sampling clock positive
    output wire clk_samp_n,     // Gated sampling clock negative
    output wire clk_comp,       // Gated comparator clock
    output wire clk_update,     // Gated update clock
    
    // Power supply signals  
    inout wire vdd_d, vss_d     // Digital supply
);

    // Generate gated clocks using proper clock gates
    OPENROAD_CLKGATE clkgate_init (.CK(seq_init), .E(en_init), .GCK(clk_init));
    OPENROAD_CLKGATE clkgate_samp_p (.CK(seq_samp), .E(en_samp_p), .GCK(clk_samp_p));
    OPENROAD_CLKGATE clkgate_samp_n (.CK(seq_samp), .E(en_samp_n), .GCK(clk_samp_n));
    OPENROAD_CLKGATE clkgate_comp (.CK(seq_comp), .E(en_comp), .GCK(clk_comp));
    OPENROAD_CLKGATE clkgate_update (.CK(seq_update), .E(en_update), .GCK(clk_update));

endmodule
