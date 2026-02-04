// FRIDA DAQ Core - Simplified diagram version
// Black-box submodules for clean netlist visualization

// ===================================================================
// Black-box stubs for basil modules (diagram only, not synthesizable)
// ===================================================================

module seq_gen (
    input  wire        bus_clk,
    input  wire        bus_rst,
    input  wire [31:0] bus_add,
    inout  wire [7:0]  bus_data,
    input  wire        bus_rd,
    input  wire        bus_wr,

    input  wire        seq_ext_start,
    input  wire        seq_clk,
    output wire [7:0]  seq_out
);
endmodule

module spi (
    input  wire        bus_clk,
    input  wire        bus_rst,
    input  wire [31:0] bus_add,
    inout  wire [7:0]  bus_data,
    input  wire        bus_rd,
    input  wire        bus_wr,

    input  wire        spi_clk,
    output wire        sclk,
    output wire        sdi,
    input  wire        sdo,
    input  wire        ext_start,
    output wire        sen,
    output wire        sld
);
endmodule

module gpio (
    input  wire        bus_clk,
    input  wire        bus_rst,
    input  wire [31:0] bus_add,
    inout  wire [7:0]  bus_data,
    input  wire        bus_rd,
    input  wire        bus_wr,

    inout  wire [7:0]  io
);
endmodule

module pulse_gen (
    input  wire        bus_clk,
    input  wire        bus_rst,
    input  wire [31:0] bus_add,
    inout  wire [7:0]  bus_data,
    input  wire        bus_rd,
    input  wire        bus_wr,

    input  wire        pulse_clk,
    input  wire        ext_start,
    output wire        pulse
);
endmodule

module fast_spi_rx (
    input  wire        bus_clk,
    input  wire        bus_rst,
    input  wire [31:0] bus_add,
    inout  wire [7:0]  bus_data,
    input  wire        bus_rd,
    input  wire        bus_wr,

    input  wire        sclk,
    input  wire        sdi,
    input  wire        sen,

    input  wire        fifo_read,
    output wire        fifo_empty,
    output wire [31:0] fifo_data
);
endmodule

// ===================================================================
// DAQ Core - diagram version
// ===================================================================

module daq_core (
    // Bus interface (from SiTcp / rbcp_to_bus)
    input  wire        bus_clk,
    input  wire        bus_rst,
    input  wire [31:0] bus_add,
    inout  wire [7:0]  bus_data,
    input  wire        bus_rd,
    input  wire        bus_wr,

    // Clocks
    input  wire        seq_clk,
    input  wire        spi_clk,

    // Sequencer outputs -> LVDS to chip
    output wire        clk_init,
    output wire        clk_samp,
    output wire        clk_comp,
    output wire        clk_logic,

    // SPI interface -> chip
    output wire        spi_sclk,
    output wire        spi_sdi,
    input  wire        spi_sdo,
    output wire        spi_cs_b,

    // GPIO -> PCB
    output wire        rst_b,
    output wire        amp_en,

    // comp_out data -> bram_fifo (at top level)
    output wire [31:0] fifo_data_out,
    input  wire        fifo_read_next,
    output wire        fifo_empty,

    // comp_out from LVDS receiver
    input  wire        comp_out,

    // Global reset
    input  wire        reset
);

    // Combined reset
    wire rst;
    assign rst = bus_rst | reset;

    // Internal wires
    wire [7:0] seq_out;
    wire       pulse_out;
    wire       spi_sen;
    wire [7:0] gpio_io;

    // Capture control signals from sequencer
    wire clk_comp_cap;  // seq_out[4] - capture clock for fast_spi_rx
    wire sen_comp;      // seq_out[5] - frame enable for fast_spi_rx

    // 1. Sequencer
    seq_gen inst_seq_gen (
        .bus_clk(bus_clk),
        .bus_rst(rst),
        .bus_add(bus_add),
        .bus_data(bus_data),
        .bus_rd(bus_rd),
        .bus_wr(bus_wr),

        .seq_ext_start(pulse_out),
        .seq_clk(seq_clk),
        .seq_out(seq_out)
    );

    // LVDS clock outputs to chip
    assign clk_init  = seq_out[0];
    assign clk_samp  = seq_out[1];
    assign clk_comp  = seq_out[2];
    assign clk_logic = seq_out[3];

    // Capture control signals
    assign clk_comp_cap = seq_out[4];
    assign sen_comp     = seq_out[5];

    // 2. SPI Master
    spi inst_spi (
        .bus_clk(bus_clk),
        .bus_rst(rst),
        .bus_add(bus_add),
        .bus_data(bus_data),
        .bus_rd(bus_rd),
        .bus_wr(bus_wr),

        .spi_clk(spi_clk),
        .sclk(spi_sclk),
        .sdi(spi_sdi),
        .sdo(spi_sdo),
        .ext_start(1'b0),
        .sen(spi_sen),
        .sld()
    );

    assign spi_cs_b = ~spi_sen;

    // 3. GPIO
    gpio inst_gpio (
        .bus_clk(bus_clk),
        .bus_rst(rst),
        .bus_add(bus_add),
        .bus_data(bus_data),
        .bus_rd(bus_rd),
        .bus_wr(bus_wr),

        .io(gpio_io)
    );

    assign rst_b  = gpio_io[0];
    assign amp_en = gpio_io[1];

    // 4. Pulse Generator
    pulse_gen inst_pulse_gen (
        .bus_clk(bus_clk),
        .bus_rst(rst),
        .bus_add(bus_add),
        .bus_data(bus_data),
        .bus_rd(bus_rd),
        .bus_wr(bus_wr),

        .pulse_clk(seq_clk),
        .ext_start(1'b0),
        .pulse(pulse_out)
    );

    // 5. comp_out Receiver (fast_spi_rx)
    // Captures comp_out using basil's fast_spi_rx module
    // sclk driven by sequencer track 4 (clk_comp_cap)
    // sen driven by sequencer track 5 (sen_comp)
    fast_spi_rx inst_fast_spi_rx (
        .bus_clk(bus_clk),
        .bus_rst(rst),
        .bus_add(bus_add),
        .bus_data(bus_data),
        .bus_rd(bus_rd),
        .bus_wr(bus_wr),

        .sclk(clk_comp_cap),    // Capture clock from sequencer track 4
        .sdi(comp_out),         // Comparator output from chip
        .sen(sen_comp),         // Frame enable from sequencer track 5

        .fifo_read(fifo_read_next),
        .fifo_empty(fifo_empty),
        .fifo_data(fifo_data_out)
    );

endmodule
