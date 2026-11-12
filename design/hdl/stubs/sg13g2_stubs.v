// Blackbox modules (ports only) of the IHP SG13G2 standard cells and IO pads that
// cells_ihp_sg13g2.v and frida_top_ihp.v instantiate, so the IHP top elaborates without
// the PDK. Ports as in IHP-Open-PDK's sg13g2_stdcell.v and sg13g2_io.v (Apache-2.0).

/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNDRIVEN */

(* blackbox *)
module sg13g2_buf_2 (
    output X,
    input  A
);
endmodule

(* blackbox *)
module sg13g2_inv_2 (
    output Y,
    input  A
);
endmodule

(* blackbox *)
module sg13g2_dfrbp_1 (
    output Q,
    output Q_N,
    input  D,
    input  RESET_B,
    input  CLK
);
endmodule

(* blackbox *)
module sg13g2_lgcp_1 (
    output GCLK,
    input  GATE,
    input  CLK
);
endmodule

(* blackbox *)
module sg13g2_mux2_1 (
    output X,
    input  A0,
    input  A1,
    input  S
);
endmodule

(* blackbox *)
module sg13g2_xor2_1 (
    output X,
    input  A,
    input  B
);
endmodule

(* blackbox *)
module sg13g2_IOPadIn (
    inout  iovdd,
    inout  iovss,
    inout  vdd,
    inout  vss,
    inout  pad,
    output p2c
);
endmodule

(* blackbox *)
module sg13g2_IOPadOut4mA (
    inout iovdd,
    inout iovss,
    inout vdd,
    inout vss,
    inout pad,
    input c2p
);
endmodule

(* blackbox *)
module sg13g2_IOPadAnalog (
    inout iovdd,
    inout iovss,
    inout vdd,
    inout vss,
    inout pad,
    inout padres
);
endmodule

(* blackbox *)
module sg13g2_IOPadIOVdd (
    inout iovdd,
    inout iovss,
    inout vdd,
    inout vss
);
endmodule

(* blackbox *)
module sg13g2_IOPadIOVss (
    inout iovdd,
    inout iovss,
    inout vdd,
    inout vss
);
endmodule

(* blackbox *)
module sg13g2_IOPadVdd (
    inout iovdd,
    inout iovss,
    inout vdd,
    inout vss
);
endmodule

(* blackbox *)
module sg13g2_IOPadVss (
    inout iovdd,
    inout iovss,
    inout vdd,
    inout vss
);
endmodule

/* verilator lint_on UNDRIVEN */
/* verilator lint_on UNUSEDSIGNAL */
