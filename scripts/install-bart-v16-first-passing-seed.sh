#!/usr/bin/env bash
# macOS: select first available strictly successful FPGA seed and shared Main.
# Other matrix seeds may still be running.
# Usage: bash scripts/install-bart-v16-first-passing-seed.sh <run-id> [mister-host]
set -euo pipefail
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: bash $0 <v16-run-id> [mister-host]" >&2
  exit 2
fi
RUN="$1"
HOST="mister"
if [ "$#" -eq 2 ]; then HOST="$2"; fi
REPO="VectorLatch/mister-floppy-lab"
command -v gh >/dev/null || { echo "Install GitHub CLI (gh) first" >&2; exit 1; }
JOBS="$(gh api "repos/$REPO/actions/runs/$RUN/jobs?per_page=100")"
SEED="$(printf '%s' "$JOBS" | python3 -c '
import json,sys
jobs=json.load(sys.stdin).get("jobs",[])
main=[j for j in jobs if j.get("name","").startswith("Physical Floppy Main v16 completion-wait controller")]
if len(main)!=1 or main[0].get("conclusion")!="success":
    print("")
    sys.exit(0)
prefix="Rick-fixed Bart v16 completion-wait FPGA / fitter seed "
for seed in (31,17,13,27,3,41):
    matches=[j for j in jobs if j.get("name")==prefix+str(seed)]
    if len(matches)==1 and matches[0].get("status")=="completed" and matches[0].get("conclusion")=="success":
        print(seed)
        break
else:
    print("")
')"
if [ -z "$SEED" ]; then
  echo "No completed timing-clean v16 seed with successful Main is available in run $RUN." >&2
  echo "MiSTer unchanged. Check: gh run view $RUN --repo $REPO --json jobs" >&2
  exit 1
fi
echo "First available clean selected seed: $SEED (full matrix need not be finished)."
echo "Installer independently verifies source, jobs, checksums and all five timing margins."
bash scripts/install-bart-v16-selected-seed.sh "$RUN" "$SEED" "$HOST"
