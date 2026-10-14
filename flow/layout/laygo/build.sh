#!/usr/bin/env bash
# laygo flow for a design in standard-cell rows: templates and design script, hosted run, post.
#   flow/layout/laygo/build.sh tsmc65 design/layout/comp_c040.json
# LAYGO_CLIENT: the laygo client script (default ~/Documents/libs/laygo3-client/laygo3.py).
set -euo pipefail
pdk=$1 fp=$2
here=$(cd "$(dirname "$0")" && pwd)
name=$(basename "$fp" .json)
out=build/layout/laygo/$pdk
gen=$out/$name
mkdir -p "$gen"
# rip up and retry: a net the server's router cannot place goes first next time
export LAYGO_FIRST=${LAYGO_FIRST:-}
for attempt in 1 2 3 4 5 6 7 8; do
  uv run python "$here/rowtemplates.py" "$pdk" "$fp" "$gen"
  if python "${LAYGO_CLIENT:-$HOME/Documents/libs/laygo3-client/laygo3.py}" run "$gen/$name.py" --yaml "$gen/${name}_laygo.yaml" -o "$out/${name}_raw.gds" > "$gen/run.log" 2>&1; then
    break
  fi
  failed=$(grep -oE "(no M2 route for|no free M3 track for|no edge escape for) [A-Za-z0-9_]+" "$gen/run.log" | head -1 | awk '{print $NF}')
  if [ -z "$failed" ] || [ "$attempt" = 8 ]; then cat "$gen/run.log"; exit 1; fi
  echo "retry: $failed first"
  LAYGO_FIRST=$failed${LAYGO_FIRST:+,$LAYGO_FIRST}
done
uv run python "$here/post.py" "$pdk" "$out/${name}_raw.gds" "$gen/${name}_templates.gds" "$out/$name.gds"
echo "wrote $out/$name.gds"
