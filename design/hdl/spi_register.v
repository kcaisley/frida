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
 * Two implementations selected by define:
 *   IMPL       — gate-level with OPENROAD cells (for synthesis/P&R)
 *   BEHAVIORAL — RTL behavioral (for simulation / cosim)
 * If neither is defined, defaults to BEHAVIORAL.
 */

module spi_register(
    input wire rst_b,         // Active-low async reset
    input wire spi_cs_b,      // SPI chip select (active low)
    input wire spi_sdi,       // SPI serial data input (MOSI)
    input wire spi_sclk,      // SPI serial clock
    output wire spi_sdo,      // SPI serial data output (MISO)
    output wire [179:0] spi_bits   // Parallel output of all register bits
);

`ifdef IMPL
    // =================================================================
    // Gate-level implementation (OPENROAD cells)
    // =================================================================

    wire [179:0] shift_reg;
    wire enable;
    wire [179:0] d_in;

    assign enable = !spi_cs_b;
    assign spi_bits = shift_reg;

    genvar i;
    generate
        for (i = 0; i < 180; i = i + 1) begin : shift_stage
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

`else // BEHAVIORAL (default)
    // =================================================================
    // RTL behavioral implementation (simulation / cosim)
    // =================================================================

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

`endif

endmodule
