# Bart v10: ECS A500+ scanline-locked Denise bitplane-word diagnostics

## Corrected hardware/software configuration

The user confirmed **stock A500+ preset, Kickstart 2, ECS** on MiSTer Multisystem2. **Do not use A500 OCS/KS1.3 setup** for this test; earlier documentation was wrong. Prior v8/v9 results still reflect the user's actual ECS test. The previous good physical disk Amiberry test was on an **A500 KS1.3/OCS** configuration and cannot by itself validate this A500+ ECS configuration.

The latest v9 gameplay log `bart-v9-graphics-playing.txt` on this setup shows `GFX_BPLCON0=$4200` (4 bitplanes, low-resolution); `GFX_BPLCON1` changed $33FF → $3300 as the game scrolled. v9 observed no OCS *pending* pixel stream usage in the 3s interval, while the *legacy* stream advanced. The RTL term `ocs_lores_fmode0` in `denise_bitplanes.v` means **non-AGA lowres, non-SHRES, fmode0**; it does *not* require the ECS configuration bit to be false. This is why the v9 pending/legacy observations remain applicable to an A500+ ECS user setting. Yet the v9 counts cannot prove correct fetched graphics *data*.

## v10 target, instrumentation and limitations

**Goal:** obtain actual 16-bit words entering Denise BPL1DAT..BPL4DAT and a cumulative (non-cryptographic) data fingerprint on fixed PAL beam scanlines, to tell if graphics data appears coherent, repeated and beam-position dependent. Separately capture the *first* Agnus DMA BPL1 pointer on each beam line. These taps have a pipeline offset: **do not treat the Agnus pointer and Denise word as an exact same-cycle address/data pair without latency calibration**. Values change if scrolling, palettes or animation changes.

- Fixed Agnus beam scanlines: **$080 (decimal 128)** and **$0E0 (decimal 224)**. Under ordinary PAL, both are in the plausible gameplay area; they should be checked for actual DMA activity.
- A read-only 4-bit selector tags BPL1DAT..4DAT custom-register writes at `clk7_en`. On the corresponding `clk7n_en` (the same phase used by the original Denise holding registers), `data16` contributes to a per-line rotate/XOR fingerprint.
- On the **first** BPL1DAT latch per line/frame, the recorder stores **the actual data16 word that Denise is loading for bitplane 1**, and the existing bitplane 2/3/4 holding register top words. These values are not reconstructed from pixels and do not change the holding registers.
- Hash resets when Denise's horizontal strobe `strhor` marks the target line; it accumulates the actual BPL1DAT..4DAT bytes/words until line end. Hash is useful for repeatability/correlation, not a verified hardware CRC and not a known-good reference.
- From the original Agnus output mux: capture the first BPL1 DMA *word address* per target vpos, independently of Denise word snapshots. These are not guaranteed sample-matched to the four Denise values owing to memory/Denise pipeline latency. Pointers output as byte addresses and should reside in chip RAM on this config.
- Two 16-bit hit counters indicate how often a given target line had a BPL1DAT load.
- Live mode flags expose *actual* active ECS and AGA settings; BPLCON0/1 are also read.
- The Rick Dangerous ERSY v4 working patch and earlier CPU/Paula snapshot slots 0..44 remain preserved. v9 counters remain in hardware but slots 45..63 now present the v10 trace, not v9 statistics. No pixel-selection, DMA, blitter, floppy, CPU or RAM functional control is changed.
- This is a hardware observation system. Additional probes can alter FPGA fitter placement, so all five timing categories are strictly checked; use only a timing-clean seed where available.

## Build

- Branch `diagnostic/bart-v10-ecs-bitplane-words`.
- Workflow `.github/workflows/build-bart-v10-ecs-words.yml`; six FPGA seeds **11, 15, 18, 19, 20, 21**, maximum six concurrent runners; one matching Physical Floppy Main.
- Build FPGA source: MiSTer-devel/Minimig-AGA_MiSTer pinned `7d5d3c2f685af4ce3eb361c22893fccd153f2d87`, Rick ERSY v4 plus Bart v1/v2/v3/v6/v8/v9 then `scripts/patch_bart_fpga_words_v10.py`.
- Build Main: manfredi90/Main_MiSTer_Physical_Floppy pinned `d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2`, Bart v1/v2/v3/v6/v8/v9 plus `scripts/patch_bart_main_words_v10.py`.
- FPGA signature `B4AF`, protocol version `10`; original 64-word read on explicit `/tmp/bart-snapshot.req` request. 0..44 original CPU/Paula captures, 45..63 v10 words. The companion Main and FPGA must both be v10.
- Every fully compiled RBF plus SHA256 and five-slack JSON manifest archived **before** strict timing gate. Failed timing is still a failed job; the archive can be used for explicitly opted-in experiments only.

## V10 SPI words and log fields

| Word | Meaning |
|---|---|
| 45 | V10_ECS bit11, V10_AGA bit10, V10_DMA_A_VALID bit9, V10_DMA_B_VALID bit8, B pointer high nibble bits7:4 and A pointer high nibble bits3:0 |
| 46 | V10_A_HITS (first BPL1DAT loads on line $080) |
| 47 | V10_B_HITS (first BPL1DAT loads on line $0E0) |
| 48–49 | V10_A_HASH 32-bit rolling per-line BPL1..4 word fingerprint, low 16 first |
| 50–51 | V10_B_HASH, same for line B |
| 52–55 | V10_A_P1, V10_A_P2, V10_A_P3, V10_A_P4: BPL1 actual data16 at its capture phase, BPL2..4 most-recent holding register data |
| 56–59 | V10_B_P1..P4 for line B |
| 60 | Lower word of Agnus first BPL1 DMA word address on line A |
| 61 | Lower word of Agnus first BPL1 DMA word address on line B |
| 62 | V10_BPLCON0 |
| 63 | V10_BPLCON1 |

Two data samples taken ~3 seconds apart are **not guaranteed to match** because the game is running and can scroll or animate, even without any hardware defect. Consecutive screenshots should help correlate visually. Hash is an observation of the custom-register words, not a checksum of contents of the game disk.

## Install and capture (after selecting verified timing-clean seed from completed run)

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin
git switch diagnostic/bart-v10-ecs-bitplane-words 2>/dev/null || \
  git switch --track origin/diagnostic/bart-v10-ecs-bitplane-words
git pull --ff-only
bash scripts/install-bart-v10-selected-seed.sh <RUN_ID> <PASS_SEED> mister
```

No timing bypass for timing-clean builds. A backup of prior MiSTer.ini is saved; old Rick and v8/v9 files remain untouched. On MiSTer reboot select `_Unstable/Minimig_Bart_ECSWords_v10_seed<PASS_SEED>.rbf`, retain the user's **A500+ / KS2 / ECS** preset and boot the same SPS0884 Bart Disk2 standalone image.

When the playfield is corrupted and gameplay actually running, on Mac:
```bash
ssh root@mister '
  rm -f /tmp/bart-snapshots.txt
  touch /tmp/bart-snapshot.req
  sleep 3
  touch /tmp/bart-snapshot.req
  sleep 3
  cat /tmp/bart-snapshots.txt
'
scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-v10-ecs-playing.txt"
```

For a startup hang, keep that capture separately without resetting before it is read. User should upload the file as-is. The Main emits `SIG=B4AF VER=10` and `V10_ECS=1 V10_AGA=0` if the intended preset is active.
