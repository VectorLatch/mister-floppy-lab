# Bart CPU/Paula FPGA snapshot — usage and interpretation

**Status:** experimental, only install after GitHub Actions FPGA and ARM jobs both complete successfully AND the FPGA timing-check job passes. Hardware behaviour is not validated. No user floppy images or ROMs are included.

## Fixed test controls
- Working Rick Dangerous ERSY v4 horizontal-beam workaround retained unchanged; official Physical Floppy Main v1.3 executable remains untouched.
- A500, Kickstart 1.3, OCS, PAL, DF0 only, 512 KB Chip + 512 KB Slow RAM.
- Disk 2 alone from the exact SPS release 0884 IPF, demonstrated to boot in Amiberry 8.5.
- Load a separate `Minimig_Bart_CPU_Paula_Diag_v1.rbf` from `_Unstable` and use a separate snapshot-enabled Main only for this diagnostic.

## How to install (after workflow success)
From macOS Terminal:
```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin diagnostic/bart-paula-cpu-snapshot-v1
git switch --track origin/diagnostic/bart-paula-cpu-snapshot-v1
bash scripts/deploy-bart-snapshot-v1.sh 43870754452 mister
```
NOTE: the numeric workflow ID is preliminary until its entire GitHub Actions run is successful. Do not run this installer while any job is failed or in progress. Installer validates the workflow conclusion before touching MiSTer.

## Capture after the hang
From macOS Terminal, after leaving Disk 2 at the black screen / unexpected graphics for a few seconds:
```bash
ssh root@mister 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 2; touch /tmp/bart-snapshot.req; sleep 2; cat /tmp/bart-snapshots.txt'
scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-fpga-snapshots.txt"
```
Uploads of the log alone are sufficient; do not upload copyrighted IPF files to public repo.

## Fields and conservative interpretation
- SIG=B4A6 VER=1: correct diagnostic core/protocol.
- CPU_FETCHES: wraparound count of instruction-fetch bus operations. Compare across snapshots; increasing count means *qualified fetches* continue. It is not a cycle-exact instruction retirement counter.
- FETCH_LAST and FETCH_PREV: two most recent **qualified bus-fetch addresses** from either TG68K or fx68k, not necessarily an architectural PC. When the CPU loops these addresses may alternate; frozen addresses + no counter movement indicate no new qualifying fetch activity, but not necessarily a dead CPU clock.
- FLAGS: 16-bit bitfield, bit 15 flux_inuse, 14 virtualFloppyMode, 13 wordsync, 12 dmaen, 11 dmaon, 10 trackrd, 9 trackrdok, 8 selected_fifo_empty, 7 lenzero, 6 fifo_wr_delay, 5 blckint, 4 syncint, 3 ext_floppy_sync, 2:1 dskstate, 0 enable.
- SYNC and LEN: live Paula DSKSYNC and effective DMA-enabled DSKLEN snapshot. DMASTATE = 0 IDLE, 2 ACTIVE, 3 completion interrupt; note normal completion state is momentary so may not be visible in a live snapshot.
- dma_arms: rising transitions of Paula dmaen; dma_done: DMA block-complete blckint pulses; sync_irqs: sync interrupt rising edges; flux_sync_events: PLL/matched sync events; dmal_cycles: disk DMA request samples.
- dsklen_writes: diagnostic count of DSKLEN register-address cycles; compare changes, not necessarily unique software write instructions.
- active_fifo_empty_cycles and read_cycles are occupancy/time-cycle counters, NOT unique transfers. Count wraparound is possible; reset clears counters.
- A pair of post-hang snapshots is the primary discriminator: CPU_FETCHES frozen and dmaen active suggests a paused/blocked CPU, whereas continuing fetches with dmaen idle suggests game-code loop/exceptions. Further debugging may be required to establish cause.

## Rollback
The installer displays the exact command to restore the previous MiSTer.ini. Reload the known-good `Minimig_Rick_ERSY_v4_20261116.rbf` afterwards. Separate new RBF/Main files can remain on SD card.
