"""Build the thesis from its Markdown chapters with pandoc: a web edition (one HTML page, Plotly
figures and MathJax) and a PDF (LuaLaTeX, the ubonn-thesis package), into docs/thesis/_build.

    uv run python docs/thesis/build.py              # figures, HTML and PDF
    uv run python docs/thesis/build.py html         # the web edition only
    uv run python docs/thesis/build.py html --embed # with the fonts inside the page, to share it

The chapters (CHAPTERS, in order) number their sections, figures and equations through the
thesis.lua filter; figures.py draws each figure for both editions first.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import os
import re
import shutil
import subprocess
from pathlib import Path

import figures

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = HERE / "_build"
CHAPTERS = ["preface.md", "background.md"]
COMMON = [
    "--from=markdown+fenced_divs+bracketed_spans+raw_attribute+superscript",
    "--metadata-file=thesis.yaml",
    f"--metadata=date:{datetime.date.today():%-d %B %Y}",
    "--lua-filter=thesis.lua",
    "--citeproc",
    "--bibliography=references.bib",
    "--csl=ieee.csl",
]


def pandoc(*args: str) -> None:
    subprocess.run(["pandoc", *COMMON, *args, *CHAPTERS], cwd=HERE, check=True)


def html(embed: bool) -> Path:
    out = BUILD / "thesis.html"
    pandoc("--to=html5", "--template=template.html", "--mathjax", "--toc", "--section-divs", f"--output={out}")
    if embed:
        page = out.read_text()
        page = re.sub(
            r'url\("fonts/(LM-[\w-]+\.woff2)"\)',
            lambda m: (
                "url(data:font/woff2;base64,"
                + base64.b64encode((HERE / "fonts" / m.group(1)).read_bytes()).decode()
                + ")"
            ),
            page,
        )
        out.write_text(page)
    else:
        shutil.copytree(HERE / "fonts", BUILD / "fonts", dirs_exist_ok=True)
    return out


def pdf() -> Path:
    tex = BUILD / "thesis.tex"
    pandoc(
        "--to=latex",
        "--standalone",
        "--top-level-division=chapter",
        "--include-in-header=ubonn.tex",
        "--toc",
        f"--output={tex}",
    )
    # the TeX Live docs/makefile uses (ubonn-thesis needs a recent one), where installed
    texlive = Path(os.environ.get("TEXLIVE_BIN", "/usr/local/texlive/2026/bin/x86_64-linux"))
    path = f"{texlive}:{os.environ['PATH']}" if texlive.is_dir() else os.environ["PATH"]
    env = dict(os.environ, PATH=path, TEXINPUTS=f".:{HERE}//:{ROOT / 'libs' / 'ubonn-thesis'}//:")
    for _ in range(2):  # the second pass resolves the references
        subprocess.run(
            ["lualatex", "-interaction=nonstopmode", "-halt-on-error", tex.name],
            cwd=BUILD,
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    return BUILD / "thesis.pdf"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", choices=["html", "pdf"], default=["html", "pdf"])
    parser.add_argument("--embed", action="store_true", help="the fonts inside the HTML page")
    args = parser.parse_args()
    BUILD.mkdir(exist_ok=True)
    figures.main()
    if "html" in args.targets:
        print(html(args.embed))
    if "pdf" in args.targets:
        print(pdf())


if __name__ == "__main__":
    main()
