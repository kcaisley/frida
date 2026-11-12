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
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import figures

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = HERE / "_build"
CHAPTERS = [
    "01_applications.md",
    "02_adcs.md",
    "03_design.md",
    "04_frida1.md",
    "05_frida1_measurements.md",
    "06_frida2.md",
    "07_conclusions.md",
]
COMMON = [
    "--from=markdown+fenced_divs+bracketed_spans+raw_attribute+superscript",
    "--metadata-file=thesis.yaml",
    f"--metadata=date:{datetime.date.today():%-d %B %Y}",
    "--lua-filter=thesis.lua",
    "--citeproc",
    "--lua-filter=section-refs.lua",
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


FRIDA1_GDS = "build/adc/e2e_adc_fab/tsmc65/frida1_1layer_radix17/layout/frida1_1layer_radix17.gds"
FRIDA1_RENDERS = (
    "layout_frida1_channel=@4",
    "layout_frida1_comp=comp",
    "layout_frida1_samp=sampswitch",
    "layout_frida1_capdriver=capdriver",
    "layout_frida1_caparray=caparray_1layer_radix17",
    "layout_frida1_digital=adc_digital@3",
)


def layout_renders() -> None:
    """FRIDA-1's layouts in the viewer's style (drawings/render_layout.py), where its GDS and the
    kit's layer map are present (the main checkout with the PDK submodules); kept once made."""
    root = figures.build_dir().parent
    gds = root / FRIDA1_GDS
    if (figures.OUT / "layout_frida1_comp.png").exists() or not gds.exists():
        return
    result = subprocess.run(
        [
            sys.executable,
            str(HERE / "drawings" / "render_layout.py"),
            str(gds),
            "tsmc65",
            str(figures.OUT),
            *FRIDA1_RENDERS,
        ],
        cwd=root,
        check=False,
    )
    if result.returncode:
        print("build: FRIDA-1's layout renders need the kit's layer map; left out")


def tikz_drawings() -> None:
    """Each TikZ drawing (drawings/*.tex, built from thesis-drawings.sty) as figures/<name>.pdf
    for the PDF and figures/<name>.svg for the page."""
    work = BUILD / "tikz"
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TEXINPUTS=f".:{HERE / 'drawings'}//:")
    for tex in sorted((HERE / "drawings").glob("*.tex")):
        if tex.stem == "drawing-preamble":
            continue
        pdf, svg = figures.OUT / f"{tex.stem}.pdf", figures.OUT / f"{tex.stem}.svg"
        sources = [tex, HERE / "drawings" / "drawing-preamble.tex", HERE / "drawings" / "thesis-drawings.sty"]
        if svg.exists() and svg.stat().st_mtime >= max(s.stat().st_mtime for s in sources):
            continue
        subprocess.run(
            ["lualatex", "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={work}", str(tex)],
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        shutil.copyfile(work / f"{tex.stem}.pdf", pdf)
        subprocess.run(["pdftocairo", "-svg", str(pdf), str(svg)], check=True)


def hidden_layers_dropped(svg: str) -> str:
    """An Inkscape drawing without its hidden layers (display:none), which a page need not carry."""
    while match := re.search(r'<g\b[^>]*inkscape:groupmode="layer"[^>]*display:none[^>]*>', svg):
        depth = 0
        for tag in re.finditer(r"<g\b|</g>", svg[match.start() :]):
            depth += 1 if tag.group(0) == "<g" else -1
            if depth == 0:
                svg = svg[: match.start()] + svg[match.start() + tag.end() :]
                break
    return svg


def inline_svg(name: str) -> str:
    """A drawing's SVG for inline use in the page: Inkscape's editor state dropped, its ids
    prefixed so that drawings on one page cannot collide, and its size left to the page."""
    source = HERE / "drawings" / f"{name}.svg"
    svg = (source if source.exists() else figures.OUT / f"{name}.svg").read_text()
    svg = re.sub(r"<\?xml[^>]*\?>|<!--.*?-->", "", svg, flags=re.DOTALL)
    svg = re.sub(
        r"<sodipodi:namedview\b.*?(/>|</sodipodi:namedview>)|<metadata\b.*?</metadata>", "", svg, flags=re.DOTALL
    )
    svg = hidden_layers_dropped(svg)
    svg = re.sub(r'\bid="([^"]+)"', rf'id="{name}-\1"', svg)
    svg = re.sub(r"url\(#([^)]+)\)", rf"url(#{name}-\1)", svg)
    svg = re.sub(r'((?:xlink:)?href)="#([^"]+)"', rf'\1="#{name}-\2"', svg)
    head_end = svg.index(">", svg.index("<svg")) + 1
    head = re.sub(r'\s(width|height)="[^"]*"', "", svg[svg.index("<svg") : head_end])
    head = head.replace("<svg", '<svg class="drawing-svg" role="img"', 1)
    return head + svg[head_end:]


EMBED_MAX_BYTES = 300_000  # an image larger than this is downsampled for a shared page


def web_image(path: Path, embed: bool) -> str:
    """An existing image as the page shows it: a PDF rasterized (the PDF edition takes the PDF
    itself), linked from _build, or inside the page (downsampled when large) to share it."""
    raster = BUILD / "raster"
    raster.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        print(f"build: no {path} (a render the kit makes); left out of the page")
        return ""
    if path.suffix == ".pdf":
        png = raster / f"{path.stem}.png"
        if not png.exists() or png.stat().st_mtime < path.stat().st_mtime:
            subprocess.run(
                ["pdftocairo", "-png", "-r", "110", "-singlefile", str(path), str(png.with_suffix(""))], check=True
            )
        path = png
    if not embed:
        return os.path.relpath(path, BUILD)
    data = path.read_bytes()
    kind = "jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "png"
    if len(data) > EMBED_MAX_BYTES:
        import matplotlib.image as mpimg

        image = mpimg.imread(path)
        step = math.ceil(math.sqrt(len(data) / EMBED_MAX_BYTES))
        small = raster / f"{path.stem}.small.png"
        mpimg.imsave(small, image[::step, ::step])
        data, kind = small.read_bytes(), "png"
    return f"data:image/{kind};base64," + base64.b64encode(data).decode()


def html(embed: bool) -> Path:
    out = BUILD / "thesis.html"
    pandoc("--to=html5", "--template=template.html", "--mathjax", "--toc", "--section-divs", f"--output={out}")
    page = re.sub(
        r'<div class="drawing" data-src="drawings/([\w-]+)\.svg"></div>',
        lambda m: f'<div class="drawing">{inline_svg(m.group(1))}</div>',
        out.read_text(),
    )
    # existing images (src=): inside the page to share it, else linked from _build
    page = re.sub(
        r'<img class="photo" alt="" data-src="([^"]+)">',
        lambda m: f'<img class="photo" alt="" src="{web_image(HERE / m.group(1), embed)}">',
        page,
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
    layout_renders()
    drawing_pdfs()
    tikz_drawings()
    if "html" in args.targets:
        print(html(args.embed))
    if "pdf" in args.targets:
        print(pdf())


if __name__ == "__main__":
    main()
