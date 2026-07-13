// FRIDA DAQ Core
//
// Basil-based core module for the FRIDA ADC test chip DAQ system.
// Instantiates the functional blocks needed to control the chip
// and read back data:
//
//   1. seq_gen      - 64-bit physical sequencer. Byte lanes [0-3] are
//                     serialized in daq_top for the LVDS ADC timing inputs;
//                     bits 32 and 33 carry FastRX SEN and loopback test data.
//   2. spi          - SPI master for 180-bit chip configuration register
//                     (SPI_SCLK, SPI_SDI, SPI_SDO, SPI_CS_B)
//   3. gpio         - GPIO for PCB control signals (RST_B, AMPEN_B)
//   4. fast_spi_rx  - COMP_OUT receiver using basil fast_spi_rx module
//
// Address map (matches map_fpga.yaml):
//   0x8000      - bram_fifo control  (instantiated at top level)
//   0x80000000  - bram_fifo data     (instantiated at top level)
//   0x10000     - seq_gen
//   0x20000     - spi
//   0x30000     - gpio0: board and FastRX controls
//   0x40000     - fast_spi_rx
//   0x50000     - gpio1: comparator IDELAY controls and ready status

`timescale 1ns / 10ps

// Basil functional modules (direct children of daq_core)
`include "seq_gen/seq_gen.v"
`include "spi/spi.v"
`include "gpio/gpio.v"
`include "fast_spi_rx/fast_spi_rx.v"

module daq_core #(
    parameter integer ABUSWIDTH = 32
) (
    // Bus interface (directly from rbcp_to_bus / SiTcp)
    input wire                 BUS_CLK,
    input wire                 BUS_RST,
    input wire [ABUSWIDTH-1:0] BUS_ADD,
    inout wire [          7:0] BUS_DATA,
    input wire                 BUS_RD,
    input wire                 BUS_WR,

    // Sequencer word clock from the PLL: 200 MHz, 5 ns period.
    input wire SEQ_CLK,

    // Packed serializer word. Byte lanes [0:3] carry INIT/SAMP/COMP/LOGIC;
    // bits 32 and 33 carry FastRX SEN and loopback test data.
    output wire [63:0] SEQ_SER_DATA,

    // SPI interface -> chip carrier PCB
    input  wire SPI_CLK,   // SPI shift clock
    output wire SPI_SCLK,  // SPI clock to chip
    output wire SPI_SDI,   // SPI data to chip (MOSI)
    input  wire SPI_SDO,   // SPI data from chip (MISO)
    output wire SPI_CS_B,  // SPI chip select (active low)

    // GPIO -> PCB control signals
    output wire RST_B,   // Chip reset (active low)
    output wire AMPEN_B, // Input amplifier enable (active low)

    // GPIO1 -> comparator input-delay control
    output wire [4:0] COMP_IDELAY_TAPS,
    output wire       COMP_IDELAY_LOAD,
    input  wire       COMP_IDELAY_RDY,

    // comp_out data -> bram_fifo (instantiated at top level)
    // The fast_spi_rx module captures the 1-bit comparator output stream,
    // packs it into 32-bit words, and presents them as a FIFO source.
    output wire [31:0] FASTRX_FIFO_DATA_OUT,
    input  wire        FASTRX_FIFO_READ_NEXT,
    output wire        FASTRX_FIFO_EMPTY,

    // Comparator output from LVDS receiver
    input wire COMP_OUT,

    // Global reset (independent of BUS_RST, e.g. PLL not locked)
    input wire RESET,

    // LED output
    output wire [7:0] LED_OUT

);

    // Address map (matching map_fpga.yaml)
    localparam integer SeqGenBaseAddr = 32'h10000;
    localparam integer SeqGenHighAddr = 32'h1FFFF;

    localparam integer SpiBaseAddr = 32'h20000;
    localparam integer SpiHighAddr = 32'h200FF;

    localparam integer GpioBaseAddr = 32'h30000;
    localparam integer GpioHighAddr = 32'h300FF;

    localparam integer FastSpiRxBaseAddr = 32'h40000;
    localparam integer FastSpiRxHighAddr = 32'h400FF;

    localparam integer Gpio1BaseAddr = 32'h50000;
    localparam integer Gpio1HighAddr = 32'h500FF;

    // Combined reset
    wire rst;
    assign rst = BUS_RST | RESET;

    // Capture control wires (used by sequencer outputs and fast_spi_rx)
    wire fastrx_clk;
    wire fastrx_en;
    wire fastrx_test_data;
    wire fastrx_loopback_en;
    wire fastrx_in_tiehigh;
    wire debug_counter_en;
    wire fastrx_seq_en;
    wire seq_fastrx_en;
    wire fastrx_en_mux;

    // 1. Sequencer (seq_gen)
    // Generates the timing waveform loaded from the host.
    // The serializer firmware uses a 64-bit sequencer word: each byte carries
    // eight future time slices for one output channel. daq_top serializes byte
    // lanes [0:3] with 8:1 OSERDES blocks for the external LVDS ADC inputs.
    // FastRX samples once per 200 MHz SEQ_CLK word, so it only needs one SEN
    // bit and one optional loopback-test data bit per sequencer word.
    // seq_out[ 7: 0] = CLK_INIT serializer byte lane
    // seq_out[15: 8] = CLK_SAMP serializer byte lane
    // seq_out[23:16] = CLK_COMP serializer byte lane
    // seq_out[31:24] = CLK_LOGIC serializer byte lane
    // seq_out[32]    = RX_SEN frame-enable bit for fast_spi_rx SEN
    // seq_out[33]    = RX_TEST loopback-data bit for fast_spi_rx SDI test mode
    wire [63:0] seq_out;

    // Capture control signals
    assign fastrx_seq_en    = seq_out[32];
    assign fastrx_test_data = seq_out[33];
    assign SEQ_SER_DATA     = seq_out;

    seq_gen #(
        .BASEADDR (SeqGenBaseAddr),
        .HIGHADDR (SeqGenHighAddr),
        .ABUSWIDTH(ABUSWIDTH),
        .MEM_BYTES(256),
        .OUT_BITS (64)
    ) inst_seq_gen (
        .BUS_CLK (BUS_CLK),
        .BUS_RST (rst),
        .BUS_ADD (BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD  (BUS_RD),
        .BUS_WR  (BUS_WR),

        .SEQ_EXT_START(seq_fastrx_en),
        .SEQ_CLK      (SEQ_CLK),
        .SEQ_OUT      (seq_out)
    );


    // 2. SPI Master
    // Drives the 180-bit configuration shift register on the FRIDA chip.
    // SEN active-low directly maps to SPI_CS_B.
    // SPI loopback (GPIO bit 3): when enabled, SDO reads back from SDI
    // instead of the chip's SDO pin.  The SDI signal still drives the chip
    // only the receive path is redirected.  This lets you verify the
    // FPGA-to-chip SPI link independently.
    wire spi_sen;
    wire spi_loopback_en;  // assigned in GPIO section below
    wire spi_sdo_int;
    assign spi_sdo_int = spi_loopback_en ? SPI_SDI : SPI_SDO;
    assign SPI_CS_B    = ~spi_sen;  // SEN is active-high enable, CS_B is active-low

    spi #(
        .BASEADDR (SpiBaseAddr),
        .HIGHADDR (SpiHighAddr),
        .ABUSWIDTH(ABUSWIDTH),
        .MEM_BYTES(32)            // 256 bits > 180 bits needed
    ) inst_spi (
        .BUS_CLK (BUS_CLK),
        .BUS_RST (rst),
        .BUS_ADD (BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD  (BUS_RD),
        .BUS_WR  (BUS_WR),

        .SPI_CLK(SPI_CLK),

        .SCLK     (SPI_SCLK),
        .SDI      (SPI_SDI),
        .SDO      (spi_sdo_int),
        .EXT_START(1'b0),

        .SEN(spi_sen),
        .SLD()
    );


    // 3. GPIO
    // Bit 0: RST_B               - Chip reset (active low)
    // Bit 1: AMPEN_B             - Input amplifier enable (active low)
    // Bit 2: fastrx_loopback_en  - fast_spi_rx loopback test mode
    // Bit 3: spi_loopback_en     - SPI SDO loopback (reads SDI instead of chip SDO)
    // Bit 4: debug_counter_en    - Replace fast_spi_rx FIFO output with up-counter
    // Bit 5: fastrx_in_tiehigh   - Force fastrx_in to constant 1
    // Bit 6: seq_fastrx_en       - Sequencer external start trigger
    // Bit 7: fastrx_en_mux       - Mux select: 0=seq_fastrx_en, 1=RX_SEN sequencer bit
    wire [7:0] gpio;
    assign RST_B              = gpio[0];  // Active-low board reset
    assign AMPEN_B            = ~gpio[1];  // Active-low amp enable (gpio=1 → amp on)
    assign fastrx_loopback_en = gpio[2];  // Fast RX loopback test enable
    assign spi_loopback_en    = gpio[3];  // SPI loopback test enable
    assign debug_counter_en   = gpio[4];  // Debug: replace FIFO with counter
    assign fastrx_in_tiehigh  = gpio[5];  // Debug: force fastrx_in to 1
    assign seq_fastrx_en      = gpio[6];  // Sequencer trigger
    assign fastrx_en_mux      = gpio[7];  // fastrx_en source select



    gpio #(
        .BASEADDR    (GpioBaseAddr),
        .HIGHADDR    (GpioHighAddr),
        .ABUSWIDTH   (ABUSWIDTH),
        .IO_WIDTH    (8),
        .IO_DIRECTION(8'hFF),         // All outputs
        .IO_TRI      (0)
    ) inst_gpio (
        .BUS_CLK (BUS_CLK),
        .BUS_RST (rst),
        .BUS_ADD (BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD  (BUS_RD),
        .BUS_WR  (BUS_WR),

        .IO(gpio)
    );

    // 4. GPIO1: runtime comparator IDELAY control
    // Bits 4:0 are output tap controls, bit 5 is the output load strobe,
    // bit 6 reads IDELAYCTRL.RDY, and bit 7 is reserved low.
    wire [7:0] gpio1;
    assign COMP_IDELAY_TAPS = gpio1[4:0];
    assign COMP_IDELAY_LOAD = gpio1[5];
    assign gpio1[6]         = COMP_IDELAY_RDY;
    assign gpio1[7]         = 1'b0;

    gpio #(
        .BASEADDR    (Gpio1BaseAddr),
        .HIGHADDR    (Gpio1HighAddr),
        .ABUSWIDTH   (ABUSWIDTH),
        .IO_WIDTH    (8),
        .IO_DIRECTION(8'h3F),          // Bits 5:0 outputs; bits 7:6 inputs
        .IO_TRI      (0)
    ) inst_gpio1 (
        .BUS_CLK (BUS_CLK),
        .BUS_RST (rst),
        .BUS_ADD (BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD  (BUS_RD),
        .BUS_WR  (BUS_WR),

        .IO(gpio1)
    );

    // 5. COMP_OUT Receiver (fast_spi_rx)
    // Captures the COMP_OUT stream using basil's fast_spi_rx module.
    // This replaces the hand-rolled shift register + FIFO implementation.
    //
    // Clocked directly from SEQ_CLK (same clock as seq_gen) instead of
    // from a sequencer output.
    //
    // Output format (32-bit words):
    //   [31:28] IDENTIFIER (4'b0001 by default)
    //   [27:DATA_SIZE] Frame counter (28 - DATA_SIZE bits)
    //   [DATA_SIZE-1:0]  Captured data (DATA_SIZE bits)
    //
    wire fastrx_in;  // Input from comp, loopback test data, or tie-high
    assign fastrx_in = fastrx_in_tiehigh ? 1'b1 :
        (fastrx_loopback_en ? fastrx_test_data : COMP_OUT);
    assign fastrx_en = fastrx_en_mux ? fastrx_seq_en : seq_fastrx_en;

    // Intermediate wires between fast_spi_rx and module ports (for muxing)
    wire [31:0] fastrx_fifo_data;
    wire fastrx_fifo_empty;

    fast_spi_rx #(
        .BASEADDR  (FastSpiRxBaseAddr),
        .HIGHADDR  (FastSpiRxHighAddr),
        .ABUSWIDTH (ABUSWIDTH),
        .IDENTIFIER(4'b0001),
        .DATA_SIZE (17)                  // 17 comparator bits per conversion frame
    ) inst_fast_spi_rx (
        .BUS_CLK (BUS_CLK),
        .BUS_RST (rst),
        .BUS_ADD (BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD  (BUS_RD),
        .BUS_WR  (BUS_WR),

        .SCLK(SEQ_CLK),
        .SDI (fastrx_in),
        .SEN (fastrx_en),

        .FIFO_READ (FASTRX_FIFO_READ_NEXT),
        .FIFO_EMPTY(fastrx_fifo_empty),
        .FIFO_DATA (fastrx_fifo_data)
    );

    // Debug up-counter: replaces fast_spi_rx FIFO output for verifying
    // the upstream FIFO chain independently.
    reg [31:0] debug_counter;
    always @(posedge BUS_CLK) begin
        if (rst) begin
            debug_counter <= 32'd0;
        end else if (debug_counter_en) begin
            if (FASTRX_FIFO_READ_NEXT) begin
                debug_counter <= debug_counter + 32'd1;
            end
        end else begin
            debug_counter <= 32'd0;
        end
    end

    // Mux: debug_counter_en selects between fast_spi_rx output and counter
    assign FASTRX_FIFO_DATA_OUT = debug_counter_en ? debug_counter : fastrx_fifo_data;
    assign FASTRX_FIFO_EMPTY    = debug_counter_en ? 1'b0 : fastrx_fifo_empty;


    // 6. LEDs: All 8 LEDs set to high
    assign LED_OUT              = 8'b11111111;

endmodule
