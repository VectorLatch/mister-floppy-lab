# Bart v16 — actual blitter-completion interlock

Versioned filename: `Minimig_v16_seedXX_Bart.rbf` (XX is the fitter seed).
Matching physical-floppy Main: `MiSTer_Physical-Floppy_BartBlitterV16`.
FPGA is pinned to upstream `7d5d3c2f685af4ce3eb361c22893fccd153f2d87`; Main to `d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2`.
Retains Rick ERSYv4 fix and all six 0..255 v15 CPU-bus knobs.

## Why this differs from WHDLoad

The WHDLoad installer for Bart documents thirty **inserted code-site blitter waits**.
This FPGA experiment does not reproduce the actual patched instructions and does not modify original game media.
It instead intercepts **CPU writes to blitter registers**, holding bus acknowledge while Agnus's real blitter-busy
state is active. This operates at a broader, hardware level; it does **not** affect Copper-driven blits.

## Two live scopes and a watchdog

| Mode | Behaviour |
|---|---|
| 0 | OFF; original v15 CPU bridge behaviour |
| 1 | Wait before CPU writes to `BLTSIZE ($DF0058)` / ECS `BLTSIZH ($DF005E)` only |
| 2 | Wait before *any* CPU write to the blitter register range `$DF0040..$DF0074` |

Timeout range: 1–255. One unit is 256 ticks of `clk7n_en` (~36 microseconds at 7MHz).
**Unlike the v15 fixed CPU wait setting, this interlock ends immediately when the blitter becomes idle.**
The timeout is a maximum (not a minimum): if the blitter stays busy beyond it, the CPU write is released
and the timeout counter increments. That can still cause a glitch, but prevents indefinite freezing.
To avoid a deadlock, while the special CPU write is held, the bridge suppresses its normal `bls`
CPU-priority request, so blitter DMA can continue. This is essential.

Mode defaults to 0 (off) after FPGA core reload. Timeout defaults to 64.
Settings survive F12 Amiga reset but not full FPGA core reload.
All five status registers are read only except mode/timeout:
`EB00` mode, `EB01` timeout, `EBF0..EBF4` readback/status.

## Mac commands

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
# Preserve established CPU baseline; disable v15 BLIT_EXTRA for this experiment:
bash scripts/set-bart-v15-timing.sh 1 0 0 0 0 0 mister
# Start conservatively: guard *new blit starts* with ~2.3ms max timeout:
bash scripts/set-bart-v16-blitter.sh 1 64 mister
# Read actual FPGA mode/timeout and counts:
bash scripts/set-bart-v16-blitter.sh status mister
# Broader: guard all CPU blitter programming:
bash scripts/set-bart-v16-blitter.sh 2 64 mister
# Return to disabled state even if Bart has crashed:
bash scripts/set-bart-v16-blitter.sh off mister
# Toggle to the last verified previous mode/timeout:
bash scripts/set-bart-v16-blitter.sh restore mister
```

Every command validates the v16 FPGA response. A successful setting prints
`OK BART_V16 MODE=... TIMEOUT=... HITS=... COMPLETE=... EXPIRED=...`.
Counters are 8-bit and wrap after 255; compare shortly before/after a boot.
F12 -> Reset Amiga after each mode change. A reboot is only needed once after installing new Main/core.

## Suggested test sequence

Use same A500+ ECS KS2 and original SPS0884 Disk2 IPF. Set v15 six CPU knobs to `1 0 0 0 0 0`.
Mode 1 timeout 64: three F12 boots, note P (perfect), G (corrupt), C (crash), H (hang).
Run `status`; note HITS, COMPLETE, EXPIRED. Repeat three boots in mode 2 timeout 64.
Do not increase timeout until results indicate that expirations are the limiting factor.
If `HITS` stays at 0 with mode 2, this hypothesis is probably not exercised at the failure site;
then stop tuning and inspect the control/address path rather than trying more numbers.

## Safety and limitations

The blitter can be frozen or DMA-disabled; the watchdog will release the CPU bus after its cap.
The interlock does not guarantee correct playfield or eliminate Line-F exceptions.
This is an experimental core, not a validated general-purpose Minimig fix.
Back up the MiSTer.ini before installation, preserve the existing v15 core, and install only a
seed passing all five strict timing categories. Existing debugging logs remain optional.
