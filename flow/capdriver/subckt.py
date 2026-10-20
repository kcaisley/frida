"""PDK-independent, C0-first standard-cell capacitor drivers.

Each stage drives its output with ``dac_state[stage] XOR dac_drive_invert``, from standard cells
the PDK's compile pass picks. Two builds:

- ``Cells.GENERIC`` (the default): the generic cells every PDK's library has
  (``flow.circuit.cells``): an ``xor2_x1``, and after it a ``buf_x<strength>`` where the stage's
  strength (1, 2, 4, 8 or 16) is above 1.
- ``Cells.CLOCK_XOR``: FRIDA-1's, one ``generic.clock_xor`` per stage in drive band 1, 2 or 4,
  which each PDK's compile pass replaces with its library's clock XOR of that band (or cells
  that make one), preserving the A, B, Y, VDD, VSS interface.

Either way the inversion connects to A and the state to B, preserving the historical TSMC65
A1/A2 assignment and its asymmetric input timing paths. There is deliberately no transistor or
behavioral fallback here.
"""

from enum import Enum, auto

import hdl21 as h
from pydantic import StrictInt

from flow.circuit.cells import DRIVES, cell
from flow.circuit.ports import module_from_ports, port_connections

# the drive weights a generic stage reaches: the XOR alone, or the XOR and a buffer of the weight
GENERIC_STRENGTHS = (1, *DRIVES["buf"])
CLOCK_XOR_BANDS = (1, 2, 4)


class Cells(Enum):
    GENERIC = auto()  # an xor2_x1 per stage and a buf_x<strength> after it (flow.circuit.cells)
    CLOCK_XOR = auto()  # FRIDA-1's: a generic.clock_xor per stage, a library clock XOR per band


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
        desc="C0-first drive weights: 1, 2, 4, 8 or 16 (CLOCK_XOR: bands 1, 2, 4); None selects (4, 4, 2, 2, 1, ...)",
        default=None,
    )
    cells = h.Param(dtype=Cells, desc="Which standard cells build the stages", default=Cells.GENERIC)


def stage_strengths(params: CapDriverParams) -> tuple[int, ...]:
    """Each stage's drive weight, C0 first (the default where ``strengths`` is None)."""

    if type(params.n_stages) is not int or params.n_stages <= 0:
        raise ValueError("CapDriver n_stages must be a positive integer")
    strengths = params.strengths
    if strengths is None:
        strengths = (4, 4, 2, 2)[: params.n_stages] + (1,) * max(0, params.n_stages - 4)
    if len(strengths) != params.n_stages:
        raise ValueError("CapDriver strengths must have one drive weight per stage")
    allowed = GENERIC_STRENGTHS if params.cells == Cells.GENERIC else CLOCK_XOR_BANDS
    if any(type(strength) is not int or strength not in allowed for strength in strengths):
        raise ValueError(f"CapDriver strengths must be integers in {allowed} for {params.cells.name}")
    return tuple(strengths)


# PDK compilation mutates modules in place; each request needs a fresh driver.
@h.generator(enable_cache=False)
def CapDriver(params: CapDriverParams) -> h.Module:
    """Drive each stage with dac_state XOR the shared dac_drive_invert input."""
    strengths = stage_strengths(params)
    CapDriver = module_from_ports("CapDriver", driver_ports(params.n_stages))

    if params.cells == Cells.GENERIC:
        supplies = {"VDD": CapDriver.vdd, "VSS": CapDriver.vss}
        for stage, strength in enumerate(strengths):
            out = CapDriver.dac_drive[stage]
            xor_out = out if strength == 1 else CapDriver.add(h.Signal(), name=f"xor_out_{stage}")
            CapDriver.add(
                cell("xor2", 1)(A=CapDriver.dac_drive_invert, B=CapDriver.dac_state[stage], Y=xor_out, **supplies),
                name=f"xor_{stage}",
            )
            if strength > 1:
                CapDriver.add(cell("buf", strength)(A=xor_out, Y=out, **supplies), name=f"buf_{stage}")
        return CapDriver

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


# single drive stages, one per generic drive weight: the characterization's cases
CASES = {f"x{strength}": CapDriverParams(n_stages=1, strengths=(strength,)) for strength in GENERIC_STRENGTHS}
