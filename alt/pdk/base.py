"""
Abstract base class for FRIDA PDK plugins.

Each PDK plugin implements this interface to provide access to
PDK-specific transistor models and compilation routines.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import hdl21 as h
from hdl21.pdk import Corner
from hdl21.prefix import n, m
import hdl21.sim as hs


class FridaPdk(ABC):
    """Abstract base class for FRIDA PDK plugins.

    Each PDK must define:
    - Process parameters: W_MIN, L_MIN, VDD_NOM
    - Device accessors: Nmos, Pmos, NmosLvt, PmosLvt, NmosHvt, PmosHvt
    - compile() method to convert primitives to PDK modules
    - include_statements() for simulator model files
    """

    # Process parameters - override in subclasses
    W_MIN: h.Prefixed = 1000 * n  # Minimum transistor width
    L_MIN: h.Prefixed = 100 * n   # Minimum transistor length
    VDD_NOM: h.Prefixed = 1200 * m  # Nominal supply voltage (in volts)

    @property
    @abstractmethod
    def name(self) -> str:
        """PDK name identifier."""
        ...

    @property
    @abstractmethod
    def Nmos(self) -> h.ExternalModule:
        """Standard Vth NMOS device."""
        ...

    @property
    @abstractmethod
    def Pmos(self) -> h.ExternalModule:
        """Standard Vth PMOS device."""
        ...

    @property
    @abstractmethod
    def NmosLvt(self) -> h.ExternalModule:
        """Low Vth NMOS device."""
        ...

    @property
    @abstractmethod
    def PmosLvt(self) -> h.ExternalModule:
        """Low Vth PMOS device."""
        ...

    @property
    def NmosHvt(self) -> Optional[h.ExternalModule]:
        """High Vth NMOS device. Optional - returns None if not available."""
        return None

    @property
    def PmosHvt(self) -> Optional[h.ExternalModule]:
        """High Vth PMOS device. Optional - returns None if not available."""
        return None

    @abstractmethod
    def compile(self, src: h.Elaboratables) -> None:
        """
        Compile generic primitives to PDK-specific modules.

        This walks the hierarchy and replaces hdl21.primitives
        with PDK-specific ExternalModules.
        """
        ...

    def include_statements(self, corner: Corner) -> List[hs.Lib]:
        """
        Return simulator include statements for this PDK at given corner.

        Override in PDK implementations that have model files.
        Returns empty list by default (for generic PDK).
        """
        return []
