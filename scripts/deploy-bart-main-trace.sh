#!/usr/bin/env bash
# macOS: bash scripts/deploy-bart-main-trace.sh <successful run ID> <MiSTer hostname>
# Installs a separate traced Main; changes only [Minimig] main=, safely backed up.
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "Usage: bash $0 <run ID> <MiSTer hostname or IP>" >&2
  exit 2
fi
RUN_ID="$1"; MISTER="$2"; REPO="VectorLatch/mister-floppy-lab"
FILE="MiSTer_Physical-Floppy_BartTrace"
BASE="$HOME/Downloads/mister-floppy-lab/bart-main-v1/$RUN_ID"
mkdir -p "$BASE"
for name in gh ssh scp python3 shasum find; do
  command -v "$name" >/dev/null || { echo "Missing required tool: $name" >&2; exit 1; }
done

BINARY="$(find "$BASE" -type f -name "$FILE" -print -quit)"
if [ -z "$BINARY" ]; then
  gh run download "$RUN_ID" --repo "$REPO" --name Bart-Main-Trace-v1 --dir "$BASE"
  BINARY="$(find "$BASE" -type f -name "$FILE" -print -quit)"
fi
if [ -z "$BINARY" ] || [ ! -s "$BINARY" ]; then
  echo "No nonempty diagnostic Main binary downloaded. Check that the build succeeded." >&2
  exit 1
fi
BINDIR="$(dirname "$BINARY")"
test -s "$BINDIR/$FILE.sha256" || { echo "Missing binary checksum"; exit 1; }
(cd "$BINDIR" && shasum -a 256 -c "$FILE.sha256")

scp "root@$MISTER:/media/fat/MiSTer.ini" "$BASE/MiSTer.ini.before-bart"
python3 - "$BASE/MiSTer.ini.before-bart" "$BASE/MiSTer.ini.traced" <<'PY'
import pathlib, re, sys
raw=pathlib.Path(sys.argv[1]).read_bytes()
new_line=b"main=MiSTer_Physical-Floppy_BartTrace"
lines=raw.splitlines(keepends=True)
in_minimig=False
found_section=False
found_main=False
for i, line in enumerate(lines):
    stripped=line.strip()
    m=re.match(rb"^\s*\[([^\]]+)\]", stripped)
    if m:
        in_minimig=(m.group(1).strip().lower()==b"minimig")
        if in_minimig:
            found_section=True
        continue
    if in_minimig and re.match(rb"^\s*main\s*=", stripped, re.I):
        nl=b"\r\n" if line.endswith(b"\r\n") else b"\n"
        lines[i]=new_line+nl
        found_main=True
if not found_section or not found_main:
    raise SystemExit("Expected existing [Minimig] main=... entry. Refusing to edit the ini.")
out=b"".join(lines)
pathlib.Path(sys.argv[2]).write_bytes(out)
print("Prepared change of the existing [Minimig] main= entry only.")
PY

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="/media/fat/backup-floppy-lab/bart-main-v1-$STAMP"
ssh "root@$MISTER" "set -e; mkdir -p '$BACKUP'; cp -p /media/fat/MiSTer.ini '$BACKUP/MiSTer.ini'; if [ -f /media/fat/$FILE ]; then cp -p /media/fat/$FILE '$BACKUP/$FILE'; fi"
echo "$BACKUP" > "$BASE/remote-backup-path.txt"
echo "Remote backup path: $BACKUP"
scp "$BINARY" "root@$MISTER:/media/fat/$FILE"
scp "$BASE/MiSTer.ini.traced" "root@$MISTER:/media/fat/MiSTer.ini.bart-tmp"
ssh "root@$MISTER" "set -e; chmod +x '/media/fat/$FILE'; mv /media/fat/MiSTer.ini.bart-tmp /media/fat/MiSTer.ini; sync; grep -A4 -i '^\[Minimig\]' /media/fat/MiSTer.ini | head -n 5"
echo "Diagnostic Main installed. Exit/relaunch Minimig_Rick_ERSY_v4_20261116 from _Unstable."
echo "Original Physical-Floppy v1.3 and the Rick FPGA remain untouched."
echo "Rollback (from Mac Terminal):"
echo "ssh root@$MISTER \"cp -p '$BACKUP/MiSTer.ini' /media/fat/MiSTer.ini && sync\""
