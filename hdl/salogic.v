// SAR Logic Module - Non-traditional SAR logic implementation
// Inputs: dac_astate (16 bits), dac_bstate (16 bits), dac_mode, comp, clk_init, clk_update


// A potential issues reported by Yosys:
// The SAR logic has two always blocks that can both drive dac_state and dac_cycle, which creates the multiple driver warnings.
// The second always block only executes when clk_init is low, but the synthesis tool doesn't understand this mutual exclusion properly.

module salogic (
    // Clock inputs for Mealy state machine
    input wire clk_init,                    // Initialize signal
    input wire clk_update,                  // Update signal

    // Control and data inputs
    input wire [15:0] dac_astate,              // 16 bits input A from SPI
    input wire [15:0] dac_bstate,              // 16 bits input B from SPI
    input wire dac_mode,                       // Mode selection
    input wire comp,                       // Comparator output used for state update

    // Outputs
    output reg [15:0] dac_state       // Current output register
);

// Position counter for tracking which bit to update in dac_state
// Counter width calculated to accommodate 16 bits
reg [15:0] dac_cycle;

// Simplified single clock domain with synchronous reset-like behavior
always @(posedge clk_update) begin
    if (clk_init) begin
        // Initialize dac_state to dac_astate when clk_init is high
        dac_state <= dac_astate;
        dac_cycle <= {1'b1, {(15){1'b0}}};  // First bit is 1, others are 0 (MSB first)
    end else begin
        // Update dac_state when clk_init is low
        if (dac_mode == 1) begin
            // Mode 1: Use dac_cycle as one-hot mask to update only the selected bit
            // Update only the bit where dac_cycle has a 1, preserve others
            dac_state <= (dac_state & ~dac_cycle) | (dac_cycle & {16});
            // Right shift the 1 in dac_cycle for next bit position
            dac_cycle <= dac_cycle >> 1;
        end else begin
            // Mode 0: Set dac_state to dac_bstate, don't increment counter
            dac_state <= dac_bstate;
        end
    end
end

endmodule
