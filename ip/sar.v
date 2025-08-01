// SAR Logic Module - Non-traditional SAR logic implementation
// Inputs: spi_a (Nbits-bit), spi_b (Nbits-bit), mode, comp, seq_init, seq_update

module sar_logic #(
    parameter Nbits = 16  // Parameterizable width for inputs/outputs
) (
    // Clock inputs for Mealy state machine
    input wire seq_init,                    // Initialize signal
    input wire seq_update,                  // Update signal

    // Control and data inputs
    input wire [Nbits-1:0] spi_a,          // Nbits-bit input A from SPI
    input wire [Nbits-1:0] spi_b,          // Nbits-bit input B from SPI
    input wire mode,                       // Mode selection
    input wire comp,                       // Comparator input

    // Outputs
    output reg [Nbits-1:0] dac_state       // Current output register
);

// Position counter for tracking which bit to update in dac_state
// Counter width calculated to accommodate Nbits bits
reg [Nbits-1:0] dac_cycle;

// Initialize dac_state to spi_a on rising edge of seq_init
always @(posedge seq_init) begin
    dac_state <= spi_a;
    dac_cycle <= {1'b1, {(Nbits-1){1'b0}}};  // First bit is 1, others are 0 (MSB first)
end

// Update dac_state on rising edge of seq_update (when seq_init is low)
always @(posedge seq_update) begin
    if (~seq_init) begin  // Only update when seq_init is low
        if (mode == 1) begin
            // Mode 1: Use dac_cycle as one-hot mask to update only the selected bit
            // Update only the bit where dac_cycle has a 1, preserve others
            dac_state <= (dac_state & ~dac_cycle) | (dac_cycle & {Nbits{comp}});
            // Right shift the 1 in dac_cycle for next bit position
            dac_cycle <= dac_cycle >> 1;
        end else begin
            // Mode 0: Set dac_state to spi_b, don't increment counter
            dac_state <= spi_b;
        end
    end
end

endmodule
