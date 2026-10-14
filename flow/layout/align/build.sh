#!/usr/bin/env bash
# ALIGN flow for a design in standard-cell rows: the PDK's ALIGN directory (make_pdk.py), the
# design directory (make_design.py), ALIGN (run.sh), then post.py for signoff.
#   flow/layout/align/build.sh tsmc65 design/layout/comp_frida1.json [--free]
#   flow/layout/align/build.sh tsmc65 build/layout/netlists/tsmc65/comp_frida1_transistors.sp
# POST_ARGS (e.g. "--fill decap --ring") and ALIGN_ARGS are passed through; the PDK's ALIGN_ROUTER
# (pdk/<pdk>/layout/tech.py) picks ALIGN's router.
set -euo pipefail
pdk=$1
shift
here=$(cd "$(dirname "$0")" && pwd)
# ALIGN imports the PDK directory as a package named after it: the generated one is called pdk
pdkdir=$(uv run python "$here/make_pdk.py" "$pdk" "build/layout/align/$pdk/pdk" | tail -1)
design=$(uv run python "$here/make_design.py" "$pdk" "$@" | tail -1)
name=$(basename "$design")
router=$(cd "pdk/$pdk/layout" && python3 -c "import tech; print(getattr(tech, 'ALIGN_ROUTER', ''))")
# standard cells: in rows of their own (dense wrapper) with a floorplan, isolated without one
if grep -q '"Floorplan"' "$design/$name.const.json"; then export STEMS_STD_DENSE=1; else export ONE_AXIS=1; fi
# the PDK's router, and ALIGN's default where that one crashes (hanan on a very small design)
if ! { [ -n "$router" ] && ALIGN_ARGS="--router $router ${ALIGN_ARGS:-}" POST="$here/post.py $pdk" \
  "$here/run.sh" "$design" "$pdkdir" "build/layout/align/$pdk/$name"; }; then
  POST="$here/post.py $pdk" "$here/run.sh" "$design" "$pdkdir" "build/layout/align/$pdk/$name"
fi
mv "build/layout/align/$pdk/$name/$name.out.gds" "build/layout/align/$pdk/$name/$name.gds"
echo "wrote build/layout/align/$pdk/$name/$name.gds"
