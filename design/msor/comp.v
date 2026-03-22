// Structural Verilog netlist for FRIDA Strong-ARM comparator
// Expanded from comp_latch CDL: each m>1 device is split into
// parallel unit instances sharing the same gate and bulk connections.

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

  wire tail;
  wire outp_int;
  wire outn_int;

  // ── Tail current source: MM0 nch_lvt l=800n w=550n m=1 ──

  sg13_lv_nmos mtail (.d(tail), .g(clk), .s(vss), .b(vss));

  // ── Tail PMOS reset: MM7 pch_lvt l=60n w=500n m=1 ──

  sg13_lv_pmos mtail_rst (.d(tail), .g(clk), .s(vdd), .b(vdd));

  // ── Differential pair: MM1 nch_lvt l=300n w=1.1u m=4 ──

  sg13_lv_nmos mdiff_p1 (.d(outn_int), .g(inp), .s(tail), .b(vss));
  sg13_lv_nmos mdiff_p2 (.d(outn_int), .g(inp), .s(tail), .b(vss));
  sg13_lv_nmos mdiff_p3 (.d(outn_int), .g(inp), .s(tail), .b(vss));
  sg13_lv_nmos mdiff_p4 (.d(outn_int), .g(inp), .s(tail), .b(vss));

  // ── Differential pair: MM2 nch_lvt l=300n w=1.1u m=4 ──

  sg13_lv_nmos mdiff_n1 (.d(outp_int), .g(inn), .s(tail), .b(vss));
  sg13_lv_nmos mdiff_n2 (.d(outp_int), .g(inn), .s(tail), .b(vss));
  sg13_lv_nmos mdiff_n3 (.d(outp_int), .g(inn), .s(tail), .b(vss));
  sg13_lv_nmos mdiff_n4 (.d(outp_int), .g(inn), .s(tail), .b(vss));

  // ── Dummy/bias: MM8[0:3] nch_lvt l=60n w=1.1u m=1 x4 ──

  sg13_lv_nmos mbias1 (.d(tail), .g(vss), .s(vss), .b(vss));
  sg13_lv_nmos mbias2 (.d(tail), .g(vss), .s(vss), .b(vss));
  sg13_lv_nmos mbias3 (.d(tail), .g(vss), .s(vss), .b(vss));
  sg13_lv_nmos mbias4 (.d(tail), .g(vss), .s(vss), .b(vss));

  // ── Preamp PMOS reset: MS1 pch_lvt l=60n w=500n m=2 ──

  sg13_lv_pmos mrst_p1 (.d(outn_int), .g(clk), .s(vdd), .b(vdd));
  sg13_lv_pmos mrst_p2 (.d(outn_int), .g(clk), .s(vdd), .b(vdd));

  // ── Preamp PMOS reset: MS2 pch_lvt l=60n w=500n m=2 ──

  sg13_lv_pmos mrst_n1 (.d(outp_int), .g(clk), .s(vdd), .b(vdd));
  sg13_lv_pmos mrst_n2 (.d(outp_int), .g(clk), .s(vdd), .b(vdd));

  // ── Latch PMOS clocked reset: MS3 pch_lvt l=60n w=500n m=2 ──

  sg13_lv_pmos mlatch_rst_p1 (.d(outn_int), .g(clk), .s(vdd), .b(vdd));
  sg13_lv_pmos mlatch_rst_p2 (.d(outn_int), .g(clk), .s(vdd), .b(vdd));

  // ── Latch PMOS clocked reset: MS4 pch_lvt l=60n w=500n m=2 ──

  sg13_lv_pmos mlatch_rst_n1 (.d(outp_int), .g(clk), .s(vdd), .b(vdd));
  sg13_lv_pmos mlatch_rst_n2 (.d(outp_int), .g(clk), .s(vdd), .b(vdd));

  // ── Latch PMOS cross-coupled: MM5 pch_lvt l=1u w=2u m=2 ──

  sg13_lv_pmos ma_p1 (.d(outn_int), .g(outp_int), .s(vdd), .b(vdd));
  sg13_lv_pmos ma_p2 (.d(outn_int), .g(outp_int), .s(vdd), .b(vdd));

  // ── Latch PMOS cross-coupled: MM6 pch_lvt l=1u w=2u m=2 ──

  sg13_lv_pmos ma_n1 (.d(outp_int), .g(outn_int), .s(vdd), .b(vdd));
  sg13_lv_pmos ma_n2 (.d(outp_int), .g(outn_int), .s(vdd), .b(vdd));

  // ── Latch NMOS cross-coupled: MM3 nch_lvt l=350n w=750n m=4 ──

  sg13_lv_nmos mb_p1 (.d(outn_int), .g(outp_int), .s(vss), .b(vss));
  sg13_lv_nmos mb_p2 (.d(outn_int), .g(outp_int), .s(vss), .b(vss));
  sg13_lv_nmos mb_p3 (.d(outn_int), .g(outp_int), .s(vss), .b(vss));
  sg13_lv_nmos mb_p4 (.d(outn_int), .g(outp_int), .s(vss), .b(vss));

  // ── Latch NMOS cross-coupled: MM4 nch_lvt l=350n w=750n m=4 ──

  sg13_lv_nmos mb_n1 (.d(outp_int), .g(outn_int), .s(vss), .b(vss));
  sg13_lv_nmos mb_n2 (.d(outp_int), .g(outn_int), .s(vss), .b(vss));
  sg13_lv_nmos mb_n3 (.d(outp_int), .g(outn_int), .s(vss), .b(vss));
  sg13_lv_nmos mb_n4 (.d(outp_int), .g(outn_int), .s(vss), .b(vss));

  // ── Output buffers (from comp_inverter_lvil, m=1 each) ──

  sg13_lv_pmos mbuf_outp_top (.d(outp), .g(outn_int), .s(vdd), .b(vdd));
  sg13_lv_nmos mbuf_outp_bot (.d(outp), .g(outn_int), .s(vss), .b(vss));

  sg13_lv_pmos mbuf_outn_top (.d(outn), .g(outp_int), .s(vdd), .b(vdd));
  sg13_lv_nmos mbuf_outn_bot (.d(outn), .g(outp_int), .s(vss), .b(vss));

endmodule
