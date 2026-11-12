#!/usr/bin/env bash
# Quarto's pre-render: draw the thesis's figures (PDF for print, Plotly JSON for the web) with the
# repository's own environment, from this checkout's flow and phys.
set -euo pipefail
cd "$(dirname "$0")/../.."
exec uv run --quiet python docs/thesis/figures.py
