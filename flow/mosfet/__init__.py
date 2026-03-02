"""
MOSFET layout primitive module for FRIDA.

Exports:
- MosfetParams: MOSFET layout parameters
- mosfet: MOSFET layout generator
"""

from .primitive import MosfetParams, mosfet

__all__ = ["MosfetParams", "mosfet"]
