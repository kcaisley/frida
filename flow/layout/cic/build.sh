#!/usr/bin/env bash
# cIcCreator (cicpy) flow for a design in standard-cell rows: the PDK's tech file, placeholders
# and real cells (gen.py), routes (route.py), compile, convert to GDS, finish (post.py).
#   flow/layout/cic/build.sh tsmc65 design/layout/comp_frida1.json
set -euo pipefail
pdk=$1 fp=$2
here=$(cd "$(dirname "$0")" && pwd)
name=$(basename "$fp" .json)
root=build/layout/cic/$pdk
out=$root/$name
top=$(echo "$name" | tr a-z A-Z)
tech=$(uv run python "$here/make_tech.py" "$pdk" "$root/$pdk.tech" | tail -1)
uv run python "$here/gen.py" "$pdk" "$fp" "$root"
uv run python "$here/route.py" "$pdk" "$out" "$fp"
(cd "$out" && rm -f "$name.cic" && cicpy compile "$name.json" "$PWD/../$pdk.tech" "$name" > compile.log 2>&1)
if grep -qE "ERROR|Traceback" "$out/compile.log"; then grep -E "ERROR|Traceback" "$out/compile.log" | head; exit 1; fi
uv run python "$here/cic2gds.py" "$out/$name.cic" "$tech" "$out/${name}_raw.gds" "$top"
uv run python "$here/post.py" "$pdk" "$out/${name}_raw.gds" "$out/${name}_cells.gds" "$out/$name.gds" "$top"
echo "wrote $out/$name.gds"
