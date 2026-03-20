
# ------------------------------------------------------------
#  Copyright (c) SILAB , Physics Institute of Bonn University
# ------------------------------------------------------------
#
#   Constraints for the BDAQ53 PCB with the Mercury+ KX2(160T-2) FPGA board
#
#   VCC_IO
#   ------
#   Bank 12: VCCO_12        1.0 - 3.3 V
#   Bank 13: VCCO_13        1.0 - 3.3 V
#   Bank 14: VCCO_0/VCCO_14 1.8 - 2.5 V     ETH-PHY
#   Bank 15: VCCO_15        1.0 - 3.3 V
#   Bank 16: VCCO_16        1.8 - 3.3 V
#
# Clock domains
# CLK_SYS: 100 MHz, from xtal oscillator
# -> PLL1: CLK40PLL: TDC
#          CLK160PLL: TDC
#          CLK320PLL: TDC
# -> PLL2: BUS_CLK_PLL: 142.86 MHz, main system clock (7 ns)
#          CLK125PLLTX, Ethernet
#          CLK125PLLTX90: Ethernet
# CLK_MGT_REF: 160 MHz, from Si570 programmable oscilaltor
# ->        CMDCLK: 160 MHz, command encoder
#           USERCLK: 20 MHz, Aurora word clock
# CLK_RGMII_RX: 125 MHz, from Ethernet chip

# Clock inputs
create_clock -period 10.000 -name CLK_SYS -add [get_ports clkin]
create_clock -period 8.000 -name CLK_RGMII_RX -add [get_ports rgmii_rxc]
create_clock -period 6.250 -name CLK_MGT_REF -add [get_ports MGT_REFCLK0_P]

# Internally generated Aurora receiver clocks
create_clock -period 25.000 -name RXOUTCLK_0 [get_pins -hier -filter {name=~*i_aurora_rx*[0]*gtxe2_i/RXOUTCLK}]
create_clock -period 25.000 -name RXOUTCLK_1 [get_pins -hier -filter {name=~*i_aurora_rx*[1]*gtxe2_i/RXOUTCLK}]
create_clock -period 25.000 -name RXOUTCLK_2 [get_pins -hier -filter {name=~*i_aurora_rx*[2]*gtxe2_i/RXOUTCLK}]
create_clock -period 25.000 -name RXOUTCLK_3 [get_pins -hier -filter {name=~*i_aurora_rx*[3]*gtxe2_i/RXOUTCLK}]
create_clock -period 25.000 -name RXOUTCLK_4 [get_pins -hier -filter {name=~*i_aurora_rx*[4]*gtxe2_i/RXOUTCLK}]
create_clock -period 25.000 -name RXOUTCLK_5 [get_pins -hier -filter {name=~*i_aurora_rx*[5]*gtxe2_i/RXOUTCLK}]
create_clock -period 25.000 -name RXOUTCLK_6 [get_pins -hier -filter {name=~*i_aurora_rx*[6]*gtxe2_i/RXOUTCLK}]

# Only needed for mult-lane FW (instead of the single-lane clocks above)
create_clock -period 25.000 -name RXOUTCLK [get_pins -hier -filter {name=~*i_aurora_rx*gtxe2_i/RXOUTCLK}]

# Derived and forwarded clocks
create_generated_clock -name I2C_CLK -source [get_pins PLLE2_BASE_inst/CLKOUT0] -divide_by 1600 [get_pins i_bdaq53_core/i_clock_divisor_i2c/CLOCK_reg/Q]
create_generated_clock -name SPI_CLK -source [get_pins PLLE2_BASE_inst/CLKOUT0] -divide_by 4 [get_pins i_bdaq53_core/i_clock_divisor_spi/CLOCK_reg/Q]
create_generated_clock -name i_bdaq53_core/i_aurora_tx/i_clock_divisor_aur/AURORA_TX_CLK_DIV -source [get_pins {i_bdaq53_core/i_aurora_tx/mmcm_adv_inst_tx/CLKOUT0}] -divide_by 20 [get_pins {i_bdaq53_core/i_aurora_tx/i_clock_divisor_aur/CLOCK_reg/Q}]
create_generated_clock -name DP_GPIO_AUX_P -source [get_pins {oddr_cmd_clk/C}] -divide_by 1 [get_ports {DP_GPIO_AUX_P}]
create_generated_clock -name rgmii_txc -source [get_pins {rgmii/ODDR_inst/C}] -divide_by 1 [get_ports {rgmii_txc}]

# Exclude asynchronous clock domains from timing (handled by CDC FIFOs etc)
set_clock_groups -asynchronous \
-group BUS_CLK_PLL \
-group CLK_RGMII_RX \
-group {CLK125PLLTX CLK125PLLTX90} \
-group {CLK320PLL CLK160PLL CLK40PLL} \
-group [get_clocks -include_generated_clocks CLK_MGT_REF] \
-group [get_clocks RXOUTCLK*] \
-group SPI_CLK \
-group I2C_CLK

# Exclusive clocks (phase switching for data merging)
set_clock_groups -logically_exclusive -group [get_clocks -include_generated_clocks {AURORA_SER_CLK_PLL}] -group [get_clocks -include_generated_clocks {AURORA_SER_CLK_B_PLL}]

# SiTCP
set_max_delay -datapath_only -from [get_clocks CLK125PLLTX] -to [get_ports {rgmii_txd[*]}] 4
set_max_delay -datapath_only -from [get_clocks CLK125PLLTX] -to [get_ports rgmii_tx_ctl] 4
set_max_delay -datapath_only -from [get_clocks CLK125PLLTX90] -to [get_ports rgmii_txc] 4

# false paths (resets etc)
set_false_path -from [get_pins {i_bdaq53_core/i_aurora_rx/aurora_frame/aurora_64b66b_1lane_block_i/generate_aurora_rx[3].aurora_64b66b_1lane_i/inst/aurora_64b66b_1lane_wrapper_i/common_reset_cbcc_i/reset_cbcc_comb_reg/C}] -to [get_pins {i_bdaq53_core/i_aurora_rx/aurora_frame/aurora_64b66b_1lane_block_i/generate_aurora_rx[3].aurora_64b66b_1lane_i/inst/aurora_64b66b_1lane_wrapper_i/common_reset_cbcc_i/u_rst_sync_rst_cbcc_rd_clk/stg1_aurora_64b66b_1lane_cdc_to_reg/D}]
set_false_path -from [get_pins {i_bdaq53_core/i_aurora_rx/aurora_frame/RX_CHANNEL_UP_reg[*]/C}]
set_false_path -from [get_pins {generate_hitor_ibufds[*].oddr_hitor_gen/C}] -to [get_pins {i_bdaq53_core/i_tlu_controller/i_tlu_controller_core/three_stage_lemo_trigger_synchronizer_trg_clk/out_d_ff_1_reg[0]/D}]
set_false_path -from [get_pins sitcp/SiTCP/SiTCP/UDP/UDP_LOC/busAddr_21/C] -to [get_pins {i_bdaq53_core/i_gpio_xadc_fpga_temp/core/DIRECTION_DATA_reg[0][*]/CE}]
set_false_path -from [get_pins sitcp/SiTCP/SiTCP/UDP/UDP_LOC/busAddr_21/C] -to [get_pins {i_bdaq53_core/i_gpio_xadc_vpvn/core/DIRECTION_DATA_reg[1][*]/CE}]

#Oscillator 100MHz
set_property PACKAGE_PIN AA4 [get_ports clkin]
set_property IOSTANDARD LVCMOS15 [get_ports clkin]

#Oscillator 200MHz
#set_property PACKAGE_PIN AC11 [get_ports CLK200_N]
#set_property PACKAGE_PIN AB11 [get_ports CLK200_P]
#set_property IOSTANDARD LVDS [get_ports CLK200_*]

#CLK Mux
set_property PACKAGE_PIN D23 [get_ports MGT_REF_SEL]
set_property IOSTANDARD LVCMOS33 [get_ports MGT_REF_SEL]
set_property PULLUP true [get_ports MGT_REF_SEL]

#Reset push button
set_property PACKAGE_PIN G9 [get_ports RESET_BUTTON]
set_property IOSTANDARD LVCMOS25 [get_ports RESET_BUTTON]
set_property PULLUP true [get_ports RESET_BUTTON]

#USER push button
set_property PACKAGE_PIN Y26 [get_ports USER_BUTTON]
set_property IOSTANDARD LVCMOS25 [get_ports USER_BUTTON]
set_property PULLUP true [get_ports USER_BUTTON]

#SITCP
set_property SLEW FAST [get_ports mdio_phy_mdc]
set_property IOSTANDARD LVCMOS33 [get_ports mdio_phy_mdc]
set_property PACKAGE_PIN B25 [get_ports mdio_phy_mdc]

set_property SLEW FAST [get_ports mdio_phy_mdio]
set_property IOSTANDARD LVCMOS33 [get_ports mdio_phy_mdio]
set_property PACKAGE_PIN B26 [get_ports mdio_phy_mdio]

set_property SLEW FAST [get_ports phy_rst_n]
set_property IOSTANDARD LVCMOS33 [get_ports phy_rst_n]
#M20 is routed to Connector C. The Ethernet PHY on th KX2 board has NO reset connection to an FPGA pin
set_property PACKAGE_PIN M20 [get_ports phy_rst_n]

set_property IOSTANDARD LVCMOS33 [get_ports rgmii_rxc]
set_property PACKAGE_PIN G22 [get_ports rgmii_rxc]

set_property IOSTANDARD LVCMOS33 [get_ports rgmii_rx_ctl]
set_property PACKAGE_PIN F23 [get_ports rgmii_rx_ctl]
set_property IOSTANDARD LVCMOS33 [get_ports {rgmii_rxd[0]}]
set_property PACKAGE_PIN H23 [get_ports {rgmii_rxd[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgmii_rxd[1]}]
set_property PACKAGE_PIN H24 [get_ports {rgmii_rxd[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgmii_rxd[2]}]
set_property PACKAGE_PIN J21 [get_ports {rgmii_rxd[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgmii_rxd[3]}]
set_property PACKAGE_PIN H22 [get_ports {rgmii_rxd[3]}]

set_property SLEW FAST [get_ports rgmii_txc]
set_property IOSTANDARD LVCMOS33 [get_ports rgmii_txc]
set_property PACKAGE_PIN K23 [get_ports rgmii_txc]

set_property SLEW FAST [get_ports rgmii_tx_ctl]
set_property IOSTANDARD LVCMOS33 [get_ports rgmii_tx_ctl]
set_property PACKAGE_PIN J23 [get_ports rgmii_tx_ctl]

set_property SLEW FAST [get_ports {rgmii_txd[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgmii_txd[0]}]
set_property PACKAGE_PIN J24 [get_ports {rgmii_txd[0]}]
set_property SLEW FAST [get_ports {rgmii_txd[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgmii_txd[1]}]
set_property PACKAGE_PIN J25 [get_ports {rgmii_txd[1]}]
set_property SLEW FAST [get_ports {rgmii_txd[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgmii_txd[2]}]
set_property PACKAGE_PIN L22 [get_ports {rgmii_txd[2]}]
set_property SLEW FAST [get_ports {rgmii_txd[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgmii_txd[3]}]
set_property PACKAGE_PIN K22 [get_ports {rgmii_txd[3]}]

# Aurora related signals
set_property PACKAGE_PIN H6 [get_ports MGT_REFCLK0_P]
set_property PACKAGE_PIN H5 [get_ports MGT_REFCLK0_N]
#set_property PACKAGE_PIN K6 [get_ports MGT_REFCLK1_P]
#set_property PACKAGE_PIN K5 [get_ports MGT_REFCLK1_N]

set_property PACKAGE_PIN R4 [get_ports {MGT_RX_P[0]}]
set_property PACKAGE_PIN R3 [get_ports {MGT_RX_N[0]}]
set_property PACKAGE_PIN N4 [get_ports {MGT_RX_P[1]}]
set_property PACKAGE_PIN N3 [get_ports {MGT_RX_N[1]}]
set_property PACKAGE_PIN L4 [get_ports {MGT_RX_P[2]}]
set_property PACKAGE_PIN L3 [get_ports {MGT_RX_N[2]}]
set_property PACKAGE_PIN J4 [get_ports {MGT_RX_P[3]}]
set_property PACKAGE_PIN J3 [get_ports {MGT_RX_N[3]}]
set_property PACKAGE_PIN G3 [get_ports {MGT_RX_N[4]}]
set_property PACKAGE_PIN G4 [get_ports {MGT_RX_P[4]}]
set_property PACKAGE_PIN E4 [get_ports {MGT_RX_P[5]}]
set_property PACKAGE_PIN E3 [get_ports {MGT_RX_N[5]}]
set_property PACKAGE_PIN C4 [get_ports {MGT_RX_P[6]}]
set_property PACKAGE_PIN C3 [get_ports {MGT_RX_N[6]}]
set_property PACKAGE_PIN B6 [get_ports {MGT_RX_P[7]}]
set_property PACKAGE_PIN B5 [get_ports {MGT_RX_N[7]}]

# DP_ML ("DP2") connected to SelectIOs
set_property PACKAGE_PIN A18 [get_ports DP_GPIO_P[0]]
set_property PACKAGE_PIN A19 [get_ports DP_GPIO_N[0]]
set_property PACKAGE_PIN C19 [get_ports DP_GPIO_P[1]]
set_property PACKAGE_PIN B19 [get_ports DP_GPIO_N[1]]
set_property PACKAGE_PIN E18 [get_ports DP_GPIO_P[2]]
set_property PACKAGE_PIN D18 [get_ports DP_GPIO_N[2]]
set_property PACKAGE_PIN B17 [get_ports DP_GPIO_P[3]]
set_property PACKAGE_PIN A17 [get_ports DP_GPIO_N[3]]
set_property IOSTANDARD LVDS_25 [get_ports DP_GPIO*]
set_property PACKAGE_PIN C16 [get_ports DP_GPIO_AUX_P]
set_property PACKAGE_PIN B16 [get_ports DP_GPIO_AUX_N]
set_property IOSTANDARD LVDS_25 [get_ports DP_GPIO_AUX*]

# mDP_ML ("mini DP") connected to SelectIOs
set_property PACKAGE_PIN B14 [get_ports {mDP_GPIO_P[0]}]
set_property PACKAGE_PIN A14 [get_ports {mDP_GPIO_N[0]}]
set_property PACKAGE_PIN C12 [get_ports {mDP_GPIO_P[1]}]
set_property PACKAGE_PIN C11 [get_ports {mDP_GPIO_N[1]}]
set_property PACKAGE_PIN H14 [get_ports {mDP_GPIO_P[2]}]
set_property PACKAGE_PIN G14 [get_ports {mDP_GPIO_N[2]}]
set_property PACKAGE_PIN B12 [get_ports {mDP_GPIO_P[3]}]
set_property PACKAGE_PIN B11 [get_ports {mDP_GPIO_N[3]}]
set_property IOSTANDARD LVDS_25 [get_ports mDP_GPIO*]

# DP_ML ("DP1") connected to MGTs
set_property PACKAGE_PIN H19 [get_ports DP_ML_AUX_P]
set_property PACKAGE_PIN G20 [get_ports DP_ML_AUX_N]
set_property IOSTANDARD LVDS_25 [get_ports DP_ML_AUX*]

# DP_SL ("DP2..4") connected to MGTs
# DP_SL0: B124, B126; DP_SL1: B130, B132; DP_SL2: B136, B138
set_property PACKAGE_PIN C17 [get_ports {DP_SL_AUX_P[2]}]
set_property PACKAGE_PIN C18 [get_ports {DP_SL_AUX_N[2]}]
set_property PACKAGE_PIN G17 [get_ports {DP_SL_AUX_P[1]}]
set_property PACKAGE_PIN F18 [get_ports {DP_SL_AUX_N[1]}]
set_property PACKAGE_PIN D19 [get_ports {DP_SL_AUX_P[0]}]
set_property PACKAGE_PIN D20 [get_ports {DP_SL_AUX_N[0]}]
set_property IOSTANDARD LVDS_25 [get_ports DP_SL_AUX*]

# Displayport RESET signals 0:DP1, 1:DP3, 2:DP4, 3:DP5, 4:mDP
#set_property PACKAGE_PIN G10 [get_ports {GPIO_RESET[4]}]
set_property PACKAGE_PIN K18 [get_ports {GPIO_RESET[3]}]
set_property PACKAGE_PIN L17 [get_ports {GPIO_RESET[2]}]
set_property PACKAGE_PIN H11 [get_ports {GPIO_RESET[1]}]
set_property PACKAGE_PIN H12 [get_ports {GPIO_RESET[0]}]
set_property IOSTANDARD LVCMOS25 [get_ports GPIO_RESET*]
set_property PULLUP TRUE [get_ports GPIO_RESET*]

# Displayport VDD_SENSE signals 0:DP1, 1:DP3, 2:DP4, 3:DP5
set_property PACKAGE_PIN V22 [get_ports {GPIO_SENSE[3]}]
set_property PACKAGE_PIN W23 [get_ports {GPIO_SENSE[2]}]
set_property PACKAGE_PIN W24 [get_ports {GPIO_SENSE[1]}]
set_property PACKAGE_PIN AD26 [get_ports {GPIO_SENSE[0]}]
set_property IOSTANDARD LVCMOS25 [get_ports GPIO_SENSE*]
set_property PULLUP TRUE [get_ports GPIO_SENSE*]

# Debug LEDs
#LED 0..3 are onboard LEDs: Bank 32, 33 running at 1.5 V)
set_property PACKAGE_PIN U9 [get_ports {LED[0]}]
set_property IOSTANDARD LVCMOS15 [get_ports {LED[0]}]
set_property PACKAGE_PIN V12 [get_ports {LED[1]}]
set_property IOSTANDARD LVCMOS15 [get_ports {LED[1]}]
set_property PACKAGE_PIN V13 [get_ports {LED[2]}]
set_property IOSTANDARD LVCMOS15 [get_ports {LED[2]}]
set_property PACKAGE_PIN W13 [get_ports {LED[3]}]
set_property IOSTANDARD LVCMOS15 [get_ports {LED[3]}]
#LED 4..7 are LEDs on the BDAQ53 base board. They have pull-ups to 1.8 V.
set_property PACKAGE_PIN E21 [get_ports {LED[4]}]
set_property IOSTANDARD LVCMOS33 [get_ports {LED[4]}]
set_property PACKAGE_PIN E22 [get_ports {LED[5]}]
set_property IOSTANDARD LVCMOS33 [get_ports {LED[5]}]
set_property PACKAGE_PIN D21 [get_ports {LED[6]}]
set_property IOSTANDARD LVCMOS33 [get_ports {LED[6]}]
set_property PACKAGE_PIN C22 [get_ports {LED[7]}]
set_property IOSTANDARD LVCMOS33 [get_ports {LED[7]}]
set_property SLEW SLOW [get_ports LED*]


# LEMO
set_property PACKAGE_PIN AB21 [get_ports LEMO_TX0]
set_property PACKAGE_PIN AD25 [get_ports LEMO_TX1]
set_property IOSTANDARD LVCMOS25 [get_ports LEMO_TX*]
set_property SLEW FAST [get_ports LEMO_TX*]
set_property PACKAGE_PIN AB22 [get_ports LEMO_RX0]
set_property PACKAGE_PIN AD23 [get_ports LEMO_RX1]
set_property IOSTANDARD LVCMOS25 [get_ports LEMO_RX*]

# PMOD
#  ____________
# |1 2 3 4  G +|  First PMOD channel (4 signal lines, ground and vcc)
# |7_8_9_10_G_+|  Second PMOD channel ("")
#
# PMOD connector Pin10-->PMOD0; Pin9-->PMOD1; Pin8-->PMOD2; Pin7-->PMOD3;
set_property PACKAGE_PIN AC23 [get_ports {PMOD[0]}]
set_property PACKAGE_PIN AC24 [get_ports {PMOD[1]}]
set_property PACKAGE_PIN W25 [get_ports {PMOD[2]}]
set_property PACKAGE_PIN W26 [get_ports {PMOD[3]}]
# PMOD connector Pin4-->PMOD4; Pin3-->PMOD5; Pin2-->PMOD6; Pin1-->PMOD7;
set_property PACKAGE_PIN U26 [get_ports {PMOD[4]}]
set_property PACKAGE_PIN V26 [get_ports {PMOD[5]}]
set_property PACKAGE_PIN AE25 [get_ports {PMOD[6]}]
set_property PACKAGE_PIN AD24 [get_ports {PMOD[7]}]
set_property IOSTANDARD LVCMOS25 [get_ports PMOD*]
# pull down the PMOD pins which are used as inputs
set_property PULLDOWN true [get_ports {PMOD[0]}]
set_property PULLDOWN true [get_ports {PMOD[1]}]
set_property PULLDOWN true [get_ports {PMOD[2]}]
set_property PULLDOWN true [get_ports {PMOD[3]}]

# I2C pins
set_property PACKAGE_PIN L23 [get_ports I2C_SCL]
set_property PACKAGE_PIN C24 [get_ports I2C_SDA]
set_property IOSTANDARD LVCMOS33 [get_ports I2C_*]
set_property SLEW SLOW [get_ports I2C_*]

# EEPROM (SPI for SiTCP)
set_property PACKAGE_PIN A20 [get_ports EEPROM_CS]
set_property PACKAGE_PIN B20 [get_ports EEPROM_SK]
set_property PACKAGE_PIN A24 [get_ports EEPROM_DI]
set_property PACKAGE_PIN A23 [get_ports EEPROM_DO]
set_property IOSTANDARD LVCMOS33 [get_ports EEPROM_*]

# SPI configuration flash
set_property CONFIG_MODE SPIx4 [current_design]
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property BITSTREAM.CONFIG.CONFIGRATE 33 [current_design]

# TLU
set_property PACKAGE_PIN AE23 [get_ports RJ45_TRIGGER]
set_property PACKAGE_PIN U22 [get_ports RJ45_RESET]
set_property IOSTANDARD LVCMOS25 [get_ports RJ45_RESET]
set_property IOSTANDARD LVCMOS25 [get_ports RJ45_TRIGGER]

# NTC_MUX
set_property PACKAGE_PIN B21 [get_ports {NTC_MUX[0]}]
set_property PACKAGE_PIN D26 [get_ports {NTC_MUX[1]}]
set_property PACKAGE_PIN C26 [get_ports {NTC_MUX[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {NTC_MUX*}]
set_property SLEW SLOW [get_ports NTC*]

set_switching_activity -toggle_rate 0.000 -static_probability 0.000 [get_nets sitcp/SiTCP/SiTCP_INT/SiTCP_RESET_OUT]
