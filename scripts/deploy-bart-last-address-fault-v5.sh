#!/usr/bin/env bash
# macOS: bash scripts/deploy-bart-last-address-fault-v5.sh <successful-run-id> <mister-host>
# Experimental FPGA has explicitly relaxed setup slack (not production-safe).
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: bash $0 <successful v5 run id> <MiSTer hostname or IP>" >&2
  exit 2
fi
RUN="$1"
HOST="$2"
REPO="VectorLatch/mister-floppy-lab"
BRANCH="diagnostic/bart-last-address-fault-v5"
FPGA="Minimig_Bart_LastFault_v5.rbf"
FPGA_SUM="Minimig_Bart_LastFault_v5.sha256"
MAIN="MiSTer_Physical-Floppy_BartFaultV5"
MAIN_SUM="$MAIN.sha256"
DIR="$HOME/Downloads/mister-floppy-lab/bart-last-address-fault-v5/$RUN"

for bin in gh ssh scp python3 shasum; do
  command -v "$bin" >/dev/null || { echo "Missing command: $bin" >&2; exit 1; }
done
mkdir -p "$DIR/fpga" "$DIR/main"

RUN_JSON="$(gh api "repos/$REPO/actions/runs/$RUN")"
python3 -c '
import json,sys
r=json.load(sys.stdin)
assert r["status"]=="completed" and r["conclusion"]=="success", "No successful build"
assert r["head_branch"]=="diagnostic/bart-last-address-fault-v5", "Wrong experiment branch"
assert r["path"]==".github/workflows/build-bart-last-address-fault-v5.yml", "Wrong build workflow"
' <<< "$RUN_JSON"

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
ensure_file fpga Bart-LastFault-FPGA-v5 "$FPGA"
ensure_file fpga Bart-LastFault-FPGA-v5 "$FPGA_SUM"
ensure_file main Bart-LastFault-Main-v5 "$MAIN"
ensure_file main Bart-LastFault-Main-v5 "$MAIN_SUM"

(cd "$DIR/fpga" && shasum -a 256 -c "$FPGA_SUM")
(cd "$DIR/main" && shasum -a 256 -c "$MAIN_SUM")
echo "Validated source build run $RUN and binary checksums."

scp "root@$HOST:/media/fat/MiSTer.ini" "$DIR/MiSTer.ini.before"
python3 - "$DIR/MiSTer.ini.before" "$DIR/MiSTer.ini.bart-v5" "$MAIN" <<'PY'
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
BACKUP="/media/fat/backup-floppy-lab/bart-lastfault-v5-$STAMP"
ssh "root@$HOST" "set -e; mkdir -p '$BACKUP' /media/fat/_Unstable; cp -p /media/fat/MiSTer.ini '$BACKUP/MiSTer.ini'; if [ -e /media/fat/_Unstable/$FPGA ]; then cp -p /media/fat/_Unstable/$FPGA '$BACKUP/$FPGA'; fi; if [ -e /media/fat/$MAIN ]; then cp -p /media/fat/$MAIN '$BACKUP/$MAIN'; fi"
echo "$BACKUP" > "$DIR/remote-backup.txt"

scp "$DIR/fpga/$FPGA" "root@$HOST:/media/fat/_Unstable/$FPGA"
scp "$DIR/main/$MAIN" "root@$HOST:/media/fat/$MAIN"
scp "$DIR/MiSTer.ini.bart-v5" "root@$HOST:/media/fat/MiSTer.ini.bart-lastfault-v5-tmp"
ssh "root@$HOST" "set -e; chmod +x /media/fat/$MAIN; mv /media/fat/MiSTer.ini.bart-lastfault-v5-tmp /media/fat/MiSTer.ini; sync"
printf '\nInstalled experimental Bart latest two odd-address events diagnostic v5.\n'
printf 'Backup: %s\n' "$BACKUP"
printf 'Reboot MiSTer, load _Unstable/%s, boot original SPS 0884 Disk2 IPF.\n' "$FPGA"
printf '\nWhen hung, capture on Mac:\n'
printf "ssh root@%s 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 3; touch /tmp/bart-snapshot.req; sleep 3; cat /tmp/bart-snapshots.txt'\n" "$HOST"
printf "scp root@%s:/tmp/bart-snapshots.txt \"\$HOME/Downloads/bart-last-address-fault-v5.txt\"\n" "$HOST"
printf '\nRestore previous Main ini and restart MiSTer:\n'
printf "ssh root@%s \"cp -p '%s/MiSTer.ini' /media/fat/MiSTer.ini && sync\"\n" "$HOST" "$BACKUP"
printf 'Original Rick FPGA and original Physical Floppy Main executables were not overwritten.\n'
