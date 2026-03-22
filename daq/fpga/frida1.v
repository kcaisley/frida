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
`include "frida1_core.v"

module frida1 (
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
    output wire       VSS_LS,           // Level shifter VCCB low reference
    output wire       VDD_LS,           // Level shifter VCCB high reference

    // Comparator output from chip (LVDS)
    input wire        COMP_OUT_P, COMP_OUT_N,

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
// PLL: 100 MHz -> BUS_CLK, CLK125TX, CLK125TX90, SEQ_CLK
// ===================================================================
wire RST;
wire BUS_CLK_PLL, CLK125PLLTX, CLK125PLLTX90, SEQ_CLK_PLL;
wire PLL_FEEDBACK, LOCKED;

PLLE2_BASE #(
    .BANDWIDTH("OPTIMIZED"),
    .CLKFBOUT_MULT(10),        // 100 MHz * 10 = 1000 MHz VCO
    .CLKFBOUT_PHASE(0.0),
    .CLKIN1_PERIOD(10.000),     // 100 MHz input
    .DIVCLK_DIVIDE(1),
    .REF_JITTER1(0.0),
    .STARTUP_WAIT("FALSE"),

    .CLKOUT0_DIVIDE(7),        // 1000/7 = 142.86 MHz (BUS_CLK)
    .CLKOUT0_DUTY_CYCLE(0.5),
    .CLKOUT0_PHASE(0.0),

    .CLKOUT1_DIVIDE(8),        // 1000/8 = 125 MHz (CLK125TX)
    .CLKOUT1_DUTY_CYCLE(0.5),
    .CLKOUT1_PHASE(0.0),

    .CLKOUT2_DIVIDE(8),        // 1000/8 = 125 MHz (CLK125TX90)
    .CLKOUT2_DUTY_CYCLE(0.5),
    .CLKOUT2_PHASE(90.0),

    .CLKOUT3_DIVIDE(5),        // 1000/5 = 200 MHz (SEQ_CLK)
    .CLKOUT3_DUTY_CYCLE(0.5),
    .CLKOUT3_PHASE(0.0)
) PLLE2_BASE_inst (
    .CLKOUT0(BUS_CLK_PLL),
    .CLKOUT1(CLK125PLLTX),
    .CLKOUT2(CLK125PLLTX90),
    .CLKOUT3(SEQ_CLK_PLL),
    .CLKOUT4(),
    .CLKOUT5(),
    .CLKFBOUT(PLL_FEEDBACK),
    .LOCKED(LOCKED),
    .CLKIN1(FCLK_IN),
    .PWRDWN(0),
    .RST(!RESET_BUTTON),
    .CLKFBIN(PLL_FEEDBACK)
);

(* KEEP = "{TRUE}" *) wire BUS_CLK;
wire CLK125TX, CLK125TX90, CLK125RX, SEQ_CLK;
BUFG BUFG_inst_BUS_CLK   ( .O(BUS_CLK),    .I(BUS_CLK_PLL)   );
BUFG BUFG_inst_CLK125TX  ( .O(CLK125TX),   .I(CLK125PLLTX)   );
BUFG BUFG_inst_CLK125TX90( .O(CLK125TX90), .I(CLK125PLLTX90)  );
BUFG BUFG_inst_CLK125RX  ( .O(CLK125RX),   .I(rgmii_rxc)      );
BUFG BUFG_inst_SEQ_CLK   ( .O(SEQ_CLK),    .I(SEQ_CLK_PLL)    );

assign RST = !RESET_BUTTON | !LOCKED;


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
    .O(CLK_SAMP_P), .OB(CLK_SAMP_N), .I(clk_samp_int)
);
OBUFDS #(.IOSTANDARD("LVDS_25")) i_obufds_clk_comp (
    .O(CLK_COMP_P), .OB(CLK_COMP_N), .I(clk_comp_int)
);
OBUFDS #(.IOSTANDARD("LVDS_25")) i_obufds_clk_logic (
    .O(CLK_LOGIC_P), .OB(CLK_LOGIC_N), .I(clk_logic_int)
);

// Comparator output from chip (LVDS input)
wire comp_out_int;
IBUFDS #(
    .DIFF_TERM("TRUE"),
    .IBUF_LOW_PWR("FALSE"),
    .IOSTANDARD("LVDS_25")
) i_ibufds_comp_out (
    .O(comp_out_int),
    .I(COMP_OUT_P),
    .IB(COMP_OUT_N)
);


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

    .spi_clk(BUS_CLK),         // SPI module divides internally
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

    .reset(RST)
);


// ===================================================================
// Level shifter reference voltages
// ===================================================================
assign VSS_LS = 1'b0;  // Low reference
assign VDD_LS = 1'b1;  // High reference


// ===================================================================
// LEDs: rolling pattern, all flash when USER_BUTTON pressed
// ===================================================================
// ~143 MHz BUS_CLK -> need ~24 bits to count 0.5s (2^23 = 8M, 143M/8M ~ 18 steps/s)
// Use bits [25:23] for ~0.5s per LED step at 143 MHz (143M / 2^23 = ~17 Hz, 8 steps = ~0.47s each)
reg [25:0] led_counter;
always @(posedge BUS_CLK or posedge RST)
    if (RST)
        led_counter <= 0;
    else
        led_counter <= led_counter + 1;

wire [2:0] led_phase = led_counter[25:23];
reg [7:0] led_rolling;
always @(*) begin
    led_rolling = 8'b0;
    led_rolling[led_phase] = 1'b1;
end

// Button is active-low: pressed = 0, released = 1
// When pressed: all LEDs on (flash using bit 22 for visible blink ~35 Hz)
// When released: rolling pattern
// LEDs are active-low on BDAQ53 (accent with ~)
assign LED = USER_BUTTON ? ~led_rolling : (led_counter[22] ? 8'h00 : 8'hFF);

endmodule
