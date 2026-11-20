# Bart v15 — runtime timing controls (8-bit)

FPGA filename format: `Minimig_v15_seedXX_Bart.rbf`, where XX is fitter seed.
Matching Main: `MiSTer_Physical-Floppy_BartTimingV15`.
Upstream FPGA and Main are pinned; proven Rick ERSY v4 fix and Physical Floppy support retained.

## Six values 0–255

| Knob | E9 opcode | Hardware effect |
|---|---|---|
| CHIP | E900 | Base wait for CPU chip/slow-RAM and DF custom register accesses |
| CIA | E901 | CPU CIA E-clock-qualified wait |
| READ | E902 | Extra CPU chip/slow-RAM reads |
| WRITE | E903 | Extra CPU chip/slow-RAM writes |
| CUSTOM | E904 | Extra DFxxxx custom register timing |
| BLIT | E905 | Extra CPU chip/slow-RAM wait during blitter-priority arbitration |

Each is 8 bits, combined wait counter is 10 bits (max possible 765).
Values count eligible CPU DTACK opportunities, **not** fixed-length sysclock cycles.
BLIT does not change Agnus blitter speed or hold the CPU until blitter completion.
All values reset to zero at FPGA core reload, but are retained through F12 Amiga soft reset.
**High settings can stall startup**; use low values initially and recover with `zero` or `baseline`.

## Mac commands (not over SSH)

```bash
# Historical known baseline: Chip=1, CIA=0, extras=0
bash scripts/set-bart-v15-timing.sh baseline mister
# Test BLIT extra 5:
bash scripts/set-bart-v15-timing.sh 1 0 0 0 0 5 mister
# Restore the last successful profile (toggle between current and previous):
bash scripts/set-bart-v15-timing.sh restore mister
# Return to all-zero settings:
bash scripts/set-bart-v15-timing.sh zero mister
```

Main reads live E9F0..E9F5 FPGA registers before each write, confirms every requested value,
and stores the real previous values on the MiSTer Linux host in `/tmp/bart-v15-previous`.
`restore` and `zero` can be used even when emulated Amiga is hung; host Main must still be responsive.
Previous values survive F12 soft resets but not full MiSTer Linux reboot.
After any adjustment, F12 -> Reset Amiga before testing. No FPGA rebuild.
Old v11/v14 configuration scripts are not valid for v15.

## Short test

Start with baseline, then test BLIT extras 1, 2 and 5 (three attempts each),
looking for fully playable, correct playfield on repeated starts.
Only then try 8, 12 or larger values if data justify it.
Mark each start P=perfect, G=corrupt-but-playable, E=red 8000000B or H=hang.

## Build safety

Workflow `.github/workflows/build-bart-v15-timing-controls.yml` builds six Quartus fitter seeds
3,13,17,27,31,41 with strict nonnegative slack requirements in all five timing categories.
Use `scripts/install-bart-v15-first-passing-seed.sh` with the run ID to select a passing seed;
installer checks GitHub source, job success, timing manifest and SHA256,
backs up MiSTer.ini and preserves old v14 binaries.
