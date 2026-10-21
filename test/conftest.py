"""Let cocotb run Icarus from the OSS CAD Suite with this project's Python.

The suite's ``bin/vvp`` is a wrapper that runs ``libexec/vvp`` under the suite's
own glibc loader with ``--inhibit-cache --library-path <suite>/lib``. That loader
was built on Debian, so beyond the suite's lib it only searches the multiarch
directories and ``/lib``, ``/usr/lib``. When cocotb embeds the project's Python,
its libpython (uv's python-build-standalone, linked for old glibc) still needs
``librt.so.1`` and ``libutil.so.1``, which the suite does not ship. On RHEL-like
hosts the 64-bit copies live in ``/usr/lib64`` and ``/lib`` holds 32-bit ones, so
vvp fails with "librt.so.1: wrong ELF class: ELFCLASS32" and cocotb reports no
results file. The wrapper also exports the suite's ``PYTHONHOME`` and
``PYTHONEXECUTABLE``, which point the embedded interpreter at the suite's Python.

So when ``vvp`` on PATH is the suite's wrapper, put an equivalent launcher ahead of
it that also searches the host's 64-bit library directories (what the suite's
loader already does on Debian hosts) and leaves the Python variables alone.
A system Icarus, as on CI, is left untouched.
"""

from __future__ import annotations

import os
import shlex
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

HOST_LIB_DIRS = ("/lib64", "/usr/lib64")


def _oss_cad_suite(vvp: Path) -> Path | None:
    """Return the suite's top directory when ``vvp`` is its loader wrapper."""

    top = vvp.resolve().parent.parent
    if (top / "libexec" / "vvp").is_file() and (top / "lib" / "ld-linux-x86-64.so.2").is_file():
        return top
    return None


@pytest.fixture(scope="session", autouse=True)
def oss_cad_suite_vvp(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Shadow the OSS CAD Suite's ``vvp`` wrapper for cocotb's simulations."""

    found = shutil.which("vvp")
    top = _oss_cad_suite(Path(found)) if found else None
    if top is None:
        yield
        return

    lib_dirs = [str(top / "lib")]
    for lib_dir in HOST_LIB_DIRS:
        resolved = os.path.realpath(lib_dir)
        if os.path.isdir(resolved) and resolved not in lib_dirs:
            lib_dirs.append(resolved)

    bin_dir = tmp_path_factory.mktemp("oss_cad_suite_vvp")
    launcher = bin_dir / "vvp"
    loader = shlex.quote(str(top / "lib" / "ld-linux-x86-64.so.2"))
    library_path = shlex.quote(os.pathsep.join(lib_dirs))
    vvp = shlex.quote(str(top / "libexec" / "vvp"))
    launcher.write_text(
        f'#!/bin/sh\nexec {loader} --inhibit-cache --inhibit-rpath "" --library-path {library_path} {vvp} "$@"\n'
    )
    launcher.chmod(0o755)

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PATH", str(bin_dir), prepend=os.pathsep)
        yield
