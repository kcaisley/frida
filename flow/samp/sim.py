"""Sampler testbench and named TSMC65 Spectre simulation targets."""

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
from hdl21.primitives import C, Vdc, Vpulse

from ..circuit.netlist import write_spectre_input
from ..circuit.params import PvtParams, supply_voltage, temperature_c
from ..pdks import set_pdk
from .subckt import Samp, SampParams

BASE_PATH = Path(__file__).resolve().parents[2]
MAX_PARALLEL_SIMULATIONS = 1
SPECTRE_THREADS_PER_SIMULATION = 4
MODEL_LIBRARY = Path("/eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/models/spectre/toplevel.scs")


@h.paramclass
class SampTbParams:
    """Sampler testbench parameters."""

    pvt = h.Param(dtype=PvtParams, desc="PVT conditions", default=PvtParams())
    samp = h.Param(dtype=SampParams, desc="Sampler parameters", default=SampParams())
    cload = h.Param(dtype=h.Prefixed, desc="Load capacitance", default=1 * f)


@h.generator
def SampTb(params: SampTbParams) -> h.Module:
    """
    Sampler testbench generator.

    Creates a testbench with:
    - DC supply voltage
    - Complementary clock pulses
    - DC input voltage
    - Load capacitor
    - DUT sampler instance
    """
    vdd = supply_voltage(params.pvt.v)

    @h.module
    class SampTb:
        """Sampler testbench module."""

        vss = h.Port(desc="Ground")

        # Supply
        vdd = h.Signal()

        # Clocks - complementary pulses
        clk = h.Signal()
        clk_b = h.Signal()

        # Input - mid-supply DC voltage
        din = h.Signal()

        # Output with load capacitor
        dout = h.Signal()

    SampTb.vvdd = Vdc(dc=vdd)(p=SampTb.vdd, n=SampTb.vss)

    SampTb.vclk = Vpulse(
        v1=0 * m,
        v2=vdd,
        period=100 * n,
        width=50 * n,
        rise=100 * p,
        fall=100 * p,
        delay=0 * n,
    )(p=SampTb.clk, n=SampTb.vss)
    SampTb.vclk_b = Vpulse(
        v1=vdd,
        v2=0 * m,
        period=100 * n,
        width=50 * n,
        rise=100 * p,
        fall=100 * p,
        delay=0 * n,
    )(p=SampTb.clk_b, n=SampTb.vss)

    SampTb.vdin = Vdc(dc=vdd / 2)(p=SampTb.din, n=SampTb.vss)
    SampTb.cload = C(c=params.cload)(p=SampTb.dout, n=SampTb.vss)

    SampTb.dut = Samp(params.samp)(
        din=SampTb.din,
        dout=SampTb.dout,
        clk=SampTb.clk,
        clk_b=SampTb.clk_b,
        vdd=SampTb.vdd,
        vss=SampTb.vss,
    )

    return SampTb


def sim_input(params: SampTbParams) -> hs.Sim:
    """Create one selected-signal TSMC65 sampler transient input."""

    return hs.Sim(
        tb=SampTb(params),
        attrs=[
            hs.Lib(path=MODEL_LIBRARY, section="tt_lib"),
            hs.Lib(path=MODEL_LIBRARY, section="pre_simu"),
            hs.Options(name="temp", value=temperature_c(params.pvt.t)),
            h.Literal("saveOptions options save=selected rawfmt=nutascii"),
            h.Literal("save xtop.din xtop.dout xtop.clk xtop.clk_b xtop.vvdd:p"),
            h.Literal("tran tran stop=500n strobeperiod=100p strobeoutput=strobeonly"),
        ],
    )


@dataclass(frozen=True, slots=True)
class _SampSpectreCase:
    params: SampTbParams
    case_dir: Path
    deck_path: Path
    raw_path: Path
    log_path: Path


def _prepare_case(run_dir: Path, params: SampTbParams) -> _SampSpectreCase:
    """Generate one standalone sampler Spectre input."""

    set_pdk("tsmc65")
    case_dir = run_dir / "baseline"
    case_dir.mkdir(parents=True, exist_ok=True)
    deck_path = case_dir / "input.scs"
    simulation = sim_input(params)
    h.pdk.compile(simulation.tb)
    write_spectre_input(simulation, deck_path)
    return _SampSpectreCase(
        params=params,
        case_dir=case_dir,
        deck_path=deck_path,
        raw_path=case_dir / "result.raw",
        log_path=case_dir / "spectre.log",
    )


def _execute_case(case: _SampSpectreCase) -> Path:
    """Run one prepared standalone sampler case."""

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


def _run_campaign(run_dir: Path, cases: Sequence[SampTbParams], *, execute: bool) -> Path:
    """Prepare one sampler run and optionally execute every case."""

    prepared = tuple(_prepare_case(run_dir, params) for params in cases)
    if not execute:
        print(f"Prepared {len(prepared)} sampler netlist beneath {run_dir}")
        return run_dir
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SIMULATIONS) as executor:
        tuple(executor.map(_execute_case, prepared))
    print(f"Completed {len(prepared)} sampler simulation beneath {run_dir}")
    return run_dir


def frida65_baseline_netlist() -> Path:
    """Generate one standalone fabricated-size sampler netlist."""

    # TODO: Change every target in this module to build/sim_samp/<short-datetime>.
    run_dir = BASE_PATH / "build/sim/samp" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(run_dir, (SampTbParams(),), execute=False)


def frida65_baseline_transient() -> Path:
    """Run one standalone fabricated-size sampler transient."""

    run_dir = BASE_PATH / "build/sim/samp" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    return _run_campaign(run_dir, (SampTbParams(),), execute=True)


TARGETS: dict[str, Callable[[], Path]] = {
    target.__name__: target for target in (frida65_baseline_netlist, frida65_baseline_transient)
}


def main() -> None:
    """Run one explicitly named sampler netlist or simulation target."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(TARGETS))
    args = parser.parse_args()
    if args.target is None:
        print("Available sampler simulation targets:")
        for target in sorted(TARGETS):
            print(f"  {target}")
        return
    run_dir = TARGETS[args.target]()
    print(f"Simulation output: {run_dir}")


if __name__ == "__main__":
    main()
