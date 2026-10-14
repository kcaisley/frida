#!/usr/bin/env bash
# DRC and LVS of a row-design layout with the PDK's signoff scripts: the LVS source is the
# floorplan's netlist for the PDK (pdk/<pdk>/netlist/lvs_source.py adds the library
# subcircuits); DRC and LVS through pdk/<pdk>/calibre/signoff_rules.py where calibre runs, else
# the PDK's KLayout decks (pdk/<pdk>/klayout/drc.py, lvs.py). CHECKER=calibre|klayout forces one.
# First the PDK's gdscheck precheck (pdk/<pdk>/gdscheck), where gdscheck is installed. One line out.
#   flow/layout/check.sh tsmc65 cic design/layout/comp_frida1.json build/layout/cic/tsmc65/comp_frida1/comp_frida1.gds
set -euo pipefail
pdk=$1 tool=$2 fp=$3 gds=$4
name=$(basename "$fp" .json)
tag=${pdk}_${tool}_$name
run=build/signoff/$pdk/${tool}_$name
mkdir -p "$run"
netlist=$(python3 -c "import json, sys, pathlib; f = pathlib.Path(sys.argv[1]); print(f.parent / json.loads(f.read_text())['netlist'].format(pdk=sys.argv[2]))" "$fp" "$pdk")
src_top=$(awk 'tolower($1) == ".subckt" { top = $2 } END { print top }' "$netlist")
top=$(uv run python -c "import klayout.db as k, sys; l = k.Layout(); l.read(sys.argv[1]); print(max(l.top_cells(), key=lambda c: c.bbox().area()).name)" "$gds")
uv run python "pdk/$pdk/netlist/lvs_source.py" "$netlist" "$run/source.cdl"
if [ -f "$gds.extra.sp" ]; then
  uv run python flow/layout/lvs_extra.py "$pdk" "$run/source.cdl" "$gds.extra.sp" "$src_top" "$run/source.cdl"
fi
g=""
if command -v gdscheck >/dev/null && [ -f "pdk/$pdk/gdscheck/pdk.yml" ]; then
  g="gdscheck: $(gdscheck run -i "$gds" -p "pdk/$pdk/gdscheck/pdk.yml" -t "$top" -s precheck 2>&1 | tail -n 1 || true) | "
fi
# Calibre where it is installed (the asiclab hosts: /eda/local/scripts), else KLayout
calibre_host() { command -v calibre >/dev/null || ls /eda/local/scripts/siemens_*.sh >/dev/null 2>&1; }
checker=${CHECKER:-$(calibre_host && [ -f "pdk/$pdk/calibre/signoff_rules.py" ] && echo calibre || echo klayout)}
if [ "$checker" = calibre ]; then
  d=$(uv run python "pdk/$pdk/calibre/signoff_rules.py" drc "$gds" "$top" "$run/drc" 2>&1 | tail -n 1)
  l=$(uv run python "pdk/$pdk/calibre/signoff_rules.py" lvs "$gds" "$top" "$run/source.cdl" "$src_top" "$run/lvs" 2>&1 | tail -n 1)
else
  d=$(uv run python "pdk/$pdk/klayout/drc.py" "$gds" "$top" "$run/kdrc" 2>&1 | tail -n 1)
  l=$(uv run python "pdk/$pdk/klayout/lvs.py" "$gds" "$top" "$run/source.cdl" "$src_top" "$run/klvs" 2>&1 | tail -n 1)
fi
echo "$tag ($top, $checker): $g$d | $l"
