/*
 * FRIDA Top-Level Module for IHP-SG13G2
 * 1.5mm x 1.5mm Mixed-Signal SAR ADC Array Chip
 *
 * Features:
 * - 16 ADC instances in 4x4 grid
 * - 1280-bit SPI configuration register
 * - 16:1 comparator output multiplexer
 * - IHP-SG13G2 I/O pad ring (pads placed by OpenROAD flow)
 */

module frida_top(
    // I/O Pad connections (must match pad.tcl instance names with _PAD suffix)

    // System Clock and Reset
    inout wire clk_PAD,                           // Main system clock pad
    inout wire reset_b_PAD,                       // Global reset pad (active low)

    // SPI Interface
    inout wire spi_sclk_PAD,                      // SPI serial clock pad
    inout wire spi_sdi_PAD,                       // SPI serial data input pad (MOSI)
    inout wire spi_sdo_PAD,                       // SPI serial data output pad (MISO)
    inout wire spi_cs_b_PAD,                      // SPI chip select pad (active low)

    // Sequencer Control Signals (differential pairs as individual CMOS)
    inout wire seq_init_p_PAD,                    // DAC init positive pad
    inout wire seq_init_n_PAD,                    // DAC init negative pad
    inout wire seq_samp_p_PAD,                    // Sample phase positive pad
    inout wire seq_samp_n_PAD,                    // Sample phase negative pad
    inout wire seq_cmp_p_PAD,                     // Comparator timing positive pad
    inout wire seq_cmp_n_PAD,                     // Comparator timing negative pad
    inout wire seq_logic_p_PAD,                   // SAR logic timing positive pad
    inout wire seq_logic_n_PAD,                   // SAR logic timing negative pad

    // Analog Inputs
    inout wire vin_p_PAD,                         // Analog input positive pad
    inout wire vin_n_PAD,                         // Analog input negative pad

    // Data Output (differential pair as individual CMOS)
    inout wire comp_out_p_PAD,                    // Data output positive pad
    inout wire comp_out_n_PAD,                    // Data output negative pad

    // Power Supply Pad Connections (handled by OpenROAD PDN)
    inout wire vdd_a_PAD, vss_a_PAD,              // Analog supply pads
    inout wire vdd_d_PAD, vss_d_PAD,              // Digital supply pads
    inout wire vdd_io_PAD, vss_io_PAD,            // I/O supply pads
    inout wire vdd_dac_PAD, vss_dac_PAD,          // DAC supply pads
    inout wire extra_vdd_PAD, extra_vss_PAD       // Extra power pads
);

    // Extract core signals from pad connections
    // The OpenROAD flow will automatically connect these signals to the I/O pads

    // Pad-to-core signal assignments
    wire clk = clk_PAD;                           // Clock from pad
    wire reset_b = reset_b_PAD;                   // Reset from pad
    wire spi_sclk = spi_sclk_PAD;                 // SPI clock from pad
    wire spi_sdi = spi_sdi_PAD;                   // SPI data in from pad
    wire spi_cs_b = spi_cs_b_PAD;                 // SPI chip select from pad

    // Sequencer signals from pads
    wire seq_init_p = seq_init_p_PAD;
    wire seq_init_n = seq_init_n_PAD;
    wire seq_samp_p = seq_samp_p_PAD;
    wire seq_samp_n = seq_samp_n_PAD;
    wire seq_cmp_p = seq_cmp_p_PAD;
    wire seq_cmp_n = seq_cmp_n_PAD;
    wire seq_logic_p = seq_logic_p_PAD;
    wire seq_logic_n = seq_logic_n_PAD;

    // Analog inputs from pads
    wire vin_p = vin_p_PAD;
    wire vin_n = vin_n_PAD;

    // Core-to-pad output assignments
    wire spi_sdo;                                 // SPI data out to pad
    wire comp_out_p, comp_out_n;                 // Comparator outputs to pads
    assign spi_sdo_PAD = spi_sdo;
    assign comp_out_p_PAD = comp_out_p;
    assign comp_out_n_PAD = comp_out_n;

    // Convert differential signals to single-ended
    wire seq_init   = seq_init_p & ~seq_init_n;
    wire seq_samp   = seq_samp_p & ~seq_samp_n;
    wire seq_cmp    = seq_cmp_p  & ~seq_cmp_n;
    wire seq_logic  = seq_logic_p & ~seq_logic_n;

    // Single-ended comparator output converted to differential
    wire comp_out;
    assign comp_out_p = comp_out;
    assign comp_out_n = ~comp_out;

    // Power rail connections (handled by PDN)
    wire vdd_a, vss_a, vdd_d, vss_d, vdd_io, vss_io, vdd_dac, vss_dac;

    // Instantiate core logic
    frida_core frida_core (
        .seq_init(seq_init),
        .seq_samp(seq_samp),
        .seq_cmp(seq_cmp),
        .seq_logic(seq_logic),
        .spi_sclk(spi_sclk),
        .spi_sdi(spi_sdi),
        .spi_sdo(spi_sdo),
        .spi_cs_b(spi_cs_b),
        .reset_b(reset_b),
        .vin_p(vin_p),
        .vin_n(vin_n),
        .comp_out(comp_out),
        .vdd_a(vdd_a),
        .vss_a(vss_a),
        .vdd_d(vdd_d),
        .vss_d(vss_d),
        .vdd_io(vdd_io),
        .vss_io(vss_io),
        .vdd_dac(vdd_dac),
        .vss_dac(vss_dac)
    );

endmodule