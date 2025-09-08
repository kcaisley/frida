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
    input wire spi_sclk_PAD,                       // SPI serial clock (input)
    input wire spi_sdi_PAD,                        // SPI serial data input (MOSI)
    output wire spi_sdo_PAD,                       // SPI serial data output (MISO)
    input wire spi_cs_b_PAD,                       // SPI chip select (active low)
    input wire reset_b_PAD,                        // Global reset (active low)
    
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
    wire spi_sclk, spi_sdi, spi_sdo, spi_cs_b, reset_b;
    wire vin_p, vin_n;
    wire comp_out;
    
    // Internal power supply signals
    wire vdd_a, vss_a;               // Analog supply
    wire vdd_d, vss_d;               // Digital supply  
    wire vdd_io, vss_io;             // I/O supply
    wire vdd_dac, vss_dac;           // DAC supply

    // LVDS Receiver Pads for clocks
    LVDS_RX_CUP_pad lvds_seq_init (
        .PAD_P(seq_init_p_PAD),
        .PAD_N(seq_init_n_PAD),
        .O(seq_init),
        .EN_B(1'b0),    // Enable active
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io), // Connected to I/O ground rail
        .VDD(vdd_io),   // Connected to I/O supply
        .VSS(vss_io)    // Connected to I/O supply
    );
    
    LVDS_RX_CUP_pad lvds_seq_samp (
        .PAD_P(seq_samp_p_PAD),
        .PAD_N(seq_samp_n_PAD),
        .O(seq_samp),
        .EN_B(1'b0),    // Enable active
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io), // Connected to I/O ground rail
        .VDD(vdd_io),   // Connected to I/O supply
        .VSS(vss_io)    // Connected to I/O supply
    );
    
    LVDS_RX_CUP_pad lvds_seq_cmp (
        .PAD_P(seq_cmp_p_PAD),
        .PAD_N(seq_cmp_n_PAD),
        .O(seq_cmp),
        .EN_B(1'b0),    // Enable active
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io), // Connected to I/O ground rail
        .VDD(vdd_io),   // Connected to I/O supply
        .VSS(vss_io)    // Connected to I/O supply
    );
    
    LVDS_RX_CUP_pad lvds_seq_logic (
        .PAD_P(seq_logic_p_PAD),
        .PAD_N(seq_logic_n_PAD),
        .O(seq_logic),
        .EN_B(1'b0),    // Enable active
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io), // Connected to I/O ground rail
        .VDD(vdd_io),   // Connected to I/O supply
        .VSS(vss_io)    // Connected to I/O supply
    );

    // CMOS I/O Pads
    CMOS_IO_CUP_pad cmos_spi_sclk (
        .PAD(spi_sclk_PAD),
        .A(1'b0),       // Input only
        .Z(spi_sclk),
        .OUT_EN(1'b0),  // Output disabled (input mode)
        .PEN(1'b1),     // Pull enable
        .IO(vdd_io),    // Connected to I/O supply
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io), // Connected to I/O ground rail
        .DS(1'b0),      // Drive strength control
        .Z_h(),         // Not used
        .UD_B(1'b1)     // Pull up/down control
    );
    
    CMOS_IO_CUP_pad cmos_spi_sdi (
        .PAD(spi_sdi_PAD),
        .A(1'b0),
        .Z(spi_sdi),
        .OUT_EN(1'b0),
        .PEN(1'b1),
        .IO(vdd_io),    // Connected to I/O supply
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io),  // Connected to I/O ground rail
        .DS(),
        .Z_h(),
        .UD_B(1'b1)
    );
    
    CMOS_IO_CUP_pad cmos_spi_sdo (
        .PAD(spi_sdo_PAD),
        .A(spi_sdo),
        .Z(spi_sdo),
        .OUT_EN(1'b1),
        .PEN(1'b1),
        .IO(vdd_io),    // Connected to I/O supply
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io),  // Connected to I/O ground rail
        .DS(),
        .Z_h(),
        .UD_B(1'b1)
    );
    
    CMOS_IO_CUP_pad cmos_spi_cs_b (
        .PAD(spi_cs_b_PAD),
        .A(1'b0),
        .Z(spi_cs_b),
        .OUT_EN(1'b0),
        .PEN(1'b1),
        .IO(vdd_io),    // Connected to I/O supply
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io),  // Connected to I/O ground rail
        .DS(),
        .Z_h(),
        .UD_B(1'b1)
    );
    
    CMOS_IO_CUP_pad cmos_reset_b (
        .PAD(reset_b_PAD),
        .A(1'b0),
        .Z(reset_b),
        .OUT_EN(1'b0),
        .PEN(1'b1),
        .IO(vdd_io),    // Connected to I/O supply
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io),  // Connected to I/O ground rail
        .DS(),
        .Z_h(),
        .UD_B(1'b1)
    );

    // Analog Input Pads
    PASSIVE_CUP_pad passive_vin_p (
        .PAD(vin_p_PAD),
        .I(1'b0),       // Not used for input pads
        .O(vin_p),      // Output to core
        .VDD(vdd_a_PAD), // Connected to analog power PAD
        .VSS(vss_a_PAD), // Connected to analog ground PAD
        .VDDPST(vdd_a),  // Connected to internal analog power rail
        .VSSPST(vss_a)   // Connected to internal analog ground rail
    );
    
    PASSIVE_CUP_pad passive_vin_n (
        .PAD(vin_n_PAD),
        .I(1'b0),       // Not used for input pads
        .O(vin_n),      // Output to core
        .VDD(vdd_a_PAD), // Connected to analog power PAD
        .VSS(vss_a_PAD), // Connected to analog ground PAD
        .VDDPST(vdd_a),  // Connected to internal analog power rail
        .VSSPST(vss_a)   // Connected to internal analog ground rail
    );

    // LVDS Transmitter Pad for output
    LVDS_TX_CUP_pad lvds_comp_out (
        .PAD_P(comp_out_p_PAD),
        .PAD_N(comp_out_n_PAD),
        .I(comp_out),
        .EN_B(1'b0),    // Enable active
        .DS(3'b000),    // Drive strength control
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io), // Connected to I/O ground rail
        .VDD(vdd_io),   // Connected to I/O supply
        .VSS(vss_io)    // Connected to I/O supply
    );

    // Reserved Pads (no connections for future expansion)
    PASSIVE_CUP_pad passive_reserved_0 (
        .PAD(passive_reserved_0_PAD),
        .I(1'b0),       // Tied off
        .O(),           // Left unconnected
        .VDD(vdd_io_PAD), // Connected to I/O power PAD
        .VSS(vss_io_PAD), // Connected to I/O ground PAD
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io)  // Connected to I/O ground rail
    );
    
    CMOS_IO_CUP_pad cmos_reserved_1 (
        .PAD(cmos_reserved_1_PAD),
        .A(1'b0),       // Tied off
        .Z(),           // Left unconnected
        .OUT_EN(1'b0),  // Output disabled
        .PEN(1'b1),     // Pull enabled to prevent floating
        .IO(vdd_io),    // Connected to I/O supply
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io), // Connected to I/O ground rail
        .DS(1'b0),      // Drive strength control
        .Z_h(),         // Left unconnected
        .UD_B(1'b0)     // Pull down
    );
    
    CMOS_IO_CUP_pad cmos_reserved_2 (
        .PAD(cmos_reserved_2_PAD),
        .A(1'b0),       // Tied off
        .Z(),           // Left unconnected
        .OUT_EN(1'b0),  // Output disabled
        .PEN(1'b1),     // Pull enabled to prevent floating
        .IO(vdd_io),    // Connected to I/O supply
        .VDDPST(vdd_io), // Connected to I/O power rail
        .VSSPST(vss_io), // Connected to I/O ground rail
        .DS(1'b0),      // Drive strength control
        .Z_h(),         // Left unconnected
        .UD_B(1'b0)     // Pull down
    );

    // Power distribution is handled through the POWER_CUP_pad and GROUND_CUP_pad instances below

    POWER_CUP_pad power_vdd_a (
        .VSS(vss_a),         // Connected to analog ground rail
        .VDD(vdd_a_PAD),     // Connected to analog power PAD  
        .VDDPST(vdd_a),      // Connected to internal analog rail
        .VSSPST(vss_a)       // Connected to internal analog rail
    );
    
    GROUND_CUP_pad ground_vss_a (
        .VSS(vss_a_PAD),     // Connected to analog ground PAD
        .VDD(vdd_a),         // Connected to analog power rail
        .VDDPST(vdd_a),      // Connected to internal analog rail
        .VSSPST(vss_a)       // Connected to internal analog rail
    );
    
    POWER_CUP_pad power_vdd_d (
        .VSS(vss_d),         // Connected to digital ground rail
        .VDD(vdd_d_PAD),     // Connected to digital power PAD
        .VDDPST(vdd_d),      // Connected to internal digital rail
        .VSSPST(vss_d)       // Connected to internal digital rail
    );
    
    GROUND_CUP_pad ground_vss_d (
        .VSS(vss_d_PAD),     // Connected to digital ground PAD
        .VDD(vdd_d),         // Connected to digital power rail
        .VDDPST(vdd_d),      // Connected to internal digital rail
        .VSSPST(vss_d)       // Connected to internal digital rail
    );
    
    POWER_CUP_pad power_vdd_io (
        .VSS(vss_io),        // Connected to I/O ground rail
        .VDD(vdd_io_PAD),    // Connected to I/O power PAD
        .VDDPST(vdd_io),     // Connected to internal I/O rail
        .VSSPST(vss_io)      // Connected to internal I/O rail
    );
    
    GROUND_CUP_pad ground_vss_io (
        .VSS(vss_io_PAD),    // Connected to I/O ground PAD
        .VDD(vdd_io),        // Connected to I/O power rail
        .VDDPST(vdd_io),     // Connected to internal I/O rail
        .VSSPST(vss_io)      // Connected to internal I/O rail
    );
    
    POWER_CUP_pad power_vdd_dac (
        .VSS(vss_dac),       // Connected to DAC ground rail
        .VDD(vdd_dac_PAD),   // Connected to DAC power PAD
        .VDDPST(vdd_dac),    // Connected to internal DAC rail
        .VSSPST(vss_dac)     // Connected to internal DAC rail
    );
    
    GROUND_CUP_pad ground_vss_dac (
        .VSS(vss_dac_PAD),   // Connected to DAC ground PAD
        .VDD(vdd_dac),       // Connected to DAC power rail
        .VDDPST(vdd_dac),    // Connected to internal DAC rail
        .VSSPST(vss_dac)     // Connected to internal DAC rail
    );

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