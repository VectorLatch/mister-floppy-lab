#!/usr/bin/env bash
# macOS: bash scripts/deploy-bart-first-reset-linef-v8.sh <run-id> <mister-host> [--allow-timing-fail]
# Timing-failed builds remain installable for explicit experimental testing only.
set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "Usage: bash $0 <v8 run id> <MiSTer hostname or IP> [--allow-timing-fail]" >&2
  exit 2
fi
RUN="$1"
HOST="$2"
ALLOW_FLAGS=()
if [ "${3:-}" = "--allow-timing-fail" ]; then
  ALLOW_FLAGS=(--allow-timing-fail)
elif [ "$#" -eq 3 ]; then
  echo "Unknown option: $3 (expected --allow-timing-fail)" >&2
  exit 2
fi
REPO="VectorLatch/mister-floppy-lab"
BRANCH="diagnostic/bart-first-reset-linef-v8"
FPGA="Minimig_Bart_ResetLineF_v8.rbf"
FPGA_SUM="Minimig_Bart_ResetLineF_v8.sha256"
MAIN="MiSTer_Physical-Floppy_BartResetLineFV8"
MAIN_SUM="$MAIN.sha256"
DIR="$HOME/Downloads/mister-floppy-lab/bart-first-reset-linef-v8/$RUN"

for bin in gh ssh scp python3 shasum; do
  command -v "$bin" >/dev/null || { echo "Missing command: $bin" >&2; exit 1; }
done
mkdir -p "$DIR/fpga" "$DIR/main"

# Validate the run *after downloading* the signed/hashed artifacts.
# Failed FPGA timing is usable only by explicit opt-in and only when
# compilation, Main, and every other job step succeeded.

ensure_file() {
  local group="$1" artifact="$2" name="$3"
  local dest="$DIR/$group/$name"
  if [ -s "$dest" ]; then return; fi
  if ! find "$DIR/$group" -type f -name "$name" -print -quit | grep -q .; then
    gh run download "$RUN" --repo "$REPO" --name "$artifact" --dir "$DIR/$group"
  fi
  if [ ! -s "$dest" ]; then
    local from
    from="$(find "$DIR/$group" -type f -name "$name" -print -quit)"
    if [ -z "$from" ]; then
      echo "Artifact missing: $name" >&2
      exit 1
    fi
    cp "$from" "$dest"
  fi
  test -s "$dest"
}
ensure_file fpga Bart-ResetLineF-FPGA-v8 "$FPGA"
ensure_file fpga Bart-ResetLineF-FPGA-v8 "$FPGA_SUM"
ensure_file main Bart-ResetLineF-Main-v8 "$MAIN"
ensure_file main Bart-ResetLineF-Main-v8 "$MAIN_SUM"
ensure_file fpga Bart-ResetLineF-FPGA-v8 "TIMING-STATUS.json"

(cd "$DIR/fpga" && shasum -a 256 -c "$FPGA_SUM")
(cd "$DIR/main" && shasum -a 256 -c "$MAIN_SUM")
python3 scripts/verify-bart-diagnostic-build.py \
  --repo "$REPO" --run "$RUN" \
  --branch "$BRANCH" \
  --workflow ".github/workflows/build-bart-first-reset-linef-v8.yml" \
  --status-json "$DIR/fpga/TIMING-STATUS.json" \
  --fpga-binary "$FPGA" "${ALLOW_FLAGS[@]}"

echo "Validated source build run $RUN, timing classification, job failure reasons and binary checksums."

scp "root@$HOST:/media/fat/MiSTer.ini" "$DIR/MiSTer.ini.before"
python3 - "$DIR/MiSTer.ini.before" "$DIR/MiSTer.ini.bart-v8" "$MAIN" <<'PY'
from pathlib import Path
import re,sys
data=Path(sys.argv[1]).read_bytes()
lines=data.splitlines(keepends=True)
in_minimig=False
section_seen=False
changed=0
for i,raw in enumerate(lines):
    stripped=raw.strip()
    m=re.match(rb'^\[([^\]]+)\]',stripped)
    if m:
        in_minimig=m.group(1).lower()==b'minimig'
        section_seen|=in_minimig
    elif in_minimig and re.match(rb'^main\s*=',stripped,re.I):
        eol=b'\r\n' if raw.endswith(b'\r\n') else b'\n'
        lines[i]=b'main='+sys.argv[3].encode()+eol
        changed+=1
if not section_seen or changed!=1:
    raise SystemExit(f'Expected one main= line in [Minimig]; found {changed}. Original ini unchanged.')
Path(sys.argv[2]).write_bytes(b''.join(lines))
PY

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="/media/fat/backup-floppy-lab/bart-reset-linef-v8-$STAMP"
ssh "root@$HOST" "set -e; mkdir -p '$BACKUP' /media/fat/_Unstable; cp -p /media/fat/MiSTer.ini '$BACKUP/MiSTer.ini'; if [ -e /media/fat/_Unstable/$FPGA ]; then cp -p /media/fat/_Unstable/$FPGA '$BACKUP/$FPGA'; fi; if [ -e /media/fat/$MAIN ]; then cp -p /media/fat/$MAIN '$BACKUP/$MAIN'; fi"
echo "$BACKUP" > "$DIR/remote-backup.txt"

scp "$DIR/fpga/$FPGA" "root@$HOST:/media/fat/_Unstable/$FPGA"
scp "$DIR/main/$MAIN" "root@$HOST:/media/fat/$MAIN"
scp "$DIR/MiSTer.ini.bart-v8" "root@$HOST:/media/fat/MiSTer.ini.bart-reset-linef-v8-tmp"
ssh "root@$HOST" "set -e; chmod +x /media/fat/$MAIN; mv /media/fat/MiSTer.ini.bart-reset-linef-v8-tmp /media/fat/MiSTer.ini; sync"
printf '\nInstalled experimental Bart first CPU RESET + Line-F trace v8.\n'
printf 'Backup: %s\n' "$BACKUP"
printf 'Reboot MiSTer, load _Unstable/%s, boot current Bart SPS 0884 Disk 2 IPF standalone. If it fails on first boot, preserve first-failure capture; for successful-after-F12 path, reset via F12 and capture at gameplay hang or Guru (do not reset before capture).\n' "$FPGA"
printf '\nWhen hung, capture on Mac:\n'
printf "ssh root@%s 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 3; touch /tmp/bart-snapshot.req; sleep 3; cat /tmp/bart-snapshots.txt'\n" "$HOST"
printf "scp root@%s:/tmp/bart-snapshots.txt \"\$HOME/Downloads/bart-first-reset-linef-v8.txt\"\n" "$HOST"
printf '\nRestore previous Main ini and restart MiSTer:\n'
printf "ssh root@%s \"cp -p '%s/MiSTer.ini' /media/fat/MiSTer.ini && sync\"\n" "$HOST" "$BACKUP"
printf 'Original Rick FPGA and original Physical Floppy Main executables were not overwritten.\n'
