# Bart v17 — independent 32-bit blitter/CPU observability

v17 is an experimental diagnostic instrument, **not a new attempted timing fix**.
The objective is to explain why v16 Mode 1 and 2 both reported HITS=0 while
Bart repeatedly crashed or displayed a corrupt playfield.

Retains pinned Minimig baseline, proven Rick ERSY v4 patch, matching physical-floppy Main,
all six v15 8-bit CPU timing knobs, and the v16 blitter completion guard.
No game-code patch, disk-drive, ROM, graphics, DMA-grant, CPU DTACK or blitter FSM modifications in v17.

## Counters

Seven **32-bit** counters, independent of the existing v16 8-bit counters:

| Name | Counted event |
|---|---|
| `STARTS` | Rising edge of Agnus's actual `blit_busy` / `DMACONR` busy bit |
| `BLIT_WRITES` | CPU attempted write to `$DF0040..$DF0074`, once per `/AS` transaction |
| `BUSY_WRITES` | Such a CPU write overlapping actual blitter-busy, regardless of v16 mode |
| `RAM_WHILE_BUSY` | CPU chip/slow-RAM address-strobe transactions overlapping blitter busy |
| `WAIT_CANDIDATES` | The actual v16 `bart_v16_candidate` condition, counted once per transaction |
| `CPU_CYCLES` | All observed CPU `/AS` transactions, a positive signal-control |
| `BUSY_TICKS` | 7MHz-enabled ticks with blitter-busy high, a positive signal-control |

CPU cycles and CPU memory events exclude HPS host accesses. The RAM category follows
the Minimig bridge `dbs` slowdown decode, excluding `$DFxxxx` custom registers and CIA.
CPU write and RAM counters record an **attempted transaction**, not proof of memory commit.
Counts do not reset on F12 Amiga reset; clear explicitly before a run.

## Atomic readout

`EC7F` returns v17 signature `C717`.
`EC00` snapshots all seven counters on the same 7MHz edge; `EC01` explicitly clears
counters and the snapshot. `EC20..EC2D` read low/high 16-bit halves of the frozen
seven 32-bit counters. `EC2E` reads the snapshot sequence counter.
Matching Main verifies the v17 signature, demands that the snapshot sequence increment
by exactly one, and reads the frozen values. This prevents silently reporting stale counters.

## Mac commands

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
# Keep prior six fixed CPU knobs at the historical baseline:
bash scripts/set-bart-v15-timing.sh 1 0 0 0 0 0 mister
# Disable completion interlock for a pure v16-off reference:
bash scripts/set-bart-v16-blitter.sh off mister
# Before attempting Bart:
bash scripts/bart-v17-counters.sh clear mister
# After three F12 resets / Bart boots:
bash scripts/bart-v17-counters.sh snapshot mister
# Alias:
bash scripts/bart-v17-counters.sh status mister
```

Then enable v16 Mode 2 without changing CPU waits, clear counters again, and repeat:

```bash
bash scripts/set-bart-v16-blitter.sh 2 64 mister
bash scripts/bart-v17-counters.sh clear mister
# Boot Bart three times via F12 Reset, then:
bash scripts/bart-v17-counters.sh snapshot mister
```

Report the entire `OK BART_V17 ...` line and each P/G/C/H result.

### Interpretation

- `STARTS>0` and `BUSY_TICKS>0`: the Agnus status signal is present.
- `CPU_CYCLES>0`: the CPU bus event detector is running.
- `BLIT_WRITES>0`, `BUSY_WRITES=0`: CPU writes were seen but no overlap.
- `BUSY_WRITES>0`, `WAIT_CANDIDATES=0` in Mode 2: examine the specific
  candidate gate (`_ta_n`, mode, l_as, address decode); do not increase timeouts.
- `BUSY_WRITES=0`, `RAM_WHILE_BUSY>0`: conflicts are more likely in RAM
  accesses overlapping blitter DMA than in register writes.
- All counters zero: suspect diagnostic routing, not 'the game uses no blitter'.

Watchouts: snapshot counters don't stop the game or mask F12 resets;
32-bit counters wrap if left accumulating long enough (busy ticks wrap in roughly
ten minutes of continuously active blitter). Read after short test sequences.
At initial startup some low values may be collected from idle Kickstart activity.

## Build

Workflow `.github/workflows/build-bart-v17-blitter-observability.yml` uses at most
six concurrent fitter seeds (3,13,17,27,31,41) with all five strict timing margins.
Installer: `scripts/install-bart-v17-first-passing-seed.sh <run-id> mister`.
Preferred filename `Minimig_v17_seedXX_Bart.rbf`, matching Main
`MiSTer_Physical-Floppy_BartObserveV17`.
Preserves v15/v16 binaries and backs up the current MiSTer.ini.