// FRIDA 65 Chip Core Module
// Top-level core to be instantiated inside pad ring
// Differential LVDS pairs converted to single-ended CMOS by LVDS RX / TX blocks

module core (
    // Sequencing signals (converted from LVDS differential to single-ended)
    input  wire seq_init,      // DAC initialization sequencing
    input  wire seq_samp,      // Sample phase control sequencing  
    input  wire seq_cmp,       // Comparator timing sequencing
    input  wire seq_logic,     // SAR logic timing sequencing
    
    // SPI interface
    input  wire spi_sclk,      // SPI serial clock
    input  wire spi_sdi,       // SPI device input (MOSI)
    output wire spi_sdo,       // SPI master output (MISO)
    input  wire spi_cs_b,      // Chip select (active low)
    
    // Analog inputs
    input  wire vin_p,         // Analog input positive
    input  wire vin_n,         // Analog input negative
    
    // Data output (converted from LVDS differential to single-ended)
    output wire comp_out,      // Data output
    
    // Global reset
    input  wire reset_b        // Global reset (active low)
);




endmodule
