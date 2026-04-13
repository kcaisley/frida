# Simulation Backends for FRIDA Scans
#
# Provides SimAWG and SimPSU (simulation implementations of the peripheral
# interfaces) and helper functions for setting up the cocotbext-ams bridge.

from __future__ import annotations

import logging
from pathlib import Path


from cocotbext.ams import AnalogBlock, DigitalPin, MixedSignalBridge


logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]
DESIGN_HDL = REPO / "design" / "hdl"
DESIGN_FPGA = REPO / "design" / "fpga"
DESIGN_SPICE = REPO / "design" / "spice"


# -------------------------------------------------------------------------
# Simulation peripherals
# -------------------------------------------------------------------------


class SimAWG:
    """Simulation function generator — drives vin_p/vin_n via the bridge."""

    def __init__(self, bridge: MixedSignalBridge, block_name: str = "i_chip.adc_inst"):
        self._bridge = bridge
        self._block = block_name

    async def set_differential(self, diff: float, cm: float) -> None:
        vin_p = cm + diff / 2
        vin_n = cm - diff / 2
        self._bridge.set_analog_input(self._block, "vin_p", vin_p)
        self._bridge.set_analog_input(self._block, "vin_n", vin_n)

    async def start_sin(
        self,
        amplitude: float,
        offset: float,
        freq_hz: float,
    ) -> None:
        raise NotImplementedError(
            "Sinusoidal drive not yet implemented for simulation. Use set_differential() with a manual sweep instead."
        )


class SimPSU:
    """Simulation power supply — VDD is fixed in the SPICE netlist."""

    def __init__(self, nominal_vdd: float = 1.2):
        self._vdd = nominal_vdd

    async def set_voltage(self, v: float) -> None:
        if abs(v - self._vdd) > 0.001:
            logger.warning(
                "SimPSU: VDD is fixed at %.3fV in the SPICE netlist; ignoring request to change to %.3fV",
                self._vdd,
                v,
            )

    async def on(self) -> None:
        pass

    async def off(self) -> None:
        pass


# -------------------------------------------------------------------------
# ADC analog block definition
# -------------------------------------------------------------------------


def _adc_port_order() -> list[str]:
    """Return the exact .subckt adc pin order from design/spice/adc.sp."""
    ports = [
        "seq_init",
        "seq_samp",
        "seq_comp",
        "seq_update",
        "comp_out",
        "en_init",
        "en_samp_p",
        "en_samp_n",
        "en_comp",
        "en_update",
        "dac_mode",
        "dac_diffcaps",
    ]
    for bus in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n"):
        for bit in range(15, -1, -1):
            ports.append(f"{bus}[{bit}]")
    ports += ["vin_p", "vin_n", "vdd_a", "vss_a", "vdd_d", "vss_d", "vdd_dac", "vss_dac"]
    return ports


def create_adc_block(vdd: float = 1.2) -> AnalogBlock:
    """Create an AnalogBlock for the FRIDA ADC subcircuit."""
    digital_pins = {
        # Sequencer inputs (driven by daq_core via Verilog)
        "seq_init": DigitalPin("input", vdd=vdd),
        "seq_samp": DigitalPin("input", vdd=vdd),
        "seq_comp": DigitalPin("input", vdd=vdd),
        "seq_update": DigitalPin("input", vdd=vdd),
        # Enable signals (driven by SPI register via Verilog)
        "en_init": DigitalPin("input", vdd=vdd),
        "en_samp_p": DigitalPin("input", vdd=vdd),
        "en_samp_n": DigitalPin("input", vdd=vdd),
        "en_comp": DigitalPin("input", vdd=vdd),
        "en_update": DigitalPin("input", vdd=vdd),
        # DAC config
        "dac_mode": DigitalPin("input", vdd=vdd),
        "dac_diffcaps": DigitalPin("input", vdd=vdd),
        "dac_astate_p": DigitalPin("input", width=16, vdd=vdd),
        "dac_bstate_p": DigitalPin("input", width=16, vdd=vdd),
        "dac_astate_n": DigitalPin("input", width=16, vdd=vdd),
        "dac_bstate_n": DigitalPin("input", width=16, vdd=vdd),
        # Output
        "comp_out": DigitalPin("output", vdd=vdd),
    }

    return AnalogBlock(
        name="i_chip.adc_inst",
        spice_file=DESIGN_SPICE / "adc.sp",
        subcircuit="adc",
        digital_pins=digital_pins,
        analog_inputs={"vin_p": vdd / 2, "vin_n": vdd / 2},
        vdd=vdd,
        vss=0.0,
        tran_step="0.1n",
        extra_lines=[],
        port_order=_adc_port_order(),
        supplies={
            "vdd_a": vdd,
            "vss_a": 0.0,
            "vdd_d": vdd,
            "vss_d": 0.0,
            "vdd_dac": vdd,
            "vss_dac": 0.0,
        },
        bus_delimiter="[]",
    )


# -------------------------------------------------------------------------
# Verilog source list
# -------------------------------------------------------------------------


def verilog_sources() -> list[Path]:
    """Return the Verilog source files for the cocotbext-ams testbench."""
    import basil

    basil_fw = Path(basil.__file__).parent / "firmware" / "modules"
    return [
        DESIGN_FPGA / "daq_core.v",
        DESIGN_HDL / "tb_integration.v",
        DESIGN_HDL / "frida_core_1chan.v",
        DESIGN_HDL / "spi_register.v",
        DESIGN_HDL / "adc_stub.v",
        basil_fw / "utils" / "RAMB16_S1_S9_sim.v",
    ]


def include_dirs() -> list[Path]:
    """Return the Verilog include directories."""
    import basil

    basil_fw = Path(basil.__file__).parent / "firmware" / "modules"
    return [DESIGN_HDL, DESIGN_FPGA, basil_fw, basil_fw / "utils"]
