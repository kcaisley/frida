"""PDK registry and activation for the FRIDA design flow.

Public API
----------
list_pdks()  – return the list of supported PDK short-names.
set_pdk(name) – resolve *name* to its hdl21 pdk module, set it as
               the default, and reset generator caches.
"""

from importlib import import_module
from types import ModuleType

import hdl21 as h

_PDK_PACKAGES: dict[str, str] = {
    "ihp130": "pdk.ihp130",
    "tsmc65": "pdk.tsmc65",
    "tsmc28": "pdk.tsmc28",
    "tower180": "pdk.tower180",
}

# Generators whose caches must be flushed after a PDK switch.
# Each entry is (dotted_module_path, class_name).
_CACHED_GENERATORS: list[tuple[str, str]] = [
    ("flow.samp.subckt", "Samp"),
    ("flow.samp.testbench", "SampTb"),
    ("flow.comp.subckt", "Comp"),
    ("flow.comp.testbench", "CompTb"),
    ("flow.cdac.subckt", "Cdac"),
    ("flow.cdac.testbench", "CdacTb"),
]


def list_pdks() -> list[str]:
    """Return the short-names of every supported PDK."""
    return list(_PDK_PACKAGES.keys())


def set_pdk(name: str) -> ModuleType:
    """Activate a PDK by short-name.

    1. Resolve *name* → its ``pdk_logic`` module.
    2. Call ``h.pdk.set_default(...)`` so hdl21 uses it for compilation.
    3. Reset all known generator caches (safe to call even if a
       generator has not been imported yet).
    """
    # -- resolve --------------------------------------------------------
    if name not in _PDK_PACKAGES:
        available = ", ".join(list_pdks())
        raise ValueError(f"Unknown PDK '{name}'. Available: {available}")

    pkg = import_module(_PDK_PACKAGES[name])
    pdk_module = getattr(pkg, "pdk_logic", None)
    if pdk_module is None:
        raise RuntimeError(f"PDK package '{_PDK_PACKAGES[name]}' has no `pdk_logic`")

    # -- activate -------------------------------------------------------
    h.pdk.set_default(pdk_module)

    # -- reset caches ---------------------------------------------------
    for mod_path, cls_name in _CACHED_GENERATORS:
        try:
            mod = import_module(mod_path)
            cls = getattr(mod, cls_name)
            cls.Cache.reset()
        except (ImportError, AttributeError):
            pass

    return pdk_module
