// Capacitor Array Module - Analog black box
// Parameterizable capacitive DAC array

/* verilator lint_off UNUSEDSIGNAL */
(* blackbox *)
module caparray #(
    parameter integer N_STAGES = 16  // Capacitor stages; FRIDA has 16
) (
    input  wire                cap_topplate_in,    // Top plate input from the sampling switch
    output wire                cap_topplate_out,   // Top plate output to the comparator
    input  wire [N_STAGES-1:0] cap_botplate_main,  // Stage 0 is C0, the largest capacitor
    input  wire [N_STAGES-1:0] cap_botplate_diff   // Stage N_STAGES-1 is switched last
);

    // Black box - analog implementation
    // This module will be implemented at the analog level

endmodule
