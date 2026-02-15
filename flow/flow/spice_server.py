"""
SpiceServer gRPC client helpers for FRIDA simulation flows.
"""

import os
import sys
from pathlib import Path
from typing import Any

from vlsirtools.spice import SupportedSimulators

DEFAULT_SPICE_SERVER_PORT = 50051

_SIMULATOR_TO_FLAVOUR = {
    SupportedSimulators.SPECTRE: "SPECTRE",
    SupportedSimulators.NGSPICE: "NGSPICE",
    SupportedSimulators.XYCE: "XYCE",
}


def _pythonpath_candidates() -> list[Path]:
    """Get candidate paths for SpiceServer's generated Python protobuf modules."""
    candidates: list[Path] = []

    env_paths = os.environ.get("FRIDA_SPICE_SERVER_PYTHONPATH", "")
    if env_paths:
        for path in env_paths.split(os.pathsep):
            if path:
                candidates.append(Path(path).expanduser())

    candidates.extend(
        [
            Path.home() / "libs" / "spice_server" / "example_client",
            Path.home() / "libs" / "spice_server",
        ]
    )
    return candidates


def _load_client_modules() -> tuple[Any, Any, Any]:
    """
    Load gRPC and generated SpiceServer protobuf modules.

    Returns:
        Tuple of (grpc, spice_simulator_pb2, spice_simulator_pb2_grpc)

    Raises:
        RuntimeError: If required modules are unavailable.
    """
    try:
        import grpc
        import spice_simulator_pb2
        import spice_simulator_pb2_grpc
    except ModuleNotFoundError:
        for candidate in _pythonpath_candidates():
            resolved = candidate.resolve()
            if resolved.exists():
                resolved_str = str(resolved)
                if resolved_str not in sys.path:
                    sys.path.append(resolved_str)

        try:
            import grpc
            import spice_simulator_pb2
            import spice_simulator_pb2_grpc
        except ModuleNotFoundError as err:
            msg = (
                "Failed to import SpiceServer client modules. Ensure grpcio is "
                "installed and protobuf stubs are generated (for example, run "
                "'./generate_protobufs.sh' in ~/libs/spice_server/example_client), "
                "or set FRIDA_SPICE_SERVER_PYTHONPATH."
            )
            raise RuntimeError(msg) from err

    return grpc, spice_simulator_pb2, spice_simulator_pb2_grpc


def _normalize_target(target: str) -> str:
    """Normalize target string into host:port form."""
    clean = target.strip()
    if ":" in clean:
        return clean
    return f"{clean}:{DEFAULT_SPICE_SERVER_PORT}"


def run_remote_sim_inputs(
    sim_inputs: list[Any],
    simulator: SupportedSimulators,
    target: str,
) -> None:
    """
    Run VLSIR SimInput messages through a remote SpiceServer.

    Args:
        sim_inputs: VLSIR SimInput messages
        simulator: Simulator flavour to request
        target: SpiceServer target in host:port format

    Raises:
        RuntimeError: On import/setup failures or non-zero simulator exit.
        ValueError: For invalid simulator settings.
    """
    if simulator not in _SIMULATOR_TO_FLAVOUR:
        raise ValueError(f"Unsupported simulator for SpiceServer: {simulator}")

    grpc, spice_simulator_pb2, spice_simulator_pb2_grpc = _load_client_modules()
    flavour_name = _SIMULATOR_TO_FLAVOUR[simulator]

    try:
        flavour = getattr(spice_simulator_pb2.Flavour, flavour_name)
    except AttributeError as err:
        msg = f"SpiceServer client missing flavour enum: {flavour_name}"
        raise RuntimeError(msg) from err

    endpoint = _normalize_target(target)
    with grpc.insecure_channel(endpoint) as channel:
        stub = spice_simulator_pb2_grpc.SpiceSimulatorStub(channel)
        for idx, sim_input in enumerate(sim_inputs):
            request = spice_simulator_pb2.SimulationRequest()
            request.simulator = flavour
            request.vlsir_sim_input.CopyFrom(sim_input)

            exit_code: int | None = None
            for response in stub.RunSimulation(request):
                if response.output:
                    for line in response.output.splitlines():
                        print(f"remote[{idx}]: {line}")
                if response.done:
                    exit_code = response.exit_code

            if exit_code is None:
                raise RuntimeError(
                    f"SpiceServer returned no completion message for simulation {idx}"
                )
            if exit_code != 0:
                raise RuntimeError(
                    f"SpiceServer simulation {idx} failed with exit code {exit_code}"
                )
