"""Shared argument parsing for primitive-layout commands."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path


def primitive_main(
    module_name: str,
    run_layout: Callable[[str, str, bool, Path], None],
    *,
    default_tech: str = "ihp130",
) -> None:
    """Parse module-level primitive options and run its layout sweep."""
    parser = argparse.ArgumentParser(
        prog=f"python -m {module_name}",
        description=f"Generate {module_name.split('.')[-2]} layout primitives",
    )
    parser.add_argument("-t", "--tech", default=default_tech, help="Target PDK technology")
    parser.add_argument(
        "-m", "--mode", default="min", choices=["min", "max"], help="min: default only; max: full sweep"
    )
    parser.add_argument("-v", "--visual", action="store_true", help="Render the generated GDS")
    # TODO: Change the default to build/<layout-module>/<short-datetime>.
    parser.add_argument("-o", "--out", default="build", type=Path, help="Output directory")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    run_layout(args.tech, args.mode, args.visual, args.out)
