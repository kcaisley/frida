"""One symmetry axis for a free (no floorplan) ALIGN design, from ALIGN's own detection.

ALIGN's symmetry search writes one SymmetricBlocks group per traced start point, and the
placer gives every group its own axis: a differential block whose trace breaks (a
cross-coupled pair of standard cells looks the same from both of its nets) ends up on two
axes, side by side. This takes ALIGN's first-pass result for the top cell (its primitive
groupings and symmetry groups, 1_topology/<name>.const.json), merges the groups into one,
and writes a design for the second pass with these as the constraints and ALIGN's own
constraint generation off. The symmetric nets are left out: ALIGN derives block symmetry
from user-given nets, and those groups would overlap the merged one.

flow/layout/align/run.py calls ``one_axis`` between its two passes.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


def one_axis(design_dir: Path, pass1_dir: Path, out_dir: Path) -> Path:
    """Write the second-pass design for ``design_dir`` into ``out_dir`` and return it."""

    name = design_dir.name
    user = json.loads((design_dir / f"{name}.const.json").read_text())
    found = json.loads((pass1_dir / "1_topology" / f"{name}.const.json").read_text())

    groups = [c for c in found if c["constraint"] == "GroupBlocks"]
    symm = [c for c in found if c["constraint"] == "SymmetricBlocks"]
    merged = [p for c in symm for p in c["pairs"]]
    const = [{"constraint": "ConfigureCompiler", "auto_constraint": False, "propagate": False}, *user, *groups]
    if merged:
        const.append({"constraint": "SymmetricBlocks", "direction": "V", "pairs": merged})

    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(design_dir / f"{name}.sp", out_dir / f"{name}.sp")
    (out_dir / f"{name}.const.json").write_text(json.dumps(const, indent=1) + "\n")
    print(f"{out_dir}: {len(symm)} symmetry groups -> 1 axis ({len(merged)} entries), {len(groups)} groups")
    return out_dir
