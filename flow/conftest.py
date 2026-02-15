"""
Pytest configuration for FRIDA HDL21 tests.

Provides fixtures for flow control, simulator selection, and PDK selection.
"""

import shutil
import socket
from pathlib import Path
from typing import Any

import pytest
from vlsirtools.spice import SupportedSimulators

from .flow import get_param_axes, print_netlist_summary
from .pdk import get_pdk, list_pdks, set_pdk

# Hosts with SPICE simulators and PDKs available
SIM_HOSTS = {"jupiter", "juno", "asiclab003"}

# Simulator binaries to probe on PATH
SIMULATOR_BINARIES: dict[SupportedSimulators, tuple[str, ...]] = {
    SupportedSimulators.SPECTRE: ("spectre",),
    SupportedSimulators.NGSPICE: ("ngspice",),
    SupportedSimulators.XYCE: ("Xyce", "xyce"),
}


def _is_xdist_worker(config: pytest.Config) -> bool:
    """Check whether this pytest process is an xdist worker."""
    return hasattr(config, "workerinput")


def clean_scratch_dir(path: Path = Path("./scratch")) -> None:
    """Remove all contents from the scratch directory."""
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def pytest_addoption(parser):
    """Add command line options for test configuration."""
    pdk_choices = list_pdks()
    sim_choices = [sim.value for sim in SupportedSimulators]

    parser.addoption(
        "--flow",
        action="store",
        default="netlist",
        choices=["netlist", "simulate", "measure"],
        help="Flow mode (default: netlist): netlist, simulate, measure",
    )
    parser.addoption(
        "--mode",
        action="store",
        default="min",
        choices=["min", "max"],
        help="Variant mode (default: min): min (limit to 10), max (full cartesian)",
    )
    parser.addoption(
        "--montecarlo",
        action="store",
        default="no",
        choices=["yes", "no"],
        help="Monte Carlo mode (default: no): yes, no",
    )
    parser.addoption(
        "--tech",
        action="store",
        default="ihp130",
        choices=pdk_choices,
        help=f"Technology PDK (default: ihp130): {', '.join(pdk_choices)}",
    )
    parser.addoption(
        "--simulator",
        action="store",
        default=SupportedSimulators.SPECTRE.value,
        choices=sim_choices,
        help=f"Simulator backend (default: spectre): {', '.join(sim_choices)}",
    )
    parser.addoption(
        "--clean",
        action="store",
        default="no",
        choices=["yes", "no"],
        help="Scratch cleanup (default: no): yes, no",
    )
    parser.addoption(
        "--sim-server",
        action="store",
        default="",
        help=(
            "Remote SpiceServer target in host[:port] format. "
            "When set, simulate/measure flows use remote execution."
        ),
    )


def pytest_configure(config):
    """Set up PDK and register markers before tests run."""
    tech_name = config.getoption("--tech")
    set_pdk(tech_name)

    # Clean once in the xdist controller process when requested.
    if config.getoption("--clean") == "yes" and not _is_xdist_worker(config):
        clean_scratch_dir()

    # Register the requires_sim marker
    config.addinivalue_line(
        "markers",
        "requires_sim: mark test as requiring SPICE simulator (skipped on non-sim hosts)",
    )


@pytest.fixture
def flow(request) -> str:
    """Get flow selection from command line."""
    return request.config.getoption("--flow")


@pytest.fixture
def mode(request) -> str:
    """Get variant selection mode from command line."""
    return request.config.getoption("--mode")


@pytest.fixture
def montecarlo(request) -> bool:
    """Get Monte Carlo selection from command line."""
    return request.config.getoption("--montecarlo") == "yes"


@pytest.fixture
def sim_options(request):
    """
    Provide simulation options for tests that need them.

    Returns options for the simulator selected via --simulator.
    """
    from .flow.sim import get_sim_options

    sim = SupportedSimulators(request.config.getoption("--simulator"))
    return get_sim_options(rundir=Path("./scratch"), simulator=sim)


@pytest.fixture
def simulator(request) -> SupportedSimulators:
    """Get simulator selection from command line."""
    return SupportedSimulators(request.config.getoption("--simulator"))


@pytest.fixture
def sim_server(request) -> str | None:
    """Get optional remote SpiceServer target from command line."""
    target = request.config.getoption("--sim-server").strip()
    return target or None


@pytest.fixture
def require_sim_for_flow(
    flow: str,
    simulator: SupportedSimulators,
    sim_server: str | None,
) -> None:
    """
    Skip simulate/measure flows when simulator access is unavailable.

    Uses local host/binary checks unless a remote SpiceServer is configured.
    """
    if flow not in {"simulate", "measure"}:
        return
    if sim_server:
        return

    hostname = socket.gethostname().split(".")[0].lower()
    if hostname not in SIM_HOSTS:
        hosts = ", ".join(sorted(SIM_HOSTS))
        pytest.skip(
            f"{flow} flow requires simulator access: host '{hostname}' "
            f"is not in the simulator allow-list ({hosts})"
        )

    binaries = SIMULATOR_BINARIES[simulator]
    if not any(shutil.which(binary) for binary in binaries):
        pytest.skip(
            f"{flow} flow requires simulator access: "
            f"simulator binary '{simulator.value}' is unavailable"
        )


@pytest.fixture
def tech():
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
