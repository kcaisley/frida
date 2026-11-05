"""ALIGN flow for a design in standard-cell rows: the PDK's ALIGN directory (make_pdk.py), the
design directory, ALIGN (run.py), then post.py for signoff.

``build_design`` lays out a design directory a block's module gives (``flow.circuit.netlists.
align_design``: placed as its generator states, ALIGN deriving only the rest); ``build`` a netlist
from elsewhere (make_design.py), which ALIGN places on its own, in an outline of ALIGN's aspect
ratio (2/3 to 3/2), else any where none fits (many self-symmetric blocks). The router is the
PDK's ``ALIGN_ROUTER`` (pdk/<pdk>/layout/tech.py), and ALIGN's default where that one fails
(hanan on a very small design).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from flow.layout.package import pdk_dir as align_pdk_dir
from flow.layout.pdkproc import access_points, in_pdk, pdk_value
from flow.layout.run import run_align

LOG = logging.getLogger("flow.layout.build")


@dataclass(frozen=True)
class PostOptions:
    """post.py's addition (a PDK with a guard ring): a guard ring with its N-well on ``ring_net``
    and the substrate ring on ``sub_net``."""

    ring: bool = False
    ring_net: str = "vdd"
    sub_net: str = "vsub"


PLAIN = PostOptions()  # the comparator layouts: no ring


def _align_gds(work: Path, name: str) -> Path:
    """The GDS ALIGN wrote in ``work``."""

    found = sorted(p for p in work.glob("*.gds") if not p.name.endswith(".out.gds"))
    found = found or [p for p in work.rglob("*.gds") if p.name in (f"{name.upper()}_0.gds", f"{name}_0.gds")]
    if not found:
        raise FileNotFoundError(f"ALIGN wrote no GDS for {name} in {work}")
    return found[0]


def _mom_units(work: Path) -> dict[str, int]:
    """The MOM units ALIGN generated (its ``2_primitives/__primitives__.json``): each primitive's cell
    name to the metals its plates use, for ``post``'s shield ties."""
    record = work / "2_primitives" / "__primitives__.json"
    if not record.exists():
        return {}
    return {
        name.upper(): int(entry["parameters"]["values"]["layers"])
        for name, entry in json.loads(record.read_text()).items()
        if entry.get("parameters", {}).get("real_inst_type") == "MomUnit"
    }


def route_shorts(work: Path, name: str) -> dict[tuple[str, str], int]:
    """Where ALIGN's routes join two nets (its placed-and-routed ``3_pnr/<NAME>_0.json``: a wire or
    cut of one net touching another's on its own or the adjacent layer; the off-grid router lays
    one net's wire over another's now and then): the shapes touching, by the pair of nets. Empty
    where none do, or where ALIGN wrote no such file."""

    found = sorted(work.rglob(f"3_pnr/{name.upper()}_0.json"))
    if not found:
        return {}
    stack = [f"{kind}{n}" for n in range(1, 10) for kind in ("M", "V")]
    levels: dict[int, list[tuple[int, int, int, int, str]]] = {}
    for t in json.loads(found[0].read_text()).get("terminals", []):
        if t.get("netName") and t["layer"] in stack:
            x0, y0, x1, y1 = t["rect"]
            levels.setdefault(stack.index(t["layer"]), []).append((x0, y0, x1, y1, t["netName"]))
    shorts: dict[tuple[str, str], int] = {}

    def sweep(shapes: list[tuple[int, int, int, int, str, int]], across: bool) -> None:
        """Each pair of ``shapes`` that touch (and, ``across``, lie on two layers: the last field),
        found by a sweep along x: a shape against those begun before it and not yet ended."""
        active: list[tuple[int, int, int, int, str, int]] = []
        for shape in sorted(shapes, key=lambda s: s[0]):
            x0, y0, _, y1, net, level = shape
            active = [a for a in active if a[2] >= x0]
            for a in active:
                if a[4] != net and (not across or a[5] != level) and a[1] <= y1 and y0 <= a[3]:
                    pair = (min(a[4], net), max(a[4], net))
                    shorts[pair] = shorts.get(pair, 0) + 1
            active.append(shape)

    for level, shapes in levels.items():  # on one layer, and on it and the next
        sweep([(*s, level) for s in shapes], across=False)
        if level + 1 in levels:
            sweep([(*s, level) for s in shapes] + [(*s, level + 1) for s in levels[level + 1]], across=True)
    return shorts


def annealed(work: Path) -> bool:
    """Whether ALIGN's placer searched by annealing anywhere in the runs under ``work`` (their
    ``LOG/align.log``): a module whose placement leaves one sequence pair is enumerated instead, and
    another seed places it the same."""
    return any("perturbations" in line for log in work.rglob("LOG/align.log") for line in log.open(errors="replace"))


def _timed(work: Path, timing: dict[str, Any], attempt: Any, router: str | None) -> Path:
    """One attempt, its seconds written to ``work/build.json`` whether it succeeds or not."""
    try:
        return attempt(router)
    finally:
        if work.is_dir():
            (work / "build.json").write_text(json.dumps(timing, indent=1) + "\n")


def build(
    pdk: str,
    netlist: Path,
    out_dir: Path,
    *,
    name: str | None = None,
    post: PostOptions = PLAIN,
    symmetric: bool = True,
    seed: int = 0,
) -> Path:
    """Lay out the netlist from elsewhere ``netlist`` in ``pdk`` with ALIGN on its own, with its
    symmetry search unless ``symmetric`` is False; returns the GDS ``out_dir/<name>/<name>.gds``
    (``<name>``: given, else the netlist's). ALIGN's work directory, ``out_dir/<name>``, keeps its
    placement and constraints. ``seed``: the placer's random seed."""

    # the library cells the design (the netlist's last subcircuit) instantiates: not its own
    # subcircuits, nor the generator elements within them, which no library holds (named, they
    # would have the access points remade on every build)
    text = netlist.read_text().splitlines()
    starts = [k for k, line in enumerate(text) if line.split()[:1] and line.split()[0].lower() == ".subckt"]
    design = text[starts[-1] :] if starts else text
    own = {text[k].split()[1] for k in starts}
    started = time.monotonic()
    access_points(pdk, sorted({line.split()[-1] for line in design if line[:1] in "Xx"} - own))
    name = name or netlist.stem
    design = in_pdk(
        pdk, "flow.layout.make_design", "make_design", pdk, netlist, out_dir / "input", name=name, symmetric=symmetric
    )
    LOG.info(f"ALIGN's input: {design} (the netlist, its constraints)")
    return run(pdk, design, out_dir, name=name, placed=False, post=post, seed=seed, started=started)


def build_design(
    pdk: str,
    design: Path,
    cells: list[str],
    out_dir: Path,
    *,
    placed: bool,
    post: PostOptions = PLAIN,
    seed: int = 0,
    router: str | None = None,
) -> Path:
    """Lay out ALIGN's design directory ``design`` (``flow.circuit.netlists.align_design``: the
    netlist from hdl21 and vlsir, a constraint file a module), the library ``cells`` it calls;
    ``placed`` where its top states its layout; ``router``: ALIGN's (``run``). Returns the GDS, as
    ``build``."""
    started = time.monotonic()
    access_points(pdk, cells)
    return run(
        pdk, design, out_dir, name=design.name, placed=placed, post=post, seed=seed, started=started, router=router
    )


def pdk_router(pdk: str) -> str:
    """ALIGN's router a PDK routes with (``ALIGN_ROUTER``, else ALIGN's default ``astar``)."""
    return pdk_value(pdk, "tech", "ALIGN_ROUTER") or "astar"


def other_router(router: str) -> str:
    """ALIGN's other router: ``hanan`` for ``astar`` and the other way round."""
    return "astar" if router == "hanan" else "hanan"


def run(
    pdk: str,
    design: Path,
    out_dir: Path,
    *,
    name: str,
    placed: bool,
    post: PostOptions = PLAIN,
    seed: int = 0,
    started: float | None = None,
    router: str | None = None,
) -> Path:
    """ALIGN on ``design`` (its input directory) and the post step, again without the outline's
    AspectRatio where ALIGN placed it on its own and failed, and again with ALIGN's default router
    where the PDK's own failed; the GDS ``out_dir/<name>/<name>.gds``. ``router``: ALIGN's router
    (``astar``, ``hanan``), else the PDK's (``ALIGN_ROUTER``)."""
    pdk_dir = align_pdk_dir(pdk)  # ALIGN imports the PDK directory as a package named after it
    work = out_dir / name
    dense = {"ROWS_STD_DENSE": "1"} if placed else {}  # post.py as the generators drew the cells
    # the build's seconds (work/build.json): ALIGN's input, and each attempt's ALIGN and post step
    started = time.monotonic() if started is None else started
    timing: dict[str, Any] = {"input": round(time.monotonic() - started, 1), "attempts": []}

    def attempt(router: str | None) -> Path:
        LOG.info(f"ALIGN: topology, primitives, placement and routing in {work} (its log LOG/align.log)")
        begun = time.monotonic()
        entry: dict[str, Any] = {"router": router}
        timing["attempts"].append(entry)
        run_align(design, pdk_dir, work, router=router, seed=seed)
        entry["align"] = round(time.monotonic() - begun, 1)
        begun = time.monotonic()
        out = in_pdk(
            pdk,
            "flow.layout.post",
            "post",
            _align_gds(work, name),
            work / f"{name}.out.gds",
            environ=dense,
            mom_units=_mom_units(work),
            **asdict(post),
        )
        entry["post"] = round(time.monotonic() - begun, 1)
        done = Path(f"{out}.post.json")
        if done.exists():
            LOG.info("post: " + ", ".join(f"{n} {what}" for what, n in json.loads(done.read_text()).items()))
        return out

    router = router or pdk_value(pdk, "tech", "ALIGN_ROUTER")
    router = None if router == "astar" else router  # ALIGN's default: no --router
    const = design / f"{name}.const.json"
    try:
        out = _timed(work, timing, attempt, router or None)
    except Exception as error:
        kept = [c for c in json.loads(const.read_text()) if c["constraint"] != "AspectRatio"]
        if not placed and len(kept) < len(json.loads(const.read_text())):
            LOG.warning(f"{name}: no placement in ALIGN's square outline ({str(error)[:80]}...); any outline")
            const.write_text(json.dumps(kept, indent=1) + "\n")
            try:
                out = _timed(work, timing, attempt, router or None)
            except Exception as again:
                if not router:
                    raise
                LOG.warning(
                    f"{name}: ALIGN with --router {router} failed ({str(again)[:80]}...); again with ALIGN's default router"
                )
                out = _timed(work, timing, attempt, None)
        elif router:
            LOG.warning(f"{name}: ALIGN with --router {router} failed ({error}); again with ALIGN's default router")
            out = _timed(work, timing, attempt, None)
        else:
            raise
    gds = out.rename(work / f"{name}.gds")
    Path(f"{out}.extra.sp").rename(f"{gds}.extra.sp")  # the devices post.py added, for the LVS source
    if Path(f"{out}.post.json").exists():
        Path(f"{out}.post.json").rename(f"{gds}.post.json")  # what post.py did
    return gds


def _shown(path: Path) -> str:
    """A path from the repository's root where it is inside."""
    root = Path(__file__).resolve().parents[2]
    path = Path(path).resolve()
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
