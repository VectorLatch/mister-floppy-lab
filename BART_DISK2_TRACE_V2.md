# Bart Disk 2 trace v2 — Main-only watchdog

## What v1 showed

On the new Cartoon Classics two-disk Bart release, Disk 2 hangs on the MiSTer when booted directly from either Greaseweazle physical floppy or IPF. KS1.3 and KS2.0, only DF0, and F12 Reset do not help. Disk 2 boots standalone in Amiberry.

The user uploaded the IPF v1 log showing normal Main-to-FPGA flux delivery without dummy fallback or select errors. At the last *summary* (167.932 session seconds), 710 core read requests and 1428 flux data blocks were logged, with no dummy data or failed select operations. Further track transitions continue to track 24 (cylinder 12/head 0) at 169.535. **These are not terminal cumulative totals.** The v1 trace logs before calling `ReadTrack`, not whether it returns, and no heartbeat appears if the core stops requesting data.

The observed DSKSYNC changed `4489 → 8914 → 8911 → 8912 → 8914 → 8951 → 4489` during early boot. This is consistent with special loader use but **does not prove** copy protection caused the hang. Main's `Copy Lock` workaround writes a local replacement DSKSYNC only for sector formatting and does not change the raw flux in the IPF codepath.

## What v2 adds

Same physical-floppy Main v1.3 source, same host-only v1 trace, PLUS:

- Separate atomic entry/exit markers around `ReadTrack` for every track change.
- A detached watchdog thread logging `BARTTRACE HEARTBEAT` every 3 seconds, independent of any new disk requests.
- `in_read=1` means the Main servicing thread is currently inside `ReadTrack()` at that snapshot. `in_read=0` with no new requests means Main returned from the last read; it does **not** by itself prove the emulated CPU has halted.
- The watchdog stops after two minutes without another read to avoid unbounded logs.

**No FPGA rebuild** and no changes to image data, flux encoding, clocks, DMA or CPU semantics. The Rick-fixed FPGA remains the same.

## Run it

From macOS Terminal:

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin diagnostic/bart-disk2-main-v2
git switch --track origin/diagnostic/bart-disk2-main-v2
bash scripts/deploy-bart-main-trace-v2.sh 43860000000 mister
```

Replace the numeric run placeholder with the successful `build-bart-main-trace-v2.yml` workflow run ID (the reference above is a **placeholder**, not a real run). After deployment, reload the `Minimig_Rick_ERSY_v4_20261116` core.

Boot Cartoon Classics Disk 2 IPF **directly** with DF0 only. When the screen hangs, **leave the MiSTer core running for 20–30 seconds**, then:

```bash
scp root@mister:/media/fat/logs/pfloppy.log "$HOME/Downloads/bart-disk2-IPF-trace-v2.log"
```

Inspect the `BARTTRACE HEARTBEAT`, `READ_ENTER` and `READ_EXIT` records. The deploy script prints the exact command to restore the previous ini.

If Main has returned but the core no longer asks for disk data, next step is minimal FPGA-level Paula disk DMA/CPU progress capture and comparison with the working Amiberry loader. Do **not** randomize seeds or port old Bart speculative fixes until this distinction is demonstrated.
