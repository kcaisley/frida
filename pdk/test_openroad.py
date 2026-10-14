"""Each PDK's OpenROAD collateral (``pdk/<tech>/openroad``) reads in completely.

OpenROAD reads the technology LEF, every cell LEF and every Liberty corner (through the PDK's
``init.tcl`` where it has one, so the script itself is tested too), then reads and links the
design in ``v/``: one instance of every standard cell, so each cell resolves to its Liberty and
LEF views. KLayout reads every GDS; every netlist defines subcircuits.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PDK = Path(__file__).resolve().parent
TECHS = sorted(p.parent.parent.name for p in PDK.glob("*/openroad/*.lef"))

needs_openroad = pytest.mark.skipif(shutil.which("openroad") is None, reason="openroad is not on PATH")


def _views(tech: str, kind: str, pattern: str) -> list[Path]:
    return sorted((PDK / tech / "openroad" / kind).glob(pattern))


def _design(tech: str) -> tuple[Path, list[str]] | None:
    """The PDK's all-cells design and the cells it instantiates."""
    designs = _views(tech, "v", "*.v")
    assert len(designs) <= 1, designs
    if not designs:
        return None
    return designs[0], re.findall(r"^\s*(\w+)\s+u\d+\s*\(\s*\);", designs[0].read_text(), re.MULTILINE)


def _read_script(tech: str, design: Path | None) -> str:
    """Tcl that reads all of the PDK's LEF and Liberty files, links the design and reports what it got."""
    root = PDK / tech / "openroad"
    init = root / "init.tcl"
    lines = []
    if init.exists():
        lines.append(f"source {init}")
        done = {Path(f).name for f in re.findall(r"^read_(?:lef|liberty)\s+(\S+)", init.read_text(), re.MULTILINE)}
    else:
        lines += [f"read_lef {lef}" for lef in sorted(root.glob("*.lef"))]
        done = set()
    lines += [f"read_lef {lef}" for lef in _views(tech, "lef", "*.lef") if lef.name not in done]
    lines += [f"read_liberty {lib}" for lib in _views(tech, "lib", "*.lib*") if lib.name not in done]
    lines += [
        'puts "LAYERS [[ord::get_db_tech] getLayerCount]"',
        "foreach lib [[ord::get_db] getLibs] {",
        '  foreach m [$lib getMasters] { puts "MASTER [$m getName]" }',
        "}",
        "set it [sta::liberty_library_iterator]",
        "while {[$it has_next]} {",
        "  set lib [$it next]",
        '  puts "LIBERTY [$lib name] [llength [$lib find_liberty_cells_matching * 0 0]]"',
        '  foreach c [$lib find_liberty_cells_matching * 0 0] { puts "CELL [$c name]" }',
        "}",
        "$it finish",
    ]
    if design is not None:
        lines += [
            f"read_verilog {design}",
            f"link_design {design.stem}",
            'puts "INSTANCES [llength [[ord::get_db_block] getInsts]]"',
        ]
    return "\n".join(lines) + "\n"


@needs_openroad
@pytest.mark.parametrize("tech", TECHS)
def test_openroad_reads_collateral(tech, tmp_path):
    design = _design(tech)
    script = tmp_path / "read.tcl"
    script.write_text(_read_script(tech, design and design[0]))
    run = subprocess.run(
        ["openroad", "-exit", "-no_init", "-no_splash", str(script)],
        capture_output=True,
        check=False,
        text=True,
        timeout=900,
    )
    out = run.stdout + run.stderr
    assert run.returncode == 0, out[-2000:]
    errors = [line for line in out.splitlines() if line.startswith("Error") or "[ERROR" in line]
    assert not errors, errors[:10]

    assert int(re.search(r"^LAYERS (\d+)", out, re.MULTILINE).group(1)) > 0
    masters = set(re.findall(r"^MASTER (\S+)", out, re.MULTILINE))
    libs = re.findall(r"^LIBERTY (\S+) (\d+)", out, re.MULTILINE)
    assert len(libs) == len(_views(tech, "lib", "*.lib*")), libs
    assert all(int(n) > 0 for _, n in libs), libs
    if _views(tech, "lef", "*.lef"):
        assert masters
    read = set(re.findall(r"^CELL (\S+)", out, re.MULTILINE))
    missing = read - masters
    assert not missing, f"Liberty cells without a LEF macro: {sorted(missing)[:20]}"
    if read:
        assert design is not None, f"{tech}: no all-cells design in openroad/v"
        cells = design[1]
        assert set(cells) == read, f"design and Liberty cells differ: {sorted(set(cells) ^ read)[:20]}"
        assert int(re.search(r"^INSTANCES (\d+)", out, re.MULTILINE).group(1)) == len(cells)


@pytest.mark.parametrize("tech", TECHS)
def test_klayout_reads_gds(tech):
    kdb = pytest.importorskip("klayout.db")
    for gds in _views(tech, "gds", "*.gds*"):
        layout = kdb.Layout()
        layout.read(str(gds))
        assert layout.cells() > 0, gds


@pytest.mark.parametrize("tech", TECHS)
def test_netlists_define_subckts(tech):
    for sp in _views(tech, "sp", "*.sp"):
        assert re.search(r"^\.subckt\s", sp.read_text(errors="replace"), re.IGNORECASE | re.MULTILINE), sp
