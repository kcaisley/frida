(* blackbox *)
module nch_lvt (
    input d,
    input g,
    input s,
    input b
);
endmodule
(* blackbox *) module nch (
    input d,
    input g,
    input s,
    input b
);
endmodule
(* blackbox *) module pch_lvt (
    input d,
    input g,
    input s,
    input b
);
endmodule
(* blackbox *) module capacitor_v (
    input  A,
    output B
);
endmodule

module Comp_netlistsvg (
    inp,
    inn,
    outp,
    outn,
    clk,
    clkb,
    vdd,
    vss
);
    input inp;
    input inn;
    output outp;
    output outn;
    input clk;
    input clkb;
    input vdd;
    input vss;
    wire tail;
    wire preamp_p;
    wire preamp_n;
    wire cap_node;
    wire innerp;
    wire innern;

    nch_lvt Mdiff_p (
        .d(preamp_n),
        .g(inp),
        .s(tail),
        .b(vss)
    );
    nch_lvt Mdiff_n (
        .d(preamp_p),
        .g(inn),
        .s(tail),
        .b(vss)
    );
    nch Mtail (
        .d(tail),
        .g(clk),
        .s(cap_node),
        .b(vss)
    );
    nch Mbias (
        .d(cap_node),
        .g(clkb),
        .s(vss),
        .b(vss)
    );
    capacitor_v Cbias (
        .A(cap_node),
        .B(vss)
    );
    pch_lvt Mrst_p (
        .d(preamp_n),
        .g(clk),
        .s(vdd),
        .b(vdd)
    );
    pch_lvt Mrst_n (
        .d(preamp_p),
        .g(clk),
        .s(vdd),
        .b(vdd)
    );
    pch_lvt Mcross_init_p (
        .d(innerp),
        .g(innern),
        .s(vdd),
        .b(vdd)
    );
    pch_lvt Mcross_init_n (
        .d(innern),
        .g(innerp),
        .s(vdd),
        .b(vdd)
    );
    pch_lvt Minner_init_p (
        .d(innerp),
        .g(clk),
        .s(vdd),
        .b(vdd)
    );
    pch_lvt Minner_init_n (
        .d(innern),
        .g(clk),
        .s(vdd),
        .b(vdd)
    );
    nch_lvt Mcross_on_p (
        .d(innerp),
        .g(innern),
        .s(preamp_p),
        .b(vss)
    );
    nch_lvt Mcross_on_n (
        .d(innern),
        .g(innerp),
        .s(preamp_n),
        .b(vss)
    );
    pch_lvt Mbuf_outp_top (
        .d(outp),
        .g(innern),
        .s(vdd),
        .b(vdd)
    );
    nch_lvt Mbuf_outp_bot (
        .d(outp),
        .g(innern),
        .s(vss),
        .b(vss)
    );
    pch_lvt Mbuf_outn_top (
        .d(outn),
        .g(innerp),
        .s(vdd),
        .b(vdd)
    );
    nch_lvt Mbuf_outn_bot (
        .d(outn),
        .g(innerp),
        .s(vss),
        .b(vss)
    );
endmodule
