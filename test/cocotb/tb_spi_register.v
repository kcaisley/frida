`timescale 1ns/1ps

module tb_spi_register;
    reg rst_b;
    reg spi_cs_b;
    reg spi_sdi;
    reg spi_sclk;
    wire spi_sdo;
    wire [179:0] spi_bits;

    spi_register dut (
        .rst_b(rst_b),
        .spi_cs_b(spi_cs_b),
        .spi_sdi(spi_sdi),
        .spi_sclk(spi_sclk),
        .spi_sdo(spi_sdo),
        .spi_bits(spi_bits)
    );

    initial begin
        rst_b = 1'b0;
        spi_cs_b = 1'b1;
        spi_sdi = 1'b0;
        spi_sclk = 1'b0;
    end
endmodule
