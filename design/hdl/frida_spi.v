`timescale 1ns/1ps

/*
 * 180-bit shift register for ADC control
 * Standard SPI interface (SCLK, SDI, SDO, CS_B)
 *
 * Physically implemented FRIDA variant using explicit OPENROAD_* cells for
 * synthesis/P&R experiments. Simulation targets should include behavioral
 * models for the OPENROAD_* cells.
 *
 * Note: the module remains named spi_register so this file can be swapped in
 * for design/hdl/spi.v without changing the surrounding FRIDA hierarchy.
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

    wire [179:0] shift_reg;
    wire enable;
    wire [179:0] d_in;

    assign enable   = !spi_cs_b;
    assign spi_bits = shift_reg;

    genvar i;
    generate
        for (i = 0; i < 180; i = i + 1) begin : g_shift_stage
            assign d_in[i] = (i == 0) ? spi_sdi : shift_reg[i-1];

            OPENROAD_DFFER dff_inst (
                .D(d_in[i]),
                .C(spi_sclk),
                .E(enable),
                .R(rst_b),
                .Q(shift_reg[i])
            );
        end
    endgenerate

    wire spi_sclk_n;

    OPENROAD_CLKINV clk_inv (
        .A(spi_sclk),
        .Y(spi_sclk_n)
    );

    OPENROAD_DFFER sdo_dff (
        .D(shift_reg[179]),
        .C(spi_sclk_n),
        .E(enable),
        .R(rst_b),
        .Q(spi_sdo)
    );

endmodule
// verilog_lint: waive-stop module-filename
