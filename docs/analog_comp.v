module comp (inp, inn, outp, outn, clk, clkb, vdd, vss);

    input inp;
    input inn;
    output outp;
    output outn;
    input clk;
    input clkb;
    inout vdd;
    inout vss;

    wire tail;

    nch_lvt M_preamp_diffp (.d(outn), .g(inp), .s(tail), .b(vss));
    nch_lvt M_preamp_diffn (.d(outp), .g(inn), .s(tail), .b(vss));
    nch_lvt M_preamp_tail (.d(tail), .g(clk), .s(vss), .b(vss));
    pch_lvt M_preamp_rstp (.d(outn), .g(clk), .s(vdd), .b(vdd));
    pch_lvt M_preamp_rstn (.d(outp), .g(clk), .s(vdd), .b(vdd));
    pch_lvt Ma_latchp (.d(outn), .g(outp), .s(vdd), .b(vdd));
    pch_lvt Ma_latchn (.d(outp), .g(outn), .s(vdd), .b(vdd));
    nch_lvt Mb_latchp (.d(outn), .g(outp), .s(vss), .b(vss));
    nch_lvt Mb_latchn (.d(outp), .g(outn), .s(vss), .b(vss));
    pch_lvt M_latch_int_rstp (.d(outn), .g(clkb), .s(vdd), .b(vdd));
    pch_lvt M_latch_int_rstn (.d(outp), .g(clkb), .s(vdd), .b(vdd));

endmodule
