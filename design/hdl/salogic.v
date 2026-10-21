// SAR Logic Module - Non-traditional SAR logic implementation
// Inputs: dac_astate (N_STAGES bits), dac_bstate (N_STAGES bits), dac_mode, comp, clk_init, clk_update

// Include enabled flip-flop cell mapping
//`include "platforms/tsmc65/cells_dffe.v"


// A potential issues reported by Yosys:
// The SAR logic has two always blocks that can both drive dac_state and dac_cycle, which creates the multiple driver warnings.
// The second always block only executes when clk_init is low, but the synthesis tool doesn't understand this mutual exclusion properly.

module salogic #(
    parameter integer N_STAGES = 16  // Capacitor stages, one SAR decision each; FRIDA has 16
) (
    // Clock inputs for Mealy state machine
    input wire clk_init,   // Initialize signal
    input wire clk_update, // Update signal positive

    // Control and data inputs - positive side
    input wire [N_STAGES-1:0] dac_astate_p,  // C0-first A state, positive side
    input wire [N_STAGES-1:0] dac_bstate_p,  // C0-first B state, positive side
    input wire                dac_mode,      // Mode selection (shared for both sides)
    input wire                comp_p,        // Comparator output positive used for state update

    // Control and data inputs - negative side
    input wire [N_STAGES-1:0] dac_astate_n,  // C0-first A state, negative side
    input wire [N_STAGES-1:0] dac_bstate_n,  // C0-first B state, negative side
    input wire                comp_n,        // Comparator output negative used for state update

    // Outputs
    output wire [N_STAGES-1:0] dac_state_p,  // Current output register positive
    output wire [N_STAGES-1:0] dac_state_n   // Current output register negative

    // Power supply signals
`ifdef USE_POWER_PINS
    inout wire vdd_d,  // Digital supply positive
    inout wire vss_d   // Digital supply ground
`endif
);

    // One-hot conversion-stage selector. Stage 0 is the first register and
    // controls C0, the largest capacitor; stage N_STAGES-1 is switched last.
    reg [N_STAGES-1:0] dac_cycle;

    // D input generation for each flip-flop based on control logic
    wire [N_STAGES-1:0] dac_state_p_d, dac_state_n_d;
    wire [N_STAGES-1:0] dac_state_p_en, dac_state_n_en;

    // Generate D inputs according to the logic table:
    // DAC_MODE | SEQ_INIT | D input
    // 0        | 0        | dac_bstate_*
    // 0        | 1        | dac_astate_*
    // 1        | 0        | comp_*
    // 1        | 1        | dac_astate_*
    assign dac_state_p_d = clk_init ? dac_astate_p : (dac_mode ? {N_STAGES{comp_p}} : dac_bstate_p);

    assign dac_state_n_d = clk_init ? dac_astate_n : (dac_mode ? {N_STAGES{comp_n}} : dac_bstate_n);

    // Generate enable signals for each flip-flop:
    // DAC_MODE | SEQ_INIT | E input
    // 0        | 0        | 1 (all bits)
    // 0        | 1        | 1 (all bits)
    // 1        | 0        | dac_cycle (one-hot)
    // 1        | 1        | 1 (all bits)
    assign dac_state_p_en = clk_init ? {N_STAGES{1'b1}} : (dac_mode ? dac_cycle : {N_STAGES{1'b1}});

    assign dac_state_n_en = clk_init ? {N_STAGES{1'b1}} : (dac_mode ? dac_cycle : {N_STAGES{1'b1}});

    // Individual enabled flip-flops for each bit
    genvar i;
    generate
        for (i = 0; i < N_STAGES; i = i + 1) begin : g_dac_ff
            // Explicitly instantiate enabled flip-flops to ensure proper mapping
            OPENROAD_DFFE dac_state_p_ff (
                .D(dac_state_p_d[i]),
                .C(clk_update),
                .E(dac_state_p_en[i]),
                .Q(dac_state_p[i])
            );

            OPENROAD_DFFE dac_state_n_ff (
                .D(dac_state_n_d[i]),
                .C(clk_update),
                .E(dac_state_n_en[i]),
                .Q(dac_state_n[i])
            );
        end
    endgenerate

    // Conversion-stage selector management
    // Runs for exactly N_STAGES cycles after each clk_init, regardless of DAC mode
    // Initialized with stage 0 selected, then advances toward stage N_STAGES-1.
    always @(posedge clk_update) begin
        if (clk_init) begin
            dac_cycle <= {{(N_STAGES - 1) {1'b0}}, 1'b1};
        end else begin
            dac_cycle <= dac_cycle << 1;
        end
    end


endmodule
