"""
Tower Semiconductor 180nm PDK plugin for FRIDA.

This PDK implements Tower 180nm (TS18) process with:
- 6 transistor flavors: nmos/pmos × lvt/svt/hvt
- VDD nominal: 1.8V
- Minimum dimensions: W=220nm, L=180nm

Model files:
- FET: /eda/kits/TOWER/ts18is_Rev_6.3.6/HOTCODE/models/ts18sl/v5.6.00/spectre/fet.scs
  Sections: NOM, SLOW, FAST, SLOWFAST, FASTSLOW, STAT
- Global: /eda/kits/TOWER/ts18is_Rev_6.3.6/HOTCODE/models/ts18sl/v5.6.00/spectre/global.scs
  Section: BSIM (always included)
"""

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import hdl21 as h
from hdl21.pdk import Corner, PdkInstallation
from hdl21.prefix import n, m
from hdl21.primitives import Mos, MosType, MosVth, MosParams
import hdl21.sim as hs
from vlsirtools import SpiceType

from .base import FridaPdk

PDK_NAME = "tower180"


@h.paramclass
class Tower180MosParams:
    """
    Tower 180nm MOS transistor parameters.

    These parameters match the n18/p18 model interface.
    Units follow the PDK convention (meters for w/l).

    Attributes:
        w: Width in meters. Default is 220nm (Wmin).
        l: Length in meters. Default is 180nm (Lmin).
        nf: Number of fingers. Default is 1.
        m: Multiplier. Default is 1.
    """

    w = h.Param(dtype=h.Scalar, desc="Width", default=220 * n)
    l = h.Param(dtype=h.Scalar, desc="Length", default=180 * n)
    nf = h.Param(dtype=int, desc="Number of fingers", default=1)
    m = h.Param(dtype=int, desc="Multiplier", default=1)


def _xtor_module(modname: str) -> h.ExternalModule:
    """Create Tower180 MOS transistor ExternalModule.

    Args:
        modname: SPICE model name (e.g., 'n18lvt', 'p18')

    Returns:
        ExternalModule representing the MOS device
    """
    return h.ExternalModule(
        domain=PDK_NAME,
        name=modname,
        desc=f"{PDK_NAME} PDK MOS {modname}",
        port_list=deepcopy(Mos.port_list),
        paramtype=Tower180MosParams,
        spicetype=SpiceType.MOS,
    )


# MOS transistor dictionary: (MosType, MosVth) -> ExternalModule
xtors: Dict[tuple, h.ExternalModule] = {
    # NMOS variants
    (MosType.NMOS, MosVth.LOW): _xtor_module("n18lvt"),
    (MosType.NMOS, MosVth.STD): _xtor_module("n18"),
    (MosType.NMOS, MosVth.HIGH): _xtor_module("n18hvt"),
    # PMOS variants
    (MosType.PMOS, MosVth.LOW): _xtor_module("p18lvt"),
    (MosType.PMOS, MosVth.STD): _xtor_module("p18"),
    (MosType.PMOS, MosVth.HIGH): _xtor_module("p18hvt"),
}

# Default transistor sizes (W, L) - minimum dimensions
DEFAULT_XTOR_SIZE = (220 * n, 180 * n)


@dataclass
class Install(PdkInstallation):
    """
    Tower 180nm PDK installation paths and corner mapping.

    This PDK requires two model includes:
    1. FET models (corner-dependent)
    2. Global models (always use BSIM section)

    Attributes:
        pdk_path: Path to the Tower 180nm PDK installation.
    """

    pdk_path: Path = Path("/eda/kits/TOWER/ts18is_Rev_6.3.6")

    @property
    def model_path(self) -> Path:
        """Path to the model files."""
        return self.pdk_path / "HOTCODE/models/ts18sl/v5.6.00/spectre"

    def include_fet(self, corner: Corner) -> hs.Lib:
        """
        Get the FET model include for the specified process corner.

        Args:
            corner: The process corner (TYP, FAST, SLOW).

        Returns:
            h.sim.Lib: The FET model library include.
        """
        corner_map: Dict[Corner, str] = {
            Corner.TYP: "NOM",
            Corner.FAST: "FAST",
            Corner.SLOW: "SLOW",
        }
        if corner not in corner_map:
            raise ValueError(f"Invalid corner {corner}. Valid: {list(corner_map.keys())}")

        return hs.Lib(
            path=self.model_path / "fet.scs",
            section=corner_map[corner],
        )

    def include_global(self) -> hs.Lib:
        """
        Get the global model include (always required).

        Returns:
            h.sim.Lib: The global model library include with BSIM section.
        """
        return hs.Lib(
            path=self.model_path / "global.scs",
            section="BSIM",
        )

    def include(self, corner: Corner) -> hs.Lib:
        """
        Get the primary (FET) model include for the specified corner.

        Note: For Tower180, you should also include the global models
        using include_global(). The include_statements() method of
        Tower180Pdk handles this automatically.

        Args:
            corner: The process corner (TYP, FAST, SLOW).

        Returns:
            h.sim.Lib: The FET model library include.
        """
        return self.include_fet(corner)

    def include_mc(self) -> hs.Lib:
        """Get the statistical (Monte Carlo) model include."""
        return hs.Lib(
            path=self.model_path / "fet.scs",
            section="STAT",
        )


# Module-scope cache for ExternalModuleCall instances
@dataclass
class _Cache:
    """Cache for device calls to avoid duplicate instantiation."""

    mos_modcalls: Dict[MosParams, h.ExternalModuleCall] = field(default_factory=dict)


_CACHE = _Cache()


class Tower180Walker(h.HierarchyWalker):
    """
    Hierarchical Walker for Tower 180nm PDK.

    Converts h.primitives.Mos instances to Tower180-specific ExternalModules
    during circuit compilation.
    """

    def visit_primitive_call(self, call: h.PrimitiveCall) -> h.Instantiable:
        """Replace instances of h.primitives.Mos with Tower180 ExternalModules."""
        if call.prim is Mos:
            return self.mos_module_call(call.params)
        # Pass through everything else unchanged
        return call

    def mos_module(self, params: MosParams) -> h.ExternalModule:
        """
        Select the appropriate ExternalModule for MOS parameters.

        Args:
            params: MosParams with type and threshold voltage info.

        Returns:
            ExternalModule for the device.
        """
        mostype = MosType.NMOS if params.tp is None else params.tp
        mosvth = MosVth.STD if params.vth is None else params.vth

        key = (mostype, mosvth)
        if key not in xtors:
            raise RuntimeError(
                f"No Tower180 device for type={mostype}, vth={mosvth}. "
                f"Available: {list(xtors.keys())}"
            )
        return xtors[key]

    def mos_params(self, params: MosParams) -> Tower180MosParams:
        """
        Convert hdl21 MosParams to Tower180-specific parameters.

        Implements multiplier-based scaling:
        - If w/l are integers or have UNIT prefix, treat as multipliers of W_MIN/L_MIN
        - If w/l have physical prefixes (NANO, MICRO), use as absolute values

        Args:
            params: Generic MosParams.

        Returns:
            Tower180MosParams with appropriate values.
        """
        from typing import Optional

        w = self._scale_dimension(params.w, Tower180Pdk.W_MIN, default_mult=10)
        l = self._scale_dimension(params.l, Tower180Pdk.L_MIN, default_mult=1)

        return Tower180MosParams(
            w=w,
            l=l,
            nf=params.nf if params.nf is not None else 1,
            m=params.mult if params.mult is not None else 1,
        )

    def _scale_dimension(
        self,
        value,
        min_dim: h.Prefixed,
        default_mult: int = 1,
    ) -> h.Prefixed:
        """
        Scale a dimension value using multiplier-based approach.

        Args:
            value: The input value (could be int, Prefixed, or None)
            min_dim: The minimum dimension (W_MIN or L_MIN)
            default_mult: Default multiplier if value is None

        Returns:
            Physical dimension as h.Prefixed
        """
        if value is None:
            return default_mult * min_dim

        # If it's an integer, treat as multiplier
        if isinstance(value, int):
            return value * min_dim

        # If it's a Prefixed value, check the prefix
        if isinstance(value, h.Prefixed):
            # Check if it has a physical prefix (NANO, MICRO, etc.)
            # Values with UNIT prefix (1.0) or no prefix are treated as multipliers
            if value.prefix == h.prefix.UNIT:
                # Treat the number as a multiplier
                return int(value.number) * min_dim
            else:
                # It's an absolute physical value - use as-is
                return value

        # For other numeric types, treat as multiplier
        try:
            mult = int(value)
            return mult * min_dim
        except (TypeError, ValueError):
            # Fall back to using as-is
            return value

    def mos_module_call(self, params: MosParams) -> h.ExternalModuleCall:
        """
        Get or create an ExternalModuleCall for the given MOS params.

        Uses caching to avoid duplicate instantiation.

        Args:
            params: MosParams for the device.

        Returns:
            ExternalModuleCall for the device.
        """
        if params in _CACHE.mos_modcalls:
            return _CACHE.mos_modcalls[params]

        mod = self.mos_module(params)
        modparams = self.mos_params(params)
        modcall = mod(modparams)

        _CACHE.mos_modcalls[params] = modcall
        return modcall


def compile(src: h.Elaboratables) -> None:
    """
    Compile the given circuit into Tower 180nm technology.

    Walks the hierarchy and replaces h.primitives.Mos instances
    with Tower180-specific ExternalModules.

    Args:
        src: The circuit(s) to compile.
    """
    Tower180Walker().walk(src)


class Tower180Pdk(FridaPdk):
    """Tower Semiconductor 180nm PDK implementation."""

    # Process parameters
    W_MIN = 220 * n
    L_MIN = 180 * n
    VDD_NOM = 1800 * m

    def __init__(self):
        self._install: Optional[Install] = None

    @property
    def name(self) -> str:
        return PDK_NAME

    @property
    def install(self) -> Install:
        """Get or create the PDK installation instance."""
        if self._install is None:
            self._install = Install()
        return self._install

    @property
    def Nmos(self) -> h.ExternalModule:
        return xtors[(MosType.NMOS, MosVth.STD)]

    @property
    def Pmos(self) -> h.ExternalModule:
        return xtors[(MosType.PMOS, MosVth.STD)]

    @property
    def NmosLvt(self) -> h.ExternalModule:
        return xtors[(MosType.NMOS, MosVth.LOW)]

    @property
    def PmosLvt(self) -> h.ExternalModule:
        return xtors[(MosType.PMOS, MosVth.LOW)]

    @property
    def NmosHvt(self) -> h.ExternalModule:
        return xtors[(MosType.NMOS, MosVth.HIGH)]

    @property
    def PmosHvt(self) -> h.ExternalModule:
        return xtors[(MosType.PMOS, MosVth.HIGH)]

    def compile(self, src: h.Elaboratables) -> None:
        """Compile primitives to Tower180 PDK modules."""
        return Tower180Walker().walk(src)

    def include_statements(self, corner: Corner) -> List[hs.Lib]:
        """
        Return model includes for simulation at given corner.

        Tower180 requires both FET and global model includes.
        """
        return [
            self.install.include_global(),  # Always include global first
            self.install.include_fet(corner),
        ]
