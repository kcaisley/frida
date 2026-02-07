"""
Sampling switch generator module for FRIDA.

Exports:
- Samp: Sampling switch generator
- SampParams: Sampler parameters
- SampTb: Testbench generator
- SampTbParams: Testbench parameters
"""

from .samp import Samp, SampParams
from .test_samp import SampTb, SampTbParams, sim_input

__all__ = [
    "Samp",
    "SampParams",
    "SampTb",
    "SampTbParams",
    "sim_input",
]
