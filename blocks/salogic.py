"""
SAR Logic subcircuit definition.

Digital control logic for SAR ADC - manages DAC state updates based on
comparator outputs and control signals.

This is a digital block that would typically be synthesized from HDL.
The SPICE netlist references the synthesized gate-level netlist.

Ports:
    clk_init: Initialize signal (starts conversion cycle)
    clk_update: Update clock (advances SAR state machine)
    dac_mode: Mode selection (0=parallel load, 1=SAR mode)
    comp_p/comp_n: Differential comparator outputs
    dac_astate_p/n[15:0]: Initial DAC state from SPI (positive/negative)
    dac_bstate_p/n[15:0]: Alternate DAC state from SPI (positive/negative)
    dac_state_p/n[15:0]: Current DAC output state (positive/negative)
    vdd_d/vss_d: Digital supply
"""


def calc_ports(n_bits: int) -> dict[str, str]:
    """Build port dict for salogic with n_bits DAC width."""
    ports = {
        # Clock and control
        "clk_init": "I",
        "clk_update": "I",
        "dac_mode": "I",
        # Comparator inputs (active low/high from comp)
        "comp_p": "I",
        "comp_n": "I",
        # Supply
        "vdd_d": "B",
        "vss_d": "B",
    }

    # DAC state buses (input from SPI, active during init)
    for side in ["p", "n"]:
        for bus in ["astate", "bstate"]:
            for i in range(n_bits):
                ports[f"dac_{bus}_{side}[{i}]"] = "I"

    # DAC output state (active during conversion)
    for side in ["p", "n"]:
        for i in range(n_bits):
            ports[f"dac_state_{side}[{i}]"] = "O"

    return ports


# Static subckt - salogic is a digital block, no topo_params needed for analog sweeps
# The actual implementation comes from HDL synthesis
subckt = {
    "cellname": "salogic",
    "ports": calc_ports(16),  # 16-bit DAC width
    "instances": {},  # Empty - this is a black box referencing synthesized netlist
    "tech": ["tsmc65"],
    "topo_params": {},
    "inst_params": [],
}


# No testbench for pure digital block - tested via HDL simulation
tb = None
