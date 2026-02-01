"""
IHP SG13G2 130nm BiCMOS PDK plugin for FRIDA.

This PDK implements IHP SG13G2 130nm process with:
- Low-voltage (1.2V) CMOS transistors: sg13_lv_nmos/pmos
- High-voltage (3.3V) I/O transistors: sg13_hv_nmos/pmos (optional)
- VDD nominal: 1.2V (LV core)
- Minimum dimensions: W=350nm, L=130nm (LV), L=450nm (HV)

Model files (from IHP-Open-PDK):
- LV MOS: {PDK_PATH}/libs.tech/ngspice/models/cornerMOSlv.lib
- HV MOS: {PDK_PATH}/libs.tech/ngspice/models/cornerMOShv.lib
  Sections: tt, ff, ss

This is an open-source PDK available at:
https://github.com/IHP-GmbH/IHP-Open-PDK
"""

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import hdl21 as h
import hdl21.sim as hs
from hdl21.pdk import Corner, PdkInstallation
from hdl21.prefix import NANO, m, n
from hdl21.primitives import Mos, MosParams, MosType, MosVth
from vlsirtools import SpiceType

from .base import FridaPdk

PDK_NAME = "ihp130"

# Process parameters
W_MIN = 350 * n  # 350nm minimum width
L_MIN = 130 * n  # 130nm minimum length (LV)
L_MIN_HV = 450 * n  # 450nm minimum length (HV)
VDD_NOM = 1200 * m  # 1.2V nominal supply


@h.paramclass
class Ihp130MosParams:
    """
    IHP 130nm LV MOS transistor parameters.

    These parameters match the sg13_lv_nmos/pmos subcircuit interface.
    The IHP PDK uses microns for w/l parameters.

    Attributes:
        w: Width in meters. Default is 350nm (Wmin).
        l: Length in meters. Default is 130nm (Lmin for LV).
        ng: Number of gate fingers. Default is 1.
        m: Multiplier. Default is 1.
    """

    w = h.Param(dtype=h.Scalar, desc="Width", default=350 * n)
    l = h.Param(dtype=h.Scalar, desc="Length", default=130 * n)
    ng = h.Param(dtype=int, desc="Number of gate fingers", default=1)
    m = h.Param(dtype=int, desc="Multiplier", default=1)


@h.paramclass
class Ihp130MosHvParams:
    """
    IHP 130nm HV MOS transistor parameters.

    For sg13_hv_nmos/pmos subcircuits (3.3V I/O devices).
    Minimum length is 450nm for HV devices.

    Attributes:
        w: Width in meters. Default is 350nm (Wmin).
        l: Length in meters. Default is 450nm (Lmin for HV).
        ng: Number of gate fingers. Default is 1.
        m: Multiplier. Default is 1.
    """

    w = h.Param(dtype=h.Scalar, desc="Width", default=350 * n)
    l = h.Param(dtype=h.Scalar, desc="Length", default=450 * n)
    ng = h.Param(dtype=int, desc="Number of gate fingers", default=1)
    m = h.Param(dtype=int, desc="Multiplier", default=1)


def _xtor_module(modname: str, paramtype=Ihp130MosParams) -> h.ExternalModule:
    """Create IHP130 MOS transistor ExternalModule.

    Args:
        modname: SPICE subcircuit name (e.g., 'sg13_lv_nmos')
        paramtype: Parameter class for this device

    Returns:
        ExternalModule representing the MOS device
    """
    return h.ExternalModule(
        domain=PDK_NAME,
        name=modname,
        desc=f"{PDK_NAME} PDK MOS {modname}",
        port_list=deepcopy(Mos.port_list),
        paramtype=paramtype,
        spicetype=SpiceType.SUBCKT,
    )


# MOS transistor dictionary: (MosType, MosVth) -> ExternalModule
# IHP SG13G2 has only STD Vth for both LV and HV devices
xtors: Dict[tuple, h.ExternalModule] = {
    # LV CMOS (1.2V core) - standard threshold only
    (MosType.NMOS, MosVth.STD): _xtor_module("sg13_lv_nmos"),
    (MosType.PMOS, MosVth.STD): _xtor_module("sg13_lv_pmos"),
    # Map LVT requests to STD (IHP doesn't have LVT/HVT variants for LV)
    (MosType.NMOS, MosVth.LOW): _xtor_module("sg13_lv_nmos"),
    (MosType.PMOS, MosVth.LOW): _xtor_module("sg13_lv_pmos"),
}

# HV transistors (3.3V I/O) - separate dict for different params
xtors_hv: Dict[tuple, h.ExternalModule] = {
    (MosType.NMOS, MosVth.STD): _xtor_module("sg13_hv_nmos", Ihp130MosHvParams),
    (MosType.PMOS, MosVth.STD): _xtor_module("sg13_hv_pmos", Ihp130MosHvParams),
}

# Default transistor sizes (W, L) - minimum dimensions
DEFAULT_XTOR_SIZE = (350 * n, 130 * n)


@dataclass
class Install(PdkInstallation):
    """
    IHP SG13G2 130nm PDK installation paths and corner mapping.

    The IHP-Open-PDK is available at:
    https://github.com/IHP-GmbH/IHP-Open-PDK

    Attributes:
        pdk_path: Path to the IHP-Open-PDK installation (ihp-sg13g2 directory).
    """

    pdk_path: Path = Path("/home/kcaisley/libs/IHP-Open-PDK/ihp-sg13g2")

    @property
    def model_path(self) -> Path:
        """Path to the ngspice model files."""
        return self.pdk_path / "libs.tech/ngspice/models"

    def include_mos_lv(self, corner: Corner) -> hs.Lib:
        """
        Get the LV MOS model include for the specified process corner.

        Args:
            corner: The process corner (TYP, FAST, SLOW).

        Returns:
            h.sim.Lib: The model library include for LV MOS devices.
        """
        corner_map: Dict[Corner, str] = {
            Corner.TYP: "tt",
            Corner.FAST: "ff",
            Corner.SLOW: "ss",
        }
        if corner not in corner_map:
            raise ValueError(
                f"Invalid corner {corner}. Valid: {list(corner_map.keys())}"
            )

        return hs.Lib(
            path=self.model_path / "cornerMOSlv.lib",
            section=corner_map[corner],
        )

    def include_mos_hv(self, corner: Corner) -> hs.Lib:
        """
        Get the HV MOS model include for the specified process corner.

        Args:
            corner: The process corner (TYP, FAST, SLOW).

        Returns:
            h.sim.Lib: The model library include for HV MOS devices.
        """
        corner_map: Dict[Corner, str] = {
            Corner.TYP: "tt",
            Corner.FAST: "ff",
            Corner.SLOW: "ss",
        }
        if corner not in corner_map:
            raise ValueError(
                f"Invalid corner {corner}. Valid: {list(corner_map.keys())}"
            )

        return hs.Lib(
            path=self.model_path / "cornerMOShv.lib",
            section=corner_map[corner],
        )

    def include(self, corner: Corner) -> hs.Lib:
        """
        Get the primary (LV MOS) model include for the specified corner.

        Args:
            corner: The process corner (TYP, FAST, SLOW).

        Returns:
            h.sim.Lib: The LV MOS model library include.
        """
        return self.include_mos_lv(corner)


# Module-scope cache for ExternalModuleCall instances
@dataclass
class _Cache:
    """Cache for device calls to avoid duplicate instantiation."""

    mos_modcalls: Dict[MosParams, h.ExternalModuleCall] = field(default_factory=dict)


_CACHE = _Cache()


class Ihp130Walker(h.HierarchyWalker):
    """
    Hierarchical Walker for IHP 130nm PDK.

    Converts h.primitives.Mos instances to IHP130-specific ExternalModules
    during circuit compilation.

    Implements multiplier-based scaling: w/l values are treated as multipliers
    of W_MIN/L_MIN to produce physical dimensions.
    """

    def visit_primitive_call(self, call: h.PrimitiveCall) -> h.Instantiable:
        """Replace instances of h.primitives.Mos with IHP130 ExternalModules."""
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
                f"No IHP130 device for type={mostype}, vth={mosvth}. "
                f"Available: {list(xtors.keys())}"
            )
        return xtors[key]

    def mos_params(self, params: MosParams) -> Ihp130MosParams:
        """
        Convert hdl21 MosParams to IHP130-specific parameters.

        Implements multiplier-based scaling:
        - If w/l are integers or have UNIT prefix, treat as multipliers of W_MIN/L_MIN
        - If w/l have physical prefixes (NANO, MICRO), use as absolute values

        Args:
            params: Generic MosParams.

        Returns:
            Ihp130MosParams with appropriate values.
        """
        # Get width - scale if it's a multiplier
        w = self._scale_dimension(params.w, W_MIN, default_mult=1)
        l = self._scale_dimension(params.l, L_MIN, default_mult=1)

        return Ihp130MosParams(
            w=w,
            l=l,
            ng=params.nf if params.nf is not None else 1,
            m=params.mult if params.mult is not None else 1,
        )

    def _scale_dimension(
        self,
        value: Optional[h.Scalar],
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
    Compile the given circuit into IHP 130nm technology.

    Walks the hierarchy and replaces h.primitives.Mos instances
    with IHP130-specific ExternalModules.

    Args:
        src: The circuit(s) to compile.
    """
    Ihp130Walker().walk(src)


class Ihp130Pdk(FridaPdk):
    """IHP SG13G2 130nm BiCMOS PDK implementation."""

    # Process parameters
    W_MIN = 350 * n
    L_MIN = 130 * n
    VDD_NOM = 1200 * m

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
        # IHP doesn't have LVT variant - return STD
        return xtors[(MosType.NMOS, MosVth.LOW)]

    @property
    def PmosLvt(self) -> h.ExternalModule:
        # IHP doesn't have LVT variant - return STD
        return xtors[(MosType.PMOS, MosVth.LOW)]

    @property
    def NmosHvt(self) -> Optional[h.ExternalModule]:
        """IHP doesn't have HVT variant - return None."""
        return None

    @property
    def PmosHvt(self) -> Optional[h.ExternalModule]:
        """IHP doesn't have HVT variant - return None."""
        return None

    @property
    def NmosHv(self) -> h.ExternalModule:
        """High-voltage (3.3V) NMOS for I/O."""
        return xtors_hv[(MosType.NMOS, MosVth.STD)]

    @property
    def PmosHv(self) -> h.ExternalModule:
        """High-voltage (3.3V) PMOS for I/O."""
        return xtors_hv[(MosType.PMOS, MosVth.STD)]

    def compile(self, src: h.Elaboratables) -> None:
        """Compile primitives to IHP130 PDK modules."""
        return Ihp130Walker().walk(src)

    def include_statements(self, corner: Corner) -> List[hs.Lib]:
        """
        Return model includes for simulation at given corner.

        For most circuits, only LV MOS models are needed.
        Add HV models manually if using 3.3V I/O devices.
        """
        return [self.install.include_mos_lv(corner)]
