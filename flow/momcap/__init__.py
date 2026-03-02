"""
MOMCAP layout primitive module for FRIDA.

Exports:
- MomcapParams: MOMCAP layout parameters
- momcap: MOMCAP layout generator
"""

from .primitive import MomcapParams, momcap

__all__ = ["MomcapParams", "momcap"]
