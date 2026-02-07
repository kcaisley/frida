"""
TSMC 28nm HPC+ PDK plugin for FRIDA.

This PDK implements TSMC 28nm High-Performance Compact Plus process with:
- 6 transistor flavors: nmos/pmos × lvt/svt/hvt
- VDD nominal: 0.9V
- Minimum dimensions: W=40nm, L=30nm

Model file: /eda/kits/TSMC/28HPC+/2023_v1.1/pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre/toplevel.scs
Sections: att_pt (tt), ass_ps (ss), aff_pf (ff), asf_ps (sf), afs_pf (fs), local_mc (mc)
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

PDK_NAME = "tsmc28"


@h.paramclass
class Tsmc28MosParams:
    """
    TSMC 28nm MOS transistor parameters.

    These parameters match the nch_*_mac/pch_*_mac subcircuit interface.
    Units follow the PDK convention (meters for w/l).

    Attributes:
        w: Width in meters. Default is 40nm (Wmin).
        l: Length in meters. Default is 30nm (Lmin).
        nf: Number of fingers. Default is 1.
        m: Multiplier. Default is 1.
    """

    w = h.Param(dtype=h.Scalar, desc="Width", default=40 * n)
    l = h.Param(dtype=h.Scalar, desc="Length", default=30 * n)
    nf = h.Param(dtype=int, desc="Number of fingers", default=1)
    m = h.Param(dtype=int, desc="Multiplier", default=1)


def _xtor_module(modname: str) -> h.ExternalModule:
    """Create TSMC28 MOS transistor ExternalModule.

    Args:
        modname: SPICE model name (e.g., 'nch_lvt_mac', 'pch_svt_mac')

    Returns:
        ExternalModule representing the MOS device
    """
    return h.ExternalModule(
        domain=PDK_NAME,
        name=modname,
        desc=f"{PDK_NAME} PDK MOS {modname}",
        port_list=deepcopy(Mos.port_list),
        paramtype=Tsmc28MosParams,
        spicetype=SpiceType.MOS,
    )


# MOS transistor dictionary: (MosType, MosVth) -> ExternalModule
xtors: dict[tuple, h.ExternalModule] = {
    # NMOS variants (using _mac macro models)
    (MosType.NMOS, MosVth.LOW): _xtor_module("nch_lvt_mac"),
    (MosType.NMOS, MosVth.STD): _xtor_module("nch_svt_mac"),
    (MosType.NMOS, MosVth.HIGH): _xtor_module("nch_hvt_mac"),
    # PMOS variants
    (MosType.PMOS, MosVth.LOW): _xtor_module("pch_lvt_mac"),
    (MosType.PMOS, MosVth.STD): _xtor_module("pch_svt_mac"),
    (MosType.PMOS, MosVth.HIGH): _xtor_module("pch_hvt_mac"),
}

# Default transistor sizes (W, L) - minimum dimensions
DEFAULT_XTOR_SIZE = (40 * n, 30 * n)


@dataclass
class Install(PdkInstallation):
    """
    TSMC 28nm HPC+ PDK installation paths and corner mapping.

    Provides methods to include appropriate model files for simulation.

    Attributes:
        pdk_path: Path to the TSMC 28nm PDK installation.
    """

    pdk_path: Path = Path("/eda/kits/TSMC/28HPC+/2023_v1.1")

    @property
    def model_path(self) -> Path:
        """Path to the model files."""
        return self.pdk_path / "pdk/1P9M_5X1Y1Z1U_UT_AlRDL/cdsPDK/models/spectre"

    def include(self, corner: Corner) -> hs.Lib:
        """
        Get the model include for the specified process corner.

        TSMC 28nm uses naming: att_pt (tt), ass_ps (ss), aff_pf (ff)
        where 'a' prefix means 'all devices'.

        Args:
            corner: The process corner (TYP, FAST, SLOW).

        Returns:
            h.sim.Lib: The model library include.
        """
        corner_map: dict[Corner, str] = {
            Corner.TYP: "att_pt",
            Corner.FAST: "aff_pf",
            Corner.SLOW: "ass_ps",
        }
        if corner not in corner_map:
            raise ValueError(
                f"Invalid corner {corner}. Valid: {list(corner_map.keys())}"
            )

        return hs.Lib(
            path=self.model_path / "toplevel.scs",
            section=corner_map[corner],
        )

    def include_mc(self) -> hs.Lib:
        """Get the Monte Carlo model include."""
        return hs.Lib(
            path=self.model_path / "toplevel.scs",
            section="local_mc",
        )

    def include_noise(self, noise_corner: str = "typical") -> hs.Lib:
        """
        Get the noise model include.

        Args:
            noise_corner: Either 'typical' or 'worst'.

        Returns:
            h.sim.Lib: The noise model library include.
        """
        noise_sections = {
            "typical": "noise_typical",
            "worst": "noise_worst",
        }
        if noise_corner not in noise_sections:
            raise ValueError(
                f"Invalid noise corner {noise_corner}. Valid: {list(noise_sections.keys())}"
            )

        return hs.Lib(
            path=self.model_path
            / "crn28ull_1d8_elk_v1d8_2p2_shrink0d9_embedded_usage.scs",
            section=noise_sections[noise_corner],
        )


# Module-scope cache for ExternalModuleCall instances
@dataclass
class _Cache:
    """Cache for device calls to avoid duplicate instantiation."""

    mos_modcalls: dict[MosParams, h.ExternalModuleCall] = field(default_factory=dict)


_CACHE = _Cache()


class Tsmc28Walker(h.HierarchyWalker):
    """
    Hierarchical Walker for TSMC 28nm PDK.

    Converts h.primitives.Mos instances to TSMC28-specific ExternalModules
    during circuit compilation.
    """

    def visit_primitive_call(self, call: h.PrimitiveCall) -> h.Instantiable:
        """Replace instances of h.primitives.Mos with TSMC28 ExternalModules."""
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
                f"No TSMC28 device for type={mostype}, vth={mosvth}. "
                f"Available: {list(xtors.keys())}"
            )
        return xtors[key]

    def mos_params(self, params: MosParams) -> Tsmc28MosParams:
        """
        Convert hdl21 MosParams to TSMC28-specific parameters.

        Implements multiplier-based scaling:
        - If w/l are integers or have UNIT prefix, treat as multipliers of W_MIN/L_MIN
        - If w/l have physical prefixes (NANO, MICRO), use as absolute values

        Args:
            params: Generic MosParams.

        Returns:
            Tsmc28MosParams with appropriate values.
        """
        w = self._scale_dimension(params.w, Tsmc28Pdk.W_MIN, default_mult=10)
        l = self._scale_dimension(params.l, Tsmc28Pdk.L_MIN, default_mult=1)

        return Tsmc28MosParams(
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
    Compile the given circuit into TSMC 28nm technology.

    Walks the hierarchy and replaces h.primitives.Mos instances
    with TSMC28-specific ExternalModules.

    Args:
        src: The circuit(s) to compile.
    """
    Tsmc28Walker().walk(src)


class Tsmc28Pdk(FridaPdk):
    """TSMC 28nm HPC+ PDK implementation."""

    # Process parameters
    W_MIN = 40 * n
    L_MIN = 30 * n
    VDD_NOM = 900 * m

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
        """Compile primitives to TSMC28 PDK modules."""
        return Tsmc28Walker().walk(src)

    def include_statements(self, corner: Corner) -> list[hs.Lib]:
        """Return model includes for simulation at given corner."""
        return [self.install.include(corner)]
