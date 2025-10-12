/*
 * 180-bit shift register for ADC control
 * Standard SPI interface (SCLK, SDI, SDO, CS_B)
 *
 *                    spi_bits[179:0]                                  
 *                 ||||||||....||||||||                                
 *               ┌─┴┴┴┴┴┴┴┴────┴┴┴┴┴┴┴┴──┐      ┌───────┐              
 *               | [179][178] ... [1][0] |      | 1-bit |              
 *   spi_sdi ──> |                       |─────>|       | ──> spi_sdo  
 *               └───────────┬───────────┘      └───┬───┘              
 *                           |                      o                  
 *              spi_sclk ────┴──────────────────────┘                  
 */

module spi_register(
    input wire rst_b,         // Active-low async reset
    input wire spi_cs_b,      // SPI chip select (active low)
    input wire spi_sdi,       // SPI serial data input (MOSI)
    input wire spi_sclk,      // SPI serial clock
    output wire spi_sdo,      // SPI serial data output (MISO)
    output wire [179:0] spi_bits   // Parallel output of all register bits

    // Power supply signals
`ifdef USE_POWER_PINS
    ,inout wire vdd_d, vss_d   // Digital supply
`endif
);

    // Shift register storage (180 bits)
    reg [179:0] shift_reg;

    // Output register (separate from shift register)
    reg spi_sdo_reg;

    // Output assignments
    assign spi_sdo = spi_sdo_reg;
    assign spi_bits = shift_reg;

    // Shift register: rising edge shifts data in
    always @(posedge spi_sclk or negedge rst_b) begin
        if (!rst_b) begin
            shift_reg <= 180'b0;
        end else if (!spi_cs_b) begin
            // Shift operation: MSB shifts left out, LSB shifts in from spi_sdi
            shift_reg <= {shift_reg[178:0], spi_sdi};
        end
        // If spi_cs_b high: hold current value
    end

    // Output register: falling edge updates output
    always @(negedge spi_sclk or negedge rst_b) begin
        if (!rst_b) begin
            spi_sdo_reg <= 1'b0;
        end else if (!spi_cs_b) begin
            // Update output with current MSB
            spi_sdo_reg <= shift_reg[179];
        end
    end

endmodule
