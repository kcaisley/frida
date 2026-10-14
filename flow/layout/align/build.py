"""ALIGN flow for a design in standard-cell rows: the PDK's ALIGN directory (make_pdk.py), the
design directory (make_design.py), ALIGN (run.py), then post.py for signoff.

With a floorplan, ALIGN places the rows as it says (its Floorplan constraint); without one,
ALIGN places freely, its symmetry groups merged onto one axis. The router is the PDK's
``ALIGN_ROUTER`` (pdk/<pdk>/layout/tech.py), and ALIGN's default where that one fails (hanan
on a very small design).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from flow.layout.align.run import run_align
from flow.layout.pdkproc import access_points, in_pdk, pdk_value


@dataclass(frozen=True)
class PostOptions:
    """post.py's additions (a PDK with logic cells and a guard ring): decap cells in the row
    gaps (``fill="decap"``), a guard ring with its N-well on ``ring_net`` and the substrate ring
    on ``sub_net``."""

    fill: str = "plain"
    ring: bool = False
    ring_net: str = "vdd"
    sub_net: str = "vsub"


PLAIN = PostOptions()  # the comparator layouts: plain fill, no ring


def _align_gds(work: Path, name: str) -> Path:
    """The GDS ALIGN wrote in ``work``."""

    found = sorted(p for p in work.glob("*.gds") if not p.name.endswith(".out.gds"))
    found = found or [p for p in work.rglob("*.gds") if p.name in (f"{name.upper()}_0.gds", f"{name}_0.gds")]
    if not found:
        raise FileNotFoundError(f"ALIGN wrote no GDS for {name} in {work}")
    return found[0]


def build(pdk: str, floorplan: Path | None, netlist: Path, out_dir: Path, *, post: PostOptions = PLAIN) -> Path:
    """Lay out ``netlist`` in ``pdk`` with ALIGN, placed as ``floorplan`` says (None: free);
    returns the GDS ``out_dir/<name>/<name>.gds`` (``<name>``: the floorplan's, else the netlist's)."""

    access_points(pdk)
    name = floorplan.stem if floorplan else netlist.stem
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
    )
    work = out_dir / name
    dense = {"STEMS_STD_DENSE": "1"} if floorplan else {}  # post.py as the generators drew the cells

    def attempt(router: str | None) -> Path:
        run_align(design, pdk_dir, work, router=router, one_axis=floorplan is None)
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
    try:
        out = attempt(router or None)
    except Exception as error:
        if not router:
            raise
        print(f"{name}: ALIGN with --router {router} failed ({error}); again with ALIGN's default router")
        out = attempt(None)
    gds = out.rename(work / f"{name}.gds")
    Path(f"{out}.extra.sp").rename(f"{gds}.extra.sp")  # the devices post.py added, for the LVS source
    print(f"wrote {gds}")
    return gds
