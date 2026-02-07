"""
PDK abstraction layer for FRIDA.

Provides a unified interface to access PDK-specific devices,
with support for multiple process nodes (TSMC65, TSMC28, Tower180, generic).

Usage:
    from flow.pdk import set_pdk, get_pdk

    # Set PDK by name
    set_pdk("tsmc65")

    # Or set with PDK instance
    from flow.pdk.tsmc65 import Tsmc65Pdk
    set_pdk(Tsmc65Pdk())

    # Get current PDK
    pdk = get_pdk()
    print(pdk.name, pdk.VDD_NOM)

Note: Changing PDK resets generator caches to ensure fresh device instantiation.
"""

from .base import FridaPdk
from .generic import GenericPdk
from .ihp130 import Ihp130Pdk
from .tower180 import Tower180Pdk
from .tsmc28 import Tsmc28Pdk
from .tsmc65 import Tsmc65Pdk

# Registry of available PDKs by name
_PDK_REGISTRY: dict[str, type[FridaPdk]] = {
    "generic": GenericPdk,
    "ihp130": Ihp130Pdk,
    "tsmc65": Tsmc65Pdk,
    "tsmc28": Tsmc28Pdk,
    "tower180": Tower180Pdk,
}

# Global PDK instance - set via set_pdk() or defaults to GenericPdk
_active_pdk: FridaPdk | None = None


def _reset_generator_caches() -> None:
    """Reset all FRIDA generator caches.

    This is called automatically when PDK changes to ensure generators
    create fresh modules with the new PDK's devices.
    """
    # Import generators lazily to avoid circular imports
    try:
        from ..samp.samp import Samp
        from ..samp.test_samp import SampTb

        Samp.Cache.reset()
        SampTb.Cache.reset()
    except (ImportError, AttributeError):
        pass

    try:
        from ..comp.comp import Comp
        from ..comp.test_comp import CompTb

        Comp.Cache.reset()
        CompTb.Cache.reset()
    except (ImportError, AttributeError):
        pass

    try:
        from ..cdac.cdac import Cdac
        from ..cdac.test_cdac import CdacTb

        Cdac.Cache.reset()
        CdacTb.Cache.reset()
    except (ImportError, AttributeError):
        pass


def get_pdk() -> FridaPdk:
    """Get the currently active PDK. Defaults to GenericPdk if not set."""
    global _active_pdk
    if _active_pdk is None:
        _active_pdk = GenericPdk()
    return _active_pdk


def set_pdk(pdk: str | FridaPdk) -> None:
    """
    Set the active PDK for all FRIDA generators.

    Also resets generator caches to ensure fresh device instantiation.

    Args:
        pdk: Either a PDK name string ("tsmc65", "tsmc28", "tower180", "generic")
             or a FridaPdk instance.

    Raises:
        ValueError: If pdk is a string not in the registry.
        TypeError: If pdk is neither a string nor a FridaPdk instance.
    """
    global _active_pdk

    if isinstance(pdk, str):
        if pdk not in _PDK_REGISTRY:
            available = list(_PDK_REGISTRY.keys())
            raise ValueError(f"Unknown PDK: '{pdk}'. Available: {available}")
        _active_pdk = _PDK_REGISTRY[pdk]()
    elif isinstance(pdk, FridaPdk):
        _active_pdk = pdk
    else:
        raise TypeError(f"Expected str or FridaPdk, got {type(pdk).__name__}")

    # Reset generator caches so new modules use the new PDK
    _reset_generator_caches()


def list_pdks() -> list:
    """Return list of available PDK names."""
    return list(_PDK_REGISTRY.keys())


__all__ = [
    "FridaPdk",
    "GenericPdk",
    "Ihp130Pdk",
    "Tsmc65Pdk",
    "Tsmc28Pdk",
    "Tower180Pdk",
    "get_pdk",
    "set_pdk",
    "list_pdks",
]
