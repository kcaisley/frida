"""FRIDA's checks: one entry for a developer's checkout, a local CI runner and GitHub's.

    uv run --no-project --python 3.12 python tools/check.py all          # every check
    uv run --no-project --python 3.12 python tools/check.py ruff --fix   # one check, fixing
    uv run --no-project --python 3.12 python tools/check.py ruff FILE... # a per-file check, its files
    uv run --no-project --python 3.12 python tools/check.py --staged     # the git hook
    uv run --no-project --python 3.12 python tools/check.py install      # the pinned native tools
    uv run --no-project --python 3.12 python tools/check.py install-hook # .git/hooks/pre-commit
    uv run --no-project --python 3.12 python tools/check.py editor       # LSP configs (gitignored)

Settings live in pyproject.toml: the checks' versions, files and arguments (``[tool.check]``,
``[tool.hdl]``, ``[tool.<check>]``) and the native tools' pins (``[tool.<tool>.install]``).
Python tools run through uv; the native ones (Verible, OSS CAD Suite, tex-fmt) are pinned
prebuilt Linux x86_64 releases, checksum-verified and unpacked into ``FRIDA_TOOLS`` (default
``build/tools``; a persistent directory on a self-hosted runner), each version in its own
directory, installed on first use. ``FRIDA_TOOLS=path`` uses the tools already on PATH instead.
Needs bash, git, curl, tar and uv; no system packages.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
CHECK = PROJECT["tool"]["check"]
HDL = PROJECT["tool"]["hdl"]
NATIVE = ("verible", "oss-cad-suite", "tex-fmt")
TOOLS = os.environ.get("FRIDA_TOOLS", str(ROOT / "build" / "tools"))


# ------------------------------------------------------------------------- native tools


def pin(tool: str) -> dict:
    return PROJECT["tool"][tool]["install"]


def cache_key() -> str:
    """A key naming every pinned native tool's version (a CI cache's)."""

    return "frida-tools-" + "-".join(f"{tool}-{pin(tool)['version']}" for tool in NATIVE)


def tool_dir(tool: str) -> Path:
    return Path(TOOLS).resolve() / f"{tool}-{pin(tool)['version']}"


def install(tool: str) -> Path:
    """The tool's directory, downloaded, verified and unpacked where it is not yet."""

    target = tool_dir(tool)
    if (target / ".installed").is_file():
        return target
    spec = pin(tool)
    url = spec["url"].format(version=spec["version"], date=spec["version"].replace("-", ""))
    target.parent.mkdir(parents=True, exist_ok=True)
    archive = target.with_name(target.name + ".tar.gz")
    print(f"Installing {tool} {spec['version']} into {target}", flush=True)
    subprocess.run(
        ["curl", "--fail", "--location", "--retry", "3", "--silent", "--show-error", url, "-o", archive], check=True
    )
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != spec["sha256"]:
        archive.unlink()
        raise SystemExit(f"{tool}: checksum {digest.hexdigest()} is not the pinned {spec['sha256']}")
    partial = target.with_name(target.name + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir()
    strip = str(spec.get("strip", 1))
    subprocess.run(["tar", "-xzf", archive, "-C", partial, f"--strip-components={strip}"], check=True)
    archive.unlink()
    if tool == "oss-cad-suite":
        _patch_vvp(partial / "bin" / "vvp")
    (partial / ".installed").write_text(spec["version"] + "\n")
    shutil.rmtree(target, ignore_errors=True)
    partial.rename(target)
    return target


def _patch_vvp(wrapper: Path) -> None:
    """Let Cocotb run vvp under the project's Python and the host's shared libraries."""

    text = wrapper.read_text()
    text = "\n".join(
        line for line in text.split("\n") if not line.startswith(("export PYTHONEXECUTABLE=", "export PYTHONHOME="))
    )
    system = "/lib64:/usr/lib64:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu"
    text = text.replace(
        '--library-path "$release_topdir_abs"/lib ', f'--library-path "$release_topdir_abs/lib:{system}" '
    )
    wrapper.write_text(text)


def tool_path(*tools: str) -> dict[str, str]:
    """An environment with the tools' binaries first on PATH (installing them where needed)."""

    env = dict(os.environ)
    if TOOLS == "path":
        return env
    bins = []
    for tool in tools:
        root = install(tool)
        bins.append(str(root if tool == "tex-fmt" else root / "bin"))
    env["PATH"] = os.pathsep.join([*bins, env.get("PATH", "")])
    return env


# ------------------------------------------------------------------------------- files


def tracked(pattern: str | None = None, suffixes: tuple[str, ...] = ()) -> list[str]:
    """Tracked files (submodules' contents excluded) matching a regex or suffixes."""

    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    out = []
    for name in names:
        if not name or not (ROOT / name).is_file():
            continue
        if pattern and not re.search(pattern, name):
            continue
        if suffixes and not name.endswith(suffixes):
            continue
        out.append(name)
    return sorted(out)


def hdl_files() -> list[str]:
    files = tracked(suffixes=tuple(HDL["source-suffixes"]))
    return [f for f in files if not any(f.startswith(prefix) for prefix in HDL["exclude"])]


def run(command: list[str], env: dict | None = None) -> int:
    print("$ " + " ".join(command[:6]) + (" ..." if len(command) > 6 else ""), flush=True)
    try:
        return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode
    except FileNotFoundError:
        print(f"{command[0]}: not found (FRIDA_TOOLS={TOOLS}; tools/check.py install puts the pinned tools there)")
        return 127


def uvx(package: str, *args: str) -> list[str]:
    return ["uvx", "--from", package, *args]


# ------------------------------------------------------------------------------ checks


def check_ruff(fix: bool, files: list[str] | None) -> int:
    files = files if files is not None else tracked(CHECK["python-files"])
    if not files:
        return 0
    ruff = CHECK["ruff"]
    lint = run(uvx(ruff, "ruff", "check", *(["--fix"] if fix else []), *files))
    fmt = run(uvx(ruff, "ruff", "format", *([] if fix else ["--check", "--diff"]), *files))
    return lint or fmt


def check_import_linter(fix: bool, files: list[str] | None) -> int:
    return run(uvx(CHECK["import-linter"], "lint-imports"), env={**os.environ, "PYTHONPATH": str(ROOT)})


def check_ty(fix: bool, files: list[str] | None) -> int:
    typed = subprocess.check_output(
        ["uv", "run", "python", "-c", "from flow.test_pipeline import typed; print(*typed())"], cwd=ROOT, text=True
    ).split()
    return run(["uv", "run", "ty", "check", *CHECK["ty-paths"], *typed])


def check_contracts(fix: bool, files: list[str] | None) -> int:
    return run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", *CHECK["contract-tests"]])


def check_pytest(fix: bool, files: list[str] | None) -> int:
    env = tool_path("oss-cad-suite")
    return run(["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", *CHECK["pytest"]], env=env)


def check_markdown(fix: bool, files: list[str] | None) -> int:
    files = files if files is not None else tracked(suffixes=(".md",))
    if not files:
        return 0
    return run(uvx(CHECK["rumdl"], "rumdl", "check", *(["--fix"] if fix else []), *files))


def check_tex_fmt(fix: bool, files: list[str] | None) -> int:
    files = files if files is not None else tracked(CHECK["tex-files"])
    if not files:
        return 0
    env = tool_path("tex-fmt")
    return run(["tex-fmt", *CHECK["tex-fmt-args"], *([] if fix else ["--check"]), *files], env=env)


def check_chktex(fix: bool, files: list[str] | None) -> int:
    files = files if files is not None else tracked(CHECK["chktex-files"])
    if not shutil.which("chktex"):
        print("chktex: skipped, chktex is not on PATH (it comes with TeX Live)")
        return 0
    status = 0
    args = ["--quiet", "--inputfiles=0", *(f"--nowarn={n}" for n in CHECK["chktex-nowarn"])]
    for name in files:
        # chktex can keep a non-zero status for a muted warning class: fail on visible output only
        out = subprocess.run(["chktex", *args, name], cwd=ROOT, capture_output=True, text=True, check=False)
        if (out.stdout + out.stderr).strip():
            print(out.stdout + out.stderr, end="")
            status = 1
    return status


_DIRECTIVE_COMMA = re.compile(r"^\s*(`(?:ifdef|ifndef|elsif|else|endif)\b[^\n]*,)\s*$", re.MULTILINE)


def check_verible_format(fix: bool, files: list[str] | None) -> int:
    env = tool_path("verible")
    args = PROJECT["tool"]["verible-format"]["args"]
    failed = []
    for name in files if files is not None else hdl_files():
        source = (ROOT / name).read_text()
        out = subprocess.run(
            ["verible-verilog-format", *args, name], cwd=ROOT, env=env, capture_output=True, text=True, check=False
        )
        moved = set(_DIRECTIVE_COMMA.findall(out.stdout)) - set(_DIRECTIVE_COMMA.findall(source))
        if out.returncode:
            print(out.stderr, end="")
            failed.append(name)
        elif moved:
            # Verible moves a leading comma onto a preprocessor directive, where it is lost
            print(f"{name}: Verible would put a comma on {sorted(moved)}: fence the block with")
            print("  // verilog_format: off ... // verilog_format: on")
            failed.append(name)
        elif out.stdout != source:
            if fix:
                (ROOT / name).write_text(out.stdout)
            else:
                diff = difflib.unified_diff(
                    source.splitlines(True), out.stdout.splitlines(True), name, name + " (formatted)"
                )
                sys.stdout.writelines(diff)
            failed.append(name)
    return _report("verible-format", failed)


def check_verible_lint(fix: bool, files: list[str] | None) -> int:
    env = tool_path("verible")
    rules = "--rules=" + ",".join(PROJECT["tool"]["verible-lint"]["rules"])
    failed = [
        n for n in (files if files is not None else hdl_files()) if run(["verible-verilog-lint", rules, n], env=env)
    ]
    return _report("verible-lint", failed)


def designs(files: list[str] | None = None) -> list[dict]:
    """The designs to elaborate: all, or those holding one of ``files``; a design whose files use
    the power define also with it defined."""

    chosen = [d for d in HDL["designs"] if files is None or set(d["files"]) & set(files)]
    power, out = HDL["power-define"], []
    for design in chosen:
        need = design.get("requires")
        if need and not (ROOT / need).exists():
            print(f"{design['name']}: skipped, {need} is not in this checkout")
            continue
        out.append(design)
        if any(power in (ROOT / f).read_text(errors="replace") for f in design["files"] if (ROOT / f).is_file()):
            out.append({**design, "name": f"{design['name']}+{power}", "defines": [*design.get("defines", []), power]})
    return out


def _vlt() -> Path:
    path = ROOT / "build" / "hdl" / "verilator.vlt"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["`verilator_config"]
    for waiver in PROJECT["tool"]["verilator"]["waivers"]:
        rule = f"-rule {waiver['rule']} " if waiver.get("rule") else ""
        # -match: the waiver applies to the warning as reported; without it Verilator keeps some
        # (all of SiTCP's) it ties to a source line read before the waiver
        lines.append(f'lint_off {rule}-file "{waiver["file"]}" -match "*"')
    path.write_text("\n".join(lines) + "\n")
    return path


def _standard(design: dict) -> str:
    return design.get("standard", HDL["verilog-standard"])


def check_verilator_lint(fix: bool, files: list[str] | None) -> int:
    env = tool_path("oss-cad-suite")
    vlt, failed = _vlt(), []
    for design in designs(files):
        incdirs = [*HDL["include-directories"], *design.get("include-directories", [])]
        command = [
            "verilator",
            *PROJECT["tool"]["verilator"]["args"],
            "--language",
            _standard(design),
            "--top-module",
            design["top"],
            str(vlt),
            *(f"+incdir+{d}" for d in incdirs),
            *(f"+define+{d}" for d in design.get("defines", [])),
            *(arg for d in design.get("library-directories", []) for arg in ("-y", d)),
            *design["files"],
        ]
        print(f"== {design['name']}", flush=True)
        if run(command, env=env):
            failed.append(design["name"])
    return _report("verilator-lint", failed)


def check_slang_lint(fix: bool, files: list[str] | None) -> int:
    env = tool_path("oss-cad-suite")
    failed = []
    for design in designs(files):
        incdirs = [*HDL["include-directories"], *design.get("include-directories", [])]
        command = [
            "slang",
            f"--std={_standard(design)}",
            *PROJECT["tool"]["slang"]["args"],
            "--top",
            design["top"],
            *(f"-I{d}" for d in incdirs),
            *(f"-D{d}" for d in design.get("defines", [])),
            *(arg for d in design.get("library-directories", []) for arg in ("-y", d)),
            *design["files"],
        ]
        print(f"== {design['name']}", flush=True)
        if run(command, env=env):
            failed.append(design["name"])
    return _report("slang-lint", failed)


def _report(name: str, failed: list[str]) -> int:
    for item in failed:
        print(f"{name}: FAILED {item}")
    return bool(failed)


# name -> (function, the files a staged change must touch for the hook to run it)
CHECKS: dict[str, tuple[Callable[[bool, list[str] | None], int], Callable[[str], bool]]] = {
    "ruff": (check_ruff, lambda f: bool(re.search(CHECK["python-files"], f))),
    "import-linter": (check_import_linter, lambda f: f.endswith(".py") or f == "pyproject.toml"),
    "ty": (check_ty, lambda f: f.startswith("flow/") and f.endswith(".py")),
    "contracts": (check_contracts, lambda f: f.startswith("flow/") and f.endswith(".py")),
    "markdown": (check_markdown, lambda f: f.endswith(".md")),
    "tex-fmt": (check_tex_fmt, lambda f: bool(re.search(CHECK["tex-files"], f))),
    "chktex": (check_chktex, lambda f: bool(re.search(CHECK["chktex-files"], f))),
    "verible-format": (check_verible_format, lambda f: f.endswith(tuple(HDL["source-suffixes"]))),
    "verible-lint": (check_verible_lint, lambda f: f.endswith(tuple(HDL["source-suffixes"]))),
    "verilator-lint": (check_verilator_lint, lambda f: f.endswith(tuple(HDL["source-suffixes"]))),
    "slang-lint": (check_slang_lint, lambda f: f.endswith(tuple(HDL["source-suffixes"]))),
    "pytest": (check_pytest, lambda f: False),
}
PER_FILE = {"ruff", "markdown", "tex-fmt", "chktex", "verible-format", "verible-lint", "verilator-lint", "slang-lint"}


def staged() -> int:
    """The git hook: the checks a staged change touches, fixing what they fix; a commit whose
    files a fix changed stops so the fix can be reviewed and staged."""

    names = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"], cwd=ROOT, text=True
    ).split()
    names = [n for n in names if (ROOT / n).is_file()]
    before = subprocess.check_output(["git", "diff", "--stat"], cwd=ROOT, text=True)
    status = 0
    for name, (function, touches) in CHECKS.items():
        hit = [n for n in names if touches(n)]
        if hit:
            print(f"=== {name}", flush=True)
            files = [n for n in hit if not any(n.startswith(p) for p in HDL["exclude"])] if name in PER_FILE else None
            status |= function(True, files)
    if subprocess.check_output(["git", "diff", "--stat"], cwd=ROOT, text=True) != before:
        print("A check fixed files: review and stage them, then commit again.")
        status = 1
    return status


def install_hook() -> int:
    hook = Path(
        subprocess.check_output(["git", "rev-parse", "--git-path", "hooks/pre-commit"], cwd=ROOT, text=True).strip()
    )
    hook = hook if hook.is_absolute() else ROOT / hook
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexec uv run --no-project --python 3.12 python tools/check.py --staged\n")
    hook.chmod(0o755)
    print(f"wrote {hook}")
    return 0


def editor() -> int:
    """The HDL language servers' configs (Slang's and Veridian's), from the same settings."""

    files = sorted({f for d in HDL["designs"] for f in d["files"] if (ROOT / f).is_file()} | set(hdl_files()))
    incdirs = sorted(
        {*HDL["include-directories"], *(d for x in HDL["designs"] for d in x.get("include-directories", []))}
    )
    filelist = ROOT / "build" / "hdl" / "editor.f"
    filelist.parent.mkdir(parents=True, exist_ok=True)
    filelist.write_text("\n".join([*(f"+incdir+{d}" for d in incdirs), *files]) + "\n")
    slang = ROOT / ".slang" / "server.json"
    slang.parent.mkdir(exist_ok=True)
    flags = [
        f"--std={HDL['verilog-standard']}",
        *PROJECT["tool"]["slang"]["args"],
        "-f",
        str(filelist.relative_to(ROOT)),
    ]
    slang.write_text(
        json.dumps({"flags": " ".join(flags), "indexGlobs": ["design/**/*.v", "test/**/*.v"]}, indent=2) + "\n"
    )
    veridian = {
        "include_dirs": incdirs,
        "verible": {
            "format": {"enabled": True, "args": ["--inplace", *PROJECT["tool"]["verible-format"]["args"]]},
            "lint": {"enabled": True, "args": ["--rules=" + ",".join(PROJECT["tool"]["verible-lint"]["rules"])]},
        },
        "verilator": {
            "syntax": {"enabled": True, "args": [*PROJECT["tool"]["verilator"]["args"], str(_vlt().relative_to(ROOT))]}
        },
    }
    (ROOT / "veridian.yaml").write_text(
        "# generated by tools/check.py editor from pyproject.toml\n" + json.dumps(veridian, indent=2) + "\n"
    )
    print(f"wrote {slang.relative_to(ROOT)}, veridian.yaml, {filelist.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "command", nargs="?", choices=[*CHECKS, "all", "install", "install-hook", "editor", "cache-key"]
    )
    parser.add_argument(
        "names", nargs="*", help="install: the tools (default: every pinned one); a per-file check: its files"
    )
    parser.add_argument("--fix", action="store_true", help="apply the fixes a check can make")
    parser.add_argument("--staged", action="store_true", help="the checks the staged files touch (the git hook)")
    options = parser.parse_args()
    if options.names and options.command not in {"install", *PER_FILE}:
        parser.error(f"{options.command} takes no names (files go to a per-file check: {', '.join(sorted(PER_FILE))})")
    if options.staged:
        return staged()
    match options.command:
        case "install":
            for tool in options.names or NATIVE:
                if tool not in NATIVE:
                    parser.error(f"install: {tool} is not one of {', '.join(NATIVE)}")
                install(tool)
            return 0
        case "install-hook":
            return install_hook()
        case "editor":
            return editor()
        case "cache-key":
            print(cache_key())
            return 0
        case "all":
            status = 0
            for name, (function, _) in CHECKS.items():
                print(f"=== {name}", flush=True)
                status |= function(options.fix, None)
            return status
        case None:
            parser.error("a check, or all")
    if not options.names:
        return CHECKS[options.command][0](options.fix, None)
    files = []
    for name in options.names:
        path = Path(name).resolve()
        if not path.is_file() or not path.is_relative_to(ROOT):
            parser.error(f"{options.command}: {name} is not a file in this checkout")
        files.append(str(path.relative_to(ROOT)))
    return CHECKS[options.command][0](options.fix, files)


if __name__ == "__main__":
    sys.exit(main())
