/*
 * FRIDA Top-Level Module with Pad Ring
 * 1mm x 1mm Mixed-Signal SAR ADC Array Chip
 * 
 * Features:
 * - 16 ADC instances in 4x4 grid (60μm x 60μm each, 100μm spacing)
 * - 1280-bit SPI configuration register
 * - 16:1 comparator output multiplexer  
 * - TSMC65 CUP pad ring with LVDS/CMOS/Analog/Power pads
 */

module frida_top(
    // LVDS Receiver Pads (sequencing clocks)
    input wire seq_init_p_PAD, seq_init_n_PAD,     // DAC initialization sequencing
    input wire seq_samp_p_PAD, seq_samp_n_PAD,     // Sample phase control
    input wire seq_cmp_p_PAD, seq_cmp_n_PAD,       // Comparator timing
    input wire seq_logic_p_PAD, seq_logic_n_PAD,   // SAR logic timing
    
    // CMOS I/O Pads
    inout wire spi_sclk_PAD,                       // SPI serial clock
    inout wire spi_sdi_PAD,                        // SPI serial data input (MOSI)
    inout wire spi_sdo_PAD,                        // SPI serial data output (MISO)
    inout wire spi_cs_b_PAD,                       // SPI chip select (active low)
    inout wire reset_b_PAD,                        // Global reset (active low)
    
    // Analog Input Pads
    inout wire vin_p_PAD,                          // Analog input positive
    inout wire vin_n_PAD,                          // Analog input negative
    
    // LVDS Transmitter Pad (data output)
    output wire comp_out_p_PAD, comp_out_n_PAD,    // Data output differential pair
    
    // Reserved Pads (for future expansion)
    inout wire passive_reserved_0_PAD,             // Reserved passive pad
    inout wire cmos_reserved_1_PAD,                // Reserved CMOS pad 1
    inout wire cmos_reserved_2_PAD,                // Reserved CMOS pad 2
    
    // Power Supply Pads
    inout wire vdd_a_PAD, vss_a_PAD,               // Analog supply
    inout wire vdd_d_PAD, vss_d_PAD,               // Digital supply  
    inout wire vdd_io_PAD, vss_io_PAD,             // I/O supply
    inout wire vdd_dac_PAD, vss_dac_PAD            // DAC supply
);

    // Internal signals from pads to core
    wire seq_init, seq_samp, seq_cmp, seq_logic;
    wire spi_sclk_core, spi_sdi_core, spi_sdo_core, spi_cs_b_core, reset_b_core;
    wire vin_p_core, vin_n_core;
    wire comp_out_core;
    
    // Internal bidirectional pad signals
    wire spi_sclk_int, spi_sdi_int, spi_sdo_int, spi_cs_b_int, reset_b_int;
    wire vin_p_int, vin_n_int;

    // LVDS Receiver Pads for clocks
    LVDS_RX_CUP_pad lvds_seq_init (
        .PAD_P(seq_init_p_PAD),
        .PAD_N(seq_init_n_PAD),
        .O(seq_init),
        .EN_B(1'b0),    // Enable active
        .VDDPST(),      // Connected by abutment
        .VSSPST(),      // Connected by abutment
        .VDD(),         // Connected by abutment
        .VSS()          // Connected by abutment
    );
    
    LVDS_RX_CUP_pad lvds_seq_samp (
        .PAD_P(seq_samp_p_PAD),
        .PAD_N(seq_samp_n_PAD),
        .O(seq_samp),
        .EN_B(1'b0),    // Enable active
        .VDDPST(),      // Connected by abutment
        .VSSPST(),      // Connected by abutment
        .VDD(),         // Connected by abutment
        .VSS()          // Connected by abutment
    );
    
    LVDS_RX_CUP_pad lvds_seq_cmp (
        .PAD_P(seq_cmp_p_PAD),
        .PAD_N(seq_cmp_n_PAD),
        .O(seq_cmp),
        .EN_B(1'b0),    // Enable active
        .VDDPST(),      // Connected by abutment
        .VSSPST(),      // Connected by abutment
        .VDD(),         // Connected by abutment
        .VSS()          // Connected by abutment
    );
    
    LVDS_RX_CUP_pad lvds_seq_logic (
        .PAD_P(seq_logic_p_PAD),
        .PAD_N(seq_logic_n_PAD),
        .O(seq_logic),
        .EN_B(1'b0),    // Enable active
        .VDDPST(),      // Connected by abutment
        .VSSPST(),      // Connected by abutment
        .VDD(),         // Connected by abutment
        .VSS()          // Connected by abutment
    );

    // CMOS I/O Pads
    CMOS_IO_CUP_pad cmos_spi_sclk (
        .PAD(spi_sclk_PAD),
        .A(1'b0),       // Input only
        .Z(spi_sclk_int),
        .OUT_EN(1'b0),  // Output disabled (input mode)
        .PEN(1'b1),     // Pull enable
        .IO(),          // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST(),      // Connected by abutment
        .DS(),          // Connected by abutment
        .Z_h(),         // Not used
        .UD_B(1'b1)     // Pull up/down control
    );
    assign spi_sclk_core = spi_sclk_int;
    
    CMOS_IO_CUP_pad cmos_spi_sdi (
        .PAD(spi_sdi_PAD),
        .A(1'b0),
        .Z(spi_sdi_int),
        .OUT_EN(1'b0),
        .PEN(1'b1),
        .IO(),
        .VDDPST(),
        .VSSPST(),
        .DS(),
        .Z_h(),
        .UD_B(1'b1)
    );
    assign spi_sdi_core = spi_sdi_int;
    
    CMOS_IO_CUP_pad cmos_spi_sdo (
        .PAD(spi_sdo_PAD),
        .A(spi_sdo_core),
        .Z(spi_sdo_int),
        .OUT_EN(1'b1),
        .PEN(1'b1),
        .IO(),
        .VDDPST(),
        .VSSPST(),
        .DS(),
        .Z_h(),
        .UD_B(1'b1)
    );
    
    CMOS_IO_CUP_pad cmos_spi_cs_b (
        .PAD(spi_cs_b_PAD),
        .A(1'b0),
        .Z(spi_cs_b_int),
        .OUT_EN(1'b0),
        .PEN(1'b1),
        .IO(),
        .VDDPST(),
        .VSSPST(),
        .DS(),
        .Z_h(),
        .UD_B(1'b1)
    );
    assign spi_cs_b_core = spi_cs_b_int;
    
    CMOS_IO_CUP_pad cmos_reset_b (
        .PAD(reset_b_PAD),
        .A(1'b0),
        .Z(reset_b_int),
        .OUT_EN(1'b0),
        .PEN(1'b1),
        .IO(),
        .VDDPST(),
        .VSSPST(),
        .DS(),
        .Z_h(),
        .UD_B(1'b1)
    );
    assign reset_b_core = reset_b_int;

    // Analog Input Pads
    PASSIVE_CUP_pad passive_vin_p (
        .PAD(vin_p_PAD),
        .I(1'b0),       // Not used for input pads
        .O(vin_p_int),  // Output to core
        .VDD(),         // Connected by abutment
        .VSS(),         // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST()       // Connected by abutment
    );
    assign vin_p_core = vin_p_int;
    
    PASSIVE_CUP_pad passive_vin_n (
        .PAD(vin_n_PAD),
        .I(1'b0),       // Not used for input pads
        .O(vin_n_int),  // Output to core
        .VDD(),         // Connected by abutment
        .VSS(),         // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST()       // Connected by abutment
    );
    assign vin_n_core = vin_n_int;

    // LVDS Transmitter Pad for output
    LVDS_TX_CUP_pad lvds_comp_out (
        .PAD_P(comp_out_p_PAD),
        .PAD_N(comp_out_n_PAD),
        .I(comp_out_core),
        .EN_B(1'b0),    // Enable active
        .DS(3'b000),    // Drive strength control
        .VDDPST(),      // Connected by abutment
        .VSSPST(),      // Connected by abutment
        .VDD(),         // Connected by abutment
        .VSS()          // Connected by abutment
    );

    // Reserved Pads (no connections for future expansion)
    PASSIVE_CUP_pad passive_reserved_0 (
        .PAD(passive_reserved_0_PAD),
        .I(1'b0),       // Tied off
        .O(),           // Left unconnected
        .VDD(),         // Connected by abutment
        .VSS(),         // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST()       // Connected by abutment
    );
    
    CMOS_IO_CUP_pad cmos_reserved_1 (
        .PAD(cmos_reserved_1_PAD),
        .A(1'b0),       // Tied off
        .Z(),           // Left unconnected
        .OUT_EN(1'b0),  // Output disabled
        .PEN(1'b0),     // Pull disabled
        .IO(),          // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST(),      // Connected by abutment
        .DS(),          // Connected by abutment
        .Z_h(),         // Left unconnected
        .UD_B(1'b0)     // Pull down
    );
    
    CMOS_IO_CUP_pad cmos_reserved_2 (
        .PAD(cmos_reserved_2_PAD),
        .A(1'b0),       // Tied off
        .Z(),           // Left unconnected
        .OUT_EN(1'b0),  // Output disabled
        .PEN(1'b0),     // Pull disabled
        .IO(),          // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST(),      // Connected by abutment
        .DS(),          // Connected by abutment
        .Z_h(),         // Left unconnected
        .UD_B(1'b0)     // Pull down
    );

    // Power Supply Pads
    POWER_CUP_pad power_vdd_a (
        .VSS(),         // Connected by abutment
        .VDD(),         // Connected by abutment  
        .VDDPST(),      // Connected by abutment
        .VSSPST()       // Connected by abutment
    );
    
    GROUND_CUP_pad ground_vss_a (
        .VSS(),         // Connected by abutment
        .VDD(),         // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST()       // Connected by abutment
    );
    
    POWER_CUP_pad power_vdd_d (
        .VSS(),         // Connected by abutment
        .VDD(),         // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST()       // Connected by abutment
    );
    
    GROUND_CUP_pad ground_vss_d (
        .VSS(),         // Connected by abutment
        .VDD(),         // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST()       // Connected by abutment
    );
    
    POWER_CUP_pad power_vdd_io (
        .VSS(),         // Connected by abutment
        .VDD(),         // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST()       // Connected by abutment
    );
    
    GROUND_CUP_pad ground_vss_io (
        .VSS(),         // Connected by abutment
        .VDD(),         // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST()       // Connected by abutment
    );
    
    POWER_CUP_pad power_vdd_dac (
        .VSS(),         // Connected by abutment
        .VDD(),         // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST()       // Connected by abutment
    );
    
    GROUND_CUP_pad ground_vss_dac (
        .VSS(),         // Connected by abutment
        .VDD(),         // Connected by abutment
        .VDDPST(),      // Connected by abutment
        .VSSPST()       // Connected by abutment
    );

    // Instantiate core logic
    frida_core frida_core (
        .seq_init(seq_init),
        .seq_samp(seq_samp),
        .seq_cmp(seq_cmp),
        .seq_logic(seq_logic),
        .spi_sclk(spi_sclk_core),
        .spi_sdi(spi_sdi_core),
        .spi_sdo(spi_sdo_core),
        .spi_cs_b(spi_cs_b_core),
        .reset_b(reset_b_core),
        .vin_p(vin_p_core),
        .vin_n(vin_n_core),
        .comp_out(comp_out_core)
    );

endmodule