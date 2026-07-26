"""
MOMCAP layout primitive module for FRIDA.

Exports:
- MomcapParams: MOMCAP layout parameters
- momcap: MOMCAP layout generator
"""

__all__ = ["MomcapParams", "momcap"]


def __getattr__(name: str):
    if name in __all__:
        from importlib import import_module

        return getattr(import_module(f"{__name__}.primitive"), name)
    raise AttributeError(name)
