"""
TSMC 65nm LP PDK plugin for FRIDA.

This PDK implements TSMC 65nm Low-Power process with:
- 6 transistor flavors: nmos/pmos × lvt/svt/hvt
- VDD nominal: 1.2V
- Minimum dimensions: W=120nm, L=60nm

Model file: /eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs
Sections: tt_lib, ss_lib, ff_lib, sf_lib, fs_lib, mc_lib
"""

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.pdk import Corner, PdkInstallation
from hdl21.prefix import m, n
from hdl21.primitives import Mos, MosParams, MosType, MosVth
from vlsirtools import SpiceType

from .base import FridaPdk

PDK_NAME = "tsmc65"


@h.paramclass
class Tsmc65MosParams:
    """
    TSMC 65nm MOS transistor parameters.

    These parameters match the nch/pch subcircuit interface.
    Units follow the PDK convention (meters for w/l).

    Attributes:
        w: Width in meters. Default is 120nm (Wmin).
        l: Length in meters. Default is 60nm (Lmin).
        nf: Number of fingers. Default is 1.
        m: Multiplier. Default is 1.
    """

    w = h.Param(dtype=h.Scalar, desc="Width", default=120 * n)
    l = h.Param(dtype=h.Scalar, desc="Length", default=60 * n)
    nf = h.Param(dtype=int, desc="Number of fingers", default=1)
    m = h.Param(dtype=int, desc="Multiplier", default=1)


def _xtor_module(modname: str) -> h.ExternalModule:
    """Create TSMC65 MOS transistor ExternalModule.

    Args:
        modname: SPICE model name (e.g., 'nch_lvt', 'pch')

    Returns:
        ExternalModule representing the MOS device
    """
    return h.ExternalModule(
        domain=PDK_NAME,
        name=modname,
        desc=f"{PDK_NAME} PDK MOS {modname}",
        port_list=deepcopy(Mos.port_list),
        paramtype=Tsmc65MosParams,
        spicetype=SpiceType.MOS,
    )


# MOS transistor dictionary: (MosType, MosVth) -> ExternalModule
xtors: dict[tuple, h.ExternalModule] = {
    # NMOS variants
    (MosType.NMOS, MosVth.LOW): _xtor_module("nch_lvt"),
    (MosType.NMOS, MosVth.STD): _xtor_module("nch"),
    (MosType.NMOS, MosVth.HIGH): _xtor_module("nch_hvt"),
    # PMOS variants
    (MosType.PMOS, MosVth.LOW): _xtor_module("pch_lvt"),
    (MosType.PMOS, MosVth.STD): _xtor_module("pch"),
    (MosType.PMOS, MosVth.HIGH): _xtor_module("pch_hvt"),
}

# Default transistor sizes (W, L) - minimum dimensions
DEFAULT_XTOR_SIZE = (120 * n, 60 * n)


@dataclass
class Install(PdkInstallation):
    """
    TSMC 65nm LP PDK installation paths and corner mapping.

    Provides methods to include appropriate model files for simulation.

    Attributes:
        pdk_path: Path to the TSMC 65nm PDK installation.
    """

    pdk_path: Path = Path("/eda/kits/TSMC/65LP/2024/V1.7A_1")

    def include(self, corner: Corner) -> hs.Lib:
        """
        Get the model include for the specified process corner.

        Args:
            corner: The process corner (TYP, FAST, SLOW).

        Returns:
            h.sim.Lib: The model library include.
        """
        corner_map: dict[Corner, str] = {
            Corner.TYP: "tt_lib",
            Corner.FAST: "ff_lib",
            Corner.SLOW: "ss_lib",
        }
        if corner not in corner_map:
            raise ValueError(
                f"Invalid corner {corner}. Valid: {list(corner_map.keys())}"
            )

        return hs.Lib(
            path=self.pdk_path / "1p9m6x1z1u/models/spectre/toplevel.scs",
            section=corner_map[corner],
        )

    def include_mc(self) -> hs.Lib:
        """Get the Monte Carlo model include."""
        return hs.Lib(
            path=self.pdk_path / "1p9m6x1z1u/models/spectre/toplevel.scs",
            section="mc_lib",
        )


# Module-scope cache for ExternalModuleCall instances
@dataclass
class _Cache:
    """Cache for device calls to avoid duplicate instantiation."""

    mos_modcalls: dict[MosParams, h.ExternalModuleCall] = field(default_factory=dict)


_CACHE = _Cache()


class Tsmc65Walker(h.HierarchyWalker):
    """
    Hierarchical Walker for TSMC 65nm PDK.

    Converts h.primitives.Mos instances to TSMC65-specific ExternalModules
    during circuit compilation.
    """

    def visit_primitive_call(self, call: h.PrimitiveCall) -> h.Instantiable:
        """Replace instances of h.primitives.Mos with TSMC65 ExternalModules."""
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
                f"No TSMC65 device for type={mostype}, vth={mosvth}. "
                f"Available: {list(xtors.keys())}"
            )
        return xtors[key]

    def mos_params(self, params: MosParams) -> Tsmc65MosParams:
        """
        Convert hdl21 MosParams to TSMC65-specific parameters.

        Implements multiplier-based scaling:
        - If w/l are integers or have UNIT prefix, treat as multipliers of W_MIN/L_MIN
        - If w/l have physical prefixes (NANO, MICRO), use as absolute values

        Args:
            params: Generic MosParams.

        Returns:
            Tsmc65MosParams with appropriate values.
        """
        w = self._scale_dimension(params.w, Tsmc65Pdk.W_MIN, default_mult=10)
        l = self._scale_dimension(params.l, Tsmc65Pdk.L_MIN, default_mult=1)

        return Tsmc65MosParams(
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
    Compile the given circuit into TSMC 65nm technology.

    Walks the hierarchy and replaces h.primitives.Mos instances
    with TSMC65-specific ExternalModules.

    Args:
        src: The circuit(s) to compile.
    """
    Tsmc65Walker().walk(src)


class Tsmc65Pdk(FridaPdk):
    """TSMC 65nm LP PDK implementation."""

    # Process parameters
    W_MIN = 120 * n
    L_MIN = 60 * n
    VDD_NOM = 1200 * m

    def __init__(self):
        self._install: Install | None = None

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
        """Compile primitives to TSMC65 PDK modules."""
        return Tsmc65Walker().walk(src)

    def include_statements(self, corner: Corner) -> list[hs.Lib]:
        """Return model includes for simulation at given corner."""
        return [self.install.include(corner)]
