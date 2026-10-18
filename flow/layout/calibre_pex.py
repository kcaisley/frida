"""Layout-only Calibre 3D xACT extraction, shared by the PDK providers' ``run_layout_pex``.

A primitive's test structure (a capacitor's plates, a resistor's body) is plain metal with labelled
terminals: no device to recognize, no schematic to compare. Its extraction runs on the layout's own
net names, in three stages: connectivity (``-phdb``), the 3D field solver (``-3d -pdb``), and the
netlist (``-fmt``). The PDK's extraction files set up their own foundry template (the layout and
source paths, reports and databases); each run copies the files it reads with those statements
commented out, and a control file of its own sets them for this run.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

SIEMENS = Path("/eda/local/scripts/siemens_2024-25.sh")

# the statements a foundry extraction file sets for its own template run
SETUP = re.compile(
    r"^(\s*)((LAYOUT\s+(PRIMARY|PATH|SYSTEM)\b|SOURCE\s+(PRIMARY|PATH|SYSTEM)\b|LVS\s+REPORT\s+\""
    r"|PEX\s+NETLIST\s+(SIMPLE\s+)?\"|PEX\s+REPORT\s+(DISTRIBUTED|LUMPED)?\s*(none|\")|MASK\s+SVDB\s+DIRECTORY"
    r"|(DRC|ERC)\s+(RESULTS\s+DATABASE|SUMMARY\s+REPORT)).*)$",
    re.IGNORECASE | re.MULTILINE,
)


def specialize(source: Path, destination: Path, replacements: Sequence[tuple[str, str]] = ()) -> Path:
    """Copy a foundry extraction file with its template's setup statements commented out.

    ``replacements`` first swap exact text (an include of another file this run specializes).
    Foundry files may hold encrypted bodies: the copy keeps every byte.
    """

    text = source.read_bytes().decode("latin-1")
    for old, new in replacements:
        if old not in text:
            raise ValueError(f"{source.name} no longer contains {old!r}")
        text = text.replace(old, new)
    destination.write_bytes(SETUP.sub(r"\1// set by FRIDA's control file: \2", text).encode("latin-1"))
    return destination


def run_layout_pex(
    *,
    run_dir: Path,
    gds_path: Path,
    layout_top: str,
    output_stem: str,
    deck: str,
    environment: Mapping[str, str] | None = None,
    deck_sets: Sequence[str] = (),
) -> Path:
    """Extract ``layout_top`` with 3D xACT by its layout's net names and return the Spectre netlist.

    ``deck`` is the control file's tail after its own setup: the PDK's (specialized) extraction
    files, as ``source "<tvf file>"`` lines and a ``tvf::VERBATIM { INCLUDE ... }`` block.
    ``deck_sets`` names the setup statements (their leading words) an encrypted deck sets itself,
    which the control file then leaves out.
    """

    import os

    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    # an empty schematic of the layout's top: the decks read a source, nothing is compared
    source = run_dir / f"{output_stem}.empty.cdl"
    source.write_text(f".SUBCKT {layout_top}\n.ENDS {layout_top}\n")
    netlist = run_dir / f"{output_stem}.pex.netlist"
    control = run_dir / "calibre.xact"
    setup = [
        f'LAYOUT PATH "{gds_path.resolve()}"',
        "LAYOUT SYSTEM GDSII",
        f'LAYOUT PRIMARY "{layout_top}"',
        f'SOURCE PATH "{source}"',
        "SOURCE SYSTEM SPICE",
        f'SOURCE PRIMARY "{layout_top}"',
        f'PEX NETLIST "{netlist}" SPECTRE LAYOUTNAMES SINGLEFILE',
        f'MASK SVDB DIRECTORY "{run_dir / "svdb"}" QUERY XRC',
        f'LVS REPORT "{run_dir / "calibre.lvs.report"}"',
        f'DRC RESULTS DATABASE "{run_dir / "calibre.drc.results"}" ASCII',
        f'DRC SUMMARY REPORT "{run_dir / "calibre.drc.summary"}"',
        f'ERC RESULTS DATABASE "{run_dir / "calibre.erc.results"}" ASCII',
        f'ERC SUMMARY REPORT "{run_dir / "calibre.erc.summary"}"',
    ]
    kept = [line for line in setup if not line.upper().startswith(tuple(word.upper() for word in deck_sets))]
    control.write_text("#!tvf\ntvf::VERBATIM {\n" + "".join(f"{line}\n" for line in kept) + "}\n" + deck)
    # the field solver's accuracy: at its default a small coupling beside a large net (a CDAC's top
    # plate) may be split to the substrate by a few fF; 1 keeps every stage's coupling to its plate (a
    # PEX_FS_ACCURACY already set in the environment wins)
    env = {"PEX_FS_ACCURACY": "1", **os.environ, **(environment or {})}
    for stage, arguments in (
        ("phdb", "-phdb -turbo 1"),
        ("pdb", "-3d -pdb -rcc -turbo 1"),
        ("fmt", "-fmt -rcc"),
    ):
        command = (
            f"source {shlex.quote(str(SIEMENS))} >/dev/null 2>&1; calibre -xact {arguments} {shlex.quote(str(control))}"
        )
        done = subprocess.run(
            ["bash", "-lc", command], cwd=run_dir, env=env, capture_output=True, text=True, check=False
        )
        (run_dir / f"calibre.xact.{stage}.log").write_text(done.stdout + done.stderr)
        if done.returncode:
            raise RuntimeError(f"Calibre xACT {stage} failed (status {done.returncode}); see {run_dir}")
    if not netlist.is_file():
        raise RuntimeError(f"Calibre xACT wrote no netlist; see {run_dir}")
    return netlist
