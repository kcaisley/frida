// TSMC65 Cell Mappings for OPENROAD_* Generic Modules
// Maps generic OPENROAD cell names to TSMC65 standard cells

// Generic OPENROAD enabled flip-flop mapped to TSMC65
// TSMC65 has native enabled DFF cells
module OPENROAD_DFFE (D, C, E, Q);
  input D;     // Data input
  input C;     // Clock input
  input E;     // Enable input
  output Q;    // Data output

  // Use TSMC65 enabled D flip-flop
  // EDFD2LVT: Enabled D flip-flop with 2x drive strength
  EDFD2LVT dffe (.D(D), .CP(C), .E(E), .Q(Q));

endmodule

// Generic OPENROAD enabled flip-flop with reset mapped to TSMC65
module OPENROAD_DFFER (D, C, E, R, Q);
  input D;     // Data input
  input C;     // Clock input
  input E;     // Enable input
  input R;     // Active-low async reset
  output Q;    // Data output

  // Use TSMC65 enabled D flip-flop with reset
  // EDFCND2LVT: Enabled D flip-flop with Clear-Direct-Negative (active-low reset)
  EDFCND2LVT dffe (.D(D), .CP(C), .E(E), .CDN(R), .Q(Q));

endmodule

// Generic OPENROAD XOR gate mapped to TSMC65 XOR
module OPENROAD_CLKXOR (A, B, Y);
  input A;     // Input A
  input B;     // Input B
  output Y;    // Output Y = A ^ B

  XOR2D1LVT xor_cell (.A1(A), .A2(B), .Z(Y));

endmodule

// Generic OPENROAD clock buffer mapped to TSMC65 buffer
module OPENROAD_CLKBUF (A, Y);
  input A;     // Input
  output Y;    // Output Y = A

  BUFFD2LVT buf_cell (.I(A), .Z(Y));

endmodule

// Generic OPENROAD clock inverter mapped to TSMC65 inverter
module OPENROAD_CLKINV (A, Y);
  input A;     // Input
  output Y;    // Output Y = ~A

  INVD2LVT inv_cell (.I(A), .ZN(Y));

endmodule

// Custom clock gate module that directly uses TSMC65 clock gate
// This bypasses the OPENROAD_CLKGATE define issues
module OPENROAD_CTRLGATE (CK, E, GCK);
  input CK;   // Clock input
  input E;    // Enable input
  output GCK; // Gated clock output

  // Use TSMC65 latch-based clock gate
  CKLNQD1LVT clkgate_cell (.CP(CK), .E(E), .Q(GCK));

endmodule