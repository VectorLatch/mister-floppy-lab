# Rick Dangerous ERSY v4 — controlled regression experiment

**Status:** Experimental, not yet re-tested on current upstream Minimig hardware. Do not merge until first-boot, regression, and timing results are all recorded.

## Why this experiment exists

The unmodified pinned Minimig baseline (2026-11-09 commit `7d5d3c2f685af4ce3eb361c22893fccd153f2d87`), with released Physical Floppy Main v1.3, was tested on a MiSTer Multisystem2 + Greaseweazle on 2026-11-16. Lemmings loads; Rick Dangerous still requires F12 Reset to boot.

Earlier testing (old repo, `experiment/ersy-beam-escape-v4`, FPGA based on `c5ffbf97b6496f50947b54f75efda10a45fedf7c`) identified the following mechanism: ERSY becomes set, HPOS is trapped at zero, and horizontal beam advancement and DMA scheduling stall. F12 Reset clears ERSY. The old v4 build with fitter seed 4 booted Rick Dangerous on its first attempt (A500, Kickstart 1.3); the later v7 seed 9 also worked. These are **old-hardware-baseline observations**, not current-port test results.

## Exact functional patch

Only `rtl/agnus_beamcounter.v` is changed:

```diff
-        else if (cck && (~ersy || |hpos[8:1]))
+        else if (cck)
```

No previous diagnostic HDL, debug registers, altered Main, Bart-related instruction modifications, or other changes were carried forward. Physical Floppy Main v1.3 stays installed.

**Caution:** This is the previously proven *bypass*, not a proven hardware-accurate implementation of external sync/genlock. The original experiment explicitly warned that forcing the beam counter to advance while ERSY is asserted changes legitimate genlock behaviour. Treat it as an intermediate compatibility improvement pending a more exact root-cause fix.

## Build

The dedicated `.github/workflows/build-rick-ersy-v4.yml` builds this patch against the pinned *current* baseline, using only fitter seed **4** (the seed proven in the old v4 investigation). It checks that exactly one RTL line changed, parses setup/hold/recovery/removal/minimum-pulse-width slacks, and uploads an RBF **only if timing is clean**.

The build creates artifact `Minimig-Rick-ERSY-v4`, with `Minimig_Rick_ERSY_v4_20261116.rbf`, the checksum, compilation log, timing reports and source provenance.

From macOS Terminal, once the dedicated job succeeds:

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin experiment/rick-ersy-v4
git switch --track origin/experiment/rick-ersy-v4
gh run list --repo VectorLatch/mister-floppy-lab --workflow build-rick-ersy-v4.yml --branch experiment/rick-ersy-v4 --limit 5
# Use the successful build's actual numeric run ID:
bash ./scripts/download-rick-ersy-v4.sh RUN_ID mister
```

The deployment script adds a distinctly named core to `/media/fat/_Unstable`. It does **not** edit `MiSTer.ini`, overwrite the baseline RBF, or alter either Main binary. The already configured `[Minimig] main=MiSTer_Physical-Floppy` continues to apply.

## On-device testing

1. Retain the installed stable clean baseline `Minimig_Lab_20261116.rbf` for A/B comparison.
2. Select the new `_Unstable/Minimig_Rick_ERSY_v4_20261116` core.
3. Use A500, Kickstart 1.3, PAL, OCS, 512 KB Chip + 512 KB Slow RAM.
4. Test Rick Dangerous **from first cold boot** using the same known test IPF image. Record whether the intro/loading begins and gameplay starts without F12 Reset. Repeat at least three times.
5. Repeat with Greaseweazle physical floppy in read-only `_GREASEWEAZLE_.adf` flux mode. Do not put an original floppy in write-enabled AmigaDOS mode.
6. Repeat Lemmings from the original physical floppy to check for regression.
7. If any failure occurs, record screen symptoms, the sequence and log from `/media/fat/logs/pfloppy.log`. To download the log on your Mac:

```bash
scp root@mister:/media/fat/logs/pfloppy.log "$HOME/Downloads/rick-ersy-v4-pfloppy.log"
```

8. Restore the clean baseline simply by selecting `Minimig_Lab_20261116` again.

**Decision rule:** Do not merge this bypass to main until the new FPGA build passes all timing checks, Rick boots without reset on both media, and Lemmings still works. Even then it should be labelled experimental and its external-sync limitation documented.
