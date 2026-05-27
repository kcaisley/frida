`timescale 1ns/1ps

/*
 * 180-bit shift register for ADC control
 * Standard SPI interface (SCLK, SDI, SDO, CS_B)
 *
 * Behavioral RTL implementation for simulation, cosim, and linting.
 *
 * Note: the module remains named spi_register for compatibility with the
 * existing FRIDA hierarchy and to avoid colliding with Basil's module spi.
 */

// verilog_lint: waive-start module-filename
module spi_register (
    input  wire         rst_b,     // Active-low async reset
    input  wire         spi_cs_b,  // SPI chip select (active low)
    input  wire         spi_sdi,   // SPI serial data input (MOSI)
    input  wire         spi_sclk,  // SPI serial clock
    output wire         spi_sdo,   // SPI serial data output (MISO)
    output wire [179:0] spi_bits   // Parallel output of all register bits
);

    reg [179:0] shift_reg;
    assign spi_bits = shift_reg;

    always @(posedge spi_sclk or negedge rst_b) begin
        if (!rst_b) begin
            shift_reg <= 180'b0;
        end else if (!spi_cs_b) begin
            shift_reg <= {shift_reg[178:0], spi_sdi};
        end
    end

    reg spi_sdo_reg;
    assign spi_sdo = spi_sdo_reg;

    always @(negedge spi_sclk or negedge rst_b) begin
        if (!rst_b) begin
            spi_sdo_reg <= 1'b0;
        end else if (!spi_cs_b) begin
            spi_sdo_reg <= shift_reg[179];
        end
    end

endmodule
// verilog_lint: waive-stop module-filename
