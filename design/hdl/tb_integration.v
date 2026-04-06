/*
 * Integration Testbench for Co-Simulation
 *
 * Connects the FPGA DAQ core (daq_core), PCB front-end (sediff, THS4541),
 * and single-channel ASIC core (frida_core_1chan). Driven by cocotb via
 * basil's SiSim transfer layer and BasilBusDriver.
 *
 * Signal chain: AWG (cocotb) → vin_se → sediff (SPICE) → vin_p/vin_n → ADC (SPICE)
 * Supplies: PSU (cocotb) → vdd/vss → ASIC + sediff VOCM divider
 *
 * Signal type strategy (see docs/cosim.md §5):
 *   - All analog signals are `real` variables — works with Icarus + spicebind
 *     and is cocotb-accessible via VPI on all simulators.
 *   - For Xcelium AMS, a separate wrapper would add wreal nets and connect
 *     modules. This testbench targets the open-source flow.
 *
 * Clock strategy (follows tj-monopix2 / obelix1 pattern):
 *   - BUS_CLK: input wire, driven by cocotb Clock (160 MHz, 6.25ns period)
 *   - SEQ_CLK: input wire, driven by cocotb Clock (400 MHz, 2.5ns period)
 *   - SPI_CLK: alias of BUS_CLK (matches daq_top.v)
 */

`timescale 1ns / 1ps

module tb_integration(
    // Clocks (driven by cocotb Clock instances)
    input wire          BUS_CLK,
    input wire          SEQ_CLK,

    // Basil bus interface (driven by cocotb BasilBusDriver via SiSim)
    input wire          BUS_RST,
    input wire  [31:0]  BUS_ADD,
    inout wire  [7:0]   BUS_DATA,
    input wire          BUS_RD,
    input wire          BUS_WR,

    // Analog signals (driven by cocotb via instrument mocks)
`ifdef SPICEBIND
    input real          vin_se,         // Single-ended input (from AWG mock)
    input real          vdd,            // Supply (1.2V, from PSU mock)
    input real          vss             // Ground (0V, from PSU mock)
`else
    input wreal         vin_se,
    input wreal         vdd,
    input wreal         vss
`endif
);

    // =========================================================================
    // Clock aliases
    // =========================================================================

    wire SPI_CLK;
    assign SPI_CLK = BUS_CLK;              // SPI uses bus clock (matches daq_top.v)

    // =========================================================================
    // Interconnect: DAQ core <-> ASIC core
    // =========================================================================

    // Sequencer clocks (DAQ -> ASIC)
    wire seq_init, seq_samp, seq_comp, seq_logic;

    // SPI interface (DAQ -> ASIC)
    wire spi_sclk, spi_sdi, spi_sdo, spi_cs_b;

    // Control signals (DAQ -> ASIC)
    wire rst_b;
    wire ampen_b;  // not connected to ASIC, PCB-level signal

    // Comparator output (ASIC -> DAQ)
    wire comp_out;

    // FIFO interface (daq_core internal, directly consumed by fast_spi_rx)
    wire [31:0] fifo_data_out;
    wire        fifo_read_next;
    wire        fifo_empty;

    // Sequencer pattern readback (unused in cosim, tie off)
    wire [3:0] seq_pattern_out;

    // =========================================================================
    // DAQ Core (FPGA side — basil sequencer, SPI, GPIO, pulse_gen, fast_spi_rx)
    // =========================================================================

    daq_core #(
        .ABUSWIDTH(32)
    ) i_daq_core (
        .bus_clk(BUS_CLK),
        .bus_rst(BUS_RST),
        .bus_add(BUS_ADD),
        .bus_data(BUS_DATA),
        .bus_rd(BUS_RD),
        .bus_wr(BUS_WR),

        .seq_clk(SEQ_CLK),             // 400 MHz from cocotb

        .clk_init(seq_init),
        .clk_samp(seq_samp),
        .clk_comp(seq_comp),
        .clk_logic(seq_logic),

        .spi_clk(SPI_CLK),
        .spi_sclk(spi_sclk),
        .spi_sdi(spi_sdi),
        .spi_sdo(spi_sdo),
        .spi_cs_b(spi_cs_b),

        .rst_b(rst_b),
        .ampen_b(ampen_b),

        .fifo_data_out(fifo_data_out),
        .fifo_read_next(1'b0),          // No external FIFO consumer in cosim
        .fifo_empty(fifo_empty),

        .comp_out(comp_out),

        .reset(1'b0),                   // No external reset needed

        .seq_pattern_out(seq_pattern_out),
        .seq_pattern_addr(6'b0)
    );

    // =========================================================================
    // PCB Front-End: Single-Ended to Differential Amplifier (THS4541)
    //
    // Converts the AWG's single-ended output into a differential pair
    // centered at VOCM = VDD/2. Unity gain (Rf/Rin = 499/499).
    // This block is simulated in SPICE via spicebind.
    // =========================================================================

`ifdef SPICEBIND
    wire real vin_p, vin_n;  // Differential outputs from sediff (Icarus wire real extension)
`else
    wreal vin_p, vin_n;
`endif

    sediff i_sediff (
        .vin_p_ext(vin_se),
        .vin_p(vin_p),
        .vin_n(vin_n),
        .vdd(vdd)
    );

    // =========================================================================
    // ASIC Core (single-channel FRIDA with 1 ADC)
    // =========================================================================

    frida_core_1chan i_chip (
        .seq_init(seq_init),
        .seq_samp(seq_samp),
        .seq_comp(seq_comp),
        .seq_logic(seq_logic),

        .spi_sclk(spi_sclk),
        .spi_sdi(spi_sdi),
        .spi_sdo(spi_sdo),
        .spi_cs_b(spi_cs_b),
        .reset_b(rst_b),

        .comp_out(comp_out),

        .vin_p(vin_p),
        .vin_n(vin_n),
        .vdd_a(vdd),
        .vss_a(vss),
        .vdd_d(vdd),
        .vss_d(vss),
        .vdd_dac(vdd),
        .vss_dac(vss)
    );

    // =========================================================================
    // Waveform output (VCD for gtkwave, nutascii .raw from SPICE side)
    // =========================================================================

    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, tb_integration);
    end

endmodule
