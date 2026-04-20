# ------------------------------------------------------------
# FRIDA DAQ - Constraints for BDAQ53 + Mercury KX1 (xc7k160t-1)
# ------------------------------------------------------------
#
# Pin sources:
#   System/Ethernet: bdaq53/firmware/src/bdaq53_KX1.xdc
#   DP5 pins:        Enclustra Mercury Master Pinout (Connector B)
#   RJ45 D pins:     bdaq53/firmware/src/bdaq53_KX1.xdc
#
# Signals not used by FRIDA (removed from bdaq53 reference):
#   Aurora / MGT (CLK_MGT_REF, MGT_REFCLK, MGT_RX, DP1 MGT AUX)
#   CLK200 oscillator, I2C, LEMO, PMOD, TLU (RJ45_TRIGGER/RESET)
#   mDP_ML (mini DisplayPort), GPIO_RESET, GPIO_SENSE, NTC_MUX
#   USER_BUTTON, derived clocks (I2C_CLK, SPI_CLK)

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
set_property PACKAGE_PIN AA3 [get_ports FCLK_IN]
set_property IOSTANDARD LVCMOS15 [get_ports FCLK_IN]

# ===== Reset button =====
set_property PACKAGE_PIN C18 [get_ports RESET_BUTTON]
set_property IOSTANDARD LVCMOS25 [get_ports RESET_BUTTON]
set_property PULLUP true [get_ports RESET_BUTTON]

# ===== User button (SW_USER_B, active low) =====
set_property PACKAGE_PIN AF22 [get_ports USER_BUTTON]
set_property IOSTANDARD LVCMOS25 [get_ports USER_BUTTON]
set_property PULLUP true [get_ports USER_BUTTON]

# ===== LEDs =====
# LED 0..3: onboard KX1 module LEDs (Bank 15, LVCMOS25)
set_property PACKAGE_PIN M17 [get_ports {LED[0]}]
set_property PACKAGE_PIN L18 [get_ports {LED[1]}]
set_property PACKAGE_PIN L17 [get_ports {LED[2]}]
set_property PACKAGE_PIN K18 [get_ports {LED[3]}]
# LED 4..7: BDAQ53 base board LEDs (LVCMOS25)
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
set_property IOSTANDARD LVCMOS25 [get_ports EEPROM_*]

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

# ===== FRIDA chip: DP5 (DP_ML, SelectIOs) =====
#
# Full signal chain (traced from DUT PCB frida65A.kicad_sch):
#
#   Port          | Pkg Pin | Encl. B | BDAQ net          | Src DP Pin | DUT Pin | DUT PCB net
#   --------------|---------|---------|-------------------|------------|---------|------------
#   CLK_COMP_P    |  K16    |  B164   | CMD_DP2_P/HITOR0_P |     10     |    1    | CLK_COMP_P
#   CLK_COMP_N    |  K17    |  B166   | CMD_DP2_N/HITOR0_N |     12     |    3    | CLK_COMP_N
#   CLK_LOGIC_P   |  L19    |  B160   | CMD_DP2_P/HITOR1_P |      7     |    4    | CLK_LOGIC_P
#   CLK_LOGIC_N   |  L20    |  B162   | CMD_DP2_N/HITOR1_N |      9     |    6    | CLK_LOGIC_N
#   COMP_OUT_P ~  |  H17    |  B154   | CMD_DP2_P/HITOR2_P |      4     |    7    | COMP_OUT_N
#   COMP_OUT_N ~  |  H18    |  B156   | CMD_DP2_N/HITOR2_N |      6     |    9    | COMP_OUT_P
#   CLK_SAMP_P ~  |  G19    |  B148   | CMD_DP2_P/HITOR3_P |      1     |   10    | CLK_SAMP_N
#   CLK_SAMP_N ~  |  F20    |  B150   | CMD_DP2_N/HITOR3_N |      3     |   12    | CLK_SAMP_P
#   CLK_INIT_P    |  H19    |  B142   | AUX_DP2_P         |     17     |   17    | CLK_INIT_P
#   CLK_INIT_N    |  G20    |  B144   | AUX_DP2_N         |     15     |   15    | CLK_INIT_N
#   (* P/N swap in XDC)
#
# Notes:
#   - BDAQ board swaps P/N for all HITOR lanes: HITOR_P→IO_N, HITOR_N→IO_P.
#   - DP cable reverses ML lane order (L0↔L3, L1↔L2) but not the AUX channel.
#   - CLK_COMP and CLK_LOGIC need no polarity fix: BDAQ inversion + DUT PCB inversion cancel.
#   - CLK_SAMP and COMP_OUT (~): polarity mismatch compensated in daq_top.v via RTL inversion,
#     not in XDC — Vivado rejects _P ports on _N package pins. Package pins use P→P, N→N.
#   - CLK_INIT via AUX: BDAQ also inverts AUX (AUX_P→B144→G20_N, AUX_N→B142→H19_P),
#     which maps cleanly to CLK_INIT_N/P on the N/P package pins — no inversion needed.

set_property PACKAGE_PIN K16 [get_ports CLK_COMP_P]
set_property PACKAGE_PIN K17 [get_ports CLK_COMP_N]
set_property PACKAGE_PIN L19 [get_ports CLK_LOGIC_P]
set_property PACKAGE_PIN L20 [get_ports CLK_LOGIC_N]
set_property PACKAGE_PIN H17 [get_ports COMP_OUT_P]
set_property PACKAGE_PIN H18 [get_ports COMP_OUT_N]
set_property PACKAGE_PIN G19 [get_ports CLK_SAMP_P]
set_property PACKAGE_PIN F20 [get_ports CLK_SAMP_N]
set_property PACKAGE_PIN H19 [get_ports CLK_INIT_P]
set_property PACKAGE_PIN G20 [get_ports CLK_INIT_N]
set_property IOSTANDARD LVDS_25 [get_ports CLK_*_P]
set_property IOSTANDARD LVDS_25 [get_ports CLK_*_N]
set_property IOSTANDARD LVDS_25 [get_ports COMP_OUT_*]

# ===== FRIDA chip 1: RJ45 port D (single-ended, DATA_B pairs) =====
# DATA_B on Enclustra connector B → BDAQ53 IOD block → RJ45 J1D
# Straight-through RJ45 cable to chip PCB J14
# Note: RJ45 T-568B swaps pairs B2/B3 on pins 3-6 (pair B2 on pins 3,6;
#       pair B3 on pins 4,5) — not sequential!
#   Pin 1: SPI_SDO    ← E13  (DATA_B4_P)  input from chip
#   Pin 2: SPI_CS_B   → E12  (DATA_B4_N)  output to chip
#   Pin 3: SPI_SDI    → A10  (DATA_B2_N)  output to chip (MOSI)
#   Pin 4: SPI_SCLK   → B14  (DATA_B3_P)  output to chip
#   Pin 5: RST_B      → A14  (DATA_B3_N)  output to chip
#   Pin 6: AMPEN_B    → B10  (DATA_B2_P)  output to chip
#   Pin 7: V_0V_LO    → C16  (DATA_B1_P)  0V level shifter ref
#   Pin 8: V_2V5_HI   → B16  (DATA_B1_N)  2.5V / VDD_BDAQ
set_property PACKAGE_PIN E13 [get_ports SPI_SDO]
set_property PACKAGE_PIN E12 [get_ports SPI_CS_B]
set_property PACKAGE_PIN A10 [get_ports SPI_SDI]
set_property PACKAGE_PIN B14 [get_ports SPI_SCLK]
set_property PACKAGE_PIN A14 [get_ports RST_B]
set_property PACKAGE_PIN B10 [get_ports AMPEN_B]
set_property PACKAGE_PIN C16 [get_ports V_0V_LO]
set_property PACKAGE_PIN B16 [get_ports V_2V5_HI]
set_property IOSTANDARD LVCMOS25 [get_ports {SPI_SDO SPI_CS_B SPI_SDI SPI_SCLK}]
set_property IOSTANDARD LVCMOS25 [get_ports {RST_B AMPEN_B V_0V_LO V_2V5_HI}]

# ===== FRIDA chip 2: RJ45 port C (single-ended, DATA_A pairs) =====
# DATA_A on Enclustra connector B → BDAQ53 IOB block → RJ45 J1C
# Same signal-to-pin and pair-swap mapping as port D
#   Pin 1: SPI_SDO_2  ← E10  (DATA_A4_P)  input from chip
#   Pin 2: SPI_CS_B_2 → D10  (DATA_A4_N)  output to chip
#   Pin 3: SPI_SDI_2  → D11  (DATA_A2_N)  output to chip (MOSI)
#   Pin 4: SPI_SCLK_2 → F14  (DATA_A3_P)  output to chip
#   Pin 5: RST_B_2    → F13  (DATA_A3_N)  output to chip
#   Pin 6: AMPEN_B_2  → E11  (DATA_A2_P)  output to chip
#   Pin 7: V_0V_LO_2  → D14  (DATA_A1_P)  0V level shifter ref
#   Pin 8: V_2V5_HI_2 → D13  (DATA_A1_N)  2.5V / VDD_BDAQ
set_property PACKAGE_PIN E10 [get_ports SPI_SDO_2]
set_property PACKAGE_PIN D10 [get_ports SPI_CS_B_2]
set_property PACKAGE_PIN D11 [get_ports SPI_SDI_2]
set_property PACKAGE_PIN F14 [get_ports SPI_SCLK_2]
set_property PACKAGE_PIN F13 [get_ports RST_B_2]
set_property PACKAGE_PIN E11 [get_ports AMPEN_B_2]
set_property PACKAGE_PIN D14 [get_ports V_0V_LO_2]
set_property PACKAGE_PIN D13 [get_ports V_2V5_HI_2]
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
set_property PACKAGE_PIN V26  [get_ports {PMOD[0]}]
set_property PACKAGE_PIN V24  [get_ports {PMOD[1]}]
set_property PACKAGE_PIN AB25 [get_ports {PMOD[2]}]
set_property PACKAGE_PIN AA25 [get_ports {PMOD[3]}]
set_property PACKAGE_PIN W26  [get_ports {PMOD[4]}]
set_property PACKAGE_PIN W25  [get_ports {PMOD[5]}]
set_property PACKAGE_PIN AC24 [get_ports {PMOD[6]}]
set_property PACKAGE_PIN AC23 [get_ports {PMOD[7]}]
set_property IOSTANDARD LVCMOS25 [get_ports PMOD*]

# ===== SPI configuration flash =====
set_property CONFIG_MODE SPIx4 [current_design]
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
set_property BITSTREAM.CONFIG.CONFIGRATE 33 [current_design]
