#!/usr/bin/env bash
# macOS: bash scripts/set-bart-v11-waits.sh <chip_wait:0..3> <cia_wait:0..3> [mister-host]
# Changes only experimental v11 diagnostic FPGA; MiSTer Main must match.
# User should F12-reset the emulated Amiga AFTER acknowledgement, before test.
set -euo pipefail
if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "Usage: bash $0 <chip_wait:0..3> <cia_wait:0..3> [mister-host]" >&2
  exit 2
fi
CHIP="$1"; CIA="$2"; HOST="mister"
if [ "$#" -eq 3 ]; then HOST="$3"; fi
case "$CHIP" in 0|1|2|3) ;; *) echo "Chip wait must be 0..3" >&2; exit 2;; esac
case "$CIA"  in 0|1|2|3) ;; *) echo "CIA wait must be 0..3" >&2; exit 2;; esac

# Explicitly validate readback; do not report success merely because SSH worked.
ssh "root@$HOST" "
  set -eu
  rm -f /tmp/bart-v11-waits.last
  printf '%s %s\n' '$CHIP' '$CIA' > /tmp/bart-v11-waits.req
  n=0
  while [ ! -s /tmp/bart-v11-waits.last ]; do
    sleep 1
    n=\$((n+1))
    if [ \"\$n\" -ge 6 ]; then
      echo 'ERROR: matching v11 Main is not servicing timing requests' >&2
      exit 1
    fi
  done
  cat /tmp/bart-v11-waits.last
  grep -q '^OK BART_V11 CHIP_WAIT=$CHIP CIA_WAIT=$CIA FPGA_ACK=' /tmp/bart-v11-waits.last
"
printf 'Settings confirmed. Now reset the emulated Amiga using F12 before attempting Bart.\n'
