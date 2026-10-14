#!/usr/bin/env bash
# Run ALIGN on one design directory (SPICE + const.json) with a given ALIGN PDK directory, then
# finish the layout with a technology post-processing script. Needs ALIGN built on this host
# (juno: /local/kcaisley/layout-eval/ALIGN-public) and the frida uv environment.
#
#   flow/layout/align/run.sh DESIGN_DIR PDK_DIR [WORK_DIR]
#
# Environment:
#   ONE_AXIS=1    without a Floorplan constraint, run ALIGN to its primitives first and merge its
#                 symmetry groups onto one axis (one_axis.py) for the second, full pass
#   POST          post-processing command (script and leading arguments) run on ALIGN's GDS (output: WORK_DIR/<name>.out.gds)
#   POST_ARGS     extra arguments for POST
#   ALIGN_ARGS    extra arguments for schematic2layout.py
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
design=$(cd "$1" && pwd)
pdk=$(cd "$2" && pwd)
name=$(basename "$design")
work=$(realpath -m "${3:-build/layout/align/$name}")
ALIGN_HOME=${ALIGN_HOME:-/local/kcaisley/layout-eval/ALIGN-public}

export LD_LIBRARY_PATH="$(dirname "$(find "$ALIGN_HOME/_skbuild" -name libOsiCbc.so.3 | head -1)")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
mkdir -p "$work"
if [ "${ONE_AXIS:-}" = 1 ] && ! grep -q '"Floorplan"' "$design/$name.const.json" && [[ "${ALIGN_ARGS:-}" != *flow_stop* ]]; then
  rm -rf "$work/pass1"; mkdir -p "$work/pass1"
  (cd "$work/pass1" && "$ALIGN_HOME/general/bin/schematic2layout.py" "$design" -p "$pdk" -w "$work/pass1" -s "$name" -l INFO -v INFO --flow_stop 2_primitives)
  python3 "$here/one_axis.py" "$design" "$work/pass1" "$work/design/$name"
  design="$work/design/$name"
fi
(cd "$work" && "$ALIGN_HOME/general/bin/schematic2layout.py" "$design" -p "$pdk" -w "$work" -s "$name" -l INFO -v INFO ${ALIGN_ARGS:-})

gds=$(ls "$work"/*.gds 2>/dev/null | grep -v "\.out\.gds$" | head -1 || true)
[ -n "$gds" ] || gds=$(find "$work" -name "${name^^}_0.gds" -o -name "${name}_0.gds" | head -1)
if [ -n "${POST:-}" ]; then
  uv run python $POST "$gds" "$work/$name.out.gds" ${POST_ARGS:-}  # POST: the script and its leading arguments
  echo "wrote $work/$name.out.gds"
else
  echo "wrote $gds"
fi
