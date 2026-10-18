"""Poly resistors in simulation: each PDK's resistor device, and its DC resistance in Spectre.

``polyres_device`` is the PDK's device (``tech.RES["model"]``) as an external module with the
drawn width and length; ``polyres_resistance`` biases one with 0.1 V in its PDK's typical models
and returns its resistance. ``polyres_check`` compares that with the row cell's model value
(``rescell.res_value``) in every PDK with a resistor, writing ``summary.json``.
"""

from __future__ import annotations

import argparse
import importlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from multiprocessing import get_context
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import µ
from hdl21.primitives import Vdc
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.layout.pdkproc import pdk_value

from .layout import PDKS, PolyResUnit, polyres_layout

VOLTAGE_V = 0.1


@h.paramclass
class PolyResDeviceParams:
    l = h.Param(dtype=h.Scalar, desc="Body length")
    w = h.Param(dtype=h.Scalar, desc="Body width")


def polyres_device(technology: str) -> h.ExternalModule:
    """The PDK's resistor device: its two heads, and the substrate where the model has a third pin."""

    spec = pdk_value(technology, "tech", "RES")
    ports = [h.Inout(name="PLUS"), h.Inout(name="MINUS")]
    if spec.get("bulk"):
        ports.append(h.Inout(name="BULK"))
    return h.ExternalModule(
        name=spec.get("sim_model", spec["model"]),
        desc=f"{technology} poly resistor",
        port_list=ports,
        paramtype=PolyResDeviceParams,
    )


def polyres_resistance(unit: PolyResUnit, run_dir: Path) -> float:
    """The DC resistance (ohm) of the PDK's device at the unit's drawn width and length."""

    pdk = importlib.import_module(f"pdk.{unit.technology}")
    install = importlib.import_module(f"pdk.{unit.technology}.hdl21.site").install
    h.pdk.set_default(pdk.pdk_logic)
    device = polyres_device(unit.technology)
    tb = h.sim.tb("polyres_tb")
    tb.top = h.Signal()
    tb.src = Vdc(dc=VOLTAGE_V * h.prefix.UNIT)(p=tb.top, n=tb.VSS)
    pins = {"PLUS": tb.top, "MINUS": tb.VSS}
    if len(device.port_list) == 3:
        pins["BULK"] = tb.VSS
    params = PolyResDeviceParams(l=unit.l_nm * 1e-3 * µ, w=unit.w_nm * 1e-3 * µ)
    tb.res = device(params)(**pins)
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # a PDK whose resistors have their own library
        *([install.include_res(h.pdk.Corner.TYP)] if hasattr(install, "include_res") else []),
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Op(name="op"),
    ]
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        results = hs.Sim(tb=tb, attrs=attrs).run(
            SimOptions(simulator=SupportedSimulators.SPECTRE, fmt=ResultFormat.SIM_DATA, rundir=run_dir)
        )
    except SimError as error:
        raise RuntimeError(f"Spectre failed in {run_dir}: {error}") from None
    data = results["op"].data
    current = next(abs(value) for name, value in data.items() if name.endswith(("src:p", "src:n")))
    return float(VOLTAGE_V / current)


def _check(pdk: str, run_dir: Path) -> dict:
    spec = pdk_value(pdk, "tech", "RES")
    _layout, info = polyres_layout(PolyResUnit(pdk, spec["width"], 4000))
    simulated = polyres_resistance(PolyResUnit(pdk, info["w"], info["l"]), run_dir / pdk)
    return {"w": info["w"], "l": info["l"], "cell": info["r"], "spectre": simulated, "ratio": info["r"] / simulated}


def polyres_check(run_dir: Path) -> Path:
    """Simulate each PDK's resistor at its narrowest width and 4 um, against the cell's model value."""

    summary = {}
    with ProcessPoolExecutor(max_workers=6, mp_context=get_context("spawn")) as executor:
        futures = {executor.submit(_check, pdk, run_dir): pdk for pdk in PDKS}
        for future in as_completed(futures):
            try:
                summary[futures[future]] = future.result()
            except Exception as error:  # noqa: BLE001 - report every PDK's outcome
                summary[futures[future]] = {"error": str(error)[:500]}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return run_dir


def main() -> None:
    """Create one output directory and run one named poly resistor simulation target."""

    targets = {target.__name__: target for target in (polyres_check,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available poly resistor simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "polyres"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
