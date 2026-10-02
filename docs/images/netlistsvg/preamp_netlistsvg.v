(* blackbox *)
module mos_p (
    input  G,
    input  S,
    output D
);
endmodule

(* blackbox *) module mos_n (
    input  G,
    input  D,
    output S
);
endmodule

(* blackbox *) module vcc (
    output A
);
endmodule

(* blackbox *) module gnd (
    input A
);
endmodule

module preamp_netlistsvg (
    input  inn,
    input  inp,
    input  clk,
    output xp,
    output xn
);
    wire vdd;
    wire vss;
    wire nsrc;

    vcc VDD (.A(vdd));
    gnd VSS (.A(vss));

    mos_p MP1 (
        .G(clk),
        .S(vdd),
        .D(xp)
    );
    mos_p MP2 (
        .G(clk),
        .S(vdd),
        .D(xn)
    );
    mos_n MN1 (
        .G(inn),
        .D(xp),
        .S(nsrc)
    );
    mos_n MN2 (
        .G(inp),
        .D(xn),
        .S(nsrc)
    );
    mos_n MN3 (
        .G(clk),
        .D(nsrc),
        .S(vss)
    );
endmodule
