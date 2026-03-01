"""
Pytest configuration for FRIDA HDL21 tests.

Provides fixtures for flow control, simulator selection, and PDK selection.
"""

import shutil
import socket
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

import hdl21 as h
import pytest
from vlsirtools.spice import SupportedSimulators

from .flow import get_param_axes, print_netlist_summary

# Hosts with SPICE simulators and PDKs available
SIM_HOSTS = {"jupiter", "juno", "asiclab003"}

# Simulator binaries to probe on PATH
SIMULATOR_BINARIES: dict[SupportedSimulators, tuple[str, ...]] = {
    SupportedSimulators.SPECTRE: ("spectre",),
    SupportedSimulators.NGSPICE: ("ngspice",),
    SupportedSimulators.XYCE: ("Xyce", "xyce"),
}

_PDK_PACKAGES: dict[str, str] = {
    "ihp130": "pdk.ihp130",
    "tsmc65": "pdk.tsmc65",
    "tsmc28": "pdk.tsmc28",
    "tower180": "pdk.tower180",
}


def list_pdks() -> list[str]:
    """List supported PDK names."""
    return list(_PDK_PACKAGES.keys())


def _resolve_pdk_module(name: str) -> ModuleType:
    """Resolve a PDK name to its registered HDL21 `pdk_logic` module."""
    if name not in _PDK_PACKAGES:
        available = ", ".join(list_pdks())
        raise ValueError(f"Unknown PDK '{name}'. Available: {available}")

    pkg = import_module(_PDK_PACKAGES[name])
    pdk_module = getattr(pkg, "pdk_logic", None)
    if pdk_module is None:
        raise RuntimeError(f"PDK package '{_PDK_PACKAGES[name]}' has no `pdk_logic`")
    return pdk_module


def _reset_generator_caches() -> None:
    """Reset FRIDA generator caches after PDK switch."""
    try:
        from flow.samp.samp import Samp
        from flow.samp.test_samp import SampTb

        Samp.Cache.reset()
        SampTb.Cache.reset()
    except (ImportError, AttributeError):
        pass

    try:
        from flow.comp.comp import Comp
        from flow.comp.test_comp import CompTb

        Comp.Cache.reset()
        CompTb.Cache.reset()
    except (ImportError, AttributeError):
        pass

    try:
        from flow.cdac.cdac import Cdac
        from flow.cdac.test_cdac import CdacTb

        Cdac.Cache.reset()
        CdacTb.Cache.reset()
    except (ImportError, AttributeError):
        pass


def set_pdk(name: str) -> ModuleType:
    """Set active HDL21 default PDK module by name."""
    pdk_module = _resolve_pdk_module(name)
    h.pdk.set_default(pdk_module)
    _reset_generator_caches()
    return pdk_module


def _is_xdist_worker(config: pytest.Config) -> bool:
    """Check whether this pytest process is an xdist worker."""
    return hasattr(config, "workerinput")


def clean_outdir(path: Path) -> None:
    """Remove all contents from the output directory."""
    # Needed so `--clean yes` gives reproducible test outputs and avoids stale files
    # from previous runs when comparing generated collateral.
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def resolve_outdir(config: pytest.Config) -> Path:
    """Resolve --outdir against pytest root when relative."""
    # Needed so every test (netlist + layout) writes into one shared location,
    # regardless of the current working directory used to invoke pytest.
    raw = Path(config.getoption("--outdir")).expanduser()
    path = raw if raw.is_absolute() else Path(config.rootpath) / raw
    # Needed as a safety net so writers can assume the directory exists.
    path.mkdir(parents=True, exist_ok=True)
    return path


def pytest_addoption(parser):
    """Add command line options for test configuration."""
    pdk_choices = list_pdks()
    sim_choices = [sim.value for sim in SupportedSimulators]

    parser.addoption(
        "--flow",
        action="store",
        default="netlist",
        choices=["netlist", "simulate", "measure"],
        help=(
            "Flow action for circuit-flow tests (default: netlist): "
            "netlist writes collateral, simulate runs simulator, measure runs post-processing"
        ),
    )
    parser.addoption(
        "--mode",
        action="store",
        default="min",
        choices=["min", "max"],
        help=(
            "Variant scope for flow and layout tests (default: min): "
            "min runs a small representative set, max runs full sweeps"
        ),
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
        "--fmt",
        action="store",
        default=None,
        help=(
            "Netlist format for --flow=netlist: "
            "spectre, ngspice, yaml, verilog (spice accepted as alias). "
            "Defaults to --simulator when omitted."
        ),
    )
    parser.addoption(
        "--clean",
        action="store",
        default="no",
        choices=["yes", "no"],
        help="Output directory cleanup (default: no): yes, no",
    )
    parser.addoption(
        "--visual",
        action="store",
        default="no",
        choices=["yes", "no"],
        help=(
            "Enable visual collateral generation (default: no). "
            "Currently renders layout GDS to PNG; planned extension is schematic drawing "
            "for netlists and matplotlib plots for measurement flows."
        ),
    )
    parser.addoption(
        "--outdir",
        action="store",
        default="scratch",
        help="Output directory for generated collateral (default: scratch)",
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
    flow_mode = config.getoption("--flow")
    fmt = config.getoption("--fmt")
    if flow_mode != "netlist" and fmt is not None:
        raise pytest.UsageError("--fmt is only valid with --flow=netlist")
    if flow_mode == "netlist" and fmt is not None:
        valid = {"spectre", "ngspice", "spice", "yaml", "verilog"}
        if fmt.lower() not in valid:
            raise pytest.UsageError(
                f"Invalid --fmt={fmt}. Valid values: spectre, ngspice, yaml, verilog"
            )

    outdir = resolve_outdir(config)

    # Clean once in the xdist controller process when requested.
    if config.getoption("--clean") == "yes" and not _is_xdist_worker(config):
        clean_outdir(outdir)

    # Register the requires_sim marker
    config.addinivalue_line(
        "markers",
        "requires_sim: mark test as requiring SPICE simulator (skipped on non-sim hosts)",
    )


@pytest.fixture
def flow(request) -> str:
    """Get flow selection from command line for circuit-flow tests."""
    return request.config.getoption("--flow")


@pytest.fixture
def mode(request) -> str:
    """Get variant scope (min/max) for flow and layout tests."""
    return request.config.getoption("--mode")


@pytest.fixture
def montecarlo(request) -> bool:
    """Get Monte Carlo selection from command line for simulation flows."""
    return request.config.getoption("--montecarlo") == "yes"


@pytest.fixture
def visual(request) -> bool:
    """Enable optional visual collateral generation for tests."""
    return request.config.getoption("--visual") == "yes"


@pytest.fixture
def outdir(request) -> Path:
    """Shared output directory for flow and layout tests."""
    # Needed to inject the configured output path into tests via fixture args,
    # instead of hardcoding "./scratch" in each test module.
    return resolve_outdir(request.config)


@pytest.fixture
def sim_options(request, outdir: Path):
    """
    Provide simulation options for tests that need them.

    Returns options for the simulator selected via --simulator.
    """
    from .flow.sim import get_sim_options

    sim = SupportedSimulators(request.config.getoption("--simulator"))
    return get_sim_options(rundir=outdir, simulator=sim)


@pytest.fixture
def simulator(request) -> SupportedSimulators:
    """Get simulator selection from command line."""
    return SupportedSimulators(request.config.getoption("--simulator"))


@pytest.fixture
def netlist_fmt(flow: str, simulator: SupportedSimulators, request) -> str:
    """Get normalized netlist format selection."""
    if flow != "netlist":
        return simulator.value
    fmt = request.config.getoption("--fmt")
    if fmt is None:
        return simulator.value
    if fmt.lower() == "spice":
        return "ngspice"
    return fmt.lower()


@pytest.fixture
def sim_server(request) -> str | None:
    """Get optional remote SpiceServer target from command line."""
    target = request.config.getoption("--sim-server").strip()
    return target or None


@pytest.fixture
def check_simulator_avail(
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
def tech(request) -> str:
    """
    Provide the active technology name for tests.

    The tech is set via the --tech command line option.
    Default is ihp130 (IHP SG13G2 130nm) since it's open source.
    """
    return request.config.getoption("--tech")


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
        param_axes = get_param_axes(params_list)
        print_netlist_summary(
            block=block,
            pdk_name=request.config.getoption("--tech"),
            count=count,
            param_axes=param_axes,
            wall_time=wall_time,
            outdir=str(outdir),
            errors=errors,
        )
