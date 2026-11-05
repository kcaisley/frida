"""Characterize a kit's poly resistor in Spectre at the typical corner, 25 C, and write the polyres
table (``pdk/<pdk>/devices/polyres.json``).

The kit's device at three widths (its narrowest, twice and four times it) and three lengths, each
biased with 0.1 V in one operating-point run. At each width R is linear in the length (its slope the
sheet over the effective width, its offset the ends'), and the effective width is the drawn one
less dW: fitting the slopes' inverse against the width gives the sheet resistance and dW, the
offsets the ends.

    python -m flow.layout.devices.polyres.characterize tsmc65 [tsmc28 ...]
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.prefix import µ
from hdl21.primitives import Vdc
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.layout.pdkproc import pdk_value

from ..device import ROOT, write_table
from .netlist import DeviceParams, device

_VOLTAGE_V = 0.1
_LENGTHS_UM = (2.0, 4.0, 8.0)
_WIDTHS = (1, 2, 4)  # multiples of the kit's narrowest


def characterize(pdk: str) -> Path:
    """Measure ``pdk``'s poly resistor and write its polyres table."""

    logic = importlib.import_module(f"pdk.{pdk}.hdl21.pdk_logic")
    install = importlib.import_module(f"pdk.{pdk}.hdl21.site").install
    h.pdk.set_default(logic)
    spec = pdk_value(pdk, "tech", "RES")
    grid = int(pdk_value(pdk, "tech", "MFG_GRID"))
    kit = device(pdk)
    bench = h.Module(name="polyres_characterization")
    bench.VSS = h.Port()
    points = []
    for wk in _WIDTHS:
        for l_um in _LENGTHS_UM:
            w_nm, name = spec["width"] * wk, f"w{wk}_l{int(l_um * 1000)}"
            top = bench.add(h.Signal(), name=f"t_{name}")
            bench.add(Vdc(dc=_VOLTAGE_V)(p=top, n=bench.VSS), name=f"v_{name}")
            pins = {"PLUS": top, "MINUS": bench.VSS}
            if len(kit.port_list) == 3:
                pins["BULK"] = bench.VSS
            bench.add(kit(DeviceParams(l=l_um * µ, w=w_nm * 1e-3 * µ))(**pins), name=f"r_{name}")
            points.append((name, w_nm, l_um))
    attrs = [
        install.include(h.pdk.Corner.TYP),
        *([install.include_res(h.pdk.Corner.TYP)] if hasattr(install, "include_res") else []),
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Op(name="op"),
    ]
    result = hs.Sim(tb=bench, attrs=attrs).run(
        SimOptions(
            simulator=SupportedSimulators.SPECTRE,
            fmt=ResultFormat.SIM_DATA,
            rundir=ROOT / "build" / "devices" / "polyres" / pdk,
            simulator_args=("+lqtimeout", "600"),
        )
    )
    data = result.an[0].data
    resistance = {name: _VOLTAGE_V / abs(float(data[f"xtop.v_{name}:p"])) for name, _, _ in points}
    widths = sorted({w for _, w, _ in points})
    slopes, offsets = [], []
    for w_nm in widths:
        ls = [l_um for _, w, l_um in points if w == w_nm]
        rs = [resistance[name] for name, w, _ in points if w == w_nm]
        slope, offset = np.polyfit(ls, rs, 1)
        slopes.append(slope)
        offsets.append(offset)
    # 1 / slope = (W - dW) / sheet: a line in W
    a, b = np.polyfit(np.array(widths) / 1000, 1 / np.array(slopes), 1)
    sheet, dw_nm = 1 / a, -b / a * 1000
    end = float(np.mean([offset * (w - dw_nm) / 1000 for offset, w in zip(offsets, widths, strict=True)]))
    return write_table(
        "polyres",
        pdk,
        {
            "sheet_ohm": float(sheet),
            "end_ohm_um": end,
            "dw_nm": float(dw_nm),
            "width_nm": int(spec["width"]),
            "grid_nm": grid,
            "measured": [{"w_nm": w, "l_um": l_um, "ohm": resistance[name]} for name, w, l_um in points],
        },
        method="Spectre operating point, width and length fit",
    )


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(characterize(name))
