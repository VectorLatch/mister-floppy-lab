#!/usr/bin/env bash
# Mac: set real blitter completion wait (mode, timeout) on current v16 core.
# Usage: bash scripts/set-bart-v16-blitter.sh MODE TIMEOUT [mister]
# or:    bash scripts/set-bart-v16-blitter.sh status|off|restore [mister]
# 0=off; 1=BLTSIZE/BLTSIZH starts; 2=all CPU blitter-register writes.
# TIMEOUT=1..255 units, each 256 7MHz (clk7n_en) ticks ~36.6us.
set -euo pipefail
if [ "$#" -lt 1 ] || [ "$#" -gt 3 ]; then
  echo "Usage: bash $0 MODE(0/1/2) TIMEOUT(1..255) [mister] OR status|off|restore [mister]" >&2
  exit 2
fi
HOST=mister
REQUEST=""
case "$1" in
  status|off|restore)
    if [ "$#" -gt 2 ]; then echo 'Preset takes at most one host.' >&2; exit 2; fi
    REQUEST="$1"
    if [ "$#" -eq 2 ]; then HOST="$2"; fi
    ;;
  *)
    if [ "$#" -lt 2 ]; then echo 'Expected mode and timeout.' >&2; exit 2; fi
    case "$1" in 0|1|2) ;; *) echo 'Mode must be 0, 1 or 2.' >&2; exit 2 ;; esac
    case "$2" in ''|*[!0-9]*) echo 'Timeout must be numeric, 1..255.' >&2; exit 2 ;; esac
    if [ "$2" -lt 1 ] || [ "$2" -gt 255 ]; then
      echo 'Timeout must be 1..255.' >&2; exit 2
    fi
    REQUEST="$1 $2"
    if [ "$#" -eq 3 ]; then HOST="$3"; fi
    ;;
esac
ssh "root@$HOST" "
  set -eu
  rm -f /tmp/bart-v16-blitter.last
  printf '%s\n' '$REQUEST' > /tmp/bart-v16-blitter.req
  n=0
  while [ ! -s /tmp/bart-v16-blitter.last ]; do
    sleep 1
    n=\$((n+1))
    if [ \"\$n\" -ge 12 ]; then
      echo 'ERROR v16 Main did not respond. Check active Main and core.' >&2
      exit 1
    fi
  done
  cat /tmp/bart-v16-blitter.last
  grep -q '^OK BART_V16 ' /tmp/bart-v16-blitter.last
"
