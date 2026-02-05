"""
Pytest configuration for FRIDA HDL21 tests.

Provides the SimTestMode fixture for controlling test execution depth
and PDK selection.
"""

import socket

import pytest

from .flow import SimTestMode
from .pdk import set_pdk, list_pdks

# Hosts with SPICE simulators and PDKs available
SIM_HOSTS = {"jupiter", "juno", "asiclab003"}


def has_simulator() -> bool:
    """Check if current host has simulator access."""
    hostname = socket.gethostname().split(".")[0].lower()
    return hostname in SIM_HOSTS


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
    """Set up PDK and register markers before tests run."""
    tech_name = config.getoption("--tech")
    set_pdk(tech_name)

    # Register the requires_sim marker
    config.addinivalue_line(
        "markers",
        "requires_sim: mark test as requiring SPICE simulator (skipped on non-sim hosts)",
    )


@pytest.fixture
def simtestmode(request) -> SimTestMode:
    """
    Get simulation test mode from command line.

    Automatically skips tests requiring simulation if not on a sim host
    (jupiter, juno, asiclab003) unless mode is 'netlist'.

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
    mode = SimTestMode(mode_str)

    # Skip simulation tests on hosts without simulator access
    if mode != SimTestMode.NETLIST and not has_simulator():
        pytest.skip(
            f"Simulation tests require host with simulator (jupiter/juno/asiclab003), "
            f"current host: {socket.gethostname()}"
        )

    return mode


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
