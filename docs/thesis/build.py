"""Build the thesis from its Markdown chapters with pandoc: a web edition (one HTML page, Plotly
figures and MathJax) and a PDF (LuaLaTeX, the ubonn-thesis package), into docs/thesis/_build.

    uv run python docs/thesis/build.py              # figures, HTML and PDF
    uv run python docs/thesis/build.py html         # the web edition only
    uv run python docs/thesis/build.py html --embed # with the fonts inside the page, to share it

The chapters (CHAPTERS, in order) number their sections, figures and equations through the
thesis.lua filter; figures.py draws each plot for both editions first, and each Inkscape drawing
in drawings/ goes into the page as SVG and into the PDF through rsvg-convert (or Inkscape).
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
CHAPTERS = ["applications.md", "adcs.md"]
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


def drawing_pdfs() -> None:
    """Each Inkscape drawing as the PDF the LaTeX edition includes (figures/<name>.pdf)."""
    figures.OUT.mkdir(exist_ok=True)
    for svg in sorted((HERE / "drawings").glob("*.svg")):
        pdf = figures.OUT / f"{svg.stem}.pdf"
        if pdf.exists() and pdf.stat().st_mtime >= svg.stat().st_mtime:
            continue
        if shutil.which("rsvg-convert"):
            subprocess.run(["rsvg-convert", "--format=pdf", f"--output={pdf}", str(svg)], check=True)
        else:
            subprocess.run(["inkscape", str(svg), f"--export-filename={pdf}"], check=True)


def inline_svg(name: str) -> str:
    """A drawing's SVG for inline use in the page: Inkscape's editor state dropped, its ids
    prefixed so that drawings on one page cannot collide, and its size left to the page."""
    svg = (HERE / "drawings" / f"{name}.svg").read_text()
    svg = re.sub(r"<\?xml[^>]*\?>|<!--.*?-->", "", svg, flags=re.DOTALL)
    svg = re.sub(
        r"<sodipodi:namedview\b.*?(/>|</sodipodi:namedview>)|<metadata\b.*?</metadata>", "", svg, flags=re.DOTALL
    )
    svg = re.sub(r'\bid="([^"]+)"', rf'id="{name}-\1"', svg)
    svg = re.sub(r"url\(#([^)]+)\)", rf"url(#{name}-\1)", svg)
    svg = re.sub(r'((?:xlink:)?href)="#([^"]+)"', rf'\1="#{name}-\2"', svg)
    head_end = svg.index(">", svg.index("<svg")) + 1
    head = re.sub(r'\s(width|height)="[^"]*"', "", svg[svg.index("<svg") : head_end])
    head = head.replace("<svg", '<svg class="drawing-svg" role="img"', 1)
    return head + svg[head_end:]


def html(embed: bool) -> Path:
    out = BUILD / "thesis.html"
    pandoc("--to=html5", "--template=template.html", "--mathjax", "--toc", "--section-divs", f"--output={out}")
    page = re.sub(
        r'<div class="drawing" data-src="drawings/([\w-]+)\.svg"></div>',
        lambda m: f'<div class="drawing">{inline_svg(m.group(1))}</div>',
        out.read_text(),
    )
    out.write_text(page)
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
    drawing_pdfs()
    if "html" in args.targets:
        print(html(args.embed))
    if "pdf" in args.targets:
        print(pdf())


if __name__ == "__main__":
    main()
