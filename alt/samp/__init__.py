"""
Sampling switch generator module for FRIDA.

Exports:
- Samp: Sampling switch generator
- SampParams: Sampler parameters
- samp_variants: Generate parameter sweep variants
- SampTb: Testbench generator
- SampTbParams: Testbench parameters
"""

from .samp import Samp, SampParams, samp_variants
from .test_samp import SampTb, SampTbParams, sim_input

__all__ = [
    "Samp",
    "SampParams",
    "samp_variants",
    "SampTb",
    "SampTbParams",
    "sim_input",
]
