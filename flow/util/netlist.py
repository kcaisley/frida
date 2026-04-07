"""Netlist conversion utilities: OA → CDL → SP → SP (cleaned).

Each function takes an input path and an output path. The CLI
dispatches to these based on --from / --to flags.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


# =========================================================================
# OA → CDL  (Cadence si netlister)
# =========================================================================

_SI_ENV_TEMPLATE = """\
simLibName = "{lib}"
simCellName = "{cell}"
simViewName = "schematic"
simSimulator = "auCdl"
simNotIncremental = 't
simReNetlistAll = nil
simViewList = '("auCdl" "schematic")
simStopList = '("auCdl")
simNetlistHier = t
hnlNetlistFileName = "{cell}.cdl"
resistorModel = ""
shortRES = 0.0
preserveRES = 't
checkRESVAL = 'nil
checkRESSIZE = 't
preserveCAP = 't
checkCAPVAL = 't
checkCAPAREA = 't
preserveDIO = 't
checkDIOAREA = 't
checkDIOPERI = 't
checkCAPPERI = 't
simPrintInhConnAttributes = 'nil
checkScale = "meter"
checkLDD = 'nil
pinMAP = 'nil
preserveBangInNetlist = 'nil
shrinkFACTOR = 0.0
globalPowerSig = ""
globalGndSig = ""
displayPININFO = 'f
preserveALL = 't
setEQUIV = ""
auCdlDefNetlistProc = "ansCdlSubcktCall"
allowNetNamesBeginningWithDigits = 'nil
"""


def oa_to_cdl(lib: str, cell: str, outdir: Path, cdslib: Path | None = None) -> Path:
    """Export a Cadence OA schematic to CDL via ``si -batch``.

    Writes si.env into *outdir*, symlinks cds.lib if provided,
    runs the netlister, and returns the path to the generated CDL file.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    si_env = outdir / "si.env"
    si_env.write_text(_SI_ENV_TEMPLATE.format(lib=lib, cell=cell))

    if cdslib:
        link = outdir / "cds.lib"
        link.unlink(missing_ok=True)
        link.symlink_to(cdslib.resolve())

    result = subprocess.run(
        ["si", "-batch", "-command", "netlist"],
        cwd=str(outdir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"si netlist failed:\n{result.stderr}\n{result.stdout}")

    cdl_path = outdir / f"{cell}.cdl"
    if not cdl_path.exists():
        raise FileNotFoundError(f"Expected CDL not produced: {cdl_path}")
    return cdl_path


# =========================================================================
# CDL → SP  (syntax conversion for ngspice compatibility)
# =========================================================================

# Deep-nwell cell variants → standard library equivalents
_DNW_REPLACEMENTS = {
    "CKXOR2D4LVT_dnw": "CKXOR2D4LVT",
    "CKXOR2D2LVT_dnw": "CKXOR2D2LVT",
}


def cdl_to_sp(inpath: Path, outpath: Path) -> Path:
    """Convert a Cadence CDL netlist to ngspice-compatible SPICE.

    Transformations applied:
    - Strip ``*.BUSDELIMITER`` and ``*.PININFO`` directives
    - Replace ``/ subckt`` CDL instance separator with ``subckt``
    - Replace ``capacitor c=value`` with plain ``value``
    - Replace deep-nwell cell names with standard equivalents
    """
    text = inpath.read_text()

    lines = []
    for line in text.splitlines():
        if line.startswith("*.BUSDELIMITER") or line.startswith("*.PININFO"):
            continue
        if line.startswith("X") and " / " in line:
            line = line.replace(" / ", " ")
        line = line.replace(" capacitor c=", " ")
        lines.append(line)

    text = "\n".join(lines)

    for old, new in _DNW_REPLACEMENTS.items():
        text = text.replace(old, new)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(text)
    return outpath


# =========================================================================
# CDL → SP (cleaned)  — remove fillers/decaps, fix OpenROAD hierarchy
# =========================================================================

def clean_cdl(inpath: Path, outpath: Path, verilog: Path | None = None, module: str | None = None) -> Path:
    """Convert CDL to clean SPICE, removing synthesis artifacts.

    In addition to the ``cdl_to_sp`` transformations, this:
    - Removes FILLER and DECAP instances
    - Cleans OpenROAD hierarchical separators (``\\``, ``/``, ``.``)
    - Optionally reorders .SUBCKT ports to match a Verilog module definition

    Parameters
    ----------
    inpath : Path
        Input CDL file.
    outpath : Path
        Output SPICE file.
    verilog : Path, optional
        Verilog file to extract port order from.
    module : str, optional
        Module name (required if *verilog* is given).
    """
    text = inpath.read_text()

    # Base CDL→SP cleanup
    lines = []
    for line in text.splitlines():
        if line.startswith("*.BUSDELIMITER") or line.startswith("*.PININFO"):
            continue
        if line.startswith("X") and " / " in line:
            line = line.replace(" / ", " ")
        line = line.replace(" capacitor c=", " ")
        lines.append(line)

    # Remove filler and decap instances
    lines = [l for l in lines if not re.match(r"^XFILLER", l)]

    # Clean hierarchical separators
    processed = []
    for line in lines:
        if line.strip().startswith(".") or line.strip().startswith("*."):
            processed.append(line)
            continue
        line = line.replace("\\", "")
        line = line.replace("/", "_")
        line = line.replace(".", "_")
        # Move array indices to end of net name
        for _ in range(5):
            line = re.sub(r"(\w+)\[(\d+)\]_(\w+)", r"\1_\3[\2]", line)
        processed.append(line)

    text = "\n".join(processed)
    text = re.sub(r"__+", "_", text)

    for old, new in _DNW_REPLACEMENTS.items():
        text = text.replace(old, new)

    # Optionally reorder ports to match Verilog
    if verilog and module:
        text = _reorder_subckt_ports(text, verilog, module)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(text)
    return outpath


def _reorder_subckt_ports(cdl_text: str, verilog_path: Path, module_name: str) -> str:
    """Replace .SUBCKT port order with Verilog module port order."""
    ports, pininfo = _parse_verilog_ports(verilog_path, module_name)

    new_subckt = f".SUBCKT {module_name} " + " ".join(ports)
    new_pininfo = "*.PININFO " + " ".join(pininfo)

    pattern = rf"\.SUBCKT {module_name}\s+.*?(?=\nX)"
    cdl_text = re.sub(
        pattern,
        new_subckt + "\n" + new_pininfo + "\n",
        cdl_text,
        count=1,
        flags=re.DOTALL,
    )
    return cdl_text


def _parse_verilog_ports(verilog_path: Path, module_name: str) -> tuple[list[str], list[str]]:
    """Extract ordered port names and PININFO from a Verilog module."""
    verilog = verilog_path.read_text()

    match = re.search(rf"module\s+{module_name}\s*\((.*?)\);", verilog, re.DOTALL)
    if not match:
        raise ValueError(f"Module {module_name} not found in {verilog_path}")

    body = match.group(1)

    # Strip comments, keep ifdef USE_POWER_PINS content
    filtered = []
    in_power = False
    for line in body.splitlines():
        line = re.sub(r"//.*", "", line)
        if "`ifdef USE_POWER_PINS" in line:
            in_power = True
            continue
        if in_power and "`endif" in line:
            in_power = False
            continue
        if in_power:
            line = re.sub(r"^\s*,\s*", "", line)
        filtered.append(line)

    text = "\n".join(filtered)
    dir_map = {"input": "I", "output": "O", "inout": "B"}
    ports, pininfo = [], []

    for m in re.finditer(r"(input|output|inout)\s+wire\s*(?:\[([^\]]+)\])?\s*([^;\n]+)", text):
        direction, bus_range, names_str = m.group(1), m.group(2), m.group(3)
        pin_dir = dir_map[direction]

        for name in names_str.split(","):
            name = re.sub(r"//.*", "", name).strip()
            nm = re.match(r"([a-zA-Z_]\w*)", name)
            if not nm or nm.group(1) in ("input", "output", "inout", "wire"):
                continue
            name = nm.group(1)

            if bus_range:
                rm = re.match(r"(\d+):(\d+)", bus_range.strip())
                if rm:
                    msb, lsb = int(rm.group(1)), int(rm.group(2))
                    rng = range(msb, lsb - 1, -1) if msb > lsb else range(msb, lsb + 1)
                    for i in rng:
                        ports.append(f"{name}[{i}]")
                        pininfo.append(f"{name}[{i}]:{pin_dir}")
            else:
                ports.append(name)
                pininfo.append(f"{name}:{pin_dir}")

    return ports, pininfo
