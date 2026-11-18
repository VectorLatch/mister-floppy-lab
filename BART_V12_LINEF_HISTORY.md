# Bart v12 — read-only recent Line-F history + v11 live bus waits

## Why
SPS 0884 Bart Disk 2 standalone boots normally in Amiberry in A500+ / KS2 /
ECS, but under Minimig v11 seed15 timing tests (25 attempts):
- chip 0 CIA 0: 1/5 playable with corrupted playfield, four early black screens
- chip 1 CIA 0: 3/10 playable with corrupted playfield, seven late 8000000B alerts
- chip 2 CIA 0: 0/5 playable, four late 8000000B alerts and one late black screen
- chip 0 CIA 1: 0/5 playable, two late 8000000B alerts and three early black screens

The first-ever v8 Line-F event is F2E9 at internal PC 0007009C in
successful and unsuccessful runs. The late exception cause is unproven.

## Diagnostic design
Pinned upstream FPGA and Main revisions remain in UPSTREAM_LOCK.md.
Applies Rick ERSYv4, Bart v1/v2/v3/v6/v8, v11 E8 waits, and new v12
read-only history. The original E7 snapshot is 64 words; words 0..44
unchanged. New signature B4AE and version 12 ensure the correct Main
reader is paired. Slots 45..63 are *repurposed* from v8 RESET/first-Line-F
history to first/latest/preceding Line-F history:
- 45:46 first internal PC
- 47:48 last internal PC
- 49:50 last external instruction-fetch bus address
- 51:52 last preceding instruction-fetch bus address
- 53:54 previous Line-F internal PC
- 55:56 previous Line-F external fetch
- 57:58 previous Line-F preceding fetch
- 59 last PSW, 60 last decoded IR, 61 prior decoded IR
- 62 saturated 16-bit number of Line-F recognition pulses
- 63 flags (any, prior valid, last overlay, live overlay,
  live CPU RESET-output low, RESET output low at latest Line-F,
  counter saturated)

This samples the *existing v8 fx68k sequencer exception tap* on a
rising edge. It does not affect instruction execution, bus or RAM data,
DMA, floppy data, or rendering. Internal sampled PC is not guaranteed
to be the faulting architectural PC. Prior means prior Line-F event,
not the prior instruction.

v11 bus-wait controller E800 and existing live setting helper are
unchanged. 1/0 remains the best observed startup progression; no fix is
claimed. The current v11 seed15 installation stays intact.

## Build and install
Workflow: .github/workflows/build-bart-v12-linef-history.yml
Branch: diagnostic/bart-linef-history-v12
Six parallel seeds: 11,15,21,22,23,24, one shared ARM Main. Only install
a run after the verifier confirms matching build identity, checksum,
Main job success, and nonnegative setup/hold/recovery/removal/minimum
pulse-width margins for the chosen seed.

On macOS, *after* a successful selected-seed build:

    cd "$HOME/Downloads/mister-floppy-lab-starter"
    git fetch origin
    git switch --track origin/diagnostic/bart-linef-history-v12
    bash scripts/install-bart-v12-selected-seed.sh RUN_ID SEED mister

Installer creates a timestamped MiSTer.ini backup, copies unique v12
RBF and ARM Main filenames, and sets Minimig main= to the new Main.
Restart MiSTer and select the installed v12 seed RBF.
Use the same A500+ / KS2 / ECS and Bart SPS 0884 Disk 2 IPF.

    bash scripts/set-bart-v11-waits.sh 1 0 mister

Confirm B801 readback, then F12 Reset the Amiga. When a late error
8000000B is visible, leave it on screen and capture two snapshots:

    ssh root@mister 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 3; touch /tmp/bart-snapshot.req; sleep 3; cat /tmp/bart-snapshots.txt; cat /tmp/bart-v11-waits.last'
    scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-v12-linef.txt"

Look for LF12_COUNT, LF12_FIRST_PC, LF12_LAST_PC, LF12_PRIOR_PC,
LF12_LAST_FETCH, LF12_LAST_PREV, LF12_LAST_IR and LF12_PRIOR_IR.
If LF12_COUNT stays 1 after a late alert, there was no *second
recorded* Line-F recognition, so investigate why the first exception
eventually surfaced as a failure (or what else caused the alert).
Compare the late failure with a playable boot before changing code.

No original game disks, IPFs, or Kickstart ROMs belong in this repo.
