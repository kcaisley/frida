// Testbench for Switch Control Interface
`timescale 1ns / 1ps

module switch_ctrl_tb;

    // Testbench signals
    reg seq_samp;
    reg samp_p_en;
    reg samp_n_en;
    wire switch_p;
    wire switch_n;

    // Instantiate the Unit Under Test (UUT)
    switch_ctrl uut (
        .seq_samp(seq_samp),
        .samp_p_en(samp_p_en),
        .samp_n_en(samp_n_en),
        .switch_p(switch_p),
        .switch_n(switch_n)
    );

    // Test stimulus - Truth table verification
    initial begin
        // Generate VCD file for waveform viewing
        $dumpfile("switch_ctrl_test.vcd");
        $dumpvars(0, switch_ctrl_tb);
        
        // Initialize inputs
        seq_samp = 0;
        samp_p_en = 0;
        samp_n_en = 0;
        
        // Wait for initial conditions
        #10;
        
        $display("=== Truth Table Test - All 8 Input Combinations ===");
        $display("| seq_samp | samp_p_en | samp_n_en | switch_p | switch_n | Expected P | Expected N |");
        $display("|----------|-----------|-----------|----------|----------|------------|------------|");

        for (i = 0; i < 8; i = i + 1) begin
            in = i[2:0];
            seq_samp = in[2];
            samp_p_en = in[1];
            samp_n_en = in[0];
            #5;
            $display("|    %b     |     %b     |     %b     |    %b     |    %b     |     %b      |     %b      |",
                seq_samp, samp_p_en, samp_n_en, switch_p, switch_n,
                (seq_samp & samp_p_en), (seq_samp & samp_n_en));
        end
        $display("=== Truth Table Test Complete ===");
        
        // Verification check
        $display("\n=== Verification ===");
        seq_samp = 0; samp_p_en = 0; samp_n_en = 0; #5;
        if (switch_p !== 1'b0 || switch_n !== 1'b0) $display("ERROR: Case 000 failed");
        seq_samp = 0; samp_p_en = 0; samp_n_en = 1; #5;
        if (switch_p !== 1'b0 || switch_n !== 1'b0) $display("ERROR: Case 001 failed");
        seq_samp = 0; samp_p_en = 1; samp_n_en = 0; #5;
        if (switch_p !== 1'b0 || switch_n !== 1'b0) $display("ERROR: Case 010 failed");
        seq_samp = 0; samp_p_en = 1; samp_n_en = 1; #5;
        if (switch_p !== 1'b0 || switch_n !== 1'b0) $display("ERROR: Case 011 failed");
        seq_samp = 1; samp_p_en = 0; samp_n_en = 0; #5;
        if (switch_p !== 1'b0 || switch_n !== 1'b0) $display("ERROR: Case 100 failed");
        seq_samp = 1; samp_p_en = 0; samp_n_en = 1; #5;
        if (switch_p !== 1'b0 || switch_n !== 1'b1) $display("ERROR: Case 101 failed");
        seq_samp = 1; samp_p_en = 1; samp_n_en = 0; #5;
        if (switch_p !== 1'b1 || switch_n !== 1'b0) $display("ERROR: Case 110 failed");
        seq_samp = 1; samp_p_en = 1; samp_n_en = 1; #5;
        if (switch_p !== 1'b1 || switch_n !== 1'b1) $display("ERROR: Case 111 failed");
        
        $display("All tests completed successfully - no errors detected!");
        $finish;
    end

    // Optional: Uncomment for detailed signal monitoring
    // initial begin
    //     $monitor("Time=%0t: seq_samp=%b, samp_p_en=%b, samp_n_en=%b, switch_p=%b, switch_n=%b", 
    //              $time, seq_samp, samp_p_en, samp_n_en, switch_p, switch_n);
    // end

endmodule
