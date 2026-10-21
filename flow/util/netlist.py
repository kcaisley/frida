"""Netlist conversion utilities: OA → CDL → SP → SP (cleaned).

Each function takes explicit input and output paths: ``oa_to_cdl``, ``cdl_to_sp`` and
``clean_cdl`` are the conversions.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _subcircuit_span(text: str, name: str) -> tuple[int, int]:
    start = re.search(rf"(?im)^[ \t]*\.subckt[ \t]+{re.escape(name)}(?:[ \t]|$)", text)
    if start is None:
        raise ValueError(f"source netlist has no .subckt {name}")
    end = re.search(r"(?im)^[ \t]*\.ends(?:[ \t]+[^\n]*)?$", text[start.end() :])
    if end is None:
        raise ValueError(f"source netlist has no .ends for {name}")
    return start.start(), start.end() + end.end()


def _spice_statements(text: str) -> list[str]:
    statements: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("+") and statements:
            statements[-1] = statements[-1].rstrip("\r\n") + " " + line.lstrip()[1:]
        else:
            statements.append(line)
    return statements


def subcircuit_ports(text: str, name: str) -> tuple[str, ...]:
    """Read SPICE/CDL or Spectre pins in exact positional order, without renaming."""
    spectre = re.search(rf"(?im)^[ \t]*subckt[ \t]+{re.escape(name)}\s*\(([^)]*)\)", text.replace("\\\n", " "))
    if spectre is not None:
        tokens = spectre[1].replace("\\", "").split()
    else:
        start, end = _subcircuit_span(text, name)
        tokens = _spice_statements(text[start:end])[0].split()[2:]
    ports: list[str] = []
    for token in tokens:
        if token.lower() == "params:" or "=" in token:
            break
        ports.append(token)
    if len({port.casefold() for port in ports}) != len(ports):
        raise ValueError(f"duplicate ports in {name}")
    return tuple(ports)


def normalize_bus_pin(name: str) -> str:
    """HDL21's scalar name for a case-insensitive external bus pin."""
    return re.sub(r"[<\[](\d+)[>\]]", r"_\1", name.replace("\\", "").lower())


def replace_subcircuit(
    source: str,
    *,
    old_top: str,
    new_top: str,
    old_block: str,
    new_block: str,
    pin_map: dict[str, str] | None = None,
) -> str:
    """Replace a netlisted block and reconnect every call by pin name.

    ``pin_map`` maps replacement formal names to old formal names at an explicit
    legacy boundary. Never reuse the old positional argument list blindly.
    """
    start, end = _subcircuit_span(source, old_block)
    names = re.findall(r"(?im)^[ \t]*\.subckt[ \t]+(\S+)", new_block)
    if not names:
        raise ValueError("replacement source has no .subckt")
    new_name = names[-1]  # HDL21 emits dependencies before the top module.
    old_ports = subcircuit_ports(source, old_block)
    new_ports = subcircuit_ports(new_block, new_name)
    if pin_map is None:
        pin_map = dict(zip(new_ports, new_ports))
    mapping = {key.casefold(): value.casefold() for key, value in pin_map.items()}
    if (
        len(mapping) != len(pin_map)
        or set(mapping) != {name.casefold() for name in new_ports}
        or set(mapping.values()) != {name.casefold() for name in old_ports}
        or len(mapping) != len(old_ports)
    ):
        raise ValueError("replacement pin mapping must be a complete one-to-one interface match")
    result: list[str] = []
    for statement in _spice_statements(source[:start] + source[end:]):
        tokens = statement.split()
        if tokens and tokens[0].lower().startswith("x"):
            positions = [index for index, token in enumerate(tokens[1:], 1) if token.casefold() == old_block.casefold()]
            if positions:
                index = positions[-1]
                arguments = tokens[1:index]
                if arguments and arguments[-1] == "/":
                    arguments.pop()
                if len(arguments) != len(old_ports):
                    raise ValueError(f"{tokens[0]} has {len(arguments)} connections, expected {len(old_ports)}")
                actual = dict(zip((port.casefold() for port in old_ports), arguments, strict=True))
                statement = (
                    " ".join(
                        (
                            tokens[0],
                            *(actual[mapping[port.casefold()]] for port in new_ports),
                            new_name,
                            *tokens[index + 1 :],
                        )
                    )
                    + "\n"
                )
        result.append(statement)
    text = new_block.rstrip() + "\n" + "".join(result)
    return (
        re.sub(
            rf"(?im)(^[ \t]*\.(?:subckt|ends)[ \t]+){re.escape(old_top)}(?=[ \t\r\n]|$)",
            rf"\g<1>{new_top}",
            text,
        ).rstrip()
        + "\n"
    )


def omit_subcircuit(source: str, name: str) -> str:
    """Remove a subcircuit and its calls, including continued CDL calls."""
    start, end = _subcircuit_span(source, name)
    kept: list[str] = []
    for statement in _spice_statements(source[:start] + source[end:]):
        tokens = statement.split()
        if tokens and tokens[0].lower().startswith("x") and tokens[-1].casefold() == name.casefold():
            continue
        kept.append(statement)
    return "".join(kept).rstrip() + "\n"


# OA → CDL  (Cadence si netlister)

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
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"si netlist failed:\n{result.stderr}\n{result.stdout}")

    cdl_path = outdir / f"{cell}.cdl"
    if not cdl_path.exists():
        raise FileNotFoundError(f"Expected CDL not produced: {cdl_path}")
    return cdl_path


# CDL → SP  (syntax conversion for ngspice compatibility)

# Deep-nwell cell variants (a library cell's name + "_dnw", instantiated: the line's last token)
# -> the standard library cell
_DNW_VARIANT = re.compile(r"(\S+)_dnw[ \t]*$", re.MULTILINE)


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
        if line.startswith(("*.BUSDELIMITER", "*.PININFO")):
            continue
        if line.startswith("X") and " / " in line:
            line = line.replace(" / ", " ")
        line = line.replace(" capacitor c=", " ")
        lines.append(line)

    text = "\n".join(lines)

    text = _DNW_VARIANT.sub(r"\1", text)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(text)
    return outpath


# CDL → SP (cleaned)  — remove fillers/decaps, fix OpenROAD hierarchy


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
    if bool(verilog) != bool(module):
        raise ValueError("verilog and module must be given together")
    text = inpath.read_text()

    # Base CDL→SP cleanup
    lines = []
    for line in text.splitlines():
        if line.startswith(("*.BUSDELIMITER", "*.PININFO")):
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

    text = _DNW_VARIANT.sub(r"\1", text)

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
    """Extract ordered port names and PININFO from a Verilog module; bus ranges in its parameters
    (``[N_STAGES-1:0]``) take their defaults."""
    verilog = re.sub(r"//.*", "", verilog_path.read_text())

    header = re.search(rf"module\s+{module_name}\b\s*", verilog)
    if not header:
        raise ValueError(f"Module {module_name} not found in {verilog_path}")
    position, parameters = header.end(), {}
    if verilog.startswith("#", position):
        # the parameter block, to its balanced closing parenthesis
        start = verilog.index("(", position)
        depth, end = 0, start
        for end, char in enumerate(verilog[start:], start):
            depth += {"(": 1, ")": -1}.get(char, 0)
            if depth == 0:
                break
        for name, value in re.findall(r"parameter\s+(?:integer\s+)?(\w+)\s*=\s*([^,)]+)", verilog[start : end + 1]):
            parameters[name] = value.strip()
        position = end + 1
    match = re.compile(r"\s*\((.*?)\);", re.DOTALL).match(verilog, position)
    if not match:
        raise ValueError(f"Module {module_name} has no port list in {verilog_path}")

    body = match.group(1)

    # Keep the USE_POWER_PINS branch (the power pins), drop its `else
    filtered = []
    branch = None
    for line in body.splitlines():
        if "`ifdef USE_POWER_PINS" in line:
            branch = "power"
        elif branch and "`else" in line:
            branch = "else"
        elif branch and "`endif" in line:
            branch = None
        elif branch != "else":
            filtered.append(line)

    dir_map = {"input": "I", "output": "O", "inout": "B"}
    ports, pininfo = [], []
    # ANSI style: a bare name takes the direction and range of the declaration before it; a
    # direction starts a declaration even where its comma is missing (salogic's power pins)
    pin_dir, bus_range = None, None
    for item in re.split(r",|(?=\b(?:input|output|inout)\b)", "\n".join(filtered)):
        declaration = re.fullmatch(
            r"\s*(?:(input|output|inout)\s+(?:wire\s+)?(?:\[([^\]]+)\]\s*)?)?([A-Za-z_]\w*)\s*", item
        )
        if not declaration:
            if item.strip():
                raise ValueError(f"unsupported port declaration {item.strip()!r} in {verilog_path}")
            continue
        if declaration[1]:
            pin_dir, bus_range = dir_map[declaration[1]], declaration[2]
        name = declaration[3]
        if bus_range:
            # each bound an integer expression of the parameters' defaults
            bounds = [
                re.sub(r"[A-Za-z_]\w*", lambda word: parameters[word[0]], bound) for bound in bus_range.split(":")
            ]
            if len(bounds) != 2 or not all(re.fullmatch(r"[\d\s+\-*/()]+", bound) for bound in bounds):
                raise ValueError(f"unsupported bus range [{bus_range}] of {name} in {verilog_path}")
            msb, lsb = (int(eval(bound, {"__builtins__": {}})) for bound in bounds)  # digits and operators alone
            for i in range(msb, lsb - 1, -1) if msb > lsb else range(msb, lsb + 1):
                ports.append(f"{name}[{i}]")
                pininfo.append(f"{name}[{i}]:{pin_dir}")
        else:
            ports.append(name)
            pininfo.append(f"{name}:{pin_dir}")

    return ports, pininfo
