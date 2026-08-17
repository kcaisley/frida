"""CDAC testbench and named TSMC65 Spectre simulation targets."""

import argparse
import shutil
import subprocess
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import f, m, n, p
from hdl21.primitives import C, Vdc, Vpwl

from ..circuit.netlist import pwl_points_to_wave, write_spectre_input
from ..circuit.params import PvtParams, supply_voltage, temperature_c
from ..pdks import set_pdk
from .subckt import (
    Cdac,
    CdacParams,
    get_cdac_n_bits,
)

BASE_PATH = Path(__file__).resolve().parents[2]
MAX_PARALLEL_SIMULATIONS = 1
SPECTRE_THREADS_PER_SIMULATION = 4
MODEL_LIBRARY = Path("/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs")


@h.paramclass
class CdacTbParams:
    """CDAC testbench parameters."""

    pvt = h.Param(dtype=PvtParams, desc="PVT conditions", default=PvtParams())
    cdac = h.Param(dtype=CdacParams, desc="CDAC parameters", default=CdacParams())


@h.generator
def CdacTb(params: CdacTbParams) -> h.Module:
    """
    CDAC testbench generator.

    Creates a testbench with:
    - DC supply
    - DAC code inputs (driven by sim PWL)
    - Load capacitor on output
    """
    vdd = supply_voltage(params.pvt.v)
    n_bits = get_cdac_n_bits(params.cdac)

    @h.module
    class CdacTb:
        """CDAC testbench module."""

        vss = h.Port(desc="Ground")

        # Supply
        vdd = h.Signal()

        # DAC output with load
        top = h.Signal()

        # DAC code inputs (driven by sim PWL)
        dac_bits = h.Signal(width=n_bits)

    CdacTb.vvdd = Vdc(dc=vdd)(p=CdacTb.vdd, n=CdacTb.vss)
    CdacTb.cload = C(c=100 * f)(p=CdacTb.top, n=CdacTb.vss)

    CdacTb.dut = Cdac(params.cdac)(
        top=CdacTb.top,
        dac=CdacTb.dac_bits,
        vdd=CdacTb.vdd,
        vss=CdacTb.vss,
    )

    n_codes = 2**params.cdac.n_dac
    codes = list(range(n_codes))
    bit_values: list[list[h.Scalar]] = [[] for _ in range(n_bits)]
    for code in codes:
        for bit in range(n_bits):
            bit_is_set = (code >> bit) & 1
            bit_values[bit].append(vdd if bit_is_set else 0 * m)

    t_step = 200 * n
    t_rise = 100 * p
    for bit in range(n_bits):
        points, _ = _build_pwl_points(bit_values[bit], t_step, t_rise)
        wave = pwl_points_to_wave(points)
        setattr(
            CdacTb,
            f"vdac_{bit}",
            Vpwl(wave=wave)(p=CdacTb.dac_bits[bit], n=CdacTb.vss),
        )

    return CdacTb


def _build_pwl_points(
    values: list[h.Scalar],
    t_step: h.Scalar,
    t_rise: h.Scalar,
    t_delay: h.Scalar = 0 * n,
) -> tuple[list[tuple[float, float]], float]:
    points: list[tuple[float, float]] = []
    t = float(t_delay)
    step = float(t_step)
    rise = float(t_rise)

    for i, value in enumerate(values):
        points.append((t, float(value)))
        t += step
        if i < len(values) - 1:
            points.append((t, float(value)))
            t += rise

    return points, t


def sim_input(params: CdacTbParams) -> hs.Sim:
    """Create one selected-signal TSMC65 CDAC code-ramp input."""

    n_codes = 2**params.cdac.n_dac

    t_step = 200 * n
    t_rise = 100 * p
    t_stop = n_codes * t_step + (n_codes - 1) * t_rise

    bit_names = " ".join(f"xtop.dac_bits_{bit}" for bit in range(get_cdac_n_bits(params.cdac)))
    return hs.Sim(
        tb=CdacTb(params),
        attrs=[
            hs.Lib(path=MODEL_LIBRARY, section="tt_lib"),
            hs.Lib(path=MODEL_LIBRARY, section="pre_simu"),
            hs.Options(name="temp", value=temperature_c(params.pvt.t)),
            h.Literal("saveOptions options save=selected rawfmt=nutascii"),
            h.Literal(f"save xtop.top xtop.vvdd:p {bit_names}"),
            h.Literal(
                f"tran tran stop={float(t_stop):.12g} strobeperiod={float(100 * p):.12g} strobeoutput=strobeonly"
            ),
        ],
    )


@dataclass(frozen=True, slots=True)
class _CdacSpectreCase:
    params: CdacTbParams
    case_dir: Path
    deck_path: Path
    raw_path: Path
    log_path: Path


def _prepare_case(run_dir: Path, params: CdacTbParams) -> _CdacSpectreCase:
    """Generate one standalone CDAC Spectre input."""

    set_pdk("tsmc65")
    case_dir = run_dir / "baseline"
    case_dir.mkdir(parents=True, exist_ok=True)
    deck_path = case_dir / "input.scs"
    simulation = sim_input(params)
    h.pdk.compile(simulation.tb)
    write_spectre_input(simulation, deck_path)
    return _CdacSpectreCase(
        params=params,
        case_dir=case_dir,
        deck_path=deck_path,
        raw_path=case_dir / "result.raw",
        log_path=case_dir / "spectre.log",
    )


def _execute_case(case: _CdacSpectreCase) -> Path:
    """Run one prepared standalone CDAC case."""

    if shutil.which("spectre") is None:
        raise RuntimeError("spectre is not on PATH; source design/spice/workspace.sh")
    if case.raw_path.is_dir():
        shutil.rmtree(case.raw_path)
    elif case.raw_path.exists():
        case.raw_path.unlink()
    subprocess.run(
        [
            "spectre",
            case.deck_path.name,
            "+preset=mx",
            f"+mt={SPECTRE_THREADS_PER_SIMULATION}",
            "+lqtimeout",
            "3600",
            "+escchars",
            "-raw",
            case.raw_path.name,
            "+log",
            case.log_path.name,
        ],
        cwd=case.case_dir,
        check=True,
    )
    return case.raw_path


def _run_campaign(run_dir: Path, cases: Sequence[CdacTbParams], *, execute: bool) -> Path:
    """Prepare one CDAC run and optionally execute every case."""

    prepared = tuple(_prepare_case(run_dir, params) for params in cases)
    if not execute:
        print(f"Prepared {len(prepared)} CDAC netlist beneath {run_dir}")
        return run_dir
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SIMULATIONS) as executor:
        tuple(executor.map(_execute_case, prepared))
    print(f"Completed {len(prepared)} CDAC simulation beneath {run_dir}")
    return run_dir


def frida65_baseline_netlist() -> Path:
    """Generate one standalone fabricated-size CDAC netlist."""

    run_dir = BASE_PATH / "build/sim/cdac" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(run_dir, (CdacTbParams(),), execute=False)


def frida65_baseline_transient() -> Path:
    """Run one standalone fabricated-size CDAC code-ramp transient."""

    run_dir = BASE_PATH / "build/sim/cdac" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(run_dir, (CdacTbParams(),), execute=True)


TARGETS: dict[str, Callable[[], Path]] = {
    target.__name__: target for target in (frida65_baseline_netlist, frida65_baseline_transient)
}


def main() -> None:
    """Run one explicitly named CDAC netlist or simulation target."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(TARGETS))
    args = parser.parse_args()
    if args.target is None:
        print("Available CDAC simulation targets:")
        for target in sorted(TARGETS):
            print(f"  {target}")
        return
    run_dir = TARGETS[args.target]()
    print(f"Simulation output: {run_dir}")


if __name__ == "__main__":
    main()
