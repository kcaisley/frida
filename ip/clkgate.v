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
    input  wire en_update_p,     // Enable update logic positive side
    input  wire en_update_n,     // Enable update logic negative side

    // Output gated clocks
    output wire clk_init,       // Gated initialization clock
    output wire clk_samp_p,     // Gated sampling clock positive
    output wire clk_samp_n,     // Gated sampling clock negative
    output wire clk_comp,       // Gated comparator clock
    output wire clk_update_p,    // Gated update clock positive
    output wire clk_update_n     // Gated update clock negative
);

    // Generate gated clocks by ANDing sequence signals with enables
    assign clk_init = seq_init & en_init;
    assign clk_samp_p = seq_samp & en_samp_p;
    assign clk_samp_n = seq_samp & en_samp_n;
    assign clk_comp = seq_comp & en_comp;
    assign clk_update_p = seq_update & en_update_p;
    assign clk_update_n = seq_update & en_update_n;

endmodule
