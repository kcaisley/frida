# ------------------------------------------------------------
# FRIDA DAQ - Constraints for BDAQ53 + Mercury+ KX2 (xc7k160t-2)
# ------------------------------------------------------------
#
# Pin sources:
#   System/Ethernet: bdaq53/firmware/src/bdaq53.xdc (KX2)
#   DP5 pins:        Enclustra Mercury Master Pinout (Connector B)
#   RJ45 D pins:     Mercury Master Pinout (Connector B) + BDAQ53 schematic
#
# Signals not used by FRIDA (removed from bdaq53 reference):
#   Aurora / MGT (CLK_MGT_REF, MGT_REFCLK, MGT_RX, DP1 MGT AUX, DP_SL)
#   CLK200 oscillator, I2C, LEMO, PMOD, TLU (RJ45_TRIGGER/RESET)
#   mDP_ML (mini DisplayPort), GPIO_RESET, GPIO_SENSE, NTC_MUX
#   USER_BUTTON, derived clocks (I2C_CLK, SPI_CLK, AURORA_TX_CLK_DIV)

# ===== Clocks =====
create_clock -period 10.000 -name CLK_SYS -add [get_ports FCLK_IN]
create_clock -period 8.000 -name CLK_RGMII_RX -add [get_ports rgmii_rxc]

set_clock_groups -asynchronous \
    -group {BUS_CLK_PLL} \
    -group {CLK125PLLTX CLK125PLLTX90} \
    -group CLK_RGMII_RX \
    -group {SEQ_CLK_PLL}  ;# seq_gen config regs are stable before sequencer starts

# ===== SiTCP timing =====
set_max_delay -datapath_only -from [get_clocks CLK125PLLTX] -to [get_ports {rgmii_txd[*]}] 4.000
set_max_delay -datapath_only -from [get_clocks CLK125PLLTX] -to [get_ports rgmii_tx_ctl] 4.000
set_max_delay -datapath_only -from [get_clocks CLK125PLLTX90] -to [get_ports rgmii_txc] 4.000
set_property ASYNC_REG true [get_cells sitcp/SiTCP/GMII/GMII_TXCNT/irMacPauseExe_0]
set_property ASYNC_REG true [get_cells sitcp/SiTCP/GMII/GMII_TXCNT/irMacPauseExe_1]

# ===== System clock (100 MHz) =====
# Note: KX2 uses AA4 (LVCMOS15), KX1 uses AA3 (LVCMOS15)
set_property PACKAGE_PIN AA4 [get_ports FCLK_IN]
set_property IOSTANDARD LVCMOS15 [get_ports FCLK_IN]

# ===== Reset button =====
set_property PACKAGE_PIN G9 [get_ports RESET_BUTTON]
set_property IOSTANDARD LVCMOS25 [get_ports RESET_BUTTON]
set_property PULLUP true [get_ports RESET_BUTTON]

# ===== User button (SW_USER_B, active low) =====
set_property PACKAGE_PIN Y26 [get_ports USER_BUTTON]
set_property IOSTANDARD LVCMOS25 [get_ports USER_BUTTON]
set_property PULLUP true [get_ports USER_BUTTON]

# ===== LEDs =====
# LED 0..3: onboard KX2 module LEDs (Bank 32/33, LVCMOS15)
set_property PACKAGE_PIN U9 [get_ports {LED[0]}]
set_property IOSTANDARD LVCMOS15 [get_ports {LED[0]}]
set_property PACKAGE_PIN V12 [get_ports {LED[1]}]
set_property IOSTANDARD LVCMOS15 [get_ports {LED[1]}]
set_property PACKAGE_PIN V13 [get_ports {LED[2]}]
set_property IOSTANDARD LVCMOS15 [get_ports {LED[2]}]
set_property PACKAGE_PIN W13 [get_ports {LED[3]}]
set_property IOSTANDARD LVCMOS15 [get_ports {LED[3]}]
# LED 4..7: BDAQ53 base board LEDs (LVCMOS33)
set_property PACKAGE_PIN E21 [get_ports {LED[4]}]
set_property IOSTANDARD LVCMOS33 [get_ports {LED[4]}]
set_property PACKAGE_PIN E22 [get_ports {LED[5]}]
set_property IOSTANDARD LVCMOS33 [get_ports {LED[5]}]
set_property PACKAGE_PIN D21 [get_ports {LED[6]}]
set_property IOSTANDARD LVCMOS33 [get_ports {LED[6]}]
set_property PACKAGE_PIN C22 [get_ports {LED[7]}]
set_property IOSTANDARD LVCMOS33 [get_ports {LED[7]}]
set_property SLEW SLOW [get_ports LED*]

# ===== EEPROM (SPI for SiTCP) =====
set_property PACKAGE_PIN A20 [get_ports EEPROM_CS]
set_property PACKAGE_PIN B20 [get_ports EEPROM_SK]
set_property PACKAGE_PIN A24 [get_ports EEPROM_DI]
set_property PACKAGE_PIN A23 [get_ports EEPROM_DO]
set_property IOSTANDARD LVCMOS33 [get_ports EEPROM_*]

# ===== Ethernet (RGMII) =====
# Note: KX2 Ethernet PHY uses LVCMOS33, KX1 uses LVCMOS25
set_property SLEW FAST [get_ports mdio_phy_mdc]
set_property IOSTANDARD LVCMOS33 [get_ports mdio_phy_mdc]
set_property PACKAGE_PIN B25 [get_ports mdio_phy_mdc]

set_property SLEW FAST [get_ports mdio_phy_mdio]
set_property IOSTANDARD LVCMOS33 [get_ports mdio_phy_mdio]
set_property PACKAGE_PIN B26 [get_ports mdio_phy_mdio]

set_property SLEW FAST [get_ports phy_rst_n]
set_property IOSTANDARD LVCMOS33 [get_ports phy_rst_n]
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

# ===== FRIDA chip: DP5 (DP_ML, SelectIOs) =====
# 4 LVDS pairs (sequencer clocks) + AUX (comp_out)
# Pin mapping from Enclustra Mercury Master Pinout, Connector B
set_property PACKAGE_PIN A18 [get_ports CLK_INIT_P]
set_property PACKAGE_PIN A19 [get_ports CLK_INIT_N]
set_property PACKAGE_PIN C19 [get_ports CLK_SAMP_P]
set_property PACKAGE_PIN B19 [get_ports CLK_SAMP_N]
set_property PACKAGE_PIN E18 [get_ports CLK_COMP_P]
set_property PACKAGE_PIN D18 [get_ports CLK_COMP_N]
set_property PACKAGE_PIN B17 [get_ports CLK_LOGIC_P]
set_property PACKAGE_PIN A17 [get_ports CLK_LOGIC_N]
set_property IOSTANDARD LVDS_25 [get_ports CLK_*_P]
set_property IOSTANDARD LVDS_25 [get_ports CLK_*_N]
set_property PACKAGE_PIN C16 [get_ports COMP_OUT_P]
set_property PACKAGE_PIN B16 [get_ports COMP_OUT_N]
set_property IOSTANDARD LVDS_25 [get_ports COMP_OUT_*]

# ===== FRIDA chip 1: RJ45 port D (single-ended, DATA_B pairs) =====
# DATA_B on Enclustra connector B → BDAQ53 IOD block → RJ45 J1D
# Straight-through RJ45 cable to chip PCB J14
#   Pin 1: SPI_SDO    ← F14  (DATA_B4_P)  input from chip
#   Pin 2: SPI_CS_B   → F13  (DATA_B4_N)  output to chip
#   Pin 3: SPI_SDI    → E13  (DATA_B3_P)  output to chip (MOSI)
#   Pin 4: SPI_SCLK   → E12  (DATA_B3_N)  output to chip
#   Pin 5: RST_B      → G12  (DATA_B2_P)  output to chip
#   Pin 6: AMPEN_B    → F12  (DATA_B2_N)  output to chip
#   Pin 7: V_0V_LO    → J11  (DATA_B1_P)  0V level shifter ref
#   Pin 8: V_2V5_HI   → J10  (DATA_B1_N)  2.5V / VDD_BDAQ
set_property PACKAGE_PIN F14 [get_ports SPI_SDO]
set_property PACKAGE_PIN F13 [get_ports SPI_CS_B]
set_property PACKAGE_PIN E13 [get_ports SPI_SDI]
set_property PACKAGE_PIN E12 [get_ports SPI_SCLK]
set_property PACKAGE_PIN G12 [get_ports RST_B]
set_property PACKAGE_PIN F12 [get_ports AMPEN_B]
set_property PACKAGE_PIN J11 [get_ports V_0V_LO]
set_property PACKAGE_PIN J10 [get_ports V_2V5_HI]
set_property IOSTANDARD LVCMOS25 [get_ports {SPI_SDO SPI_CS_B SPI_SDI SPI_SCLK}]
set_property IOSTANDARD LVCMOS25 [get_ports {RST_B AMPEN_B V_0V_LO V_2V5_HI}]

# ===== FRIDA chip 2: RJ45 port C (single-ended, DATA_A pairs) =====
# DATA_A on Enclustra connector B → BDAQ53 IOB block → RJ45 J1C
# Same signal-to-pin mapping as port D
#   Pin 1: SPI_SDO_2  ← G11  (DATA_A4_P)  input from chip
#   Pin 2: SPI_CS_B_2 → F10  (DATA_A4_N)  output to chip
#   Pin 3: SPI_SDI_2  → C14  (DATA_A3_P)  output to chip (MOSI)
#   Pin 4: SPI_SCLK_2 → C13  (DATA_A3_N)  output to chip
#   Pin 5: RST_B_2    → D14  (DATA_A2_P)  output to chip
#   Pin 6: AMPEN_B_2  → D13  (DATA_A2_N)  output to chip
#   Pin 7: V_0V_LO_2  → J13  (DATA_A1_P)  0V level shifter ref
#   Pin 8: V_2V5_HI_2 → H13  (DATA_A1_N)  2.5V / VDD_BDAQ
set_property PACKAGE_PIN G11 [get_ports SPI_SDO_2]
set_property PACKAGE_PIN F10 [get_ports SPI_CS_B_2]
set_property PACKAGE_PIN C14 [get_ports SPI_SDI_2]
set_property PACKAGE_PIN C13 [get_ports SPI_SCLK_2]
set_property PACKAGE_PIN D14 [get_ports RST_B_2]
set_property PACKAGE_PIN D13 [get_ports AMPEN_B_2]
set_property PACKAGE_PIN J13 [get_ports V_0V_LO_2]
set_property PACKAGE_PIN H13 [get_ports V_2V5_HI_2]
set_property IOSTANDARD LVCMOS25 [get_ports {SPI_SDO_2 SPI_CS_B_2 SPI_SDI_2 SPI_SCLK_2}]
set_property IOSTANDARD LVCMOS25 [get_ports {RST_B_2 AMPEN_B_2 V_0V_LO_2 V_2V5_HI_2}]

# ===== PMOD debug header (logic analyzer) =====
# Index matches schematic net name: PMOD[0] = Pin 1, PMOD[7] = Pin 10
# Note: bdaq53/tjmonopix2 repos use reversed numbering (Pin1→PMOD[7]) — we don't.
#
#    Pin 1  PMOD1      Pin 7   PMOD7
#    Pin 2  PMOD2      Pin 8   PMOD8
#    Pin 3  PMOD3      Pin 9   PMOD9
#    Pin 4  PMOD4      Pin 10  PMOD10
#    Pin 5  GND        Pin 11  GND
#    Pin 6  VCC        Pin 12  VCC
set_property PACKAGE_PIN AD24 [get_ports {PMOD[0]}]
set_property PACKAGE_PIN AE25 [get_ports {PMOD[1]}]
set_property PACKAGE_PIN V26  [get_ports {PMOD[2]}]
set_property PACKAGE_PIN U26  [get_ports {PMOD[3]}]
set_property PACKAGE_PIN W26  [get_ports {PMOD[4]}]
set_property PACKAGE_PIN W25  [get_ports {PMOD[5]}]
set_property PACKAGE_PIN AC24 [get_ports {PMOD[6]}]
set_property PACKAGE_PIN AC23 [get_ports {PMOD[7]}]
set_property IOSTANDARD LVCMOS25 [get_ports PMOD*]

# ===== SPI configuration flash =====
set_property CONFIG_MODE SPIx4 [current_design]
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property BITSTREAM.CONFIG.CONFIGRATE 33 [current_design]
