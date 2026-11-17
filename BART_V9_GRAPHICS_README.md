# Bart SPS 0884 Disk 2 — v9 read-only graphics-path probe

## Why v9
v8 was tested on the same MiSTer Multisystem2 with both a known timing-violating seed 6 (hold -0.131 ns) and a timing-clean seed 11 (setup +0.073 ns; hold +0.244 ns). **Both** reproduced variable startup (normal / hang / white-speckle hang / red Amiga Software Failure) and identical, repeatable corruption in the gameplay playfield, fixed in display coordinates while scrolling. CPU runs and game can be played. We must not assume a seed/timing-only explanation, nor conflate this standalone Disk 2 issue with old Disk 1 Ocean splash issue.

There is a specialised OCS low-resolution bitplane stream ownership state machine in the pinned `rtl/denise_bitplanes.v`, alongside the legacy pixel stream. v9 observes that actual choice and the surrounding Denise bitplane register/dma events. **v9 does not alter pixel generation, memory data, DMA arbitration, the Copper or the Blitter.** It does not try speculative fixes or probe actual chip RAM contents. Preserve Rick ERSY v4 one-line proven patch.

## Exact build source
- Branch: `diagnostic/bart-v9-graphics-readonly`
- GitHub workflow: `.github/workflows/build-bart-v9-graphics.yml`
- Pinned FPGA upstream: `MiSTer-devel/Minimig-AGA_MiSTer@7d5d3c2f685af4ce3eb361c22893fccd153f2d87`
- Pinned Physical-Floppy Main upstream: `manfredi90/Main_MiSTer_Physical_Floppy@d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2`
- FPGA overlays in order: Rick ERSY v4; Bart v1, v2, v3, v6, v8, then `scripts/patch_bart_fpga_graphics_v9.py`
- Main overlays in order: Bart v1, v2, v3, v6, v8, then `scripts/patch_bart_main_graphics_v9.py`
- Six parallel FPGA fitter seeds: **11, 13, 14, 15, 16, 17** (single shared Main); identical v9 logic; only fitter seed changes.
- Successful Quartus compilations are retained as nonempty `.rbf` + SHA256 + `TIMING-STATUS.json` **before** the strict five-category gate; timing-negative builds remain explicitly opt-in experiments, not passes.
- The original v8 seed11 RBF and v8 Main are left untouched.

## SPI readout
- On-demand only, triggered on MiSTer by `touch /tmp/bart-snapshot.req`; never polled during floppy loading.
- FPGA SPI E7xx signature **B4AE**, version **9**.
- Words 0..44: original CPU/Paula counters and internal CPU data preserved from v1/v2/v3. Words 45..63: below, replacing v8 first RESET/Line-F event formatting. v8 event logic still in source but those event records are not exported by v9.
- This table documents 19 v9 words, from 45 through 63 inclusive.

| SPI word(s) | Main log field | Meaning / important caveat |
|---|---|---|
| 45 | GFX_FLAGS | *Live* Denise OCS/ownership state at SPI sampling instant; bits 0 blank, 1 hdiw, 2 BPL1DAT now, 3 fetch phase, 4 phase valid, 5 pending stream selected, 6 OCS lores mode, 7 OCS trigger, 8 PF2 pending, 9 PF1 pending, 10–11 delayed stage, 12–13 ownership state; bits 14–15 zero |
| 46 | GFX_BPLCON0 | Current Denise BPLCON0 register |
| 47 | GFX_BPLCON1 | Current Denise bitplane horizontal-scroll register |
| 48–49 | GFX_DMA_SLOTS | Count of qualifying bitplane DMA cycles at clk7_en, lower word first; 32-bit wraps |
| 50–51 | GFX_BPL1DAT | Count of BPL1DAT events observed at Denise bitplane register bus |
| 52–53 | GFX_OCS_SNAPSHOTS | Count of specialised OCS pending-register snapshots |
| 54–55 | GFX_OCS_PENDING_TICKS | Active display ticks using OCS pending stream |
| 56–57 | GFX_OCS_LEGACY_TICKS | Active display ticks using legacy stream while OCS mode |
| 58 | GFX_OCS_IMMEDIATE | Number of immediate ownership events, 16-bit wraps |
| 59 | GFX_OCS_DELAYED | Number of delayed ownership events, 16-bit wraps |
| 60–61 | GFX_LAST_DMA_BYTE_ADDR | Most recent observed Agnus DMA word address rendered as byte address; not guaranteed the actual memory sample address after pipeline latency |
| 62 | GFX_LAST_DMA_BUS | Raw custom data bus during that DMA slot; **not guaranteed actual Denise sample** |
| 63 | GFX_DMA_WRITES | Count of Agnus memory DMA writes, including disk and/or Blitter, not Blitter-only (16-bit wraps) |

Counters reset with the core; snapshot read itself need not be atomic. Use two samples and look at count deltas. The live flags and last DMA address may naturally vary between samples. They are not automatically errors.

## Install a selected timing-clean seed (once the build completes)
```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin
git switch diagnostic/bart-v9-graphics-readonly 2>/dev/null || \
  git switch --track origin/diagnostic/bart-v9-graphics-readonly
git pull --ff-only
bash scripts/install-bart-v9-selected-seed.sh <RUN_ID> <SEED> mister
```
For **explicitly experimental**, fully compiled but timing-negative bitstream, append `--allow-timing-fail`. The installer checks the specific seed's GitHub job and timing manifest rather than the *overall* matrix status, as five other jobs might individually fail the strict timing gate while one succeeds. The installer verifies checksum, matching Main, sourceSHA, seed and run ID, stages downloads in fresh temporary directories, backs up MiSTer.ini, and installs uniquely named `_Unstable/Minimig_Bart_Graphics_v9_seed<SEED>.rbf` and `MiSTer_Physical-Floppy_BartGraphicsV9`.

## Collect log evidence
Boot the installed v9 experimental core with **A500 KS1.3, 512k chip + 512k slow**, current SPS 0884 Bart **Disk 2 standalone**, first capture the ordinary game-start screen before gameplay if obtainable, then the corrupted gameplay screen. Do not insert Disk 1 or repeat old unrelated tests.

On your Mac, with gameplay running:
```bash
ssh root@mister '
  rm -f /tmp/bart-snapshots.txt
  touch /tmp/bart-snapshot.req
  sleep 3
  touch /tmp/bart-snapshot.req
  sleep 3
  cat /tmp/bart-snapshots.txt
'
scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-v9-graphics-playing.txt"
```
To capture a cold boot failure, repeat the same first SSH block *before resetting*, then save as `bart-v9-cold-failure.txt`. Take a photograph of the corrupted scene for comparison to earlier seed6/11 photos.

### Interpretation boundaries
This instrumentation can reveal whether the OCS ownership stream is used and whether bitplane DMA, register writes and stream transitions continue while gameplay graphics are corrupt. It **cannot yet prove** chip RAM loaded data correctness, original disk image correctness, or exact screen pixel memory content. If the counters reveal a suspicious path, follow with targeted line/bitplane captures in v10 rather than editing video hardware based on counters alone.
