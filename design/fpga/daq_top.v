// FRIDA DAQ Top-Level
//
// Wraps the FRIDA core with SiTcp Ethernet, PLL, and RGMII.
// Based on: tj-monopix2-daq/firmware/src/tjmonopix2.v
//           basil/examples/bdaq/firmware/src/bdaq53_eth.v

`timescale 1ns / 1ps

`include "utils/fifo_32_to_8.v"
`include "utils/generic_fifo.v"
`include "utils/rgmii_io.v"
`include "utils/rbcp_to_bus.v"
`include "utils/bus_to_ip.v"

// SiTCP (patched with `default_nettype wire by manage.py get_sitcp)
`include "WRAP_SiTCP_GMII_XC7K_32K.V"
`include "SiTCP_XC7K_32K_BBT_V110.V"
`include "TIMER.v"

// User core
`include "daq_core.v"

module daq_top (
    input wire        FCLK_IN,          // 100 MHz system clock
    input wire        RESET_BUTTON,     // Active-low reset button
    input wire        USER_BUTTON,      // Active-low user button (SW_USER_B)

    // LED
    output wire [7:0] LED,

    // BDAQ53 EEPROM (SPI for SiTCP)
    `ifdef BDAQ53
        output wire   EEPROM_CS, EEPROM_SK, EEPROM_DI,
        input wire    EEPROM_DO,
    `endif

    // ----- FRIDA chip interface (active signals via connector) -----
    // Sequencer LVDS clock outputs (active, directly from seq_gen tracks)
    output wire       CLK_INIT_P,  CLK_INIT_N,
    output wire       CLK_SAMP_P,  CLK_SAMP_N,
    output wire       CLK_COMP_P,  CLK_COMP_N,
    output wire       CLK_LOGIC_P, CLK_LOGIC_N,

    // SPI to chip configuration register
    output wire       SPI_SCLK,
    output wire       SPI_SDI,          // MOSI
    input wire        SPI_SDO,          // MISO
    output wire       SPI_CS_B,

    // GPIO control signals
    output wire       RST_B,            // Chip reset (active low)
    output wire       AMPEN_B,          // Amplifier enable (active low)

    // Level shifter reference voltages (directly from FPGA GPIO)
    output wire       V_0V_LO,          // Level shifter VCCB low reference
    output wire       V_2V5_HI,         // Level shifter VCCB high reference

    // Second chip interface (active, mirrors port D signals)
    output wire       SPI_SCLK_2,
    output wire       SPI_SDI_2,         // MOSI
    input wire        SPI_SDO_2,         // MISO
    output wire       SPI_CS_B_2,
    output wire       RST_B_2,
    output wire       AMPEN_B_2,
    output wire       V_0V_LO_2,
    output wire       V_2V5_HI_2,

    // Comparator output from chip (LVDS)
    input wire        COMP_OUT_P, COMP_OUT_N,

    // PMOD debug header (active signals for logic analyzer)
    output wire [7:0] PMOD,

    // Ethernet
    output wire [3:0] rgmii_txd,
    output wire       rgmii_tx_ctl,
    output wire       rgmii_txc,
    input wire [3:0]  rgmii_rxd,
    input wire        rgmii_rx_ctl,
    input wire        rgmii_rxc,
    output wire       mdio_phy_mdc,
    inout wire        mdio_phy_mdio,
    output wire       phy_rst_n
);


// ===================================================================
// PLL 1: Communication clocks (SiTCP / Ethernet)
//   100 MHz * 10 = 1000 MHz VCO
// ===================================================================
wire RST;
wire BUS_CLK_PLL, CLK125PLLTX, CLK125PLLTX90;
wire PLL_FEEDBACK, LOCKED;

PLLE2_BASE #(
    .BANDWIDTH("OPTIMIZED"),
    .CLKFBOUT_MULT(10),        // 100 MHz * 10 = 1000 MHz VCO
    .CLKFBOUT_PHASE(0.0),
    .CLKIN1_PERIOD(10.000),     // 100 MHz input
    .DIVCLK_DIVIDE(1),
    .REF_JITTER1(0.0),
    .STARTUP_WAIT("FALSE"),

    .CLKOUT0_DIVIDE(7),        // 1000/7 = 142.86 MHz (BUS_CLK, SiTCP needs >129 MHz)
    .CLKOUT0_DUTY_CYCLE(0.5),
    .CLKOUT0_PHASE(0.0),

    .CLKOUT1_DIVIDE(8),        // 1000/8 = 125 MHz (Ethernet RGMII TX)
    .CLKOUT1_DUTY_CYCLE(0.5),
    .CLKOUT1_PHASE(0.0),

    .CLKOUT2_DIVIDE(8),        // 1000/8 = 125 MHz (Ethernet RGMII TX, 90° phase)
    .CLKOUT2_DUTY_CYCLE(0.5),
    .CLKOUT2_PHASE(90.0)
) PLLE2_BASE_comm (
    .CLKOUT0(BUS_CLK_PLL),
    .CLKOUT1(CLK125PLLTX),
    .CLKOUT2(CLK125PLLTX90),
    .CLKOUT3(),
    .CLKOUT4(),
    .CLKOUT5(),
    .CLKFBOUT(PLL_FEEDBACK),
    .LOCKED(LOCKED),
    .CLKIN1(FCLK_IN),
    .PWRDWN(0),
    .RST(!RESET_BUTTON),
    .CLKFBIN(PLL_FEEDBACK)
);

// ===================================================================
// PLL 2: Sequencer clock
//   100 MHz * 8 = 800 MHz VCO
//   2.5ns step → 40 steps per 100ns conversion = 10 Msps
// ===================================================================
wire SEQ_CLK_PLL, SPI_CLK_PLL;
wire PLL2_FEEDBACK, LOCKED2;

PLLE2_BASE #(
    .BANDWIDTH("OPTIMIZED"),
    .CLKFBOUT_MULT(8),         // 100 MHz * 8 = 800 MHz VCO
    .CLKFBOUT_PHASE(0.0),
    .CLKIN1_PERIOD(10.000),
    .DIVCLK_DIVIDE(1),
    .REF_JITTER1(0.0),
    .STARTUP_WAIT("FALSE"),

    .CLKOUT0_DIVIDE(2),        // 800/2 = 400 MHz (SEQ_CLK)
    .CLKOUT0_DUTY_CYCLE(0.5),
    .CLKOUT0_PHASE(0.0),

    .CLKOUT1_DIVIDE(80),       // 800/80 = 10 MHz (SPI_CLK)
    .CLKOUT1_DUTY_CYCLE(0.5),
    .CLKOUT1_PHASE(0.0)
) PLLE2_BASE_seq (
    .CLKOUT0(SEQ_CLK_PLL),
    .CLKOUT1(SPI_CLK_PLL),
    .CLKOUT2(),
    .CLKOUT3(),
    .CLKOUT4(),
    .CLKOUT5(),
    .CLKFBOUT(PLL2_FEEDBACK),
    .LOCKED(LOCKED2),
    .CLKIN1(FCLK_IN),
    .PWRDWN(0),
    .RST(!RESET_BUTTON),
    .CLKFBIN(PLL2_FEEDBACK)
);

(* KEEP = "{TRUE}" *) wire BUS_CLK;
wire CLK125TX, CLK125TX90, CLK125RX, SEQ_CLK, SPI_CLK;
BUFG BUFG_inst_BUS_CLK   ( .O(BUS_CLK),    .I(BUS_CLK_PLL)   );
BUFG BUFG_inst_SPI_CLK   ( .O(SPI_CLK),    .I(SPI_CLK_PLL)   );
BUFG BUFG_inst_CLK125TX  ( .O(CLK125TX),   .I(CLK125PLLTX)   );
BUFG BUFG_inst_CLK125TX90( .O(CLK125TX90), .I(CLK125PLLTX90)  );
BUFG BUFG_inst_CLK125RX  ( .O(CLK125RX),   .I(rgmii_rxc)      );
BUFG BUFG_inst_SEQ_CLK   ( .O(SEQ_CLK),    .I(SEQ_CLK_PLL)    );

assign RST = !RESET_BUTTON | !LOCKED | !LOCKED2;


// ===================================================================
// RGMII I/O
// ===================================================================
wire  gmii_tx_en;
wire [7:0] gmii_txd;
wire  gmii_tx_er;
wire  gmii_crs;
wire  gmii_col;
wire  gmii_rx_dv;
wire [7:0] gmii_rxd;
wire  gmii_rx_er;
wire  mdio_gem_i;
wire  mdio_gem_o;
wire  mdio_gem_t;
wire  link_status;
wire [1:0] clock_speed;
wire  duplex_status;

rgmii_io rgmii (
    .rgmii_txd(rgmii_txd),
    .rgmii_tx_ctl(rgmii_tx_ctl),
    .rgmii_txc(rgmii_txc),

    .rgmii_rxd(rgmii_rxd),
    .rgmii_rx_ctl(rgmii_rx_ctl),

    .gmii_txd_int(gmii_txd),
    .gmii_tx_en_int(gmii_tx_en),
    .gmii_tx_er_int(gmii_tx_er),
    .gmii_col_int(gmii_col),
    .gmii_crs_int(gmii_crs),
    .gmii_rxd_reg(gmii_rxd),
    .gmii_rx_dv_reg(gmii_rx_dv),
    .gmii_rx_er_reg(gmii_rx_er),

    .eth_link_status(link_status),
    .eth_clock_speed(clock_speed),
    .eth_duplex_status(duplex_status),

    .tx_rgmii_clk_int(CLK125TX),
    .tx_rgmii_clk90_int(CLK125TX90),
    .rx_rgmii_clk_int(CLK125RX),

    .reset(!phy_rst_n)
);


// ===================================================================
// MDIO tri-state buffer
// ===================================================================
IOBUF i_iobuf_mdio (
    .O(mdio_gem_i),
    .IO(mdio_phy_mdio),
    .I(mdio_gem_o),
    .T(mdio_gem_t)
);


// ===================================================================
// SiTCP
// ===================================================================
wire TCP_CLOSE_REQ, TCP_OPEN_ACK;
wire RBCP_ACT, RBCP_WE, RBCP_RE;
wire [7:0] RBCP_WD, RBCP_RD;
wire [31:0] RBCP_ADDR;
wire TCP_RX_WR, TCP_TX_WR;
wire [7:0] TCP_RX_DATA, TCP_TX_DATA;
wire TCP_TX_FULL;
wire RBCP_ACK;
wire SiTCP_RST;

wire EEPROM_CS_int, EEPROM_SK_int, EEPROM_DI_int, EEPROM_DO_int;

`ifdef BDAQ53
    assign EEPROM_CS = EEPROM_CS_int;
    assign EEPROM_SK = EEPROM_SK_int;
    assign EEPROM_DI = EEPROM_DI_int;
    assign EEPROM_DO_int = EEPROM_DO;
`else
    assign EEPROM_DO_int = 1'b0;
`endif

WRAP_SiTCP_GMII_XC7K_32K sitcp (
    .CLK(BUS_CLK)                ,    // in  : System Clock >129MHz
    .RST(RST)                    ,    // in  : System reset
    // Configuration parameters
    .FORCE_DEFAULTn(1'b0)        ,    // in  : Load default parameters
    .EXT_IP_ADDR(32'hc0a80a10)   ,    // in  : 192.168.10.16
    .EXT_TCP_PORT(16'd24)        ,    // in  : TCP port
    .EXT_RBCP_PORT(16'd4660)     ,    // in  : RBCP port
    .PHY_ADDR(5'd3)              ,    // in  : PHY-device MIF address
    // EEPROM
    .EEPROM_CS(EEPROM_CS_int)    ,
    .EEPROM_SK(EEPROM_SK_int)    ,
    .EEPROM_DI(EEPROM_DI_int)    ,
    .EEPROM_DO(EEPROM_DO_int)    ,
    // User registers
    .USR_REG_X3C()               ,
    .USR_REG_X3D()               ,
    .USR_REG_X3E()               ,
    .USR_REG_X3F()               ,
    // MII interface
    .GMII_RSTn(phy_rst_n)        ,
    .GMII_1000M(1'b1)            ,
    // TX
    .GMII_TX_CLK(CLK125TX)       ,
    .GMII_TX_EN(gmii_tx_en)      ,
    .GMII_TXD(gmii_txd)          ,
    .GMII_TX_ER(gmii_tx_er)      ,
    // RX
    .GMII_RX_CLK(CLK125RX)       ,
    .GMII_RX_DV(gmii_rx_dv)      ,
    .GMII_RXD(gmii_rxd)          ,
    .GMII_RX_ER(gmii_rx_er)      ,
    .GMII_CRS(gmii_crs)          ,
    .GMII_COL(gmii_col)          ,
    // Management IF
    .GMII_MDC(mdio_phy_mdc)      ,
    .GMII_MDIO_IN(mdio_gem_i)    ,
    .GMII_MDIO_OUT(mdio_gem_o)   ,
    .GMII_MDIO_OE(mdio_gem_t)    ,
    // User I/F
    .SiTCP_RST(SiTCP_RST)        ,
    // TCP connection control
    .TCP_OPEN_REQ(1'b0)          ,
    .TCP_OPEN_ACK(TCP_OPEN_ACK)  ,
    .TCP_ERROR()                 ,
    .TCP_CLOSE_REQ(TCP_CLOSE_REQ),
    .TCP_CLOSE_ACK(TCP_CLOSE_REQ),
    // FIFO I/F
    .TCP_RX_WC(1'b1)             ,
    .TCP_RX_WR(TCP_RX_WR)        ,
    .TCP_RX_DATA(TCP_RX_DATA)    ,
    .TCP_TX_FULL(TCP_TX_FULL)    ,
    .TCP_TX_WR(TCP_TX_WR)        ,
    .TCP_TX_DATA(TCP_TX_DATA)    ,
    // RBCP
    .RBCP_ACT(RBCP_ACT)          ,
    .RBCP_ADDR(RBCP_ADDR)        ,
    .RBCP_WD(RBCP_WD)            ,
    .RBCP_WE(RBCP_WE)            ,
    .RBCP_RE(RBCP_RE)            ,
    .RBCP_ACK(RBCP_ACK)          ,
    .RBCP_RD(RBCP_RD)
);


// ===================================================================
// RBCP -> Bus bridge
// ===================================================================
wire BUS_WR, BUS_RD, BUS_RST;
wire [31:0] BUS_ADD;
wire [7:0] BUS_DATA;
assign BUS_RST = SiTCP_RST;

rbcp_to_bus irbcp_to_bus (
    .BUS_RST(BUS_RST),
    .BUS_CLK(BUS_CLK),

    .RBCP_ACT(RBCP_ACT),
    .RBCP_ADDR(RBCP_ADDR),
    .RBCP_WD(RBCP_WD),
    .RBCP_WE(RBCP_WE),
    .RBCP_RE(RBCP_RE),
    .RBCP_ACK(RBCP_ACK),
    .RBCP_RD(RBCP_RD),

    .BUS_WR(BUS_WR),
    .BUS_RD(BUS_RD),
    .BUS_ADD(BUS_ADD),
    .BUS_DATA(BUS_DATA)
);


// ===================================================================
// Data FIFO: core 32-bit -> SiTcp 8-bit TCP stream
// ===================================================================
wire [31:0] FIFO_DATA_OUT;
wire FIFO_EMPTY, FIFO_READ_NEXT;
wire full_32to8;

fifo_32_to_8 #(
    .DEPTH(64*1024)
) i_data_fifo (
    .RST(BUS_RST),
    .CLK(BUS_CLK),

    .WRITE(!FIFO_EMPTY),
    .READ(TCP_TX_WR),
    .DATA_IN(FIFO_DATA_OUT),
    .FULL(full_32to8),
    .EMPTY(),
    .DATA_OUT(TCP_TX_DATA)
);

assign FIFO_READ_NEXT = !full_32to8;
assign TCP_TX_WR = !TCP_TX_FULL && !FIFO_EMPTY;


// ===================================================================
// LVDS I/O buffers
// ===================================================================
// Sequencer clock outputs to chip (active, directly from core)
wire clk_init_int, clk_samp_int, clk_comp_int, clk_logic_int;

OBUFDS #(.IOSTANDARD("LVDS_25")) i_obufds_clk_init (
    .O(CLK_INIT_P), .OB(CLK_INIT_N), .I(clk_init_int)
);
OBUFDS #(.IOSTANDARD("LVDS_25")) i_obufds_clk_samp (
    .O(CLK_SAMP_P), .OB(CLK_SAMP_N), .I(~clk_samp_int)  // invert: BDAQ swaps P/N on this lane
);
OBUFDS #(.IOSTANDARD("LVDS_25")) i_obufds_clk_comp (
    .O(CLK_COMP_P), .OB(CLK_COMP_N), .I(clk_comp_int)
);
OBUFDS #(.IOSTANDARD("LVDS_25")) i_obufds_clk_logic (
    .O(CLK_LOGIC_P), .OB(CLK_LOGIC_N), .I(clk_logic_int)
);

// Comparator output from chip (LVDS input)
// The BDAQ board swaps P/N on this lane so the raw IBUFDS output is inverted;
// comp_out_int corrects the polarity with a NOT gate.
wire comp_out_raw;
IBUFDS #(
    .DIFF_TERM("TRUE"),
    .IBUF_LOW_PWR("FALSE"),
    .IOSTANDARD("LVDS_25")
) i_ibufds_comp_out (
    .O(comp_out_raw),
    .I(COMP_OUT_P),
    .IB(COMP_OUT_N)
);
wire comp_out_int = ~comp_out_raw;


// ===================================================================
// FRIDA Core
// ===================================================================
daq_core i_frida_core (
    .bus_clk(BUS_CLK),
    .bus_rst(BUS_RST),
    .bus_add(BUS_ADD),
    .bus_data(BUS_DATA),
    .bus_rd(BUS_RD),
    .bus_wr(BUS_WR),

    .seq_clk(SEQ_CLK),

    .clk_init(clk_init_int),
    .clk_samp(clk_samp_int),
    .clk_comp(clk_comp_int),
    .clk_logic(clk_logic_int),

    .spi_clk(SPI_CLK),         // 10 MHz SPI clock
    .spi_sclk(SPI_SCLK),
    .spi_sdi(SPI_SDI),
    .spi_sdo(SPI_SDO),
    .spi_cs_b(SPI_CS_B),

    .rst_b(RST_B),
    .ampen_b(AMPEN_B),

    .fifo_data_out(FIFO_DATA_OUT),
    .fifo_read_next(FIFO_READ_NEXT),
    .fifo_empty(FIFO_EMPTY),

    .comp_out(comp_out_int),

    .reset(RST),

    .seq_pattern_out(seq_pattern_out),
    .seq_pattern_addr(led_step)
);


// ===================================================================
// Level shifter reference voltages
// ===================================================================
(* KEEP = "TRUE" *) wire v_0v_lo_int;
(* KEEP = "TRUE" *) wire v_2v5_hi_int;
assign v_0v_lo_int = 1'b0;
assign v_2v5_hi_int = 1'b1;
assign V_0V_LO = v_0v_lo_int;
assign V_2V5_HI = v_2v5_hi_int;

// ===================================================================
// Second chip interface — mirrors port D signals to port C
// ===================================================================
assign SPI_SCLK_2  = SPI_SCLK;
assign SPI_SDI_2   = SPI_SDI;
assign SPI_CS_B_2  = SPI_CS_B;
assign RST_B_2     = RST_B;
assign AMPEN_B_2   = AMPEN_B;
assign V_0V_LO_2   = v_0v_lo_int;
assign V_2V5_HI_2  = v_2v5_hi_int;


// ===================================================================
// PMOD debug header for logic analyzer
// ===================================================================
// PMOD[0..3] = PMOD1..4 (pins 1-4), PMOD[4..7] = PMOD7..10 (pins 7-10)
// Pins 5,6,11,12 are GND/VCC — not available as signals.
// Pins 1-4: SPI interface signals
// Pins 7-10: sequencer LVDS clock outputs (single-ended, from core)
assign PMOD[0] = SPI_SCLK;       // Pin 1: SPI_SCLK
assign PMOD[1] = SPI_SDI;        // Pin 2: SPI_SDI  (MOSI)
assign PMOD[2] = SPI_SDO;        // Pin 3: SPI_SDO  (MISO)
assign PMOD[3] = SPI_CS_B;       // Pin 4: SPI_CS_B
assign PMOD[4] = clk_init_int;   // Pin 7: CLK_INIT
assign PMOD[5] = clk_samp_int;   // Pin 8: CLK_SAMP
assign PMOD[6] = clk_comp_int;   // Pin 9: CLK_COMP
assign PMOD[7] = clk_logic_int;  // Pin 10: CLK_LOGIC


// ===================================================================
// LEDs: slow playback of seq_gen pattern from block RAM shadow
// ===================================================================
// LED[3:0] reads the actual pattern loaded into seq_gen memory.
// Steps through addresses 0..39 at 0.25s each = 10s total loop.
// Whatever the host writes to the sequencer is displayed.
localparam LED_COUNTS_PER_STEP = 100_000_000;  // 400 MHz * 0.25s

reg [26:0] led_timer;
reg [5:0]  led_step;  // 0..39

always @(posedge SEQ_CLK or posedge RST)
    if (RST) begin
        led_timer <= 0;
        led_step <= 0;
    end else if (led_timer >= LED_COUNTS_PER_STEP) begin
        led_timer <= 0;
        led_step <= (led_step == 39) ? 0 : led_step + 1;
    end else begin
        led_timer <= led_timer + 1;
    end

// seq_pattern_out[3:0] = {logic, comp, samp, init} at address led_step
// read from shadow copy of seq_gen block RAM (snooped on bus writes)
wire [3:0] seq_pattern_out;

// LED[3:0] = onboard module LEDs: sequencer pattern playback
// LED[7:4] = BDAQ53 board LEDs: rolling / all-flash on button press
// Active-low on BDAQ53
assign LED[3:0] = ~seq_pattern_out;

reg [3:0] led_board_rolling;
always @(*) begin
    led_board_rolling = 4'b0;
    led_board_rolling[led_step[1:0]] = 1'b1;
end
assign LED[7:4] = USER_BUTTON ? ~led_board_rolling : (led_timer[24] ? 4'hF : 4'h0);

endmodule
