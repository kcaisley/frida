"""
Sampling switch generator module for FRIDA.

Exports:
- Samp: Sampling switch generator
- SampParams: Sampler parameters
"""

from .subckt import Samp, SampParams, SwitchType

__all__ = [
    "Samp",
    "SampParams",
    "SwitchType",
]
