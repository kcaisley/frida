/*
 * FRIDA Core Module (Logic Only, No Pads)
 * Contains all the core logic without pad instantiations
 * Used as the main logic block in hierarchical design
 */

module frida_core(
    // Clock inputs (from LVDS RX pads)
    input wire seq_init,
    input wire seq_samp, 
    input wire seq_cmp,
    input wire seq_logic,
    
    // SPI interface (from pad I/O)
    input wire spi_sclk,
    input wire spi_sdi,
    output wire spi_sdo,
    input wire spi_cs_b,
    input wire reset_b,
    
    // Analog inputs (from passive pads)
    inout wire vin_p,
    inout wire vin_n,
    
    // Comparator output (to LVDS TX pad)
    output wire comp_out,
    
    // Power supply signals
    inout wire vdd_a, vss_a,               // Analog supply
    inout wire vdd_d, vss_d,               // Digital supply  
    inout wire vdd_io, vss_io,             // I/O supply
    inout wire vdd_dac, vss_dac            // DAC supply
);

    // SPI register outputs (reduced from 1280 to 180 bits)
    wire [179:0] spi_bits;

    // ADC control signal arrays (16 ADCs)
    wire [15:0] adc_en_init, adc_en_samp_p, adc_en_samp_n, adc_en_comp, adc_en_update;
    wire [15:0] adc_dac_mode, adc_dac_diffcaps;

    // Shared DAC states for all ADCs (64 bits total)
    wire [15:0] shared_dac_astate_p, shared_dac_bstate_p;
    wire [15:0] shared_dac_astate_n, shared_dac_bstate_n;

    wire [15:0] adc_comparator_out;
    wire [3:0] mux_sel;

    // Instantiate SPI register (180-bit control)
    spi_register spi_reg (
        .clk(spi_sclk),
        .rst_b(reset_b),
        .spi_cs_b(spi_cs_b),
        .spi_sdi(spi_sdi),
        .spi_sclk(spi_sclk),
        .spi_sdo(spi_sdo),
        .spi_bits(spi_bits),
        .vdd_d(vdd_d),
        .vss_d(vss_d)
    );

    // New optimized SPI bit mapping (180 bits total)
    // Layout: [179:176] mux_sel, [175:64] per-ADC controls, [63:0] shared DAC states

    // Mux selection (4 bits)
    assign mux_sel = spi_bits[179:176];

    // Shared DAC states for all ADCs (64 bits)
    assign shared_dac_astate_p = spi_bits[63:48];    // 16 bits
    assign shared_dac_bstate_p = spi_bits[47:32];    // 16 bits
    assign shared_dac_astate_n = spi_bits[31:16];    // 16 bits
    assign shared_dac_bstate_n = spi_bits[15:0];     // 16 bits

    // Per-ADC control signals (7 bits per ADC = 112 bits total)
    genvar i;
    generate
        for (i = 0; i < 16; i = i + 1) begin : spi_mapping
            localparam int BASE = 64 + i * 7;  // Start after shared DAC states

            assign adc_en_init[i] = spi_bits[BASE + 0];
            assign adc_en_samp_p[i] = spi_bits[BASE + 1];
            assign adc_en_samp_n[i] = spi_bits[BASE + 2];
            assign adc_en_comp[i] = spi_bits[BASE + 3];
            assign adc_en_update[i] = spi_bits[BASE + 4];
            assign adc_dac_mode[i] = spi_bits[BASE + 5];
            assign adc_dac_diffcaps[i] = spi_bits[BASE + 6];
        end
    endgenerate

    // Instantiate 16 ADC blocks
    generate
        for (i = 0; i < 16; i = i + 1) begin : adc_array
            adc adc_inst (
                .seq_init(seq_init),
                .seq_samp(seq_samp),
                .seq_comp(seq_cmp),
                .seq_update(seq_logic),
                .en_init(adc_en_init[i]),
                .en_samp_p(adc_en_samp_p[i]),
                .en_samp_n(adc_en_samp_n[i]),
                .en_comp(adc_en_comp[i]),
                .en_update(adc_en_update[i]),
                .dac_mode(adc_dac_mode[i]),
                .dac_astate_p(shared_dac_astate_p),
                .dac_bstate_p(shared_dac_bstate_p),
                .dac_astate_n(shared_dac_astate_n),
                .dac_bstate_n(shared_dac_bstate_n),
                .dac_diffcaps(adc_dac_diffcaps[i]),
                .vin_p(vin_p),
                .vin_n(vin_n),
                .comp_out(adc_comparator_out[i]),
                .vdd_a(vdd_a),
                .vss_a(vss_a),
                .vdd_d(vdd_d),
                .vss_d(vss_d),
                .vdd_dac(vdd_dac),
                .vss_dac(vss_dac)
            );
        end
    endgenerate

    // Instantiate 16:1 comparator multiplexer
    compmux comp_mux (
        .mux_sel(mux_sel),
        .adc_comp_out(adc_comparator_out),
        .comp_out(comp_out),
        .vdd_d(vdd_d),
        .vss_d(vss_d)
    );

endmodule
