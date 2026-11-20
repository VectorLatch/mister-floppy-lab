#!/usr/bin/env bash
# Bart v15 six 8-bit controls. Execute on Mac, not from MiSTer SSH shell.
# Usage: bash scripts/set-bart-v15-timing.sh CHIP CIA READ WRITE CUSTOM BLIT [host]
# or:    bash scripts/set-bart-v15-timing.sh baseline|zero|restore [host]
# All numerical controls accept 0..255. Confirm OK then F12 -> Reset Amiga.
set -euo pipefail
if [ "$#" -lt 1 ] || [ "$#" -gt 7 ]; then
  echo "Usage: bash $0 CHIP CIA READ WRITE CUSTOM BLIT [mister-host] OR baseline|zero|restore [mister-host]" >&2
  exit 2
fi
HOST=mister
REQUEST=""
if [ "$1" = baseline ] || [ "$1" = zero ] || [ "$1" = restore ]; then
  if [ "$#" -gt 2 ]; then
    echo "Preset accepts zero or one optional hostname." >&2; exit 2
  fi
  REQUEST="$1"
  if [ "$#" -eq 2 ]; then HOST="$2"; fi
else
  if [ "$#" -lt 6 ]; then
    echo "Numeric mode requires CHIP CIA READ WRITE CUSTOM BLIT (six values 0..255)." >&2
    exit 2
  fi
  n=1
  for v in "$1" "$2" "$3" "$4" "$5" "$6"; do
    case "$v" in
      ''|*[!0-9]*) echo "Argument $n must be an integer from 0 to 255; got '$v'." >&2; exit 2 ;;
    esac
    if [ "$v" -gt 255 ]; then
      echo "Argument $n exceeds 255: '$v'." >&2; exit 2
    fi
    n=$((n+1))
  done
  REQUEST="$1 $2 $3 $4 $5 $6"
  if [ "$#" -eq 7 ]; then HOST="$7"; fi
fi

ssh "root@$HOST" "
  set -eu
  rm -f /tmp/bart-v15-tune.last
  printf '%s\n' '$REQUEST' > /tmp/bart-v15-tune.req
  n=0
  while [ ! -s /tmp/bart-v15-tune.last ]; do
    sleep 1
    n=\$((n+1))
    if [ \"\$n\" -ge 12 ]; then
      echo 'ERROR: matching v15 Main did not process request (verify v15 Main and core).' >&2
      exit 1
    fi
  done
  cat /tmp/bart-v15-tune.last
  grep -q '^OK BART_V15 ' /tmp/bart-v15-tune.last
"
echo 'Settings confirmed by live FPGA readback. F12 -> Reset Amiga before testing.'
