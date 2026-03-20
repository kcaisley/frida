# ------------------------------------------------------------
# FRIDA DAQ - Constraints for BDAQ53 PCB with Mercury KX1 (xc7k160t-1)
# ------------------------------------------------------------
#
# System/Ethernet pins: from tj-monopix2-daq/firmware/src/bdaq53_kx1.xdc
# FRIDA chip pins:      TODO - fill in from KiCad schematic (frida65A)
#

# ===== Clock definitions =====
create_clock -period 10.000 -name CLK_SYS -add [get_ports FCLK_IN]
create_clock -period 8.000 -name CLK_RGMII_RX -add [get_ports rgmii_rxc]

# Exclude asynchronous clock domains
set_clock_groups -asynchronous \
    -group {BUS_CLK_PLL} \
    -group {CLK125PLLTX CLK125PLLTX90} \
    -group CLK_RGMII_RX

# SiTCP RGMII output timing
set_max_delay -datapath_only -from [get_clocks CLK125PLLTX] -to [get_ports {rgmii_txd[*]}] 4.000
set_max_delay -datapath_only -from [get_clocks CLK125PLLTX] -to [get_ports rgmii_tx_ctl] 4.000
set_max_delay -datapath_only -from [get_clocks CLK125PLLTX90] -to [get_ports rgmii_txc] 4.000
set_property ASYNC_REG true [get_cells sitcp/SiTCP/GMII/GMII_TXCNT/irMacPauseExe_0]
set_property ASYNC_REG true [get_cells sitcp/SiTCP/GMII/GMII_TXCNT/irMacPauseExe_1]

# ===== System clock (100 MHz) =====
set_property PACKAGE_PIN AA3 [get_ports FCLK_IN]
set_property IOSTANDARD LVCMOS15 [get_ports FCLK_IN]

# ===== Reset button =====
set_property PACKAGE_PIN C18 [get_ports RESET_BUTTON]
set_property IOSTANDARD LVCMOS25 [get_ports RESET_BUTTON]
set_property PULLUP true [get_ports RESET_BUTTON]

# ===== LEDs =====
# LED 0..3: onboard KX1 LEDs
set_property PACKAGE_PIN M17 [get_ports {LED[0]}]
set_property PACKAGE_PIN L18 [get_ports {LED[1]}]
set_property PACKAGE_PIN L17 [get_ports {LED[2]}]
set_property PACKAGE_PIN K18 [get_ports {LED[3]}]
# LED 4..7: BDAQ53 base board LEDs
set_property PACKAGE_PIN P26 [get_ports {LED[4]}]
set_property PACKAGE_PIN M25 [get_ports {LED[5]}]
set_property PACKAGE_PIN L25 [get_ports {LED[6]}]
set_property PACKAGE_PIN P23 [get_ports {LED[7]}]
set_property IOSTANDARD LVCMOS25 [get_ports {LED[*]}]
set_property SLEW SLOW [get_ports LED*]

# ===== EEPROM (SPI for SiTCP) =====
set_property PACKAGE_PIN G14 [get_ports EEPROM_CS]
set_property PACKAGE_PIN H11 [get_ports EEPROM_SK]
set_property PACKAGE_PIN D8 [get_ports EEPROM_DI]
set_property PACKAGE_PIN A8 [get_ports EEPROM_DO]
set_property IOSTANDARD LVCMOS33 [get_ports EEPROM_*]

# ===== Ethernet (RGMII) =====
set_property SLEW FAST [get_ports mdio_phy_mdc]
set_property IOSTANDARD LVCMOS25 [get_ports mdio_phy_mdc]
set_property PACKAGE_PIN N16 [get_ports mdio_phy_mdc]

set_property SLEW FAST [get_ports mdio_phy_mdio]
set_property IOSTANDARD LVCMOS25 [get_ports mdio_phy_mdio]
set_property PACKAGE_PIN U16 [get_ports mdio_phy_mdio]

set_property SLEW FAST [get_ports phy_rst_n]
set_property IOSTANDARD LVCMOS25 [get_ports phy_rst_n]
set_property PACKAGE_PIN M20 [get_ports phy_rst_n]

set_property IOSTANDARD LVCMOS25 [get_ports rgmii_rxc]
set_property PACKAGE_PIN R21 [get_ports rgmii_rxc]

set_property IOSTANDARD LVCMOS25 [get_ports rgmii_rx_ctl]
set_property PACKAGE_PIN P21 [get_ports rgmii_rx_ctl]
set_property IOSTANDARD LVCMOS25 [get_ports {rgmii_rxd[0]}]
set_property PACKAGE_PIN P16 [get_ports {rgmii_rxd[0]}]
set_property IOSTANDARD LVCMOS25 [get_ports {rgmii_rxd[1]}]
set_property PACKAGE_PIN N17 [get_ports {rgmii_rxd[1]}]
set_property IOSTANDARD LVCMOS25 [get_ports {rgmii_rxd[2]}]
set_property PACKAGE_PIN R16 [get_ports {rgmii_rxd[2]}]
set_property IOSTANDARD LVCMOS25 [get_ports {rgmii_rxd[3]}]
set_property PACKAGE_PIN R17 [get_ports {rgmii_rxd[3]}]

set_property SLEW FAST [get_ports rgmii_txc]
set_property IOSTANDARD LVCMOS25 [get_ports rgmii_txc]
set_property PACKAGE_PIN R18 [get_ports rgmii_txc]

set_property SLEW FAST [get_ports rgmii_tx_ctl]
set_property IOSTANDARD LVCMOS25 [get_ports rgmii_tx_ctl]
set_property PACKAGE_PIN P18 [get_ports rgmii_tx_ctl]

set_property SLEW FAST [get_ports {rgmii_txd[0]}]
set_property IOSTANDARD LVCMOS25 [get_ports {rgmii_txd[0]}]
set_property PACKAGE_PIN N18 [get_ports {rgmii_txd[0]}]
set_property SLEW FAST [get_ports {rgmii_txd[1]}]
set_property IOSTANDARD LVCMOS25 [get_ports {rgmii_txd[1]}]
set_property PACKAGE_PIN M19 [get_ports {rgmii_txd[1]}]
set_property SLEW FAST [get_ports {rgmii_txd[2]}]
set_property IOSTANDARD LVCMOS25 [get_ports {rgmii_txd[2]}]
set_property PACKAGE_PIN U17 [get_ports {rgmii_txd[2]}]
set_property SLEW FAST [get_ports {rgmii_txd[3]}]
set_property IOSTANDARD LVCMOS25 [get_ports {rgmii_txd[3]}]
set_property PACKAGE_PIN T17 [get_ports {rgmii_txd[3]}]

# ===== FRIDA chip signals =====
# TODO: Fill in pin assignments once PCB connector mapping is finalized
#
# DP5 (DP_ML, SelectIOs on KX1): 4 LVDS pairs for sequencer clocks
#   Pair 0: K16/K17, Pair 1: L19/L20, Pair 2: H17/H18, Pair 3: G19/G20
#
# RJ45: SPI, GPIO, and COMP_OUT
#   Pin mapping TBD from FRIDA PCB schematic

# ===== SPI configuration flash =====
set_property CONFIG_MODE SPIx4 [current_design]
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property BITSTREAM.CONFIG.CONFIGRATE 33 [current_design]
