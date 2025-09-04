/*
 * FRIDA Core Module (Logic Only, No Pads)
 * Contains all the core logic without pad instantiations
 * Used as the main logic block in hierarchical design
 */

module frida_core(
    // Clock inputs (from pad receivers)
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
    
    // Analog inputs (from pads)
    input wire vin_p,
    input wire vin_n,
    
    // Comparator output (to pad transmitter)
    output wire comp_out
);

    // SPI register outputs
    wire [1279:0] spi_bits;
    
    // ADC control signal arrays (16 ADCs)
    wire [15:0] adc_en_init, adc_en_samp_p, adc_en_samp_n, adc_en_comp, adc_en_update;
    wire [15:0] adc_dac_mode, adc_dac_diffcaps;
    wire [255:0] adc_dac_astate_p, adc_dac_bstate_p;  // 16 ADCs × 16 bits each
    wire [255:0] adc_dac_astate_n, adc_dac_bstate_n;  // 16 ADCs × 16 bits each
    wire [95:0] adc_logic_state_init;                 // 16 ADCs × 6 bits each
    wire [15:0] adc_comparator_out;
    wire [3:0] mux_sel;

    // Instantiate SPI register (1280-bit control)
    spi_register spi_reg (
        .clk(spi_sclk),
        .rst_b(reset_b),
        .spi_cs_b(spi_cs_b),
        .spi_sdi(spi_sdi),
        .spi_sclk(spi_sclk),
        .spi_sdo(spi_sdo),
        .spi_bits(spi_bits)
    );

    // Map SPI bits to ADC control signals (71 bits per ADC)
    genvar i;
    generate
        for (i = 0; i < 16; i = i + 1) begin : spi_mapping
            localparam int BASE = i * 71;
            
            assign adc_en_init[i] = spi_bits[BASE + 0];
            assign adc_en_samp_p[i] = spi_bits[BASE + 1];
            assign adc_en_samp_n[i] = spi_bits[BASE + 2];
            assign adc_en_comp[i] = spi_bits[BASE + 3];
            assign adc_en_update[i] = spi_bits[BASE + 4];
            assign adc_dac_mode[i] = spi_bits[BASE + 5];
            assign adc_dac_diffcaps[i] = spi_bits[BASE + 6];
            assign adc_dac_astate_p[i*16+15:i*16] = spi_bits[BASE + 22:BASE + 7];
            assign adc_dac_bstate_p[i*16+15:i*16] = spi_bits[BASE + 38:BASE + 23];
            assign adc_dac_astate_n[i*16+15:i*16] = spi_bits[BASE + 54:BASE + 39];
            assign adc_dac_bstate_n[i*16+15:i*16] = spi_bits[BASE + 70:BASE + 55];
        end
    endgenerate

    // Logic state initialization - using upper bits of SPI register
    assign adc_logic_state_init = spi_bits[1279:1184]; // 96 bits = 16×6
    
    // Mux selection from remaining bits
    assign mux_sel = spi_bits[1183:1180]; // 4 bits for 16:1 mux

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
                .dac_astate_p(adc_dac_astate_p[i*16+15:i*16]),
                .dac_bstate_p(adc_dac_bstate_p[i*16+15:i*16]),
                .dac_astate_n(adc_dac_astate_n[i*16+15:i*16]),
                .dac_bstate_n(adc_dac_bstate_n[i*16+15:i*16]),
                .dac_diffcaps(adc_dac_diffcaps[i]),
                .vin_p(vin_p),
                .vin_n(vin_n),
                .rst(~reset_b),
                .comp_out(adc_comparator_out[i])
            );
        end
    endgenerate

    // Instantiate 16:1 comparator multiplexer
    compmux comp_mux (
        .mux_sel(mux_sel),
        .adc_comp_out(adc_comparator_out),
        .comp_out(comp_out)
    );

endmodule