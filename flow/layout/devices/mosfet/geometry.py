"""What a transistor is drawn as: its type and threshold, its width in the PDK's unit widths, at its
minimum length (``netlist.mos``, ALIGN's ``MOSGenerator`` in a row cell)."""

from __future__ import annotations

from dataclasses import dataclass

from hdl21.primitives import MosType, MosVth


@dataclass(frozen=True)
class MosGeometry:
    """A core transistor: ``units`` of the PDK's unit width at its minimum length."""

    tp: MosType
    vth: MosVth
    units: int

    @property
    def key(self) -> str:
        """Its flavor's key in the table, ``NMOS/STD``."""
        return flavor(self.tp, self.vth)


def flavor(tp: MosType, vth: MosVth) -> str:
    """A flavor's key in the table: its type and threshold, ``NMOS/STD``."""
    return f"{tp.name}/{vth.name}"


@dataclass(frozen=True)
class InverterGeometry:
    """A complementary inverter drawn in one row cell (``rowcell.inverter``, ALIGN's
    ``CmosInverter``): its NMOS and PMOS ``n_units`` and ``p_units`` of the PDK's unit width in
    total over ``nf`` shared fingers, at the minimum length. Its netlist keeps its two transistors
    (``netlist_devices``), so a simulation and LVS see them; the generator reads them back.
    ``wide_input``: its input bar across the whole cell (``rowcell.inverter``)."""

    n_units: int
    p_units: int
    nf: int
    wide_input: bool = False
    netlist_devices = True

    @property
    def align_generator(self) -> str:
        return "CmosInverter"

    def align_parameters(self) -> dict[str, int]:
        return {"wide_input": 1} if self.wide_input else {}


@dataclass(frozen=True)
class ChainGeometry:
    """A chain of complementary inverters drawn in one row cell, each output linked to the next
    input inside it (``rowcell.inverter_chain``, ALIGN's ``CmosChain``): ``cases`` its inverters,
    input first, each (gate length, NMOS and PMOS finger widths, fingers) in nm. Its netlist keeps
    every inverter's two transistors (``netlist_devices``). ``wide_input``: its first input bar
    across its cell; ``fixed``: never mirrored."""

    cases: tuple[tuple[int, int, int, int], ...]
    wide_input: bool = False
    fixed: bool = False
    netlist_devices = True

    @property
    def align_generator(self) -> str:
        return "CmosChain"

    def align_parameters(self) -> dict[str, int | str]:
        stages = ";".join(":".join(str(v) for v in case) for case in self.cases)
        return {"stages": stages, "wide_input": int(self.wide_input), "fixed": int(self.fixed)}
