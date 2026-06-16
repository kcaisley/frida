`timescale 1ns/1ps

// Pure-Verilog Icarus testbench for the TSMC65 FRIDA pad-level top.
// Stimulus mirrors flow/scans/basic.py reset/SPI/sequence timing, but runs an
// ADC config-field alignment scan with a simple comparator-clock ADC model.
//
// Compile this bench with frida_spi.v and without adc.v/adc_macro.v; this file
// provides a simulation-only adc wrapper.

module tb_frida_digital;
    localparam integer SPI_BITS        = 180;
    localparam integer SPI_HALF_PERIOD = 50;   // 10 MHz SPI, as in the existing SPICE smoke test
    localparam integer SEQ_STEP_NS     = 10;   // One temporal slot in the 64-step sequencer pattern
    localparam integer NUM_CONFIG_SLOTS = 16;

    // Literal mux code under test. If bit order is reversed relative to the
    // assumed mapping, 4'b0101 will select ADC10 instead of ADC5.
    localparam [3:0] MUX_BITS_UNDER_TEST = 4'b0101;

    // Temporal left-to-right tracks copied from flow/scans/basic.py.
    localparam [63:0] SEQ_INIT_PATTERN  = 64'b0011000000000000000000000000000000000000000000000000000000000000;
    localparam [63:0] SEQ_SAMP_PATTERN  = 64'b0000111100000000000000000000000000000000000000000000000000000000;
    localparam [63:0] SEQ_COMP_PATTERN  = 64'b0000000001010101010101010101010101010101010000000000000000000000;
    localparam [63:0] SEQ_LOGIC_PATTERN = 64'b0001000000101010101010101010101010101010100000000000000000000000;

    reg seq_init_p_PAD;
    reg seq_init_n_PAD;
    reg seq_samp_p_PAD;
    reg seq_samp_n_PAD;
    reg seq_cmp_p_PAD;
    reg seq_cmp_n_PAD;
    reg seq_logic_p_PAD;
    reg seq_logic_n_PAD;

    reg  spi_sclk_PAD;
    reg  spi_sdi_PAD;
    wire spi_sdo_PAD;
    reg  spi_cs_b_PAD;
    reg  rst_b_PAD;

    wire vin_p_PAD = 1'b1;
    wire vin_n_PAD = 1'b0;

    wire comp_out_p_PAD;
    wire comp_out_n_PAD;

    wire passive_reserved_0_PAD;
    wire vdd_a_PAD  = 1'b1;
    wire vss_a_PAD  = 1'b0;
    wire vdd_d_PAD  = 1'b1;
    wire vss_d_PAD  = 1'b0;
    wire vdd_io_PAD = 1'b1;
    wire vss_io_PAD = 1'b0;
    wire vdd_dac_PAD = 1'b1;
    wire vss_dac_PAD = 1'b0;

    reg [SPI_BITS-1:0] spi_config;
    reg capture_comp_edges;
    integer comp_edge_count;
    integer cfg_slot;

    frida_top dut (
        .seq_init_p_PAD(seq_init_p_PAD),
        .seq_init_n_PAD(seq_init_n_PAD),
        .seq_samp_p_PAD(seq_samp_p_PAD),
        .seq_samp_n_PAD(seq_samp_n_PAD),
        .seq_cmp_p_PAD(seq_cmp_p_PAD),
        .seq_cmp_n_PAD(seq_cmp_n_PAD),
        .seq_logic_p_PAD(seq_logic_p_PAD),
        .seq_logic_n_PAD(seq_logic_n_PAD),
        .spi_sclk_PAD(spi_sclk_PAD),
        .spi_sdi_PAD(spi_sdi_PAD),
        .spi_sdo_PAD(spi_sdo_PAD),
        .spi_cs_b_PAD(spi_cs_b_PAD),
        .rst_b_PAD(rst_b_PAD),
        .vin_p_PAD(vin_p_PAD),
        .vin_n_PAD(vin_n_PAD),
        .comp_out_p_PAD(comp_out_p_PAD),
        .comp_out_n_PAD(comp_out_n_PAD),
        .passive_reserved_0_PAD(passive_reserved_0_PAD),
        .vdd_a_PAD(vdd_a_PAD),
        .vss_a_PAD(vss_a_PAD),
        .vdd_d_PAD(vdd_d_PAD),
        .vss_d_PAD(vss_d_PAD),
        .vdd_io_PAD(vdd_io_PAD),
        .vss_io_PAD(vss_io_PAD),
        .vdd_dac_PAD(vdd_dac_PAD),
        .vss_dac_PAD(vss_dac_PAD)
    );

    initial begin
        $dumpfile("build/hdl/tb_frida_digital.vcd");
        $dumpvars(0, tb_frida_digital);

        init_pads();

        $display("[%0t] Reset chip", $time);
        chip_reset();

        $display("[%0t] Mux/config alignment scan: mux code = %04b", $time, MUX_BITS_UNDER_TEST);
        $display("slot  cfg_bits[base+6:base]  adc_en_comp  comp_out_posedges");
        for (cfg_slot = 0; cfg_slot < NUM_CONFIG_SLOTS; cfg_slot = cfg_slot + 1) begin
            build_spi_config(spi_config, cfg_slot, MUX_BITS_UNDER_TEST);

            spi_write_config(spi_config);
            #(10 * SPI_HALF_PERIOD);
            spi_write_config(spi_config);
            #(10 * SPI_HALF_PERIOD);
            check_spi_config(spi_config);

            apply_sequence_once_count_edges();
            $display("%2d    %07b               %016b     %0d  mux[179:176]=%04b bits176..179=%b%b%b%b", cfg_slot,
                     dut.frida_core.spi_bits[64 + cfg_slot * 7 +: 7],
                     dut.frida_core.adc_en_comp,
                     comp_edge_count,
                     dut.frida_core.spi_bits[179:176],
                     dut.frida_core.spi_bits[176], dut.frida_core.spi_bits[177],
                     dut.frida_core.spi_bits[178], dut.frida_core.spi_bits[179]);
            #(10 * SEQ_STEP_NS);
        end

        #(20 * SEQ_STEP_NS);
        $display("[%0t] Done. mux_sel observed at core = %04b", $time, dut.frida_core.mux_sel);
        $finish;
    end

    task init_pads;
        begin
            seq_init_p_PAD  = 1'b0;
            seq_init_n_PAD  = 1'b1;
            seq_samp_p_PAD  = 1'b0;
            seq_samp_n_PAD  = 1'b1;
            seq_cmp_p_PAD   = 1'b0;
            seq_cmp_n_PAD   = 1'b1;
            seq_logic_p_PAD = 1'b0;
            seq_logic_n_PAD = 1'b1;
            spi_sclk_PAD    = 1'b0;
            spi_sdi_PAD     = 1'b0;
            spi_cs_b_PAD    = 1'b1;
            rst_b_PAD       = 1'b0;
            capture_comp_edges = 1'b0;
            comp_edge_count = 0;
        end
    endtask

    task chip_reset;
        begin
            rst_b_PAD = 1'b0;
            #(5 * SPI_HALF_PERIOD);
            rst_b_PAD = 1'b1;
            #(5 * SPI_HALF_PERIOD);
        end
    endtask

    task build_spi_config;
        output [179:0] cfg;
        input integer enabled_cfg_slot;
        input [3:0] mux_bits;
        integer control_bit;
        begin
            cfg = {SPI_BITS{1'b0}};

            // Same DAC values as the first basic.py scan case.
            cfg[63:48]  = 16'b0111111111111111;
            cfg[47:32]  = 16'b1111111111111111;
            cfg[31:16]  = 16'b0111111111111111;
            cfg[15:0]   = 16'b1111111111111111;

            // Enable exactly one 7-bit ADC config field per scan iteration.
            for (control_bit = 0; control_bit < 7; control_bit = control_bit + 1) begin
                cfg[64 + enabled_cfg_slot * 7 + control_bit] = 1'b1;
            end

            cfg[179:176] = mux_bits;
        end
    endtask

    task spi_write_config;
        input [179:0] cfg;
        integer bit_index;
        begin
            spi_cs_b_PAD = 1'b0;
            #(SPI_HALF_PERIOD);
            for (bit_index = SPI_BITS - 1; bit_index >= 0; bit_index = bit_index - 1) begin
                spi_sdi_PAD = cfg[bit_index];
                #(SPI_HALF_PERIOD);
                spi_sclk_PAD = 1'b1;
                #(SPI_HALF_PERIOD);
                spi_sclk_PAD = 1'b0;
            end
            spi_sdi_PAD  = 1'b0;
            #(SPI_HALF_PERIOD);
            spi_cs_b_PAD = 1'b1;
            #(SPI_HALF_PERIOD);
        end
    endtask

    task check_spi_config;
        input [SPI_BITS-1:0] expected;
        begin
            if (dut.frida_core.spi_bits !== expected) begin
                $display("[%0t] ERROR: SPI config mismatch", $time);
                $display("  expected = %045h", expected);
                $display("  observed = %045h", dut.frida_core.spi_bits);
                $fatal;
            end
            $display("[%0t] SPI config loaded: %045h", $time, dut.frida_core.spi_bits);
        end
    endtask

    task apply_sequence_once;
        integer step;
        begin
            for (step = 0; step < 64; step = step + 1) begin
                drive_lvds(seq_init_p_PAD,  seq_init_n_PAD,  SEQ_INIT_PATTERN[63-step]);
                drive_lvds(seq_samp_p_PAD,  seq_samp_n_PAD,  SEQ_SAMP_PATTERN[63-step]);
                drive_lvds(seq_cmp_p_PAD,   seq_cmp_n_PAD,   SEQ_COMP_PATTERN[63-step]);
                drive_lvds(seq_logic_p_PAD, seq_logic_n_PAD, SEQ_LOGIC_PATTERN[63-step]);
                #(SEQ_STEP_NS);
            end
            drive_lvds(seq_init_p_PAD,  seq_init_n_PAD,  1'b0);
            drive_lvds(seq_samp_p_PAD,  seq_samp_n_PAD,  1'b0);
            drive_lvds(seq_cmp_p_PAD,   seq_cmp_n_PAD,   1'b0);
            drive_lvds(seq_logic_p_PAD, seq_logic_n_PAD, 1'b0);
            #(SEQ_STEP_NS);
        end
    endtask

    task apply_sequence_once_count_edges;
        begin
            comp_edge_count = 0;
            capture_comp_edges = 1'b1;
            apply_sequence_once();
            capture_comp_edges = 1'b0;
        end
    endtask

    always @(posedge comp_out_p_PAD) begin
        if (capture_comp_edges) begin
            comp_edge_count = comp_edge_count + 1;
        end
    end

    task drive_lvds;
        output pad_p;
        output pad_n;
        input  value;
        begin
            pad_p = value;
            pad_n = ~value;
        end
    endtask
endmodule

// -----------------------------------------------------------------------------
// Simulation-only ADC macro replacement.
// frida_core instantiates adc macros; for this alignment scan each ADC emits
// seq_comp only when its en_comp config bit is high.
// -----------------------------------------------------------------------------
`ifndef FRIDA_USE_EXTERNAL_ADC_MODEL
module adc (
    input wire seq_init,
    input wire seq_samp,
    input wire seq_comp,
    input wire seq_update,
    input wire en_init,
    input wire en_samp_p,
    input wire en_samp_n,
    input wire en_comp,
    input wire en_update,
    input wire dac_mode,
    input wire [15:0] dac_astate_p,
    input wire [15:0] dac_bstate_p,
    input wire [15:0] dac_astate_n,
    input wire [15:0] dac_bstate_n,
    input wire dac_diffcaps,
    output wire comp_out
);
    assign comp_out = en_comp ? seq_comp : 1'b0;
endmodule
`endif

// -----------------------------------------------------------------------------
// Behavioral TSMC65 pad and OPENROAD helper-cell models for Icarus.
// -----------------------------------------------------------------------------
`ifndef FRIDA_TB_BEHAVIORAL_MODELS
`define FRIDA_TB_BEHAVIORAL_MODELS

module LVDS_RX_CUP_pad (
    input  wire PAD_P,
    input  wire PAD_N,
    output wire O,
    input  wire EN_B
`ifdef USE_POWER_PINS
    ,
    inout wire VDDPST,
    inout wire VSSPST,
    inout wire VDD,
    inout wire VSS
`endif
);
    assign O = EN_B ? 1'b0 : (PAD_P & ~PAD_N);
endmodule

module LVDS_TX_CUP_pad (
    output wire PAD_P,
    output wire PAD_N,
    input  wire I,
    input  wire EN_B,
    input  wire [2:0] DS
`ifdef USE_POWER_PINS
    ,
    inout wire VDDPST,
    inout wire VSSPST,
    inout wire VDD,
    inout wire VSS
`endif
);
    assign PAD_P = EN_B ? 1'bz : I;
    assign PAD_N = EN_B ? 1'bz : ~I;
endmodule

module CMOS_IO_CUP_pad (
    inout  wire PAD,
    input  wire A,
    output wire Z,
    input  wire OUT_EN,
    input  wire PEN,
    input  wire DS,
    output wire Z_h,
    input  wire UD_B
`ifdef USE_POWER_PINS
    ,
    inout wire VDDPST,
    inout wire VSSPST,
    inout wire VDD,
    inout wire VSS
`endif
);
    assign PAD = OUT_EN ? A : 1'bz;
    assign Z   = OUT_EN ? 1'bz : PAD;
    assign Z_h = PAD;
endmodule

module PASSIVE_CUP_pad (
    inout  wire PAD,
    input  wire I,
    output wire O
`ifdef USE_POWER_PINS
    ,
    inout wire VDD,
    inout wire VSS,
    inout wire VDDPST,
    inout wire VSSPST
`endif
);
    assign O = PAD;
endmodule

module POWER_CUP_pad (
`ifdef USE_POWER_PINS
    inout wire VSS,
    inout wire VDD,
    inout wire VDDPST,
    inout wire VSSPST
`endif
);
endmodule

module GROUND_CUP_pad (
`ifdef USE_POWER_PINS
    inout wire VSS,
    inout wire VDD,
    inout wire VDDPST,
    inout wire VSSPST
`endif
);
endmodule

module OPENROAD_DFFE (
    input  wire D,
    input  wire C,
    input  wire E,
    output reg  Q
);
    always @(posedge C) begin
        if (E) begin
            Q <= D;
        end
    end
endmodule

module OPENROAD_DFFER (
    input  wire D,
    input  wire C,
    input  wire E,
    input  wire R,
    output reg  Q
);
    always @(posedge C or negedge R) begin
        if (!R) begin
            Q <= 1'b0;
        end else if (E) begin
            Q <= D;
        end
    end
endmodule

module OPENROAD_CLKXOR (
    input  wire A,
    input  wire B,
    output wire Y
`ifdef USE_POWER_PINS
    ,
    inout wire VDD,
    inout wire VSS
`endif
);
    assign Y = A ^ B;
endmodule

module OPENROAD_CLKBUF (
    input  wire A,
    output wire Y
`ifdef USE_POWER_PINS
    ,
    inout wire VDD,
    inout wire VSS
`endif
);
    assign Y = A;
endmodule

module OPENROAD_CLKINV (
    input  wire A,
    output wire Y
`ifdef USE_POWER_PINS
    ,
    inout wire VDD,
    inout wire VSS
`endif
);
    assign Y = ~A;
endmodule

module OPENROAD_CTRLGATE (
    input  wire CK,
    input  wire E,
    output wire GCK
);
    assign GCK = CK & E;
endmodule
`endif
