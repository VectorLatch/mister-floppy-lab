#!/usr/bin/env bash
# macOS: bash scripts/install-bart-v14-selected-seed.sh <run-id> <seed> <mister-host> [--allow-timing-fail]
# Timing-failed builds remain installable for explicit experimental testing only.
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo "Usage: bash $0 <v14 split timing run id> <seed 3,13,17,27,31,41> <MiSTer hostname or IP> [--allow-timing-fail]" >&2
  exit 2
fi
RUN="$1"
SEED="$2"
HOST="$3"
if ! [[ "$SEED" =~ ^(3|13|17|27|31|41)$ ]]; then
  echo "Expected one of v14 seeds 3,13,17,27,31,41; got: $SEED" >&2
  exit 2
fi
ALLOW_TIMING_FAIL=0
if [ "${4:-}" = "--allow-timing-fail" ]; then
  ALLOW_TIMING_FAIL=1
elif [ "$#" -eq 4 ]; then
  echo "Unknown option: $4 (expected --allow-timing-fail)" >&2
  exit 2
fi
REPO="VectorLatch/mister-floppy-lab"
BRANCH="experiment/bart-timing-controls-v14"
FPGA="Minimig_Bart_Timing_v14_seed${SEED}.rbf"
FPGA_SUM="${FPGA}.sha256"
MAIN="MiSTer_Physical-Floppy_BartTimingV14"
MAIN_SUM="$MAIN.sha256"
DIR="$HOME/Downloads/mister-floppy-lab/bart-v14-timing/$RUN/seed-$SEED"

for bin in gh ssh scp python3 shasum; do
  command -v "$bin" >/dev/null || { echo "Missing command: $bin" >&2; exit 1; }
done
mkdir -p "$DIR/fpga" "$DIR/main"

# Validate the run *after downloading* the signed/hashed artifacts.
# Failed FPGA timing is usable only by explicit opt-in and only when
# compilation, Main, and every other job step succeeded.

# gh run download refuses to overwrite paths previously extracted by an
# interrupted run ("openat ... file exists"). Always extract a complete
# artifact ONCE into a brand-new empty mktemp directory, then copy only
# named candidates to deterministic local paths. This is idempotent and
# never extracts ZIP entries into an old partial download.
download_artifact() {
  local group="$1" artifact="$2"
  shift 2
  local dest="$DIR/$group"
  local name src stage
  mkdir -p "$dest"
  local complete=1
  for name in "$@"; do
    if [ ! -s "$dest/$name" ]; then complete=0; break; fi
  done
  if [ "$complete" -eq 1 ]; then
    echo "Reusing complete local $artifact download."
    return 0
  fi

  stage="$(mktemp -d "$DIR/.download-$group.XXXXXXXX")"
  echo "Downloading $artifact into clean staging directory..."
  if ! gh run download "$RUN" --repo "$REPO" --name "$artifact" --dir "$stage"; then
    rm -rf -- "$stage"
    echo "Failed downloading $artifact. MiSTer remains unchanged." >&2
    exit 1
  fi

  # Validate every required archive member exists before copying
  # anything into the installation directory.
  for name in "$@"; do
    src="$(find "$stage" -type f -name "$name" -print -quit)"
    if [ -z "$src" ] || [ ! -s "$src" ]; then
      rm -rf -- "$stage"
      echo "Artifact $artifact missing nonempty file $name" >&2
      exit 1
    fi
  done
  for name in "$@"; do
    src="$(find "$stage" -type f -name "$name" -print -quit)"
    cp -f -- "$src" "$dest/$name"
  done
  rm -rf -- "$stage"
}
download_artifact fpga "Bart-Timing-FPGA-v14-seed${SEED}" \
  "$FPGA" "$FPGA_SUM" "TIMING-STATUS.json"
download_artifact main Bart-Timing-Main-v14 \
  "$MAIN" "$MAIN_SUM"

(cd "$DIR/fpga" && shasum -a 256 -c "$FPGA_SUM")
(cd "$DIR/main" && shasum -a 256 -c "$MAIN_SUM")
# macOS ships Bash 3.2, where expanding an *empty* array with
# set -u raises "unbound variable". VERIFY_ARGS is always nonempty.
VERIFY_ARGS=(
  --repo "$REPO" --run "$RUN" --seed "$SEED"
  --branch "$BRANCH"
  --workflow ".github/workflows/build-bart-v14-timing-controls.yml"
  --status-json "$DIR/fpga/TIMING-STATUS.json"
  --fpga-binary "$FPGA"
)
if [ "$ALLOW_TIMING_FAIL" -eq 1 ]; then
  VERIFY_ARGS+=(--allow-timing-fail)
fi
python3 scripts/verify-bart-v14-selected-seed.py "${VERIFY_ARGS[@]}"

echo "Validated source build run $RUN, timing classification, job failure reasons and binary checksums."

scp "root@$HOST:/media/fat/MiSTer.ini" "$DIR/MiSTer.ini.before"
python3 - "$DIR/MiSTer.ini.before" "$DIR/MiSTer.ini.bart-v14-timing" "$MAIN" <<'PY'
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
BACKUP="/media/fat/backup-floppy-lab/bart-v14-timing-seed${SEED}-$STAMP"
ssh "root@$HOST" "set -e; mkdir -p '$BACKUP' /media/fat/_Unstable; cp -p /media/fat/MiSTer.ini '$BACKUP/MiSTer.ini'; if [ -e /media/fat/_Unstable/$FPGA ]; then cp -p /media/fat/_Unstable/$FPGA '$BACKUP/$FPGA'; fi; if [ -e /media/fat/$MAIN ]; then cp -p /media/fat/$MAIN '$BACKUP/$MAIN'; fi"
echo "$BACKUP" > "$DIR/remote-backup.txt"

scp "$DIR/fpga/$FPGA" "root@$HOST:/media/fat/_Unstable/$FPGA"
scp "$DIR/main/$MAIN" "root@$HOST:/media/fat/$MAIN"
scp "$DIR/MiSTer.ini.bart-v14-timing" "root@$HOST:/media/fat/MiSTer.ini.bart-v14-timing-tmp"
ssh "root@$HOST" "set -e; chmod +x /media/fat/$MAIN; mv /media/fat/MiSTer.ini.bart-v14-timing-tmp /media/fat/MiSTer.ini; sync"
printf '\nInstalled Bart v14 adjustable split CPU-bus timing / seed %s.\n' "$SEED"
printf 'Backup: %s\n' "$BACKUP"
printf 'Reboot MiSTer, load _Unstable/%s, boot current Bart SPS 0884 Disk 2 IPF standalone. Keep A500+ KS2 ECS and same Bart SPS0884 Disk2. First restore known base 1/0 with all extras 0: bash scripts/set-bart-v14-timing.sh 1 0 0 0 0 0 mister on the Mac, then F12 Reset before the game. Change settings without rebuilding.\n' "$FPGA"
printf '\nWhen hung, capture on Mac:\n'
printf "ssh root@%s 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 3; touch /tmp/bart-snapshot.req; sleep 3; cat /tmp/bart-snapshots.txt'\n" "$HOST"
printf "scp root@%s:/tmp/bart-snapshots.txt \"\$HOME/Downloads/bart-v14-seed${SEED}.txt\"\n" "$HOST"
printf '\nRestore previous Main ini and restart MiSTer:\n'
printf "ssh root@%s \"cp -p '%s/MiSTer.ini' /media/fat/MiSTer.ini && sync\"\n" "$HOST" "$BACKUP"
printf 'Prior v11/v12/v13 Main binaries are preserved; restore previous MiSTer.ini if needed.\n'
