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
 *
 * Post synthesis, we'd like this implementation on a register level:
 *
 *                      ┌──────────────┐
 *    shift_reg[N+1] ──>│D            Q│──> shift_reg[N]
 *                      │              │
 *       !spi_cs_b ────>│E   EDFD2LVT  │
 *                      │              │
 *        spi_sclk ────>│CP            │
 *                      │              │
 *         reset_b ────>│R             │
 *                      └──────────────┘
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
    wire [179:0] shift_reg;

    // Internal connections
    wire enable;          // Enable signal for shift registers
    wire [179:0] d_in;    // Data inputs to each flip-flop

    // Enable is active when CS is low
    assign enable = !spi_cs_b;

    // Output assignments
    assign spi_bits = shift_reg;

    // Generate 180 enabled D flip-flops for shift register
    genvar i;
    generate
        for (i = 0; i < 180; i = i + 1) begin : shift_stage
            // Data input mux: bit 0 gets spi_sdi, other bits get previous stage
            assign d_in[i] = (i == 0) ? spi_sdi : shift_reg[i-1];

            // Instantiate enabled flip-flop with reset (maps to EDFCND2LVT)
            OPENROAD_DFFER dff_inst (
                .D(d_in[i]),
                .C(spi_sclk),
                .E(enable),
                .R(rst_b),
                .Q(shift_reg[i])
            );
        end
    endgenerate

    // Old behavioral code (replaced to avoid NAND gate muxes):
    // always @(posedge spi_sclk or negedge rst_b) begin
    //     if (!rst_b) begin
    //         shift_reg <= 180'b0;
    //     end else if (!spi_cs_b) begin
    //         // Shift operation: MSB shifts left out, LSB shifts in from spi_sdi
    //         shift_reg <= {shift_reg[178:0], spi_sdi};
    //     end
    //     // If spi_cs_b high: hold current value
    // end

    // Output register: negative edge flip-flop for SDO
    // Use inverted clock to achieve negedge behavior
    wire spi_sclk_n;

    OPENROAD_CLKINV clk_inv (
        .A(spi_sclk),
        .Y(spi_sclk_n)
    );

    OPENROAD_DFFER sdo_dff (
        .D(shift_reg[179]),
        .C(spi_sclk_n),      // Inverted clock for negedge behavior
        .E(enable),
        .R(rst_b),
        .Q(spi_sdo)
    );

    // Old behavioral code (replaced to avoid NAND gate muxes):
    // reg spi_sdo_reg;
    // assign spi_sdo = spi_sdo_reg;
    // always @(negedge spi_sclk or negedge rst_b) begin
    //     if (!rst_b) begin
    //         spi_sdo_reg <= 1'b0;
    //     end else if (!spi_cs_b) begin
    //         // Update output with current MSB
    //         spi_sdo_reg <= shift_reg[179];
    //     end
    // end

endmodule
