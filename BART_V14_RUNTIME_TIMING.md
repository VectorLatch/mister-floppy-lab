# Bart v14 — runtime timing tuning, not another trace build

## Purpose
Bart SPS0884 original Disk 2 IPF, A500+ Kickstart 2.0 ECS:
- Known v11 CHI​​P_WAIT=1, CIA_WAIT=0 lets the game boot (but is intermittent).
- v13 best run was fully playable with perfect graphics; same chip/CIA
  settings also produced repeated 8000 000B Line-F crashes.
- Repeated diagnostics alone haven't identified the root cause.
- Priority: sweep *live* timing knobs between F12 Amiga resets, not build
  a new FPGA core for each experiment.

## Hardware implementation
Based on pinned upstream FPGA plus proven Rick ERSY v4 fix, v8 passive
snapshot compatibility and v11 bus-wait controller; intentionally omits
v12 and v13 Line-F trace overhead.

E8 base settings remain 100% compatible with v11:
    CHIP_WAIT 0..3 (chip, slow RAM and custom-register CPU requests)
    CIA_WAIT 0..3 (CIA peripheral ECLK opportunities)

New E9 register offers four additional *bounded* CPU acknowledge waits:
    READ_EXTRA   0..3: chip/slow-RAM CPU reads (except custom registers)
    WRITE_EXTRA  0..3: chip/slow-RAM CPU writes (except custom registers)
    CUSTOM_EXTRA 0..3: CPU reads/writes in DFxxxx custom-register space
    BLIT_EXTRA   0..3: only while Agnus blitter-priority arbitration
                       signal blit_nasty is asserted for non-custom
                       chip/slow-RAM CPU requests

All four extra values default to 0 and survive Amiga F12 reset; FPGA
core reload clears E8 and E9. This only adjusts DTACK release timing;
it NEVER blocks all CPU activity until a blit completes. If blit_nasty
is not asserted, BLIT_EXTRA has no effect. It is not a replacement
for detailed blitter busy-state modelling.

The existing bridge's eligible acknowledgement-cycle machinery is used.
The code adds delays to *eligible DTACK opportunities*, not arbitrary
28MHz clock ticks; CIA stays E-clock qualified. Host/HPS transactions
are excluded and the 0/0/0/0/0/0 default is equivalent to baseline
v11 with 0/0; 1/0/0/0/0/0 matches established v11 experiment semantics.
Target waits can reach 9 eligible opportunities in read/write+blit
cases: 3 base +3 type-specific +3 blitter-priority.

## One Mac command — one FPGA core
After installing v14 and fully rebooting MiSTer, select the installed
_Unstable/Minimig_Bart_Timing_v14_seedSEED.rbf.

From macOS Terminal in the repository directory:
    bash scripts/set-bart-v14-timing.sh CHIP CIA READ WRITE CUSTOM BLIT mister

Example (retain previous v13 baseline timing):
    bash scripts/set-bart-v14-timing.sh 1 0 0 0 0 0 mister

The script triggers on-demand Main E8 and E9 commands, double writes
for stable SPI readback, and requires an explicit OK BART_V14 with both
readback ACKs. If not acknowledged, do not trust settings. Perform
F12 -> Reset *Amiga* to boot Bart with the chosen values.
You DO NOT need to reload the FPGA core between configurations.

## Compact experiment — three attempts per setting
A. 1 0 0 0 0 0    previous known baseline
B. 1 0 1 0 0 0    slower RAM reads, targets CPU data/prefetch
C. 1 0 2 0 0 0    stronger RAM-read delay
D. 1 0 0 0 1 0    custom-register timing difference
E. 1 0 0 1 0 0    RAM write timing difference
F. 1 0 0 0 0 1    extra only when blitter priority active

Use exactly one setting at a time and record: P=perfect graphics,
G=playable graphics corruption, E=red 8000000B, H=early black hang.
Repeat each candidate three times using F12 resets (same core),
rather than gathering trace files. Stop early if a clear candidate
achieves three perfect starts; reproduce in another three starts.

Do not confuse v14 buttons with MiSTer.ini settings; the new controls
are E8/E9 SPI runtime registers set by the custom Physical Floppy Main.

## Build/integrity
Branch: experiment/bart-timing-controls-v14.
Workflow: .github/workflows/build-bart-v14-timing-controls.yml
Parallel Quartus fitter seeds: 3,13,17,27,31,41.
Matching Main: MiSTer_Physical-Floppy_BartTimingV14
Bitstreams: Minimig_Bart_Timing_v14_seedN.rbf
Strict checker requires all five setup/hold/recovery/removal/min pulse
slacks >=0 and source/sha256 consistent with the selected GitHub run.
If no seed passes do NOT install a timing-violating FPGA image.
Install is backed up and leaves old v11/v12/v13 images intact.
