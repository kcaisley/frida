/*
 * Black box definitions for CUP pad cells
 * These tell Yosys to treat the pads as black boxes during synthesis
 */

(* blackbox *)
module LVDS_RX_CUP_pad(
    inout PAD_P,
    inout PAD_N,
    output O,
    input EN_B,
    inout VDDPST,
    inout VSSPST,
    inout VDD,
    inout VSS
);
endmodule

(* blackbox *)
module LVDS_TX_CUP_pad(
    inout PAD_P,
    inout PAD_N,
    input I,
    input EN_B,
    input [2:0] DS,
    inout VDDPST,
    inout VSSPST,
    inout VDD,
    inout VSS
);
endmodule

(* blackbox *)
module CMOS_IO_CUP_pad(
    inout PAD,
    input A,
    output Z,
    input OUT_EN,
    input PEN,
    inout IO,
    inout VDDPST,
    inout VSSPST,
    inout DS,
    output Z_h,
    input UD_B
);
endmodule

(* blackbox *)
module PASSIVE_CUP_pad(
    inout PAD,
    input I,
    output O,
    inout VDD,
    inout VSS,
    inout VDDPST,
    inout VSSPST
);
endmodule

(* blackbox *)
module POWER_CUP_pad(
    inout VSS,
    inout VDD,
    inout VDDPST,
    inout VSSPST
);
endmodule

(* blackbox *)
module GROUND_CUP_pad(
    inout VSS,
    inout VDD,
    inout VDDPST,
    inout VSSPST
);
endmodule

(* blackbox *)
module SF_CORNER(
    // Physical-only cell, no electrical connections
);
endmodule

(* blackbox *)
module SF_FILLER50_CUP(
    // Physical-only cell, no electrical connections
);
endmodule

(* blackbox *)
module SF_FILLER_CUP(
    // Physical-only cell, no electrical connections
);
endmodule

(* blackbox *)
module POWERCUT_CUP(
    // Physical-only cell, no electrical connections
);
endmodule
