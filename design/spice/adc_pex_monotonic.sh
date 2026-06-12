#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

set +u
source /eda/local/scripts/cadence_2024-25.sh
set -u
uv run python design/spice/gen_tb_adc_pex_pwl.py

mkdir -p build/adc_pex_monotonic

spectre design/spice/tb_adc_pex_spectre.scs +preset=mx +escchars \
    +log build/adc_pex_monotonic/tb_adc_pex_monotonic.log \
    -raw build/adc_pex_monotonic/tb_adc_pex_monotonic.raw
