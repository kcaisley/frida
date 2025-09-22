/*
 * 180-bit SPI Shift Register for FRIDA ADC Control
 * 
 * Reference implementations:
 * - flow/designs/src/spi/spi.v (Embedded Micro, MIT License)
 * - flow/designs/src/chameleon/IPs/APB_SPI.v (Mohamed Shalan)
 * 
 * Features:
 * - 180-bit shift register for ADC control (shared 64-bit DAC states + 16 ADCs x 7 bits + 4-bit mux)  
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
    output wire [179:0] spi_bits   // Parallel output of all register bits (reduced from 1280 to 180)

    // Power supply signals
`ifdef USE_POWER_PINS
    ,inout wire vdd_d, vss_d   // Digital supply
`endif
);

    // Internal registers
    reg spi_sdi_d, spi_sdi_q;
    reg spi_cs_b_d, spi_cs_b_q;
    reg spi_sclk_d, spi_sclk_q;
    reg spi_sclk_old_d, spi_sclk_old_q;
    reg [179:0] shift_reg_d, shift_reg_q;
    reg spi_sdo_d, spi_sdo_q;
    reg [7:0] bit_count_d, bit_count_q;   // 8 bits to count up to 180
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
            bit_count_d = 8'b0;
            spi_sdo_d = shift_reg_q[179];   // Output MSB
        end else begin
            // Chip select is low (selected) - active transfer
            if (!spi_sclk_old_q && spi_sclk_q) begin  
                // Rising edge of SCLK - shift in data
                shift_reg_d = {shift_reg_q[178:0], spi_sdi_q};
                bit_count_d = bit_count_q + 1'b1;
                
                if (bit_count_q == 8'd179) begin
                    // Completed 180-bit transfer
                    transfer_done_d = 1'b1;
                    bit_count_d = 8'b0;  // Reset for continuous operation
                end
            end else if (spi_sclk_old_q && !spi_sclk_q) begin
                // Falling edge of SCLK - output next bit
                spi_sdo_d = shift_reg_q[179];
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
            shift_reg_q <= 180'b0;
            spi_sdo_q <= 1'b1;  // Idle high
            bit_count_q <= 8'b0;
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
