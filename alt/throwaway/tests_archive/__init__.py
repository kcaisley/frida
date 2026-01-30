"""
Tests and testbenches for FRIDA HDL21 generators.

Test modules:
- test_samp: Sampler testbench with width/type sweeps
- test_comp: Comparator testbench with S-curve and Monte Carlo
- test_cdac: CDAC testbench with code sweeps and linearity
"""

from .sim_options import sim_options, get_sim_options
from .test_comp import MCConfig, DEFAULT_MC_CONFIG

__all__ = [
    "sim_options",
    "get_sim_options",
    "MCConfig",
    "DEFAULT_MC_CONFIG",
]
