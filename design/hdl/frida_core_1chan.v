/*
 * FRIDA Core Module — Single-Channel Variant for Co-Simulation
 *
 * Identical to frida_core.v but with a single ADC instance instead of 16.
 * The 180-bit SPI register and bit mapping are preserved (uses ADC 0 slice)
 * so the basil host code (Frida class, map_dut.yaml) works unchanged.
 *
 * Analog and supply ports are always present (no USE_POWER_PINS guard)
 * because the co-simulation boundary requires them. Sub-modules
 * (spi_register) also have their supply ports unconditionally.
 *
 * Signal types: all ports are plain `wire`. The real-valued type conversion
 * for analog signals (real -> wreal -> SPICE) is handled in the testbench
 * (integration_top.v) and the adc stub, not here. See docs/cosim.md §5.
 */

`timescale 1ns / 1ps

module frida_core_1chan(
    // Clock inputs (from sequencer / LVDS RX)
    input wire seq_init,
    input wire seq_samp,
    input wire seq_comp,
    input wire seq_logic,

    // SPI interface
    input wire spi_sclk,
    input wire spi_sdi,
    output wire spi_sdo,
    input wire spi_cs_b,
    input wire reset_b,

    // Comparator output
    output wire comp_out,

    // Analog I/O — type depends on cosim flow (see docs/cosim.md §5)
`ifdef COCOTBEXT_AMS
    input wire vin_p, vin_n,
    input wire vdd_a, vss_a,
    input wire vdd_d, vss_d,
    input wire vdd_dac, vss_dac
`elsif SPICEBIND
    input real vin_p, vin_n,
    input real vdd_a, vss_a,
    input real vdd_d, vss_d,
    input real vdd_dac, vss_dac
`else
    input wreal vin_p, vin_n,
    input wreal vdd_a, vss_a,
    input wreal vdd_d, vss_d,
    input wreal vdd_dac, vss_dac
`endif
);

    // SPI register outputs (180 bits, same mapping as 16-ADC version)
    wire [179:0] spi_bits;

    // ADC 0 control signals (extracted from SPI bits)
    wire adc_en_init, adc_en_samp_p, adc_en_samp_n, adc_en_comp, adc_en_update;
    wire adc_dac_mode, adc_dac_diffcaps;

    // Shared DAC states (64 bits)
    wire [15:0] shared_dac_astate_p, shared_dac_bstate_p;
    wire [15:0] shared_dac_astate_n, shared_dac_bstate_n;

    // -------------------------------------------------------------------------
    // SPI Register (USE_POWER_PINS must be defined in the cosim build)
    // -------------------------------------------------------------------------

    spi_register spi_reg (
        .rst_b(reset_b),
        .spi_cs_b(spi_cs_b),
        .spi_sdi(spi_sdi),
        .spi_sclk(spi_sclk),
        .spi_sdo(spi_sdo),
        .spi_bits(spi_bits)
    );

    // -------------------------------------------------------------------------
    // SPI Bit Mapping (identical to frida_core.v, only ADC 0 used)
    // -------------------------------------------------------------------------

    // [179:176] mux_sel — unused with 1 ADC, but preserved for register compat
    // [175:64]  per-ADC controls (7 bits × 16 ADCs), only index 0 wired
    // [63:0]    shared DAC states

    // Shared DAC states
    assign shared_dac_astate_p = spi_bits[63:48];
    assign shared_dac_bstate_p = spi_bits[47:32];
    assign shared_dac_astate_n = spi_bits[31:16];
    assign shared_dac_bstate_n = spi_bits[15:0];

    // Per-ADC control — ADC 0 at BASE = 64
    assign adc_en_init    = spi_bits[64];
    assign adc_en_samp_p  = spi_bits[65];
    assign adc_en_samp_n  = spi_bits[66];
    assign adc_en_comp    = spi_bits[67];
    assign adc_en_update  = spi_bits[68];
    assign adc_dac_mode   = spi_bits[69];
    assign adc_dac_diffcaps = spi_bits[70];

    // -------------------------------------------------------------------------
    // Single ADC Instance
    // -------------------------------------------------------------------------

    adc adc_inst (
        .seq_init(seq_init),
        .seq_samp(seq_samp),
        .seq_comp(seq_comp),
        .seq_update(seq_logic),
        .en_init(adc_en_init),
        .en_samp_p(adc_en_samp_p),
        .en_samp_n(adc_en_samp_n),
        .en_comp(adc_en_comp),
        .en_update(adc_en_update),
        .dac_mode(adc_dac_mode),
        .dac_astate_p(shared_dac_astate_p),
        .dac_bstate_p(shared_dac_bstate_p),
        .dac_astate_n(shared_dac_astate_n),
        .dac_bstate_n(shared_dac_bstate_n),
        .dac_diffcaps(adc_dac_diffcaps),
        .comp_out(comp_out),
        .vin_p(vin_p),
        .vin_n(vin_n),
        .vdd_a(vdd_a),
        .vss_a(vss_a),
        .vdd_d(vdd_d),
        .vss_d(vss_d),
        .vdd_dac(vdd_dac),
        .vss_dac(vss_dac)
    );

endmodule
