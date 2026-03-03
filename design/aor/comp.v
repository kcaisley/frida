// Structural Verilog netlist for FRIDA Strong-ARM comparator
// Generated from hdl21 Comp(CompParams()) compiled with IHP SG13G2 PDK
//
// Topology: single-stage Strong-ARM latch (NMOS input, LVT devices)
// Devices:  sg13_lv_nmos, sg13_lv_pmos (LEF macros in sg13g2_macros.lef)
//
// This is a hand-cleaned version of vlsirtools VerilogNetlister output.
// The auto-generated version errors on h.Port() (direction=NONE) for vdd/vss.
// Here we patch those to inout and simplify the module name.
//
// NOTE: This is a temporary hand-written file for verifying that OpenROAD
// can read our design. The real flow will generate this from hdl21 via
// vlsirtools with a port-direction fixup wrapper.

module Comp
(
  input wire inp,
  input wire inn,
  output wire outp,
  output wire outn,
  input wire clk,
  input wire clkb,
  inout wire vdd,
  inout wire vss
);

  // Internal signals
  wire tail;
  wire outp_int;
  wire outn_int;

  // ── Preamp: NMOS differential pair ──

  sg13_lv_nmos mdiff_p
  (
    .d(outn_int),
    .g(inp),
    .s(tail),
    .b(vss)
  );

  sg13_lv_nmos mdiff_n
  (
    .d(outp_int),
    .g(inn),
    .s(tail),
    .b(vss)
  );

  // ── Preamp: NMOS tail current source (clocked) ──

  sg13_lv_nmos mtail
  (
    .d(tail),
    .g(clk),
    .s(vss),
    .b(vss)
  );

  // ── Preamp: PMOS reset/load devices ──

  sg13_lv_pmos mrst_p
  (
    .d(outn_int),
    .g(clkb),
    .s(vdd),
    .b(vdd)
  );

  sg13_lv_pmos mrst_n
  (
    .d(outp_int),
    .g(clkb),
    .s(vdd),
    .b(vdd)
  );

  // ── Latch: PMOS cross-coupled pair ──

  sg13_lv_pmos ma_p
  (
    .d(outn_int),
    .g(outp_int),
    .s(vdd),
    .b(vdd)
  );

  sg13_lv_pmos ma_n
  (
    .d(outp_int),
    .g(outn_int),
    .s(vdd),
    .b(vdd)
  );

  // ── Latch: NMOS cross-coupled pair ──

  sg13_lv_nmos mb_p
  (
    .d(outn_int),
    .g(outp_int),
    .s(vss),
    .b(vss)
  );

  sg13_lv_nmos mb_n
  (
    .d(outp_int),
    .g(outn_int),
    .s(vss),
    .b(vss)
  );

  // ── Latch: PMOS clocked reset ──

  sg13_lv_pmos mlatch_rst_p
  (
    .d(outn_int),
    .g(clkb),
    .s(vdd),
    .b(vdd)
  );

  sg13_lv_pmos mlatch_rst_n
  (
    .d(outp_int),
    .g(clkb),
    .s(vdd),
    .b(vdd)
  );

  // ── Output buffers: inverter pair ──

  sg13_lv_pmos mbuf_outp_top
  (
    .d(outp),
    .g(outn_int),
    .s(vdd),
    .b(vdd)
  );

  sg13_lv_nmos mbuf_outp_bot
  (
    .d(outp),
    .g(outn_int),
    .s(vss),
    .b(vss)
  );

  sg13_lv_pmos mbuf_outn_top
  (
    .d(outn),
    .g(outp_int),
    .s(vdd),
    .b(vdd)
  );

  sg13_lv_nmos mbuf_outn_bot
  (
    .d(outn),
    .g(outp_int),
    .s(vss),
    .b(vss)
  );

endmodule // Comp