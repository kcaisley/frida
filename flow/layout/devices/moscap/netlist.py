"""MOS capacitors: a transistor of the PDK's sized to a capacitance (``mos_cap``)."""

from hdl21.primitives import MosType

from ..device import active_pdk
from ..mosfet.netlist import mos
from .geometry import CAP_L
from .table import density


def mos_cap(c_ff: float, *, tp, vth):
    """A MOS capacitor of about ``c_ff`` fF: the gate is the capacitor's node and source, drain and
    bulk go to the rail it is measured against, so it must sit in strong inversion over the node's
    swing (the node starting a supply away from that rail). Its width the units the active PDK's
    measured gate capacitance gives (``table.density``), at ``CAP_L``, fingered as any analog
    device; without a PDK (a netlist's structure alone), as if a unit device held ``CAP_L`` x 0.1 fF."""

    per_unit = density(active_pdk(), vth)["n" if tp == MosType.NMOS else "p"] * CAP_L
    units = max(1, round(c_ff / per_unit))
    return mos(tp=tp, vth=vth, w=units, l=CAP_L)
