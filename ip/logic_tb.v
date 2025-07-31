// Testbench for 8-bit Serial Shift Register with Parallel Load
// Tests SPI configuration interface functionality

`timescale 1ns / 1ps

module logic_tb;

    // Testbench signals
    reg sclk;
    reg sdi;
    wire sdo;
    reg cs_b;
    reg rst;
    wire [7:0] cfg;
    
    // Test data
    reg [7:0] test_data = 8'b10101100;  // Test pattern to shift in
    reg [7:0] expected_cfg;
    integer i;
    
    // Instantiate the Unit Under Test (UUT)
    shift_register_8bit uut (
        .sclk(sclk),
        .sdi(sdi),
        .sdo(sdo),
        .cs_b(cs_b),
        .rst(rst),
        .cfg(cfg)
    );
    
    // Clock generation (10 MHz SPI clock)
    initial begin
        sclk = 0;
        forever #50 sclk = ~sclk;  // 100ns period = 10 MHz
    end
    
    // Test sequence
    initial begin
        // Initialize signals
        rst = 1;
        cs_b = 1;
        sdi = 0;
        expected_cfg = test_data;
        
        $display("Starting SPI Shift Register Testbench");
        $display("Test data to shift in: 8'b%b (0x%02h)", test_data, test_data);
        
        // Wait for a few clock cycles
        #200;
        
        // Release reset
        rst = 0;
        #100;
        
        // Assert chip select (start SPI transaction)
        cs_b = 0;
        $display("Time %0t: CS asserted, starting SPI transaction", $time);
        
        // Wait for one clock edge to stabilize
        @(posedge sclk);
        
        // Shift in test data (MSB first)
        for (i = 7; i >= 0; i = i - 1) begin
            @(negedge sclk);  // Setup data on falling edge
            sdi = test_data[i];
            $display("Time %0t: Shifting bit %0d: %b", $time, i, test_data[i]);
            @(posedge sclk);  // Data clocked in on rising edge
        end
        
        // Wait a bit before deasserting CS
        #50;
        
        // Deassert chip select (triggers parallel load)
        cs_b = 1;
        $display("Time %0t: CS deasserted, parallel load triggered", $time);
        
        // Wait for parallel load to complete
        #100;
        
        // Check results
        $display("\n=== Test Results ===");
        $display("Expected cfg: 8'b%b (0x%02h)", expected_cfg, expected_cfg);
        $display("Actual cfg:   8'b%b (0x%02h)", cfg, cfg);
        
        if (cfg === expected_cfg) begin
            $display("✓ PASS: Configuration register matches expected value!");
        end else begin
            $display("✗ FAIL: Configuration register mismatch!");
            $display("  Expected: 8'b%b", expected_cfg);
            $display("  Got:      8'b%b", cfg);
        end
        
        // Test reset functionality
        $display("\n=== Testing Reset Functionality ===");
        rst = 1;
        #100;
        $display("After reset - cfg: 8'b%b (expected: 8'b00000000)", cfg);
        
        if (cfg === 8'b0) begin
            $display("✓ PASS: Reset functionality works correctly!");
        end else begin
            $display("✗ FAIL: Reset did not clear configuration register!");
        end
        
        rst = 0;
        #100;
        
        // Test another data pattern
        $display("\n=== Testing Second Data Pattern ===");
        test_data = 8'b01010011;  // Different test pattern
        expected_cfg = test_data;
        $display("Test data to shift in: 8'b%b (0x%02h)", test_data, test_data);
        
        cs_b = 0;
        @(posedge sclk);
        
        // Shift in second test data
        for (i = 7; i >= 0; i = i - 1) begin
            @(negedge sclk);
            sdi = test_data[i];
            @(posedge sclk);
        end
        
        #50;
        cs_b = 1;
        #100;
        
        $display("Expected cfg: 8'b%b (0x%02h)", expected_cfg, expected_cfg);
        $display("Actual cfg:   8'b%b (0x%02h)", cfg, cfg);
        
        if (cfg === expected_cfg) begin
            $display("✓ PASS: Second test pattern successful!");
        end else begin
            $display("✗ FAIL: Second test pattern failed!");
        end
        
        // End simulation
        $display("\n=== Testbench Complete ===");
        #200;
        $finish;
    end
    
    // Monitor important signals
    initial begin
        $monitor("Time=%0t rst=%b cs_b=%b sclk=%b sdi=%b sdo=%b cfg=8'b%b", 
                 $time, rst, cs_b, sclk, sdi, sdo, cfg);
    end
    
    // Generate VCD file for waveform viewing
    initial begin
        $dumpfile("logic_tb.vcd");
        $dumpvars(0, logic_tb);
    end

endmodule
