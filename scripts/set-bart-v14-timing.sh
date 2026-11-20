#!/usr/bin/env bash
# Change all six live Bart v14 timing knobs via the matching Physical-Floppy Main.
# Usage: bash scripts/set-bart-v14-timing.sh CHIP CIA READ WRITE CUSTOM BLIT [mister-host]
# All 0..3; 1 0 0 0 0 0 is the previous v11/v13 setting.
# Run on macOS (NOT inside SSH), then F12 reset the emulated Amiga.
set -euo pipefail
if [ "$#" -lt 6 ] || [ "$#" -gt 7 ]; then
  echo "Usage: bash $0 <chip:0..3> <cia:0..3> <read_extra:0..3> <write_extra:0..3> <custom_extra:0..3> <blit_extra:0..3> [host]" >&2
  exit 2
fi
n=1
for v in "$1" "$2" "$3" "$4" "$5" "$6"; do
  case "$v" in
    0|1|2|3) ;;
    *) echo "Each value must be an integer 0,1,2 or 3 (argument $n was '$v')" >&2; exit 2 ;;
  esac
  n=$((n+1))
done
HOST="mister"
if [ "$#" -eq 7 ]; then HOST="$7"; fi
ssh "root@$HOST" "
  set -eu
  rm -f /tmp/bart-v14-tune.last
  printf '%s\n' '$1 $2 $3 $4 $5 $6' > /tmp/bart-v14-tune.req
  n=0
  while [ ! -s /tmp/bart-v14-tune.last ]; do
    sleep 1
    n=\$((n+1))
    if [ \"\$n\" -ge 10 ]; then
      echo 'ERROR: v14 Main did not service the request (is matching v14 Main running?)' >&2
      exit 1
    fi
  done
  cat /tmp/bart-v14-tune.last
  grep -q '^OK BART_V14 CHIP_WAIT=$1 CIA_WAIT=$2 READ_EXTRA=$3 WRITE_EXTRA=$4 CUSTOM_EXTRA=$5 BLIT_EXTRA=$6 FPGA_ACK_E8=' /tmp/bart-v14-tune.last
"
echo "FPGA settings verified. Perform F12 -> Reset Amiga before testing Bart."
