// Rebuild from the repository root:
// yosys -Q -q -p 'read_verilog docs/images/netlistsvg/examples/tutorial/ties.v; prep -top ties; write_json docs/images/netlistsvg/examples/tutorial/ties.json'
// npx --yes netlistsvg@1.0.2 docs/images/netlistsvg/examples/tutorial/ties.json --skin docs/images/netlistsvg/style.svg -o docs/images/netlistsvg/examples/tutorial/ties.svg
// python3 docs/images/netlistsvg/postprocess.py docs/images/netlistsvg/examples/tutorial/ties.svg docs/images/netlistsvg/examples/tutorial/ties.json
module ties (
    output wire low,
    high
);
    assign low  = 1'b0;
    assign high = 1'b1;
endmodule
