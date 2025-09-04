/*
 * 16:1 Comparator Output Multiplexer for FRIDA
 * 
 * Selects one of 16 ADC comparator outputs to route to the LVDS TX pad
 * Uses purely combinational logic for minimal propagation delay
 */

module compmux(
    input wire [15:0] adc_comp_out,     // Comparator outputs from 16 ADCs (adc_00 to adc_15)
    input wire [3:0] mux_sel,           // Selection bits from SPI register [1139:1136]
    output wire comp_out                // Selected output to LVDS TX
);

    // 16:1 mux implementation using purely combinational logic
    // This will synthesize to multiplexer standard cells with minimal delay
    assign comp_out = (mux_sel == 4'h0) ? adc_comp_out[0] :   // adc_00
                     (mux_sel == 4'h1) ? adc_comp_out[1] :   // adc_01  
                     (mux_sel == 4'h2) ? adc_comp_out[2] :   // adc_02
                     (mux_sel == 4'h3) ? adc_comp_out[3] :   // adc_03
                     (mux_sel == 4'h4) ? adc_comp_out[4] :   // adc_10
                     (mux_sel == 4'h5) ? adc_comp_out[5] :   // adc_11
                     (mux_sel == 4'h6) ? adc_comp_out[6] :   // adc_12
                     (mux_sel == 4'h7) ? adc_comp_out[7] :   // adc_13
                     (mux_sel == 4'h8) ? adc_comp_out[8] :   // adc_20
                     (mux_sel == 4'h9) ? adc_comp_out[9] :   // adc_21
                     (mux_sel == 4'ha) ? adc_comp_out[10] :  // adc_22
                     (mux_sel == 4'hb) ? adc_comp_out[11] :  // adc_23
                     (mux_sel == 4'hc) ? adc_comp_out[12] :  // adc_30
                     (mux_sel == 4'hd) ? adc_comp_out[13] :  // adc_31
                     (mux_sel == 4'he) ? adc_comp_out[14] :  // adc_32
                     (mux_sel == 4'hf) ? adc_comp_out[15] :  // adc_33
                     1'b0;                                   // Safe default

endmodule