# Bart SPS 0884 Disk 2 — CPU RESET output / first Line-F exception diagnostic v8

## This investigation (keep distinct from old Disk 1/Ocean issue)

For the current SPS 0884 Bart release, Disk 1 loads correctly on Minimig and Amiberry. Disk 2 can boot standalone on Amiberry but normally reaches an internal fx68k CPU HALT on Minimig. After a full MiSTer reboot followed by an F12 Minimig reset, the *same v7 FPGA* has twice progressed further into the game. On one full post-F12 run the user captured three stages with increasing CPU fetch counts (159 million -> 219 million -> 389 million); the CPU was still executing at all three stages. The Amiga eventually displayed Software Failure 8000 000B, a Line-F exception. Paula floppy counters reset between stages 1 and 2 while the CPU fetch counter continued; an asserted fx68k RESET output could explain that, but has **not been observed directly**.

## What v8 measures

The first real Line-F recognition in fx68k's sequencer (grp1LatchEn AND enT3 AND isLineF) and the first and most recent CPU RESET output assertions before Line-F. The CPU RESET output is separate from the CPU reset input. Snapshots include internal PC, real decoded macro-opcode Ir, PSW, last two external program-space bus fetch addresses, and Minimig's Kickstart overlay state at RESET / Line-F. First Line-F event and preceding RESET context are frozen; subsequent ROM activity cannot overwrite them.

The actual cause of an F-line exception remains unknown. This recorder is strictly observation-only: no changes to CPU microcode/functional control, memory/bus paths, Paula, physical-floppy logic, actual IPF data, or reset/overlay control.

## Exact source dependencies and implementation

- FPGA upstream pinned 7d5d3c2f685af4ce3eb361c22893fccd153f2d87
- Working Rick ERSY v4 fix preserved
- Previous Bart read-only FPGA overlays v1, v2, v3, v6 applied in order; then scripts/patch_bart_fpga_first_reset_linef_v8.py
- Paired Main upstream pinned d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2 with Main v1, v2, v3, v6, then scripts/patch_bart_main_first_reset_linef_v8.py
- v4/v5 address-error and v7 vector-input overlays are deliberately NOT applied to v8
- E7xx on-demand SPI is 64 words, signature B4AD, version 8. Existing v1/v2/v3 fields 0..44 retain identical meaning; v6 slots 45..63 repurposed for reset/Line-F event data. Must use the matching Main v8.

v8 exported fields:
- EV_FLAGS, EV_RESET_COUNT (saturates at 255), EV_RESET_SEEN, EV_LINEF_SEEN
- EV_RESET_OVL and EV_LINEF_OVL (overlay before respective event), EV_LINEF_AFTER_RESET
- EV_OVL_LIVE, EV_RESET_OUT_LOW (live state on read)
- EV_RESET_FIRST_PC, EV_RESET_LAST_PC
- EV_RESET_FETCH, EV_RESET_PREV, EV_RESET_PSW, EV_RESET_IR
- EV_LINEF_PC, EV_LINEF_FETCH, EV_LINEF_PREV, EV_LINEF_PSW, EV_LINEF_IR

EV_FLAGS bits: 0 reset seen; 1 lineF seen; 2 ovl at last reset; 3 ovl at LineF; 4 reset already seen at LineF; 5 CPU RESET output low at LineF; 6 live ovl; 7 live CPU RESET low; 15:8 saturated reset count. PC values are microarchitectural registers sampled at an event and need not be retired architectural instruction PCs. Ir is the actual decoded opcode register, rather than possibly older Ird.

## Build

Branch diagnostic/bart-first-reset-linef-v8. Workflow .github/workflows/build-bart-first-reset-linef-v8.yml. GitHub run https://github.com/VectorLatch/mister-floppy-lab/actions/runs/44070812609.

FPGA fitter exactly one seed 6 for the current retry. All worst-case setup, hold, recovery, removal and minimum pulse-width margins are still checked strictly: failed margins mark the GitHub run FAILED, not a timing-clean build. **The compiled RBF, SHA256 checksum, TIMING-STATUS.json, full logs and timing reports are now archived BEFORE the gate runs, even if timing fails.** This follows repository-wide FPGA_DIAGNOSTIC_BUILD_POLICY.md on main. Clean builds can be installed normally; if and only if the sole failure is timing and compilation/Main succeeded, experimental installation can be requested with --allow-timing-fail. Preserve known-good Rick core and prior diagnostic builds.

## Installation and testing, Mac

Only after run is confirmed fully successful:

    cd "$HOME/Downloads/mister-floppy-lab-starter"
    git fetch origin
    git switch diagnostic/bart-first-reset-linef-v8 2>/dev/null || git switch --track origin/diagnostic/bart-first-reset-linef-v8
    git pull --ff-only
    bash scripts/deploy-bart-first-reset-linef-v8.sh <NEW_SEED6_RUN_ID> mister
    # On a verified timing-only failure, explicitly opt in:
    # bash scripts/deploy-bart-first-reset-linef-v8.sh <NEW_SEED6_RUN_ID> mister --allow-timing-fail

Installer checks run, branch, workflow, paired artifact hashes, backs up MiSTer.ini and uses uniquely named _Unstable/Minimig_Bart_ResetLineF_v8.rbf and MiSTer_Physical-Floppy_BartResetLineFV8. It never overwrites known-good Rick bitstream or original released Main.

After MiSTer restart load new v8 core, same A500 KS1.3, 512KB Chip + 512KB Slow RAM. Boot current SPS 0884 Bart Disk 2 *standalone*.

If immediate failed boot: capture that state and label log bart-v8-cold.txt. If F12 reset makes Disk 2 reach the game-start screen, capture after successful start and again after gameplay hang/Guru WITHOUT another reset between. Keep files stage-separated; do not need multiple retry loops.

Snapshot commands, run on Mac:

    ssh root@mister '
    rm -f /tmp/bart-snapshots.txt
    touch /tmp/bart-snapshot.req
    sleep 3
    touch /tmp/bart-snapshot.req
    sleep 3
    cat /tmp/bart-snapshots.txt
    '
    scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-first-reset-linef-v8.txt"

Rename each captured file before obtaining the next stage, so the same filename does not overwrite earlier evidence. Capture after crash before resetting CPU. For rollback, use MiSTer.ini backup path in $HOME/Downloads/mister-floppy-lab/bart-first-reset-linef-v8/44070812609/remote-backup.txt, then restart MiSTer.

Interpret results cautiously: Line-F event Ir should reflect Fxxx opcode decode; reset event may represent an ordinary system operation; absence of events on cold-start HALT does not invalidate this probe's warm-run purpose. Do not change functional CPU/floppy logic without stronger evidence.


Seed6 run: https://github.com/VectorLatch/mister-floppy-lab/actions/runs/44079831839. Always archive .rbf before gate; explicit --allow-timing-fail if the sole failure is static timing.
