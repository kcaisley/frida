// FRIDA DAQ Top-Level
//
// Wraps the FRIDA core with SiTcp Ethernet, PLL, and RGMII.
// Based on: tj-monopix2-daq/firmware/src/tjmonopix2.v
//           basil/examples/bdaq/firmware/src/bdaq53_eth.v

`timescale 1ns / 1ps

// FRIDA core (self-contained: includes its basil functional module deps
// and the utility modules they rely on)
`include "daq_core.v"
`include "pll_drp.v"
`include "clock_reset_sync.v"

// Additional basil utility modules (directly used by daq_top)
`include "utils/fifo_32_to_8.v"
`include "utils/rgmii_io.v"
`include "utils/rbcp_to_bus.v"
`include "utils/clock_divider.v"
`include "i2c/i2c.v"

// SiTCP (patched with `default_nettype wire by manage.py get_sitcp)
`include "WRAP_SiTCP_GMII_XC7K_32K.V"
`include "SiTCP_XC7K_32K_BBT_V110.V"
`include "TIMER.v"

module daq_top (
    input wire FCLK_IN,       // 100 MHz system clock
    input wire RESET_BUTTON,  // Active-low reset button
    input wire USER_BUTTON,   // Active-low user button (SW_USER_B)

    // BDAQ53 programmable Si570 clock and control
    input  wire MGT_REFCLK0_P,
    input  wire MGT_REFCLK0_N,
    output wire MGT_REF_SEL,
    inout  wire I2C_SCL,
    inout  wire I2C_SDA,

    // LED
    output wire [7:0] LED,

    // BDAQ53 EEPROM (SPI for SiTCP)
`ifdef BDAQ53
    output wire EEPROM_CS,
    EEPROM_SK,
    EEPROM_DI,
    input  wire EEPROM_DO,
`endif

    // FRIDA chip interface (active signals via connector)
    // Sequencer LVDS clock outputs (active, directly from seq_gen tracks)
    output wire CLK_INIT_P,
    CLK_INIT_N,
    output wire CLK_SAMP_P,
    CLK_SAMP_N,
    output wire CLK_COMP_P,
    CLK_COMP_N,
    output wire CLK_LOGIC_P,
    CLK_LOGIC_N,

    // SPI to chip configuration register
    output wire SPI_SCLK,
    output wire SPI_SDI,   // MOSI
    input  wire SPI_SDO,   // MISO
    output wire SPI_CS_B,

    // GPIO control signals
    output wire RST_B,   // Chip reset (active low)
    output wire AMPEN_B, // Amplifier enable (active low)

    // Level shifter reference voltages (directly from FPGA GPIO)
    output wire V_0V_LO,  // Level shifter VCCB low reference
    output wire V_2V5_HI, // Level shifter VCCB high reference

    // Comparator output from chip (LVDS)
    input wire COMP_OUT_P,
    COMP_OUT_N,

    // PMOD debug header (active signals for logic analyzer)
    output wire [7:0] PMOD,

    // Ethernet
    output wire [3:0] rgmii_txd,
    output wire       rgmii_tx_ctl,
    output wire       rgmii_txc,
    input  wire [3:0] rgmii_rxd,
    input  wire       rgmii_rx_ctl,
    input  wire       rgmii_rxc,
    output wire       mdio_phy_mdc,
    inout  wire       mdio_phy_mdio,
    output wire       phy_rst_n
);


    // PLL 1: Communication clocks (SiTCP / Ethernet)
    // 100 MHz * 10 = 1000 MHz VCO
    wire comm_rst;
    wire bus_clk_pll, clk125_pll_tx, clk125_pll_tx90, spi_clk_pll;
    wire idelay_ref_pll;
    wire pll_feedback, locked;
    wire bus_clk;

    PLLE2_BASE #(
        .BANDWIDTH     ("OPTIMIZED"),
        .CLKFBOUT_MULT (10),           // 100 MHz * 10 = 1000 MHz VCO
        .CLKFBOUT_PHASE(0.0),
        .CLKIN1_PERIOD (10.000),       // 100 MHz input
        .DIVCLK_DIVIDE (1),
        .REF_JITTER1   (0.0),
        .STARTUP_WAIT  ("FALSE"),

        .CLKOUT0_DIVIDE    (7),    // 1000/7 = 142.86 MHz (bus_clk, SiTCP needs >129 MHz)
        .CLKOUT0_DUTY_CYCLE(0.5),
        .CLKOUT0_PHASE     (0.0),

        .CLKOUT1_DIVIDE    (8),    // 1000/8 = 125 MHz (Ethernet RGMII TX)
        .CLKOUT1_DUTY_CYCLE(0.5),
        .CLKOUT1_PHASE     (0.0),

        .CLKOUT2_DIVIDE    (8),    // 1000/8 = 125 MHz (Ethernet RGMII TX, 90° phase)
        .CLKOUT2_DUTY_CYCLE(0.5),
        .CLKOUT2_PHASE     (90.0),

        .CLKOUT3_DIVIDE    (100),  // 1000/100 = 10 MHz (spi_clk)
        .CLKOUT3_DUTY_CYCLE(0.5),
        .CLKOUT3_PHASE     (0.0),

        .CLKOUT4_DIVIDE    (5),    // Fixed 200 MHz IDELAYCTRL reference
        .CLKOUT4_DUTY_CYCLE(0.5),
        .CLKOUT4_PHASE     (0.0)
    ) PLLE2_BASE_comm (
        .CLKOUT0 (bus_clk_pll),
        .CLKOUT1 (clk125_pll_tx),
        .CLKOUT2 (clk125_pll_tx90),
        .CLKOUT3 (spi_clk_pll),
        .CLKOUT4 (idelay_ref_pll),
        .CLKOUT5 (),
        .CLKFBOUT(pll_feedback),
        .LOCKED  (locked),
        .CLKIN1  (FCLK_IN),
        .PWRDWN  (0),
        .RST     (!RESET_BUTTON),
        .CLKFBIN (pll_feedback)
    );

    // PLL 2: variable serializer/sequencer clocks. The BDAQ53 mux selects the
    // Si570 MGT reference, and IBUFDS_GTE2 makes it available to the CMT PLL.
    //   100--200 MHz * 8 = 800--1600 MHz VCO
    //   CLKOUT0 divide 4*N: sequencer/FastRX word clock
    //   CLKOUT1 divide N:   OSERDES DDR clock
    wire si570_clk_ibufds, si570_clk;
    wire seq_clk_pll, ser_clk_pll;
    wire pll2_feedback, locked2;
    wire [15:0] pll_drp_do;
    wire [15:0] pll_drp_di;
    wire [6:0] pll_drp_daddr;
    wire pll_drp_drdy, pll_drp_den, pll_drp_dwe, pll_drp_reset;

    assign MGT_REF_SEL = 1'b1;

    IBUFDS_GTE2 i_si570_refclk (
        .O    (si570_clk_ibufds),
        .ODIV2(),
        .CEB  (1'b0),
        .I    (MGT_REFCLK0_P),
        .IB   (MGT_REFCLK0_N)
    );

    // This is the same proven BDAQ53 MGT-reference path used by TJ-Monopix2.
    // The BUFG also permits the Si570 to reach a PLL outside the MGT region.
    BUFG bufg_si570_clk (
        .O(si570_clk),
        .I(si570_clk_ibufds)
    );

    PLLE2_ADV #(
        .BANDWIDTH     ("OPTIMIZED"),
        .CLKFBOUT_MULT (8),            // 100--200 MHz * 8 = 800--1600 MHz VCO
        .CLKFBOUT_PHASE(0.0),
        .CLKIN1_PERIOD (5.000),        // constrain the fastest Si570 setting
        .DIVCLK_DIVIDE (1),
        .REF_JITTER1   (0.0),
        .STARTUP_WAIT  ("FALSE"),

        .CLKOUT0_DIVIDE    (8),    // 1600/8 = 200 MHz sequencer word clock
        .CLKOUT0_DUTY_CYCLE(0.5),
        .CLKOUT0_PHASE     (0.0),

        .CLKOUT1_DIVIDE    (2),    // 1600/2 = 800 MHz OSERDES DDR clock -> 1.6 GHz interval rate
        .CLKOUT1_DUTY_CYCLE(0.5),
        .CLKOUT1_PHASE     (0.0),

        .COMPENSATION("ZHOLD")
    ) PLLE2_ADV_seq (
        .CLKOUT0 (seq_clk_pll),
        .CLKOUT1 (ser_clk_pll),
        .CLKOUT2 (),
        .CLKOUT3 (),
        .CLKOUT4 (),
        .CLKOUT5 (),
        .CLKFBOUT(pll2_feedback),
        .LOCKED  (locked2),
        .CLKIN1  (si570_clk),
        .CLKIN2  (1'b0),
        .CLKINSEL(1'b1),
        .PWRDWN  (1'b0),
        .RST     (comm_rst | pll_drp_reset),
        .DADDR   (pll_drp_daddr),
        .DCLK    (bus_clk),
        .DEN     (pll_drp_den),
        .DI      (pll_drp_di),
        .DO      (pll_drp_do),
        .DRDY    (pll_drp_drdy),
        .DWE     (pll_drp_dwe),
        .CLKFBIN (pll2_feedback)
    );

    wire clk125_tx, clk125_tx90, clk125_rx, seq_clk, ser_clk, spi_clk;
    wire idelay_ref_clk;
    BUFG bufg_bus_clk (
        .O(bus_clk),
        .I(bus_clk_pll)
    );
    BUFG bufg_spi_clk (
        .O(spi_clk),
        .I(spi_clk_pll)
    );
    BUFG bufg_idelay_ref_clk (
        .O(idelay_ref_clk),
        .I(idelay_ref_pll)
    );
    BUFG bufg_clk125tx (
        .O(clk125_tx),
        .I(clk125_pll_tx)
    );
    BUFG bufg_clk125tx90 (
        .O(clk125_tx90),
        .I(clk125_pll_tx90)
    );
    BUFG bufg_clk125rx (
        .O(clk125_rx),
        .I(rgmii_rxc)
    );
    BUFG bufg_seq_clk (
        .O(seq_clk),
        .I(seq_clk_pll)
    );
    BUFG bufg_ser_clk (
        .O(ser_clk),
        .I(ser_clk_pll)
    );

    // The communication/control plane remains available while PLL 2 is
    // reconfigured, so Python can complete and observe the DRP transaction.
    assign comm_rst = !RESET_BUTTON | !locked;


    // RGMII I/O
    wire gmii_tx_en;
    wire [7:0] gmii_txd;
    wire gmii_tx_er;
    wire gmii_crs;
    wire gmii_col;
    wire gmii_rx_dv;
    wire [7:0] gmii_rxd;
    wire gmii_rx_er;
    wire mdio_gem_i;
    wire mdio_gem_o;
    wire mdio_gem_t;
    wire link_status;
    wire [1:0] clock_speed;
    wire duplex_status;

    rgmii_io rgmii (
        .rgmii_txd   (rgmii_txd),
        .rgmii_tx_ctl(rgmii_tx_ctl),
        .rgmii_txc   (rgmii_txc),

        .rgmii_rxd   (rgmii_rxd),
        .rgmii_rx_ctl(rgmii_rx_ctl),

        .gmii_txd_int  (gmii_txd),
        .gmii_tx_en_int(gmii_tx_en),
        .gmii_tx_er_int(gmii_tx_er),
        .gmii_col_int  (gmii_col),
        .gmii_crs_int  (gmii_crs),
        .gmii_rxd_reg  (gmii_rxd),
        .gmii_rx_dv_reg(gmii_rx_dv),
        .gmii_rx_er_reg(gmii_rx_er),

        .eth_link_status  (link_status),
        .eth_clock_speed  (clock_speed),
        .eth_duplex_status(duplex_status),

        .tx_rgmii_clk_int  (clk125_tx),
        .tx_rgmii_clk90_int(clk125_tx90),
        .rx_rgmii_clk_int  (clk125_rx),

        .reset(!phy_rst_n)
    );


    // MDIO tri-state buffer
    IOBUF iobuf_mdio (
        .O (mdio_gem_i),
        .IO(mdio_phy_mdio),
        .I (mdio_gem_o),
        .T (mdio_gem_t)
    );


    // SiTCP
    wire tcp_close_req, tcp_open_ack;
    wire rbcp_act, rbcp_we, rbcp_re;
    wire [7:0] rbcp_wd, rbcp_rd;
    wire [31:0] rbcp_addr;
    wire tcp_rx_wr, tcp_tx_wr;
    wire [7:0] tcp_rx_data, tcp_tx_data;
    wire tcp_tx_full;
    wire rbcp_ack;
    wire sitcp_rst;

    wire eeprom_cs, eeprom_sk, eeprom_di, eeprom_do;

`ifdef BDAQ53
    assign EEPROM_CS = eeprom_cs;
    assign EEPROM_SK = eeprom_sk;
    assign EEPROM_DI = eeprom_di;
    assign eeprom_do = EEPROM_DO;
`else
    assign eeprom_do = 1'b0;
`endif

    WRAP_SiTCP_GMII_XC7K_32K sitcp (
        .CLK           (bus_clk),        // in  : System Clock >129MHz
        .RST           (comm_rst),       // in  : System reset
        // Configuration parameters
        .FORCE_DEFAULTn(1'b0),           // in  : Load default parameters
        .EXT_IP_ADDR   (32'hc0a80a10),   // in  : 192.168.10.16
        .EXT_TCP_PORT  (16'd24),         // in  : TCP port
        .EXT_RBCP_PORT (16'd4660),       // in  : RBCP port
        .PHY_ADDR      (5'd3),           // in  : PHY-device MIF address
        // EEPROM
        .EEPROM_CS     (eeprom_cs),
        .EEPROM_SK     (eeprom_sk),
        .EEPROM_DI     (eeprom_di),
        .EEPROM_DO     (eeprom_do),
        // User registers
        .USR_REG_X3C   (),
        .USR_REG_X3D   (),
        .USR_REG_X3E   (),
        .USR_REG_X3F   (),
        // MII interface
        .GMII_RSTn     (phy_rst_n),
        .GMII_1000M    (1'b1),
        // TX
        .GMII_TX_CLK   (clk125_tx),
        .GMII_TX_EN    (gmii_tx_en),
        .GMII_TXD      (gmii_txd),
        .GMII_TX_ER    (gmii_tx_er),
        // RX
        .GMII_RX_CLK   (clk125_rx),
        .GMII_RX_DV    (gmii_rx_dv),
        .GMII_RXD      (gmii_rxd),
        .GMII_RX_ER    (gmii_rx_er),
        .GMII_CRS      (gmii_crs),
        .GMII_COL      (gmii_col),
        // Management IF
        .GMII_MDC      (mdio_phy_mdc),
        .GMII_MDIO_IN  (mdio_gem_i),
        .GMII_MDIO_OUT (mdio_gem_o),
        .GMII_MDIO_OE  (mdio_gem_t),
        // User I/F
        .SiTCP_RST     (sitcp_rst),
        // TCP connection control
        .TCP_OPEN_REQ  (1'b0),
        .TCP_OPEN_ACK  (tcp_open_ack),
        .TCP_ERROR     (),
        .TCP_CLOSE_REQ (tcp_close_req),
        .TCP_CLOSE_ACK (tcp_close_req),
        // FIFO I/F
        .TCP_RX_WC     (16'h0001),
        .TCP_RX_WR     (tcp_rx_wr),
        .TCP_RX_DATA   (tcp_rx_data),
        .TCP_TX_FULL   (tcp_tx_full),
        .TCP_TX_WR     (tcp_tx_wr),
        .TCP_TX_DATA   (tcp_tx_data),
        // RBCP
        .RBCP_ACT      (rbcp_act),
        .RBCP_ADDR     (rbcp_addr),
        .RBCP_WD       (rbcp_wd),
        .RBCP_WE       (rbcp_we),
        .RBCP_RE       (rbcp_re),
        .RBCP_ACK      (rbcp_ack),
        .RBCP_RD       (rbcp_rd)
    );


    // RBCP -> Bus bridge
    wire bus_wr, bus_rd, bus_rst;
    wire [31:0] bus_add;
    wire [7:0] bus_data;
    assign bus_rst = sitcp_rst;

    rbcp_to_bus irbcp_to_bus (
        .BUS_RST(bus_rst),
        .BUS_CLK(bus_clk),

        .RBCP_ACT (rbcp_act),
        .RBCP_ADDR(rbcp_addr),
        .RBCP_WD  (rbcp_wd),
        .RBCP_WE  (rbcp_we),
        .RBCP_RE  (rbcp_re),
        .RBCP_ACK (rbcp_ack),
        .RBCP_RD  (rbcp_rd),

        .BUS_WR  (bus_wr),
        .BUS_RD  (bus_rd),
        .BUS_ADD (bus_add),
        .BUS_DATA(bus_data)
    );

    // Si570 control remains on the fixed communication clock domain, so it
    // stays accessible while the variable serializer PLL loses/reacquires lock.
    wire i2c_clk;
    clock_divider #(
        .DIVISOR(1428)  // (100 MHz * 10 / 7) / 1428 = 100.04 kHz
    ) i_clock_divisor_i2c (
        .CLK  (bus_clk),
        .RESET(bus_rst),
        .CE   (),
        .CLOCK(i2c_clk)
    );

    i2c #(
        .BASEADDR(32'h00070000),
        .HIGHADDR(32'h000700ff),
        .ABUSWIDTH(32),
        .MEM_BYTES(32)
    ) i_i2c (
        .BUS_CLK (bus_clk),
        .BUS_RST (bus_rst),
        .BUS_ADD (bus_add),
        .BUS_DATA(bus_data),
        .BUS_RD  (bus_rd),
        .BUS_WR  (bus_wr),
        .I2C_CLK (i2c_clk),
        .I2C_SDA (I2C_SDA),
        .I2C_SCL (I2C_SCL)
    );

    // GPIO2 commands this controller over the Basil bus. The PLL remains at
    // its fixed D=1 and M=8; only the paired output dividers are rewritten.
    wire [4:0] seq_pll_request_n;
    wire seq_pll_apply_toggle;
    wire seq_pll_applied_toggle;
    wire seq_pll_busy;
    wire seq_pll_locked;
    wire seq_pll_error;
    wire [4:0] seq_pll_active_n;
    wire pll_datapath_hold;
    wire oserdes_reset;

    pll_drp pll_drp_seq (
        .CLK                 (bus_clk),
        .RST                 (comm_rst | bus_rst),
        .REQUEST_N           (seq_pll_request_n),
        .APPLY_TOGGLE        (seq_pll_apply_toggle),
        .PLL_LOCKED          (locked2),
        .DRP_DO              (pll_drp_do),
        .DRP_DRDY            (pll_drp_drdy),
        .DRP_DADDR           (pll_drp_daddr),
        .DRP_DI              (pll_drp_di),
        .DRP_DEN             (pll_drp_den),
        .DRP_DWE             (pll_drp_dwe),
        .PLL_RESET           (pll_drp_reset),
        .APPLIED_TOGGLE      (seq_pll_applied_toggle),
        .BUSY                (seq_pll_busy),
        .LOCKED              (seq_pll_locked),
        .ERROR               (seq_pll_error),
        .ACTIVE_N            (seq_pll_active_n),
        .DATAPATH_HOLD       (pll_datapath_hold)
    );

    // OSERDESE2 internally retimes reset into both clock domains. AMD UG471
    // requires external deassertion to be synchronous to CLKDIV (seq_clk).
    clock_reset_sync oserdes_reset_sync (
        .CLK        (seq_clk),
        .ASYNC_RESET(comm_rst | pll_datapath_hold),
        .RESET      (oserdes_reset)
    );


    // Data FIFO: core 32-bit -> SiTcp 8-bit TCP stream
    wire [31:0] fastrx_fifo_data_out;
    wire fastrx_fifo_empty, fastrx_fifo_read_next;
    wire full_32to8;
    wire empty_32to8;

    fifo_32_to_8 #(
        .DEPTH(64 * 1024)
    ) i_data_fifo (
        .RST(bus_rst),
        .CLK(bus_clk),

        .WRITE   (!fastrx_fifo_empty),
        .READ    (tcp_tx_wr),
        .DATA_IN (fastrx_fifo_data_out),
        .FULL    (full_32to8),
        .EMPTY   (empty_32to8),
        .DATA_OUT(tcp_tx_data)
    );

    assign fastrx_fifo_read_next = !full_32to8;
    assign tcp_tx_wr             = !tcp_tx_full && !empty_32to8;


    // LVDS I/O buffers
    // The widened sequencer produces one 64-bit word every 5 ns.  Each active
    // byte lane holds eight future time slices for one ADC control input;
    // OSERDES emits each byte as a 1.6 GHz serialized LVDS interval stream.
    // seq_gen already registers SEQ_SER_DATA on seq_clk. Feed it directly to
    // OSERDES so the serialized controls stay word-aligned with RX_SEN.
    wire [63:0] seq_ser_data;
    wire [31:0] seq_ser_data_tx;
    wire [3:0] seq_ser;

    // Apply board-level polarity before serialization. Channel order is
    // INIT, SAMP, COMP, LOGIC in byte lanes 0 through 3.
    assign seq_ser_data_tx[7:0]   = ~seq_ser_data[7:0];
    assign seq_ser_data_tx[15:8]  = seq_ser_data[15:8];
    assign seq_ser_data_tx[23:16] = ~seq_ser_data[23:16];
    assign seq_ser_data_tx[31:24] = ~seq_ser_data[31:24];

    genvar serdes_index;
    generate
        for (
            serdes_index = 0; serdes_index < 4; serdes_index = serdes_index + 1
        ) begin : gen_seq_serdes
            OSERDESE2 #(
                .DATA_RATE_OQ  ("DDR"),
                .DATA_RATE_TQ  ("SDR"),
                .DATA_WIDTH    (8),
                .INIT_OQ       (1'b0),
                .INIT_TQ       (1'b0),
                .SERDES_MODE   ("MASTER"),
                .SRVAL_OQ      (1'b0),
                .SRVAL_TQ      (1'b0),
                .TBYTE_CTL     ("FALSE"),
                .TBYTE_SRC     ("FALSE"),
                .TRISTATE_WIDTH(1)
            ) oserdes (
                .OQ(seq_ser[serdes_index]),
                .OFB(),
                .TQ(),
                .TFB(),
                .TBYTEOUT(),
                .SHIFTOUT1(),
                .SHIFTOUT2(),
                .CLK(ser_clk),
                .CLKDIV(seq_clk),
                .D1(seq_ser_data_tx[serdes_index*8]),
                .D2(seq_ser_data_tx[serdes_index*8+1]),
                .D3(seq_ser_data_tx[serdes_index*8+2]),
                .D4(seq_ser_data_tx[serdes_index*8+3]),
                .D5(seq_ser_data_tx[serdes_index*8+4]),
                .D6(seq_ser_data_tx[serdes_index*8+5]),
                .D7(seq_ser_data_tx[serdes_index*8+6]),
                .D8(seq_ser_data_tx[serdes_index*8+7]),
                .OCE(1'b1),
                .RST(oserdes_reset),
                .SHIFTIN1(1'b0),
                .SHIFTIN2(1'b0),
                .T1(1'b0),
                .T2(1'b0),
                .T3(1'b0),
                .T4(1'b0),
                .TBYTEIN(1'b0),
                .TCE(1'b0)
            );
        end
    endgenerate

    OBUFDS #(
        .IOSTANDARD("LVDS_25")
    ) obufds_clk_init (
        .O (CLK_INIT_P),
        .OB(CLK_INIT_N),
        .I (seq_ser[0])
    );
    OBUFDS #(
        .IOSTANDARD("LVDS_25")
    ) obufds_clk_samp (
        .O (CLK_SAMP_P),
        .OB(CLK_SAMP_N),
        .I (seq_ser[1])
    );
    OBUFDS #(
        .IOSTANDARD("LVDS_25")
    ) obufds_clk_comp (
        .O (CLK_COMP_P),
        .OB(CLK_COMP_N),
        .I (seq_ser[2])
    );
    OBUFDS #(
        .IOSTANDARD("LVDS_25")
    ) obufds_clk_logic (
        .O (CLK_LOGIC_P),
        .OB(CLK_LOGIC_N),
        .I (seq_ser[3])
    );

    // Comparator output from chip (LVDS input) with a Basil-controlled delay.
    // GPIO1 loads a runtime tap value without rebuilding the bitstream; the
    // power-up and reset value is zero taps.
    wire comp_out_ibuf;
    wire comp_out;
    wire [4:0] comp_idelay_taps;
    wire comp_idelay_load;
    wire comp_idelay_rdy;

    (* IODELAY_GROUP = "frida_comp_rx_delay" *)
    IDELAYCTRL idelayctrl_comp_out (
        .RDY(comp_idelay_rdy),
        .REFCLK(idelay_ref_clk),
        .RST(comm_rst)
    );

    IBUFDS #(
        .DIFF_TERM   ("TRUE"),
        .IBUF_LOW_PWR("FALSE"),
        .IOSTANDARD  ("LVDS_25")
    ) ibufds_comp_out (
        .O (comp_out_ibuf),
        .I (COMP_OUT_P),
        .IB(COMP_OUT_N)
    );

    (* IODELAY_GROUP = "frida_comp_rx_delay" *)
    IDELAYE2 #(
        .CINVCTRL_SEL         ("FALSE"),
        .DELAY_SRC            ("IDATAIN"),
        .HIGH_PERFORMANCE_MODE("FALSE"),
        .IDELAY_TYPE          ("VAR_LOAD"),
        .IDELAY_VALUE         (0),
        .PIPE_SEL             ("FALSE"),
        .REFCLK_FREQUENCY     (200.0),
        .SIGNAL_PATTERN       ("DATA")
    ) idelaye2_comp_out (
        .CNTVALUEOUT(),
        .DATAOUT    (comp_out),
        .C          (bus_clk),
        .CE         (1'b0),
        .CINVCTRL   (1'b0),
        .CNTVALUEIN (comp_idelay_taps),
        .DATAIN     (1'b0),
        .IDATAIN    (comp_out_ibuf),
        .INC        (1'b0),
        .LD         (comp_idelay_load),
        .LDPIPEEN   (1'b0),
        .REGRST     (comm_rst)
    );


    // FRIDA DAQ control core
    wire spi_sclk;
    wire spi_sdi;
    wire spi_sdo;
    wire spi_cs_b;
    wire rst_b;
    wire ampen_b;

    daq_core frida_core (
        .BUS_CLK (bus_clk),
        .BUS_RST (bus_rst),
        .BUS_ADD (bus_add),
        .BUS_DATA(bus_data),
        .BUS_RD  (bus_rd),
        .BUS_WR  (bus_wr),

        .SEQ_CLK(seq_clk),

        .SEQ_PLL_REQUEST_N     (seq_pll_request_n),
        .SEQ_PLL_APPLY_TOGGLE  (seq_pll_apply_toggle),
        .SEQ_PLL_APPLIED_TOGGLE(seq_pll_applied_toggle),
        .SEQ_PLL_BUSY          (seq_pll_busy),
        .SEQ_PLL_LOCKED        (seq_pll_locked),
        .SEQ_PLL_ERROR         (seq_pll_error),
        .SEQ_PLL_ACTIVE_N      (seq_pll_active_n),

        .SEQ_SER_DATA(seq_ser_data),

        .SPI_CLK (spi_clk),   // 10 MHz SPI clock
        .SPI_SCLK(spi_sclk),
        .SPI_SDI (spi_sdi),
        .SPI_SDO (spi_sdo),
        .SPI_CS_B(spi_cs_b),

        .RST_B  (rst_b),
        .AMPEN_B(ampen_b),

        .COMP_IDELAY_TAPS(comp_idelay_taps),
        .COMP_IDELAY_LOAD(comp_idelay_load),
        .COMP_IDELAY_RDY (comp_idelay_rdy),

        .FASTRX_FIFO_DATA_OUT (fastrx_fifo_data_out),
        .FASTRX_FIFO_READ_NEXT(fastrx_fifo_read_next),
        .FASTRX_FIFO_EMPTY    (fastrx_fifo_empty),

        .COMP_OUT(comp_out),  // Comparator signal, input to fastrx
        .RESET   (comm_rst),
        .SEQ_RESET(pll_datapath_hold),
        .LED_OUT (LED)
    );


    // SPI Signals and Level shifter reference voltages
    (* dont_touch = "true" *) wire v_0v_lo = 1'b0;
    (* dont_touch = "true" *) wire v_2v5_hi = 1'b1;
    assign V_0V_LO   = v_0v_lo;
    assign V_2V5_HI  = v_2v5_hi;
    assign SPI_SCLK  = spi_sclk;
    assign SPI_SDI   = spi_sdi;
    assign spi_sdo   = SPI_SDO;  // Signal coming from ASIC
    assign SPI_CS_B  = spi_cs_b;
    assign RST_B     = rst_b;
    assign AMPEN_B   = ampen_b;


    // PMOD debug header for logic analyzer
    // PMOD[0..3] = PMOD1..4 (pins 1-4), PMOD[4..7] = PMOD7..10 (pins 7-10)
    // Pins 5,6,11,12 are GND/VCC — not available as signals.
    assign PMOD[0]   = spi_sclk;  // Pin 1: SPI_SCLK
    assign PMOD[1]   = spi_sdi;  // Pin 2: SPI_SDI  (MOSI)
    assign PMOD[2]   = spi_sdo;  // Pin 3: SPI_SDO  (MISO)
    assign PMOD[3]   = spi_cs_b;  // Pin 4: SPI_CS_B
    assign PMOD[7:4] = 4'b0000;  // Pins 7-10: unused

endmodule
