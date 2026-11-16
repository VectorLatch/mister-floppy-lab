#!/usr/bin/env bash
# Mac: ./scripts/download-rick-ersy-v4.sh <ACTIONS_RUN_ID> <MISTER_HOST>
# FPGA-only deployment: does not modify MiSTer.ini or Physical Floppy Main.
set -euo pipefail
if [ "$#" -ne 2 ]; then echo "Usage: $0 <Rick workflow run ID> <MiSTer host>" >&2; exit 2; fi
RUN_ID="$1"; MISTER="$2"; REPO="VectorLatch/mister-floppy-lab"
NAME="Minimig_Rick_ERSY_v4_20261116.rbf"; ARTIFACT="Minimig-Rick-ERSY-v4"
BASE="$HOME/Downloads/mister-floppy-lab/rick-ersy-v4/$RUN_ID"
mkdir -p "$BASE"
for c in gh ssh scp shasum find; do command -v "$c" >/dev/null || { echo "Missing: $c" >&2; exit 1; }; done
CORE="$(find "$BASE" -type f -name "$NAME" -print -quit)"
if [ -z "$CORE" ]; then
  gh run download "$RUN_ID" --repo "$REPO" --name "$ARTIFACT" --dir "$BASE"
  CORE="$(find "$BASE" -type f -name "$NAME" -print -quit)"
fi
if [ -z "$CORE" ] || [ ! -s "$CORE" ]; then echo "No nonempty $NAME in the artifact" >&2; exit 1; fi
CORE_DIR="$(dirname "$CORE")"
CHECKSUM="${NAME%.rbf}.sha256"
test -s "$CORE_DIR/$CHECKSUM" || { echo "Missing checksum file" >&2; exit 1; }
(cd "$CORE_DIR" && shasum -a 256 -c "$CHECKSUM")
echo "Verified FPGA core: $CORE"
ssh "root@$MISTER" 'set -e; test -s /media/fat/MiSTer_Physical-Floppy; test -s /media/fat/MiSTer.ini; mkdir -p /media/fat/_Unstable'
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="/media/fat/backup-floppy-lab/rick-ersy-v4-$STAMP"
ssh "root@$MISTER" "set -e; mkdir -p '$BACKUP'; if [ -f '/media/fat/_Unstable/$NAME' ]; then cp -p '/media/fat/_Unstable/$NAME' '$BACKUP/$NAME'; fi"
echo "Old Rick experiment binary backed up to $BACKUP if one existed"
scp "$CORE" "root@$MISTER:/media/fat/_Unstable/$NAME"
ssh "root@$MISTER" "set -e; test -s '/media/fat/_Unstable/$NAME'; sync; ls -lh '/media/fat/_Unstable/$NAME'"
echo "FPGA-only deployment complete: select _Unstable / Minimig_Rick_ERSY_v4_20261116"
echo "Original baseline core, Main, and MiSTer.ini remain unchanged"
