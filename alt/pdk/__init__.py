"""
PDK abstraction layer for FRIDA.

Provides a unified interface to access PDK-specific devices,
with support for multiple process nodes (TSMC65, TSMC28, Tower180, generic).

Usage:
    from alt.pdk import set_pdk, get_pdk

    # Set PDK by name
    set_pdk("tsmc65")

    # Or set with PDK instance
    from alt.pdk.tsmc65 import Tsmc65Pdk
    set_pdk(Tsmc65Pdk())

    # Get current PDK
    pdk = get_pdk()
    print(pdk.name, pdk.VDD_NOM)
"""

from typing import Optional, Union, Dict, Type
from .base import FridaPdk
from .generic import GenericPdk
from .tsmc65 import Tsmc65Pdk
from .tsmc28 import Tsmc28Pdk
from .tower180 import Tower180Pdk

# Registry of available PDKs by name
_PDK_REGISTRY: Dict[str, Type[FridaPdk]] = {
    "generic": GenericPdk,
    "tsmc65": Tsmc65Pdk,
    "tsmc28": Tsmc28Pdk,
    "tower180": Tower180Pdk,
}

# Global PDK instance - set via set_pdk() or defaults to GenericPdk
_active_pdk: Optional[FridaPdk] = None


def get_pdk() -> FridaPdk:
    """Get the currently active PDK. Defaults to GenericPdk if not set."""
    global _active_pdk
    if _active_pdk is None:
        _active_pdk = GenericPdk()
    return _active_pdk


def set_pdk(pdk: Union[str, FridaPdk]) -> None:
    """
    Set the active PDK for all FRIDA generators.

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


def list_pdks() -> list:
    """Return list of available PDK names."""
    return list(_PDK_REGISTRY.keys())


__all__ = [
    "FridaPdk",
    "GenericPdk",
    "Tsmc65Pdk",
    "Tsmc28Pdk",
    "Tower180Pdk",
    "get_pdk",
    "set_pdk",
    "list_pdks",
]
