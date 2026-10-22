"""Every target of the flow: ``python -m flow`` lists them, ``python -m flow <block>.<target>`` runs one.

A target is a public function without arguments in a package's ``targets.py``; it makes its own
run directory under ``build/``.
"""

from __future__ import annotations

import inspect
import sys

from flow.adc import targets as adc
from flow.bias import targets as bias
from flow.caparray import targets as caparray
from flow.capdriver import targets as capdriver
from flow.cdac import targets as cdac
from flow.clkgen import targets as clkgen
from flow.cml import targets as cml
from flow.comp import targets as comp
from flow.csa import targets as csa
from flow.delay import targets as delay
from flow.disc import targets as disc
from flow.follower import targets as follower
from flow.idac import targets as idac
from flow.latch import targets as latch
from flow.lvshift import targets as lvshift
from flow.momcap import targets as momcap
from flow.moscap import targets as moscap
from flow.mosfet import targets as mosfet
from flow.ota import targets as ota
from flow.pi import targets as pi
from flow.polyres import targets as polyres
from flow.ringamp import targets as ringamp
from flow.samp import targets as samp
from flow.schmitt import targets as schmitt
from flow.sweep import targets as sweep
from flow.web import targets as web

BLOCKS = {
    "adc": adc,
    "bias": bias,
    "caparray": caparray,
    "capdriver": capdriver,
    "cdac": cdac,
    "clkgen": clkgen,
    "cml": cml,
    "comp": comp,
    "csa": csa,
    "delay": delay,
    "disc": disc,
    "follower": follower,
    "idac": idac,
    "latch": latch,
    "lvshift": lvshift,
    "momcap": momcap,
    "moscap": moscap,
    "mosfet": mosfet,
    "ota": ota,
    "pi": pi,
    "polyres": polyres,
    "ringamp": ringamp,
    "samp": samp,
    "schmitt": schmitt,
    "sweep": sweep,
    "web": web,
}


def targets(module) -> dict:
    """The targets a ``targets.py`` defines, by name, in source order."""
    return {
        name: function
        for name, function in vars(module).items()
        if inspect.isfunction(function) and function.__module__ == module.__name__ and not name.startswith("_")
    }


def main() -> None:
    if len(sys.argv) < 2:
        for block, module in BLOCKS.items():
            for name in targets(module):
                print(f"{block}.{name}")
        return
    block, _, name = sys.argv[1].partition(".")
    module = BLOCKS.get(block)
    if module is None or name not in targets(module):
        raise SystemExit(f"no target {sys.argv[1]}: python -m flow lists them")
    targets(module)[name]()


if __name__ == "__main__":
    main()
