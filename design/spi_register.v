/*
 * 1280-bit SPI Shift Register for FRIDA ADC Control
 * 
 * Reference implementations:
 * - flow/designs/src/spi/spi.v (Embedded Micro, MIT License)
 * - flow/designs/src/chameleon/IPs/APB_SPI.v (Mohamed Shalan)
 * 
 * Features:
 * - 1280-bit shift register for ADC control (16 ADCs x 71 bits + 144 spare bits)  
 * - Standard SPI interface (SCLK, SDI, SDO, CS_B)
 * - Parallel readout of all bits
 * - Readback capability for verification
 */

module spi_register(
    input wire clk,           // System clock
    input wire rst_b,         // Active-low reset
    input wire spi_cs_b,      // SPI chip select (active low) 
    input wire spi_sdi,       // SPI serial data input (MOSI)
    input wire spi_sclk,      // SPI serial clock
    output wire spi_sdo,      // SPI serial data output (MISO)
    output wire [1279:0] spi_bits,  // Parallel output of all register bits
    
    // Power supply signals  
    inout wire vdd_d, vss_d   // Digital supply
);

    // Internal registers
    reg spi_sdi_d, spi_sdi_q;
    reg spi_cs_b_d, spi_cs_b_q;
    reg spi_sclk_d, spi_sclk_q;
    reg spi_sclk_old_d, spi_sclk_old_q;
    reg [1279:0] shift_reg_d, shift_reg_q;
    reg spi_sdo_d, spi_sdo_q;
    reg [10:0] bit_count_d, bit_count_q;  // 11 bits to count up to 1280
    reg transfer_done_d, transfer_done_q;

    // Output assignments
    assign spi_sdo = spi_sdo_q;
    assign spi_bits = shift_reg_q;

    // Combinational logic
    always @(*) begin
        // Default assignments
        spi_cs_b_d = spi_cs_b;
        spi_sdi_d = spi_sdi;
        spi_sdo_d = spi_sdo_q;
        spi_sclk_d = spi_sclk;
        spi_sclk_old_d = spi_sclk_q;
        shift_reg_d = shift_reg_q;
        transfer_done_d = 1'b0;
        bit_count_d = bit_count_q;

        if (spi_cs_b_q) begin
            // Chip select is high (deselected) - reset for next transfer
            bit_count_d = 11'b0;
            spi_sdo_d = shift_reg_q[1279];  // Output MSB
        end else begin
            // Chip select is low (selected) - active transfer
            if (!spi_sclk_old_q && spi_sclk_q) begin  
                // Rising edge of SCLK - shift in data
                shift_reg_d = {shift_reg_q[1278:0], spi_sdi_q};
                bit_count_d = bit_count_q + 1'b1;
                
                if (bit_count_q == 11'd1279) begin
                    // Completed 1280-bit transfer
                    transfer_done_d = 1'b1;
                    bit_count_d = 11'b0;  // Reset for continuous operation
                end
            end else if (spi_sclk_old_q && !spi_sclk_q) begin
                // Falling edge of SCLK - output next bit
                spi_sdo_d = shift_reg_q[1279];
            end
        end
    end

    // Sequential logic
    always @(posedge clk or negedge rst_b) begin
        if (!rst_b) begin
            // Reset all registers
            spi_sdi_q <= 1'b0;
            spi_cs_b_q <= 1'b1;
            spi_sclk_q <= 1'b0;
            spi_sclk_old_q <= 1'b0;
            shift_reg_q <= 1280'b0;
            spi_sdo_q <= 1'b1;  // Idle high
            bit_count_q <= 11'b0;
            transfer_done_q <= 1'b0;
        end else begin
            // Update registers
            spi_sdi_q <= spi_sdi_d;
            spi_cs_b_q <= spi_cs_b_d;
            spi_sclk_q <= spi_sclk_d;
            spi_sclk_old_q <= spi_sclk_old_d;
            shift_reg_q <= shift_reg_d;
            spi_sdo_q <= spi_sdo_d;
            bit_count_q <= bit_count_d;
            transfer_done_q <= transfer_done_d;
        end
    end

endmodule