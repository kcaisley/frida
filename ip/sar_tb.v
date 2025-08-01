// Testbench for SAR Logic Module
`timescale 1ns / 1ps

module sar_tb;

// Parameters
parameter Nbits = 16;
parameter CLK_PERIOD = 10; // 10ns clock period

// Testbench signals
reg seq_init;
reg seq_update;
reg [Nbits-1:0] spi_a;
reg [Nbits-1:0] spi_b;
reg mode;
reg comp;
wire [Nbits-1:0] dac_state;

// Instantiate the SAR logic module
sar_logic #(.Nbits(Nbits)) dut (
    .seq_init(seq_init),
    .seq_update(seq_update),
    .spi_a(spi_a),
    .spi_b(spi_b),
    .mode(mode),
    .comp(comp),
    .dac_state(dac_state)
);

// Access internal dac_cycle for monitoring
wire [Nbits-1:0] dac_cycle = dut.dac_cycle;

// Clock generation helper task
task pulse_seq_init;
begin
    seq_init = 1'b1;
    #CLK_PERIOD;
    seq_init = 1'b0;
    #CLK_PERIOD;
end
endtask

task pulse_seq_update;
begin
    seq_update = 1'b1;
    #CLK_PERIOD;
    seq_update = 1'b0;
    #CLK_PERIOD;
end
endtask

// Test sequence
initial begin
    // Initialize all signals
    seq_init = 1'b0;
    seq_update = 1'b0;
    spi_a = 16'b0;
    spi_b = 16'b0;
    mode = 1'b0;
    comp = 1'b0;
    
    $display("=== SAR Logic Testbench Starting ===");
    $display("Time\t seq_init seq_update mode comp spi_a\t\t spi_b\t\t dac_state\t dac_cycle");
    $monitor("%0t\t %b\t  %b\t    %b    %b   %b %b %b %b", 
             $time, seq_init, seq_update, mode, comp, spi_a, spi_b, dac_state, dac_cycle);
    
    #(2*CLK_PERIOD);
    
    // === TEST 1: Initial setup with alternating patterns ===
    $display("\n=== TEST 1: Setting up initial patterns ===");
    
    // Set spi_a to alternating pattern (10101010...)
    spi_a = 16'b1010101010101010;
    
    // Set spi_b to first half 1's, second half 0's
    spi_b = 16'b1111111100000000;
    
    // Set initial conditions
    comp = 1'b0;
    mode = 1'b0; // Mode 0: dac_state <= spi_b on seq_update
    
    #CLK_PERIOD;
    $display("spi_a set to alternating: %b", spi_a);
    $display("spi_b set to half 1's: %b", spi_b);
    
    // Trigger seq_init - should set dac_state to spi_a
    $display("\n--- Triggering seq_init (should set dac_state = spi_a) ---");
    pulse_seq_init();
    $display("After seq_init: dac_state = %b (expected: %b)", dac_state, spi_a);
    $display("                dac_cycle = %b (expected: MSB set)", dac_cycle);
    
    // Trigger seq_update 3 times in mode 0 - should set dac_state to spi_b each time
    $display("\n--- Triggering seq_update 3x in mode 0 (should set dac_state = spi_b) ---");
    repeat(3) begin
        pulse_seq_update();
        $display("After seq_update: dac_state = %b (expected: %b)", dac_state, spi_b);
    end
    
    // === TEST 2: Auto counting mode ===
    $display("\n=== TEST 2: Auto counting mode (mode = 1) ===");
    
    // Set mode to 1 for auto counting
    mode = 1'b1;
    
    // Set spi_a to all zeros
    spi_a = 16'b0000000000000000;
    
    // Set comp to 1
    comp = 1'b1;
    
    #CLK_PERIOD;
    $display("Mode set to 1 (auto counting)");
    $display("spi_a set to all zeros: %b", spi_a);
    $display("comp set to 1");
    
    // Fire seq_init once - should set dac_state to all zeros and reset counter
    $display("\n--- Triggering seq_init (should reset to spi_a = all zeros) ---");
    pulse_seq_init();
    $display("After seq_init: dac_state = %b (expected: all zeros)", dac_state);
    $display("                dac_cycle = %b (expected: MSB set)", dac_cycle);
    
    // Fire seq_update 20 times - should see bit-by-bit climbing for first 16, then no change
    $display("\n--- Triggering seq_update 20x times (should process MSB to LSB) ---");
    repeat(20) begin
        pulse_seq_update();
        $display("After seq_update: dac_state = %b, dac_cycle = %b", dac_state, dac_cycle);
        
        // Add small delay between updates for clarity
        #(CLK_PERIOD/2);
    end
    
    $display("Final dac_state after 20 updates: %b", dac_state);
    $display("Final dac_cycle after 20 updates: %b", dac_cycle);
    $display("Expected after 16 updates: dac_cycle should be all zeros");
    
    // Fire seq_init one more time - should reset to current spi_a value (all zeros)
    $display("\n--- Final seq_init (should reset to spi_a = all zeros) ---");
    pulse_seq_init();  
    $display("Final dac_state: %b (expected: all zeros)", dac_state);
    $display("Final dac_cycle: %b (expected: MSB set)", dac_cycle);
    
    // === TEST COMPLETE ===
    $display("\n=== Testbench Complete ===");
    #(5*CLK_PERIOD);
    $finish;
end

// Optional: Save waveforms
initial begin
    $dumpfile("sar_tb.vcd");
    $dumpvars(0, sar_tb);
end

endmodule
