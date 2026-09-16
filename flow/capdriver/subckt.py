"""PDK-independent, C0-first standard-cell capacitor drivers.

PDK compile passes must replace generic.clock_xor with a standard-cell view
implementing Y = A XOR B, preserving the A, B, Y, VDD, VSS interface. Drive
bands select library variants; they are not transistor-width multipliers.
CapDriver connects inversion to A and state to B, preserving the historical
TSMC65 A1/A2 assignment and its asymmetric input timing paths.
There is deliberately no transistor or behavioral fallback here.
"""

import hdl21 as h
from pydantic import StrictInt

from flow.circuit.ports import module_from_ports, port_connections


@h.paramclass
class ClockXorParams:
    drive_band = h.Param(dtype=StrictInt, desc="Standard-cell drive band: 1, 2, or 4", default=1)

    def __post_init__(self):
        if type(self.drive_band) is not int or self.drive_band not in (1, 2, 4):
            raise ValueError("ClockXor drive_band must be an integer in (1, 2, 4)")


@h.bundle
class ClockXorPorts:
    A, B = h.Input(), h.Input()
    Y = h.Output()
    VDD = h.Power(direction=h.PortDir.INOUT)
    VSS = h.Ground(direction=h.PortDir.INOUT)


ClockXor = h.ExternalModule(
    domain="generic",
    name="clock_xor",
    paramtype=ClockXorParams,
    port_list=list(ClockXorPorts.signals.values()),
    desc="Clock XOR standard cell; Y = A XOR B; requires PDK compile substitution",
)


def driver_ports(n_stages: int) -> dict[str, h.Signal]:
    """The C0-first driver interface, shared by generation and layout adapters."""

    @h.bundle
    class Ports:
        dac_state = h.Input(width=n_stages)
        dac_drive = h.Output(width=n_stages)
        dac_drive_invert = h.Input()
        vdd = h.Power(direction=h.PortDir.INOUT)
        vss = h.Ground(direction=h.PortDir.INOUT)

    return Ports.signals


@h.paramclass
class CapDriverParams:
    n_stages = h.Param(dtype=StrictInt, desc="Number of C0-first conversion stages")
    strengths = h.Param(
        dtype=tuple[StrictInt, ...] | None,
        desc="C0-first drive bands; None selects (4, 4, 2, 2, 1, ...)",
        default=None,
    )


# PDK compilation mutates modules in place; each request needs a fresh driver.
@h.generator(enable_cache=False)
def CapDriver(params: CapDriverParams) -> h.Module:
    """Drive each stage with dac_state XOR the shared dac_drive_invert input."""
    if type(params.n_stages) is not int or params.n_stages <= 0:
        raise ValueError("CapDriver n_stages must be a positive integer")
    strengths = params.strengths
    if strengths is None:
        strengths = (4, 4, 2, 2)[: params.n_stages] + (1,) * max(0, params.n_stages - 4)
    if len(strengths) != params.n_stages:
        raise ValueError("CapDriver strengths must have one drive band per stage")
    if any(type(band) is not int or band not in (1, 2, 4) for band in strengths):
        raise ValueError("CapDriver strengths must be integers in (1, 2, 4)")

    CapDriver = module_from_ports("CapDriver", driver_ports(params.n_stages))

    for stage, band in enumerate(strengths):
        setattr(
            CapDriver,
            f"xor_{stage}",
            ClockXor(ClockXorParams(drive_band=band))(
                **port_connections(
                    ClockXor.ports,
                    CapDriver,
                    A=CapDriver.dac_drive_invert,
                    B=CapDriver.dac_state[stage],
                    Y=CapDriver.dac_drive[stage],
                    VDD=CapDriver.vdd,
                    VSS=CapDriver.vss,
                )
            ),
        )
    return CapDriver
