#!/usr/bin/env bash
# macOS: read/reset independent Bart v18 activity counters.
# Usage: bash scripts/bart-v18-gates.sh clear|snapshot|status [mister]
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
  rm -f /tmp/bart-v18-gates.last
  printf '%s\n' '$REQUEST' > /tmp/bart-v18-gates.req
  n=0
  while [ ! -s /tmp/bart-v18-gates.last ]; do
    sleep 1
    n=\$((n+1))
    if [ \"\$n\" -ge 12 ]; then
      echo 'ERROR: matching v18 Main did not service the request.' >&2
      exit 1
    fi
  done
  cat /tmp/bart-v18-gates.last
  grep -q '^OK BART_V18 ' /tmp/bart-v18-gates.last
"
