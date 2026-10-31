"""ALIGN flow for a design in standard-cell rows: the PDK's ALIGN directory (make_pdk.py), the
design directory (make_design.py), ALIGN (run.py), then post.py for signoff.

With a floorplan, ALIGN places the rows as it says (its Floorplan constraint); without one,
ALIGN derives every constraint itself (its primitives, symmetry) and places and routes on its
own, in an outline of ALIGN's aspect ratio (2/3 to 3/2), else any where none fits (many
self-symmetric blocks). The router is the PDK's
``ALIGN_ROUTER`` (pdk/<pdk>/layout/tech.py), and ALIGN's default where that one fails (hanan
on a very small design).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from flow.layout.align.run import run_align
from flow.layout.pdkproc import access_points, in_pdk, pdk_value


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


def route_shorts(work: Path, name: str) -> dict[tuple[str, str], int]:
    """Where ALIGN's routes join two nets (its placed-and-routed ``3_pnr/<NAME>_0.json``: a wire or
    cut of one net touching another's on its own or the adjacent layer; the off-grid router lays
    one net's wire over another's now and then): the shapes touching, by the pair of nets. Empty
    where none do, or where ALIGN wrote no such file."""

    import itertools

    found = sorted(work.rglob(f"3_pnr/{name.upper()}_0.json"))
    if not found:
        return {}
    terminals = [t for t in json.loads(found[0].read_text()).get("terminals", []) if t.get("netName")]
    stack = [f"{kind}{n}" for n in range(1, 10) for kind in ("M", "V")]
    shorts: dict[tuple[str, str], int] = {}
    for a, b in itertools.combinations(terminals, 2):
        if a["netName"] == b["netName"] or a["layer"] not in stack or b["layer"] not in stack:
            continue
        if abs(stack.index(a["layer"]) - stack.index(b["layer"])) > 1:
            continue
        (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) = a["rect"], b["rect"]
        if ax0 <= bx1 and bx0 <= ax1 and ay0 <= by1 and by0 <= ay1:
            pair = tuple(sorted((a["netName"], b["netName"])))
            shorts[pair] = shorts.get(pair, 0) + 1
    return shorts


def build(
    pdk: str,
    floorplan: Path | None,
    netlist: Path,
    out_dir: Path,
    *,
    name: str | None = None,
    post: PostOptions = PLAIN,
    symmetric: bool = True,
) -> Path:
    """Lay out ``netlist`` in ``pdk`` with ALIGN, placed as ``floorplan`` says (None: by ALIGN, with
    its symmetry search unless ``symmetric`` is False); returns the GDS ``out_dir/<name>/<name>.gds``
    (``<name>``: given, else the floorplan's, else the netlist's). ALIGN's work directory,
    ``out_dir/<name>``, keeps its placement and constraints."""

    # the library cells the netlist names, its own subcircuits' names among them (none of the library's)
    access_points(pdk, sorted({line.split()[-1] for line in netlist.read_text().splitlines() if line[:1] in "Xx"}))
    name = name or (floorplan.stem if floorplan else netlist.stem)
    # ALIGN imports the PDK directory as a package named after it: the generated one is called pdk
    pdk_dir = in_pdk(pdk, "flow.layout.align.make_pdk", "build", pdk, out_dir / "pdk")
    design = in_pdk(
        pdk,
        "flow.layout.align.make_design",
        "make_design",
        pdk,
        netlist,
        out_dir / "input",
        floorplan=floorplan,
        name=name,
        symmetric=symmetric,
    )
    work = out_dir / name
    dense = {"STEMS_STD_DENSE": "1"} if floorplan else {}  # post.py as the generators drew the cells

    def attempt(router: str | None) -> Path:
        run_align(design, pdk_dir, work, router=router)
        return in_pdk(
            pdk,
            "flow.layout.align.post",
            "post",
            _align_gds(work, name),
            work / f"{name}.out.gds",
            environ=dense,
            **asdict(post),
        )

    router = pdk_value(pdk, "tech", "ALIGN_ROUTER")
    const = design / f"{name}.const.json"
    try:
        out = attempt(router or None)
    except Exception as error:
        kept = [c for c in json.loads(const.read_text()) if c["constraint"] != "AspectRatio"]
        if floorplan is None and len(kept) < len(json.loads(const.read_text())):
            print(f"{name}: no placement in ALIGN's square outline ({str(error)[:80]}...); any outline")
            const.write_text(json.dumps(kept, indent=1) + "\n")
            try:
                out = attempt(router or None)
            except Exception as again:
                if not router:
                    raise
                print(
                    f"{name}: ALIGN with --router {router} failed ({str(again)[:80]}...); again with ALIGN's default router"
                )
                out = attempt(None)
        elif router:
            print(f"{name}: ALIGN with --router {router} failed ({error}); again with ALIGN's default router")
            out = attempt(None)
        else:
            raise
    gds = out.rename(work / f"{name}.gds")
    Path(f"{out}.extra.sp").rename(f"{gds}.extra.sp")  # the devices post.py added, for the LVS source
    print(f"wrote {gds}")
    return gds
