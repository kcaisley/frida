"""
Sampling switch generator module for FRIDA.

Exports:
- Samp: Sampling switch generator
- SampParams: Sampler parameters
- SampTb: Testbench generator
- SampTbParams: Testbench parameters
"""

from .subckt import Samp, SampParams, SwitchType

__all__ = [
    "Samp",
    "SampParams",
    "SampTb",
    "SampTbParams",
    "SwitchType",
    "sim_input",
]


def __getattr__(name: str):
    if name in {"SampTb", "SampTbParams", "sim_input"}:
        from importlib import import_module

        return getattr(import_module(f"{__name__}.testbench"), name)
    raise AttributeError(name)
