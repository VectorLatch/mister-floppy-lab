#!/usr/bin/env bash
# macOS: read/reset independent Bart v17 activity counters.
# Usage: bash scripts/bart-v17-counters.sh clear|snapshot|status [mister]
set -euo pipefail
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: bash $0 clear|snapshot|status [hostname]" >&2; exit 2
fi
case "$1" in clear|snapshot|status) ;; *)
    echo "Expected clear, snapshot, or status" >&2; exit 2 ;;
esac
HOST=mister
if [ "$#" -eq 2 ]; then HOST="$2"; fi
REQUEST="$1"
ssh "root@$HOST" "
  set -eu
  rm -f /tmp/bart-v17-diagnostics.last
  printf '%s\n' '$REQUEST' > /tmp/bart-v17-diagnostics.req
  n=0
  while [ ! -s /tmp/bart-v17-diagnostics.last ]; do
    sleep 1
    n=\$((n+1))
    if [ \"\$n\" -ge 12 ]; then
      echo 'ERROR: matching v17 Main did not service the request.' >&2
      exit 1
    fi
  done
  cat /tmp/bart-v17-diagnostics.last
  grep -q '^OK BART_V17 ' /tmp/bart-v17-diagnostics.last
"
