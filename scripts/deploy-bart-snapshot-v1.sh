#!/usr/bin/env bash
# macOS:
# bash scripts/deploy-bart-snapshot-v1.sh <successful-build-run-id> <mister-host>
# Only after both jobs succeed, and FPGA setup/hold/recovery/removal/pulse timing passes.
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "Usage: bash $0 <successful run ID> <MiSTer hostname/IP>" >&2
  exit 2
fi
RUN="$1"
HOST="$2"
REPO="VectorLatch/mister-floppy-lab"
FPGA="Minimig_Bart_CPU_Paula_Diag_v1.rbf"
MAIN="MiSTer_Physical-Floppy_BartSnapshot"
DIR="$HOME/Downloads/mister-floppy-lab/bart-snapshot/$RUN"
mkdir -p "$DIR/fpga" "$DIR/main"
for bin in gh ssh scp python3 shasum; do
  command -v "$bin" >/dev/null 2>&1 || { echo "Missing $bin" >&2; exit 1; }
done

# github API status gate: no installing while build is pending or failed.
RUN_JSON="$(gh api "repos/$REPO/actions/runs/$RUN")"
python3 -c 'import json,sys; j=json.loads(sys.stdin.read()); assert j["status"]=="completed" and j["conclusion"]=="success", "GitHub build not successful"' <<< "$RUN_JSON"

if [ ! -s "$DIR/fpga/$FPGA" ]; then
  gh run download "$RUN" --repo "$REPO" --name Bart-FPGA-Snapshot-v1 --dir "$DIR/fpga"
fi
if [ ! -s "$DIR/main/$MAIN" ]; then
  gh run download "$RUN" --repo "$REPO" --name Bart-Main-Snapshot-v1 --dir "$DIR/main"
fi
test -s "$DIR/fpga/$FPGA"
test -s "$DIR/fpga/$FPGA.sha256"
test -s "$DIR/main/$MAIN"
test -s "$DIR/main/$MAIN.sha256"
(cd "$DIR/fpga" && shasum -a 256 -c "$FPGA.sha256")
(cd "$DIR/main" && shasum -a 256 -c "$MAIN.sha256")

scp "root@$HOST:/media/fat/MiSTer.ini" "$DIR/MiSTer.ini.before"
python3 - "$DIR/MiSTer.ini.before" "$DIR/MiSTer.ini.bart" "$MAIN" <<'PY'
from pathlib import Path
import sys,re
before=Path(sys.argv[1]).read_bytes()
value=("main="+sys.argv[3]).encode()
lines=before.splitlines(keepends=True)
found_section=found_key=False
in_section=False
for i,raw in enumerate(lines):
    token=raw.strip()
    section=re.match(rb"^\[([^\]]+)\]",token)
    if section:
        in_section=(section.group(1).lower()==b"minimig")
        found_section|=in_section
        continue
    if in_section and re.match(rb"^main\s*=",token,re.I):
        newline=b"\r\n" if raw.endswith(b"\r\n") else b"\n"
        lines[i]=value+newline
        found_key=True
if not found_section or not found_key:
    raise SystemExit("No existing [Minimig] main= setting; refusing to change ini.")
Path(sys.argv[2]).write_bytes(b"".join(lines))
PY
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="/media/fat/backup-floppy-lab/bart-fpga-v1-$STAMP"
ssh "root@$HOST" "set -e; mkdir -p '$BACKUP'; cp -p /media/fat/MiSTer.ini '$BACKUP/MiSTer.ini'; if [ -e /media/fat/_Unstable/$FPGA ]; then cp -p /media/fat/_Unstable/$FPGA '$BACKUP/$FPGA'; fi; if [ -e /media/fat/$MAIN ]; then cp -p /media/fat/$MAIN '$BACKUP/$MAIN'; fi"
echo "$BACKUP" > "$DIR/remote-backup.txt"
scp "$DIR/fpga/$FPGA" "root@$HOST:/media/fat/_Unstable/$FPGA"
scp "$DIR/main/$MAIN" "root@$HOST:/media/fat/$MAIN"
scp "$DIR/MiSTer.ini.bart" "root@$HOST:/media/fat/MiSTer.ini.bart-tmp"
ssh "root@$HOST" "set -e; chmod +x /media/fat/$MAIN; mv /media/fat/MiSTer.ini.bart-tmp /media/fat/MiSTer.ini; sync; grep -A3 -i '^\[Minimig\]' /media/fat/MiSTer.ini"
echo ""
echo "Reload core _Unstable/$FPGA in MiSTer, select exact SPS 0884 Bart Disk 2 IPF."
echo "After hang, from macOS Terminal:"
echo "ssh root@$HOST 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 2; touch /tmp/bart-snapshot.req; sleep 2; cat /tmp/bart-snapshots.txt'"
echo "Restore original Main when finished:"
echo "ssh root@$HOST \"cp -p '$BACKUP/MiSTer.ini' /media/fat/MiSTer.ini && sync\""
echo "Original Rick FPGA & original released Main are never overwritten."
