"""
Simulation options for FRIDA testbenches.

Configures vlsirtools for Spectre simulation.
"""

from pathlib import Path
from vlsirtools.spice import SimOptions, SupportedSimulators, ResultFormat


# Default simulation options for Spectre
sim_options = SimOptions(
    rundir=Path("./scratch"),
    fmt=ResultFormat.SIM_DATA,
    simulator=SupportedSimulators.SPECTRE,
)


def get_sim_options(
    rundir: Path = None,
    simulator: SupportedSimulators = SupportedSimulators.SPECTRE,
) -> SimOptions:
    """
    Create simulation options with custom settings.

    Args:
        rundir: Directory for simulation files (None for temp dir)
        simulator: Simulator to use (SPECTRE, NGSPICE, etc.)

    Returns:
        SimOptions instance
    """
    return SimOptions(
        rundir=rundir,
        fmt=ResultFormat.SIM_DATA,
        simulator=simulator,
    )
