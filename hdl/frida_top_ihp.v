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

    // Reserved Pads (for future expansion)
    inout wire cmos_reserved_0_PAD,               // Reserved CMOS pad 0
    inout wire cmos_reserved_1_PAD,               // Reserved CMOS pad 1
    inout wire cmos_reserved_2_PAD,               // Reserved CMOS pad 2
    inout wire cmos_reserved_3_PAD,               // Reserved CMOS pad 3

    // Power Supply Pad Connections (handled by OpenROAD PDN)
`ifdef POWER_PINS
    inout wire vdd_a_PAD, vss_a_PAD,              // Analog supply pads
    inout wire vdd_d_PAD, vss_d_PAD,              // Digital supply pads
    inout wire vdd_io_PAD, vss_io_PAD,            // I/O supply pads
    inout wire vdd_dac_PAD, vss_dac_PAD           // DAC supply pads
`endif
);

    // Core interface signals (directly connected to IO cells)
    wire spi_sclk, spi_sdi, spi_cs_b, spi_sdo;
    wire seq_init_p, seq_init_n, seq_samp_p, seq_samp_n;
    wire seq_cmp_p, seq_cmp_n, seq_logic_p, seq_logic_n;
    wire vin_p, vin_n;
    wire comp_out_p, comp_out_n;

    // Reserved pad output signals (driven high to prevent optimization)
    wire cmos_reserved_0_out = 1'b1;
    wire cmos_reserved_1_out = 1'b1;
    wire cmos_reserved_2_out = 1'b1;
    wire cmos_reserved_3_out = 1'b1;

    // IO Cell Instantiations (matching pad.tcl instance names)

    // SPI Interface - Input pads (directly connected to core)
    sg13g2_IOPadIn sg13g2_IOPad_spi_sdi (
        .pad (spi_sdi_PAD),
        .p2c (spi_sdi)
    );

    sg13g2_IOPadIn sg13g2_IOPad_spi_sclk (
        .pad (spi_sclk_PAD),
        .p2c (spi_sclk)
    );

    sg13g2_IOPadIn sg13g2_IOPad_spi_cs_b (
        .pad (spi_cs_b_PAD),
        .p2c (spi_cs_b)
    );

    // SPI Interface - Output pad
    sg13g2_IOPadOut4mA sg13g2_IOPad_spi_sdo (
        .pad (spi_sdo_PAD),
        .c2p (spi_sdo)
    );

    // Sequencer Control - Input pads (directly connected for differential conversion)
    sg13g2_IOPadIn sg13g2_IOPad_seq_init_p (
        .pad (seq_init_p_PAD),
        .p2c (seq_init_p)
    );

    sg13g2_IOPadIn sg13g2_IOPad_seq_init_n (
        .pad (seq_init_n_PAD),
        .p2c (seq_init_n)
    );

    sg13g2_IOPadIn sg13g2_IOPad_seq_samp_p (
        .pad (seq_samp_p_PAD),
        .p2c (seq_samp_p)
    );

    sg13g2_IOPadIn sg13g2_IOPad_seq_samp_n (
        .pad (seq_samp_n_PAD),
        .p2c (seq_samp_n)
    );

    sg13g2_IOPadIn sg13g2_IOPad_seq_cmp_p (
        .pad (seq_cmp_p_PAD),
        .p2c (seq_cmp_p)
    );

    sg13g2_IOPadIn sg13g2_IOPad_seq_cmp_n (
        .pad (seq_cmp_n_PAD),
        .p2c (seq_cmp_n)
    );

    sg13g2_IOPadIn sg13g2_IOPad_seq_logic_p (
        .pad (seq_logic_p_PAD),
        .p2c (seq_logic_p)
    );

    sg13g2_IOPadIn sg13g2_IOPad_seq_logic_n (
        .pad (seq_logic_n_PAD),
        .p2c (seq_logic_n)
    );

    // Analog Inputs - Use analog passive cells (directly connected to core)
    sg13g2_IOPadAnalog sg13g2_IOPad_vin_p (
        .pad (vin_p_PAD),
        .padres (vin_p)
    );

    sg13g2_IOPadAnalog sg13g2_IOPad_vin_n (
        .pad (vin_n_PAD),
        .padres (vin_n)
    );

    // Comparator Outputs - Output pads (directly connected for differential conversion)
    sg13g2_IOPadOut4mA sg13g2_IOPad_comp_out_p (
        .pad (comp_out_p_PAD),
        .c2p (comp_out_p)
    );

    sg13g2_IOPadOut4mA sg13g2_IOPad_comp_out_n (
        .pad (comp_out_n_PAD),
        .c2p (comp_out_n)
    );

    // Reserved Pads - Output pads driven high (prevents optimization)
    sg13g2_IOPadOut4mA sg13g2_IOPad_cmos_reserved_0 (
        .pad (cmos_reserved_0_PAD),
        .c2p (cmos_reserved_0_out)
    );

    sg13g2_IOPadOut4mA sg13g2_IOPad_cmos_reserved_1 (
        .pad (cmos_reserved_1_PAD),
        .c2p (cmos_reserved_1_out)
    );

    sg13g2_IOPadOut4mA sg13g2_IOPad_cmos_reserved_2 (
        .pad (cmos_reserved_2_PAD),
        .c2p (cmos_reserved_2_out)
    );

    sg13g2_IOPadOut4mA sg13g2_IOPad_cmos_reserved_3 (
        .pad (cmos_reserved_3_PAD),
        .c2p (cmos_reserved_3_out)
    );

`ifdef POWER_PINS
    // Power pads - instantiated but no connections needed
    sg13g2_IOPadVdd sg13g2_IOPad_vdd_a ();
    sg13g2_IOPadVss sg13g2_IOPad_vss_a ();
    sg13g2_IOPadVdd sg13g2_IOPad_vdd_d ();
    sg13g2_IOPadVss sg13g2_IOPad_vss_d ();
    sg13g2_IOPadIOVdd sg13g2_IOPad_vdd_io ();
    sg13g2_IOPadIOVss sg13g2_IOPad_vss_io ();
    sg13g2_IOPadVdd sg13g2_IOPad_vdd_dac ();
    sg13g2_IOPadIOVss sg13g2_IOPad_vss_dac ();
`endif


    // Convert differential signals to single-ended for core
    wire seq_init   = seq_init_p & ~seq_init_n;
    wire seq_samp   = seq_samp_p & ~seq_samp_n;
    wire seq_cmp    = seq_cmp_p  & ~seq_cmp_n;
    wire seq_logic  = seq_logic_p & ~seq_logic_n;

    // Single-ended comparator output from core converted to differential for pads
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