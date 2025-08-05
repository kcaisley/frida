// SAR Logic Module - Non-traditional SAR logic implementation
// Inputs: dac_astate (Ndac bits), dac_bstate (Ndac bits), dac_mode, comp, clk_init, clk_update

module salogic #(
    parameter Ndac = 16  // Parameterizable number of step DAC
) (
    // Clock inputs for Mealy state machine
    input wire clk_init,                    // Initialize signal
    input wire clk_update,                  // Update signal

    // Control and data inputs
    input wire [Ndac-1:0] dac_astate,              // Ndac bits input A from SPI
    input wire [Ndac-1:0] dac_bstate,              // Ndac bits input B from SPI
    input wire dac_mode,                       // Mode selection
    input wire comp,                       // Comparator output used for state update

    // Outputs
    output reg [Ndac-1:0] dac_state       // Current output register
);

// Position counter for tracking which bit to update in dac_state
// Counter width calculated to accommodate Ndac bits
reg [Ndac-1:0] dac_cycle;

// Initialize dac_state to dac_astate on rising edge of clk_init
always @(posedge clk_init) begin
    dac_state <= dac_astate;
    dac_cycle <= {1'b1, {(Ndac-1){1'b0}}};  // First bit is 1, others are 0 (MSB first)
end

// Update dac_state on rising edge of clk_update (when clk_init is low)
always @(posedge clk_update) begin
    if (~clk_init) begin  // Only update when clk_init is low
        if (dac_mode == 1) begin
            // Mode 1: Use dac_cycle as one-hot mask to update only the selected bit
            // Update only the bit where dac_cycle has a 1, preserve others
            dac_state <= (dac_state & ~dac_cycle) | (dac_cycle & {Ndac{comp}});
            // Right shift the 1 in dac_cycle for next bit position
            dac_cycle <= dac_cycle >> 1;
        end else begin
            // Mode 0: Set dac_state to dac_bstate, don't increment counter
            dac_state <= dac_bstate;
        end
    end
end

endmodule
