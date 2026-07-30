#!/usr/bin/env bash

set -u

# ChkTeX can retain a non-zero status for a warning class muted with --nowarn,
# even though it emits no diagnostic. Fail on visible, unsuppressed findings.
chktex_args=(
  --quiet
  --inputfiles=0
  --nowarn 1
  --nowarn 3
  --nowarn 8
  --nowarn 12
  --nowarn 13
  --nowarn 17
  --nowarn 25
  --nowarn 26
  --nowarn 31
  --nowarn 35
  --nowarn 36
  --nowarn 37
  --nowarn 44
  --nowarn 47
  --nowarn 48
)

status=0
for file in "$@"; do
  output="$(chktex "${chktex_args[@]}" "$file" 2>&1 || :)"
  if [[ -n "$output" ]]; then
    printf '%s\n' "$output"
    status=1
  fi
done

exit "$status"
