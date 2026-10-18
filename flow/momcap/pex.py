"""The FMOM characterization: test structures extracted in 3D, in every PDK with Calibre extraction.

``momcap_characterization`` draws every style at one to three stacked metals, six plate lengths at
the PDK's minimum spacing and three at wider ones (``mom_unit_layout``), extracts each by its own
net names (``flow.layout.signoff.run_layout_pex``), and writes
``<pdk>/<style>_<layers>l/s<nm>/len<nm>/result.h5`` (a ``MeasMomcap``) with every terminal pair's
capacitance in its readbacks. The fits to these are what ``tech.MOM_MODEL`` holds; the extraction
is a study, not a step of a capacitor's generation.
"""

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from itertools import combinations
from multiprocessing import get_context
from pathlib import Path

import numpy as np

from flow.analysis.io import write_measurement
from flow.momcap.layout import TERMINALS, MomTestParams, MomUnit, mom_geometry, mom_unit_layout
from flow.momcap.subckt import MomStyle

# the PDKs whose kits extract with Calibre (pdk/<tech>/signoff.py ``run_layout_pex``)
PDKS = ("tsmc65", "tsmc28", "tower180", "tpsc65", "ihp130")
LENGTHS_UM = (1, 2, 4, 8, 16, 32)
# wider spacings, in multiples of the PDK's minimum (snapped to its grid), at fewer lengths
SPACINGS = (1.5, 2.0, 3.0)
SPACED_LENGTHS_UM = (2, 8, 32)
# a difference unit's two fingers share one span: the main finger's length and the difference
# finger's the rest of it, as in a unit family
DIFFERENCE_SPAN_UM = 33

_CAPACITOR = re.compile(r"^\s*\S+\s+\(\s*(\S+)\s+(\S+)\s*\)\s+capacitor\s+c=([-+0-9.eE]+)([a-zA-Z]?)", re.MULTILINE)
_SCALE = {"": 1.0, "f": 1e-15, "a": 1e-18, "p": 1e-12, "n": 1e-9}


def pair_capacitances(netlist: str, terminals: tuple[str, ...]) -> dict[tuple[str, str], float]:
    """Sum an extracted netlist's capacitors between labelled terminals (and ``GROUND``: node 0 or
    the substrate), pair by pair; a terminal's split nodes (``N_TOP_1``, ``TOP:2``) count as it."""

    names = (*terminals, "SHIELD")
    node = re.compile(r"^(?:N_)?(" + "|".join(names) + r")(?:[:#_].*)?$", re.IGNORECASE)
    totals: dict[tuple[str, str], float] = {}
    for first, second, value, unit in _CAPACITOR.findall(netlist):
        ends = []
        for name in (first, second):
            match = node.match(name)
            ends.append(match.group(1).upper() if match else "GROUND")
        if ends[0] == ends[1]:
            continue
        pair = tuple(sorted(ends))
        totals[pair] = totals.get(pair, 0.0) + float(value) * _SCALE[unit.lower()]
    return totals


def _extract(run_dir: Path, params: MomTestParams) -> dict[tuple[str, str], float]:
    from flow.layout.signoff import run_layout_pex

    run_dir.mkdir(parents=True, exist_ok=True)
    top = "momunit"
    gds = run_dir / f"{top}.gds"
    mom_unit_layout(params, top).write(str(gds))
    netlist = run_layout_pex(params.unit.technology, gds, top, top, run_dir)
    return pair_capacitances(netlist.read_text(), TERMINALS[params.unit.style])


def momcap_characterization(run_dir: Path, *, check: bool = False, pdks: tuple[str, ...] = PDKS) -> Path:
    """Extract every style at one to three metals, six lengths at the minimum spacing and three at
    each wider one, in every Calibre PDK (135 per PDK).

    ``check`` extracts one short ring per PDK instead, writing no measurement; ``pdks`` limits the
    run to some of them (into an existing run directory: the PDKs' results are side by side).
    """

    from flow.analysis.types import MeasInfo
    from flow.momcap.analysis import MeasMomcap

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in pdks:
        for style in MomStyle:
            for layers in (1, 2, 3):
                if check and (style != MomStyle.RING or layers != 2):
                    continue
                unit = MomUnit(pdk, style, layers)
                geometry = mom_geometry(unit)
                sweep = [(geometry.min_space, LENGTHS_UM[:1] if check else LENGTHS_UM)]
                if not check:
                    sweep += [
                        (-(-round(factor * geometry.min_space) // geometry.grid) * geometry.grid, SPACED_LENGTHS_UM)
                        for factor in SPACINGS
                    ]
                for space, lengths in sweep:
                    for length in lengths:
                        diff = DIFFERENCE_SPAN_UM - length if style == MomStyle.DIFFERENCE else 0
                        name = f"{pdk}/{style.name.lower()}_{layers}l/s{space}/len{length * 1000}"
                        jobs[name] = MomTestParams(unit, length * 1000, diff * 1000, space)
    failures: dict[str, str] = {}
    # eight extractions at a time: the extractor's licences are shared
    with ProcessPoolExecutor(max_workers=8, mp_context=get_context("spawn")) as executor:
        futures = {executor.submit(_extract, run_dir / name, params): (name, params) for name, params in jobs.items()}
        for future in as_completed(futures):
            name, params = futures[future]
            try:
                pairs = future.result()
                if check:
                    continue
                readbacks: dict[str, str | int | float | bool] = {
                    "pdk": params.unit.technology,
                    "style": params.unit.style.name.lower(),
                    "layers": params.unit.layers,
                    "length_um": params.length_nm / 1000,
                    "diff_length_um": params.diff_length_nm / 1000,
                    "space_nm": params.space_nm,
                    "extractor": "Calibre xACT 3D",
                }
                terminals = (*TERMINALS[params.unit.style], "SHIELD", "GROUND")
                for first, second in combinations(terminals, 2):
                    pair = tuple(sorted((first, second)))
                    readbacks[f"c_{first.lower()}_{second.lower()}_f"] = pairs.get(pair, 0.0)
                measurement = MeasMomcap(
                    group=None,
                    index=None,
                    dut=params.unit,
                    info=MeasInfo(
                        backend="spice",
                        timestamp_utc=datetime.now(tz=UTC),
                        instruments={"extractor": "Calibre xACT 3D"},
                        readbacks=readbacks,
                    ),
                    param=params,
                    trial_index=np.arange(1, dtype=np.int64),
                )
                write_measurement(run_dir / name / "result.h5", measurement)
            except Exception as error:  # noqa: BLE001 - report every independent point failure
                failures[name] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} MOM test structures failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named MOM extraction target."""

    targets = {target.__name__: target for target in (momcap_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available MOM capacitor extraction targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "pex"
        / "momcap"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
