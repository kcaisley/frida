/*
 * FRIDA Core Module (Logic Only, No Pads)
 * Contains all the core logic without pad instantiations
 * Used as the main logic block in hierarchical design
 */

module frida_core #(
    parameter integer N_STAGES = 16  // Capacitor stages per ADC; FRIDA has 16
) (
    // Clock inputs (from LVDS RX pads)
    input wire seq_init,
    input wire seq_samp,
    input wire seq_comp,
    input wire seq_logic,

    // SPI interface (from pad I/O)
    input  wire spi_sclk,
    input  wire spi_sdi,
    output wire spi_sdo,
    input  wire spi_cs_b,
    input  wire reset_b,

    // Comparator output (to LVDS TX pad)
`ifdef USE_POWER_PINS
    output wire comp_out,
    input  wire vin_p,     // Positive input
    input  wire vin_n,     // Negative input
    inout  wire vdd_a,     // Analog supply positive
    inout  wire vss_a,     // Analog supply ground
    inout  wire vdd_d,     // Digital supply positive
    inout  wire vss_d,     // Digital supply ground
    inout  wire vdd_dac,   // DAC supply positive
    inout  wire vss_dac    // DAC supply ground
`else
    output wire comp_out
`endif
);

    // SPI register length: four shared DAC state fields, 7 controls for each of
    // the 16 ADCs, and the 4 mux select bits (reduced from 1280 to 180 bits).
    localparam integer SpiBits = 4 * N_STAGES + 16 * 7 + 4;

    // SPI register outputs
    wire [SpiBits-1:0] spi_bits;

    // ADC control signal arrays (16 ADCs)
    wire [15:0] adc_en_init, adc_en_samp_p, adc_en_samp_n, adc_en_comp, adc_en_update;
    wire [15:0] adc_dac_mode, adc_dac_diffcaps;

    // Shared DAC states for all ADCs (4 x N_STAGES bits, 64 on FRIDA)
    wire [N_STAGES-1:0] shared_dac_astate_p, shared_dac_bstate_p;
    wire [N_STAGES-1:0] shared_dac_astate_n, shared_dac_bstate_n;

    wire [15:0] adc_comparator_out;
    wire [3:0] mux_sel;

    // Instantiate SPI register (180-bit control on FRIDA)
    spi_register #(
        .WIDTH(SpiBits)
    ) spi_reg (
        .rst_b   (reset_b),
        .spi_cs_b(spi_cs_b),
        .spi_sdi (spi_sdi),
        .spi_sclk(spi_sclk),
        .spi_sdo (spi_sdo),
        .spi_bits(spi_bits)
    );

    // New optimized SPI bit mapping (180 bits total on FRIDA, N = N_STAGES)
    // Layout: [4N+115:4N+112] mux_sel, [4N+111:4N] per-ADC controls,
    //         [4N-1:0] shared DAC states ([179:176], [175:64], [63:0] for N = 16)

    // Mux selection (4 bits)
    assign mux_sel = spi_bits[SpiBits-1-:4];

    // The serialized fields retain the fabricated wire order, with C0 at the
    // high end. Reverse once here so every internal ADC bus is C0-first at
    // index 0. Per-ADC controls remain direct.
    genvar i;
    generate
        for (i = 0; i < N_STAGES; i = i + 1) begin : g_dac_state_mapping
            assign shared_dac_astate_p[i] = spi_bits[4*N_STAGES-1-i];
            assign shared_dac_bstate_p[i] = spi_bits[3*N_STAGES-1-i];
            assign shared_dac_astate_n[i] = spi_bits[2*N_STAGES-1-i];
            assign shared_dac_bstate_n[i] = spi_bits[N_STAGES-1-i];
        end

        for (i = 0; i < 16; i = i + 1) begin : g_spi_mapping
            localparam integer BASE = 4 * N_STAGES + i * 7;  // Start after shared DAC states

            assign adc_en_init[i]      = spi_bits[BASE+0];
            assign adc_en_samp_p[i]    = spi_bits[BASE+1];
            assign adc_en_samp_n[i]    = spi_bits[BASE+2];
            assign adc_en_comp[i]      = spi_bits[BASE+3];
            assign adc_en_update[i]    = spi_bits[BASE+4];
            assign adc_dac_mode[i]     = spi_bits[BASE+5];
            assign adc_dac_diffcaps[i] = spi_bits[BASE+6];
        end
    endgenerate

    // Instantiate 16 ADC blocks. Synthesis sees the hard macro of adc_macro.v,
    // whose pins are fixed when it is hardened, so that instance takes no
    // parameter (OpenROAD's netlist reader rejects parameterized instances).
    // Simulation passes N_STAGES down to the RTL ADC. Keep complete
    // instances in each preprocessing branch.
    generate
        for (i = 0; i < 16; i = i + 1) begin : g_adc_array
`ifdef SYNTHESIS
            adc adc_inst (
                .seq_init    (seq_init),
                .seq_samp    (seq_samp),
                .seq_comp    (seq_comp),
                .seq_update  (seq_logic),
                .en_init     (adc_en_init[i]),
                .en_samp_p   (adc_en_samp_p[i]),
                .en_samp_n   (adc_en_samp_n[i]),
                .en_comp     (adc_en_comp[i]),
                .en_update   (adc_en_update[i]),
                .dac_mode    (adc_dac_mode[i]),
                .dac_astate_p(shared_dac_astate_p),
                .dac_bstate_p(shared_dac_bstate_p),
                .dac_astate_n(shared_dac_astate_n),
                .dac_bstate_n(shared_dac_bstate_n),
                .dac_diffcaps(adc_dac_diffcaps[i]),
                .comp_out    (adc_comparator_out[i])
            );
`else
            adc #(
                .N_STAGES(N_STAGES)
            ) adc_inst (
                .seq_init    (seq_init),
                .seq_samp    (seq_samp),
                .seq_comp    (seq_comp),
                .seq_update  (seq_logic),
                .en_init     (adc_en_init[i]),
                .en_samp_p   (adc_en_samp_p[i]),
                .en_samp_n   (adc_en_samp_n[i]),
                .en_comp     (adc_en_comp[i]),
                .en_update   (adc_en_update[i]),
                .dac_mode    (adc_dac_mode[i]),
                .dac_astate_p(shared_dac_astate_p),
                .dac_bstate_p(shared_dac_bstate_p),
                .dac_astate_n(shared_dac_astate_n),
                .dac_bstate_n(shared_dac_bstate_n),
                .dac_diffcaps(adc_dac_diffcaps[i]),
                .comp_out    (adc_comparator_out[i])
            );
`endif
        end
    endgenerate

    // Instantiate 16:1 comparator multiplexer
    compmux comp_mux (
        .mux_sel    (mux_sel),
        .adc_comp_in(adc_comparator_out),
        .comp_out   (comp_out)
    );

endmodule
