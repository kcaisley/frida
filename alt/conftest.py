"""
Pytest configuration for FRIDA HDL21 tests.

Provides the SimTestMode fixture for controlling test execution depth.

Note: SimTestMode enum can be imported without pytest installed,
but pytest hooks and fixtures only work when running under pytest.
"""

from enum import Enum


class SimTestMode(Enum):
    """
    Simulation test mode controlling test execution depth.

    Schematic/Simulation stages:
        NETLIST: HDL21 netlist generation only (no simulator needed)
        MIN: One setting, one corner (quick sanity check)
        TYP: One corner, many settings (typical parameter sweep)
        MAX: Full PVT sweep (comprehensive characterization)

    Physical design stages (future):
        LAYOUT: gdsfactory layout generation
        DRC: KLayout DRC checks
        LVS: Layout vs Schematic
        PNR: OpenROAD place & route
    """

    # Schematic/Simulation stages
    NETLIST = "netlist"
    MIN = "min"
    TYP = "typ"
    MAX = "max"

    # Physical design stages (future)
    LAYOUT = "layout"
    DRC = "drc"
    LVS = "lvs"
    PNR = "pnr"


# Pytest hooks and fixtures - only defined if pytest is available
try:
    import pytest

    def pytest_addoption(parser):
        """Add --simtestmode command line option."""
        parser.addoption(
            "--simtestmode",
            action="store",
            default="netlist",
            choices=[m.value for m in SimTestMode],
            help="Simulation/flow test mode: netlist (default), min, typ, max, layout, drc, lvs, pnr",
        )

    @pytest.fixture
    def simtestmode(request) -> SimTestMode:
        """
        Get simulation test mode from command line.

        Usage in tests:
            def test_something(simtestmode: SimTestMode):
                if simtestmode == SimTestMode.NETLIST:
                    # Just verify netlist generation
                    ...
                elif simtestmode == SimTestMode.MIN:
                    # Run one quick simulation
                    ...
                elif simtestmode in (SimTestMode.TYP, SimTestMode.MAX):
                    # Run parameter sweeps
                    ...
        """
        mode_str = request.config.getoption("--simtestmode")
        return SimTestMode(mode_str)

    @pytest.fixture
    def sim_options():
        """
        Provide simulation options for tests that need them.

        Returns the default Spectre simulation options.
        """
        from .common.sim_options import sim_options as opts

        return opts

except ImportError:
    # pytest not installed - that's fine for non-test usage
    pass
