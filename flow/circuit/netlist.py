"""Small shared utilities for HDL21 simulation inputs."""

from pathlib import Path

import hdl21.sim as hs
from hdl21.sim import to_proto
from vlsirtools.netlist import NetlistOptions
from vlsirtools.netlist.spectre import SpectreNetlister


def pwl_points_to_wave(points: list[tuple[float, float]]) -> str:
    """Format time/value points for HDL21's string-valued ``Vpwl.wave`` parameter."""

    return " ".join(f"{time_s:.12e} {value:.6e}" for time_s, value in points)


def write_spectre_input(
    sim: hs.Sim,
    dest: Path,
) -> None:
    """Write one completed HDL21 simulation as a compact Spectre input deck."""

    proto = to_proto(sim)
    options = NetlistOptions(compact=True)
    with dest.open("w") as stream:
        SpectreNetlister(dest=stream, opts=options).write_sim_input(proto)
