"""
Pytest configuration for FRIDA HDL21 tests.

Provides the SimTestMode fixture for controlling test execution depth
and PDK selection.
"""

import pytest

from .flow import SimTestMode
from .pdk import set_pdk, list_pdks


def pytest_addoption(parser):
    """Add command line options for test configuration."""
    parser.addoption(
        "--mode",
        action="store",
        default="netlist",
        choices=[m.value for m in SimTestMode],
        help="Test mode: netlist (default), min, typ, max, layout, drc, lvs, pnr",
    )
    parser.addoption(
        "--tech",
        action="store",
        default="ihp130",
        choices=list_pdks(),
        help=f"Technology/PDK: {list_pdks()}. Default: ihp130",
    )


def pytest_configure(config):
    """Set up PDK before tests run."""
    tech_name = config.getoption("--tech")
    set_pdk(tech_name)


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
    mode_str = request.config.getoption("--mode")
    return SimTestMode(mode_str)


@pytest.fixture
def sim_options():
    """
    Provide simulation options for tests that need them.

    Returns the default Spectre simulation options.
    """
    from .flow.sim import sim_options as opts

    return opts


@pytest.fixture
def tech(request):
    """
    Provide the active technology/PDK instance for tests.

    The tech is set via the --tech command line option.
    Default is ihp130 (IHP SG13G2 130nm) since it's open source.
    """
    from .pdk import get_pdk

    return get_pdk()
