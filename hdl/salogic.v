// SAR Logic Module - Non-traditional SAR logic implementation
// Inputs: dac_astate (16 bits), dac_bstate (16 bits), dac_mode, comp, clk_init, clk_update


// A potential issues reported by Yosys:
// The SAR logic has two always blocks that can both drive dac_state and dac_cycle, which creates the multiple driver warnings.
// The second always block only executes when clk_init is low, but the synthesis tool doesn't understand this mutual exclusion properly.

module salogic (
    // Clock inputs for Mealy state machine
    input wire clk_init,                    // Initialize signal
    input wire clk_update_p,                // Update signal positive
    input wire clk_update_n,                // Update signal negative

    // Control and data inputs - positive side
    input wire [15:0] dac_astate_p,            // 16 bits input A positive from SPI
    input wire [15:0] dac_bstate_p,            // 16 bits input B positive from SPI
    input wire dac_mode_p,                     // Mode selection positive
    input wire comp_p,                     // Comparator output positive used for state update

    // Control and data inputs - negative side
    input wire [15:0] dac_astate_n,            // 16 bits input A negative from SPI
    input wire [15:0] dac_bstate_n,            // 16 bits input B negative from SPI
    input wire dac_mode_n,                     // Mode selection negative
    input wire comp_n,                     // Comparator output negative used for state update

    // Outputs
    output reg [15:0] dac_state_p,       // Current output register positive
    output reg [15:0] dac_state_n        // Current output register negative
);

// Position counter for tracking which bit to update in dac_state
// Counter width calculated to accommodate 16 bits
reg [15:0] dac_cycle;

// Simplified single clock domain with synchronous reset-like behavior
// Positive side logic
always @(posedge clk_update_p) begin
    if (clk_init) begin
        // Initialize dac_state_p to dac_astate_p when clk_init is high
        dac_state_p <= dac_astate_p;
        dac_cycle <= {1'b1, {(15){1'b0}}};  // First bit is 1, others are 0 (MSB first)
    end else begin
        // Update dac_state_p when clk_init is low
        if (dac_mode_p == 1) begin
            // Mode 1: Use dac_cycle as one-hot mask to update only the selected bit
            // Update only the bit where dac_cycle has a 1, preserve others
            dac_state_p <= (dac_state_p & ~dac_cycle) | (dac_cycle & {16{comp_p}});
            // Right shift the 1 in dac_cycle for next bit position
            dac_cycle <= dac_cycle >> 1;
        end else begin
            // Mode 0: Set dac_state_p to dac_bstate_p, don't increment counter
            dac_state_p <= dac_bstate_p;
        end
    end
end

// Negative side logic
always @(posedge clk_update_n) begin
    if (clk_init) begin
        // Initialize dac_state_n to dac_astate_n when clk_init is high
        dac_state_n <= dac_astate_n;
    end else begin
        // Update dac_state_n when clk_init is low
        if (dac_mode_n == 1) begin
            // Mode 1: Use dac_cycle as one-hot mask to update only the selected bit
            // Update only the bit where dac_cycle has a 1, preserve others
            dac_state_n <= (dac_state_n & ~dac_cycle) | (dac_cycle & {16{comp_n}});
        end else begin
            // Mode 0: Set dac_state_n to dac_bstate_n, don't increment counter
            dac_state_n <= dac_bstate_n;
        end
    end
end

endmodule
