"""
MOSFET layout primitive module for FRIDA.

Exports:
- MosfetParams: MOSFET layout parameters
- mosfet: MOSFET layout generator
"""

__all__ = ["MosfetParams", "mosfet"]


def __getattr__(name: str):
    if name in __all__:
        from importlib import import_module

        return getattr(import_module(f"{__name__}.primitive"), name)
    raise AttributeError(name)
