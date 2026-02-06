"""
Pytest configuration for FRIDA HDL21 tests.

Provides the FlowMode fixture for controlling test execution depth
and PDK selection.
"""

import socket
from typing import Any

import pytest

from .flow import FlowMode, get_param_axes, print_netlist_summary
from .pdk import get_pdk, list_pdks, set_pdk

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
        choices=[m.value for m in FlowMode],
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
def flowmode(request) -> FlowMode:
    """
    Get simulation test mode from command line.

    Automatically skips tests requiring simulation if not on a sim host
    (jupiter, juno, asiclab003) unless mode is 'netlist'.

    Usage in tests:
        def test_something(flowmode: FlowMode):
            if flowmode == FlowMode.NETLIST:
                # Just verify netlist generation
                ...
            elif flowmode == FlowMode.MIN:
                # Run one quick simulation
                ...
            elif flowmode in (FlowMode.TYP, FlowMode.MAX):
                # Run parameter sweeps
                ...
    """
    mode_str = request.config.getoption("--mode")
    mode = FlowMode(mode_str)

    # Skip simulation tests on hosts without simulator access
    if mode != FlowMode.NETLIST and not has_simulator():
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
    return get_pdk()


@pytest.fixture
def verbose(request) -> bool:
    """
    Check if pytest is running in verbose mode (-v flag).

    Use this to conditionally print summary tables.
    """
    return request.config.option.verbose >= 1


def print_summary_if_verbose(
    request,
    block: str,
    count: int,
    params_list: list[Any],
    wall_time: float,
    outdir: str,
    errors: list[str] | None = None,
) -> None:
    """
    Print netlist generation summary if pytest is running in verbose mode.

    Call this at the end of netlist generation tests to display
    a formatted summary table.

    Args:
        request: pytest request fixture
        block: Block name (e.g., "comp", "cdac", "samp")
        count: Number of netlists generated
        params_list: List of parameter objects used
        wall_time: Generation time in seconds
        outdir: Output directory path
        errors: List of error messages (or None for no errors)
    """
    if request.config.option.verbose >= 1:
        pdk = get_pdk()
        param_axes = get_param_axes(params_list)
        print_netlist_summary(
            block=block,
            pdk_name=pdk.name,
            count=count,
            param_axes=param_axes,
            wall_time=wall_time,
            outdir=str(outdir),
            errors=errors,
        )
