// Rebuild from the repository root:
// yosys -Q -q -p 'read_verilog -lib docs/images/netlistsvg/examples/hierarchy/child.v; read_verilog docs/images/netlistsvg/examples/hierarchy/top.v; prep -top top; techmap; opt; write_json docs/images/netlistsvg/examples/hierarchy/netlist.json'
module top (
    input  wire a,
    b,
    output wire y
);
    child u_child (
        .a(a),
        .b(b),
        .y(y)
    );
endmodule
