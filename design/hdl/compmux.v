/*
 * 16:1 Comparator Output Multiplexer for FRIDA
 * 
 * Selects one of 16 ADC comparator outputs to route to the LVDS TX pad
 * Uses purely combinational logic for minimal propagation delay
 */

module compmux(
    input wire [15:0] adc_comp_in,     // Comparator outputs from 16 ADCs (adc_00 to adc_15)
    input wire [3:0] mux_sel,           // Selection bits from SPI register [179:176]
    output wire comp_out               // Selected output to LVDS TX

    // Power supply signals
    `ifdef USE_POWER_PINS
    ,inout wire vdd_d, vss_d            // Digital supply
    `endif
);

    // 16:1 mux using direct array indexing
    // Synthesizes to identical multiplexer logic as explicit ternary operators
    assign comp_out = adc_comp_in[mux_sel];

endmodule
