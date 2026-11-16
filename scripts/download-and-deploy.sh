#!/usr/bin/env bash
# Run on the MAC, not on the MiSTer: ./scripts/download-and-deploy.sh <GITHUB_RUN_ID> <MISTER_IP_OR_HOST>
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <successful GitHub Actions run ID> <MiSTer IP/host>" >&2
  exit 2
fi
RUN_ID="$1"; MISTER="$2"; REPO='VectorLatch/mister-floppy-lab'
for cmd in gh curl shasum ssh scp python3; do
  command -v "$cmd" >/dev/null || { echo "Required command not found: $cmd" >&2; exit 1; }
done
BASE="${HOME}/Downloads/mister-floppy-lab/${RUN_ID}"
mkdir -p "$BASE"
cd "$BASE"
echo "Fetching FPGA build artifacts from $REPO run $RUN_ID ..."
# GitHub's artifact may contain dist/ because upload-artifact used multiple path roots.
# Reuse already-downloaded files, including downloads from before this fix.
CORE="$(find "$BASE/core" -type f -name 'Minimig_Lab_20261116.rbf' -print -quit 2>/dev/null || true)"
if [ -z "$CORE" ]; then
  gh run download "$RUN_ID" --repo "$REPO" --name 'Minimig-Lab-baseline' --dir "$BASE/core"
  CORE="$(find "$BASE/core" -type f -name 'Minimig_Lab_20261116.rbf' -print -quit)"
fi
if [ -z "$CORE" ] || [ ! -s "$CORE" ]; then
  echo "No nonempty Minimig_Lab_20261116.rbf in downloaded artifact. Check its contents under $BASE/core" >&2
  exit 1
fi
CORE_DIR="$(dirname "$CORE")"
test -s "$CORE_DIR/Minimig_Lab_20261116.sha256" || { echo "Missing core checksum next to $CORE" >&2; exit 1; }
(cd "$CORE_DIR" && shasum -a 256 -c Minimig_Lab_20261116.sha256)
echo "Verified FPGA core: $CORE"
echo 'Downloading official Physical Floppy v1.3 binary (not an unverified source-built version) ...'
curl -fL --retry 3 -o "$BASE/MiSTer_Physical-Floppy" 'https://github.com/manfredi90/Main_MiSTer_Physical_Floppy/releases/download/v1.3/MiSTer_Physical-Floppy'
printf '%s  %s\n' '4420074539883d8fcd43ac53eff7ebc6168b047356ada9a0a524f825b44d186f' 'MiSTer_Physical-Floppy' > "$BASE/MiSTer_Physical-Floppy.sha256"
(cd "$BASE" && shasum -a 256 -c MiSTer_Physical-Floppy.sha256)
echo 'Collecting current MiSTer.ini (the live config is backed up before editing) ...'
scp "root@${MISTER}:/media/fat/MiSTer.ini" "$BASE/MiSTer.ini.original"
cp "$BASE/MiSTer.ini.original" "$BASE/MiSTer.ini.new"
python3 - "$BASE/MiSTer.ini.new" <<'PY'
import pathlib,re,sys
path=pathlib.Path(sys.argv[1]); raw=path.read_bytes()
# Preserve line endings and avoid modifying encodings the editor cannot safely read.
newline='\r\n' if b'\r\n' in raw else '\n'
text=raw.decode('latin-1').replace('\r\n','\n')
lines=text.splitlines(keepends=True)
section=re.compile(r'^\s*\[([^\]]+)\]')
start=next((i for i,line in enumerate(lines) if (m:=section.match(line)) and m.group(1).strip().lower()=='minimig'),None)
if start is None:
    if lines and not lines[-1].endswith('\n'): lines[-1]+='\n'
    lines.extend(['\n','[Minimig]\n','main=MiSTer_Physical-Floppy\n','PFLOPPY_LOG=1\n'])
else:
    end=next((i for i in range(start+1,len(lines)) if section.match(lines[i])),len(lines))
    kept=[line for line in lines[start+1:end] if not re.match(r'^\s*(main|PFLOPPY_LOG)\s*=',line,re.I)]
    lines[start+1:end]=['main=MiSTer_Physical-Floppy\n','PFLOPPY_LOG=1\n']+kept
path.write_bytes(''.join(lines).replace('\n',newline).encode('latin-1'))
PY
# Back up both exact remote binary paths and the ini before any changes.
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="/media/fat/backup-floppy-lab/${STAMP}"
ssh "root@${MISTER}" "set -e; mkdir -p '$BACKUP' /media/fat/_Unstable; cp -p /media/fat/MiSTer.ini '$BACKUP/MiSTer.ini'; if [ -f /media/fat/MiSTer_Physical-Floppy ]; then cp -p /media/fat/MiSTer_Physical-Floppy '$BACKUP/MiSTer_Physical-Floppy'; fi; if [ -f /media/fat/_Unstable/Minimig_Lab_20261116.rbf ]; then cp -p /media/fat/_Unstable/Minimig_Lab_20261116.rbf '$BACKUP/Minimig_Lab_20261116.rbf'; fi"
echo "Backups saved to MiSTer: ${BACKUP}"
# Copy binary and core, then atomically replace the ini.
scp "$BASE/MiSTer_Physical-Floppy" "root@${MISTER}:/media/fat/MiSTer_Physical-Floppy"
scp "$CORE" "root@${MISTER}:/media/fat/_Unstable/Minimig_Lab_20261116.rbf"
scp "$BASE/MiSTer.ini.new" "root@${MISTER}:/media/fat/MiSTer.ini.floppy-lab-tmp"
ssh "root@${MISTER}" 'set -e; mv /media/fat/MiSTer.ini.floppy-lab-tmp /media/fat/MiSTer.ini; chmod +x /media/fat/MiSTer_Physical-Floppy || true; sync; grep -A4 -i "^\[Minimig\]" /media/fat/MiSTer.ini | head -n 5'
echo 'Deployment completed. In the MiSTer menu, launch the lab core in _Unstable.'
echo 'For rollback, restore files from the backup folder printed above.'
