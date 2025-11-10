// IHP SG13G2 Cell Mappings for OPENROAD_* Generic Modules
// Maps generic OPENROAD cell names to IHP SG13G2 standard cells

// Generic OPENROAD enabled flip-flop mapped to IHP SG13G2
// Since IHP-SG13G2 doesn't have a native enabled DFF, we implement it with mux + DFF
module OPENROAD_DFFE (D, C, E, Q);
  input D;     // Data input
  input C;     // Clock input
  input E;     // Enable input
  output Q;    // Data output

  wire mux_out;

  // When E=1, pass D; when E=0, pass current Q (feedback for hold)
  sg13g2_mux2_1 enable_mux (.A0(Q), .A1(D), .S(E), .X(mux_out));

  // DFF with RESET_B tied high for no reset
  sg13g2_dfrbp_1 dff_cell (.D(mux_out), .CLK(C), .RESET_B(1'b1), .Q(Q), .Q_N());

endmodule

// Generic OPENROAD XOR gate mapped to IHP SG13G2 XOR
module OPENROAD_CLKXOR (A, B, Y);
  input A;     // Input A
  input B;     // Input B
  output Y;    // Output Y = A ^ B

  sg13g2_xor2_1 xor_cell (.A(A), .B(B), .X(Y));

endmodule

// Generic OPENROAD clock buffer mapped to IHP SG13G2 buffer
module OPENROAD_CLKBUF (A, Y);
  input A;     // Input
  output Y;    // Output Y = A

  sg13g2_buf_2 buf_cell (.A(A), .X(Y));

endmodule

// Generic OPENROAD clock inverter mapped to IHP SG13G2 inverter
module OPENROAD_CLKINV (A, Y);
  input A;     // Input
  output Y;    // Output Y = ~A

  sg13g2_inv_2 inv_cell (.A(A), .Y(Y));

endmodule

// Custom clock gate module that directly uses sg13g2_lgcp_1
// This bypasses the OPENROAD_CLKGATE define issues
module OPENROAD_CTRLGATE (CK, E, GCK);
  input CK;   // Clock input
  input E;    // Enable input
  output GCK; // Gated clock output

  sg13g2_lgcp_1 clkgate_cell (.CLK(CK), .GATE(E), .GCLK(GCK));

endmodule

