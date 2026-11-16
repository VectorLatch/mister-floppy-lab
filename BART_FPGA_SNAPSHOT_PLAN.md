# Bart Disk 2 — read-only CPU/Paula snapshot plan

## Established evidence
- The hardware-proven Rick ERSY v4 patch is the baseline. Preserve it.
- Verified SPS 0884 Disk 1/2 pair; Disk 2 boots alone in Amiberry, hangs alone on Minimig from IPF and physical floppy with KS1.3 and KS2.0, DF0 only.
- Disk 2 logical track 1 is a variable-density Copylock-style track with sync words 8914, 8911, 8912, 8951 confirmed in the Main loading trace.
- Disk 2 track 24 (cylinder 12 head 0) is ordinary density; it is the final track requested from Main before the stall.
- v2 Main watchdog proved ReadTrack returns; no further disk requests for 90+ seconds. Its flashing-video side effect means host diagnostic logging can affect game timing.
- Main trace cannot determine whether CPU or disk-DMA state is stuck. No protection failure proven.

## Next implementation: minimally intrusive read-only FPGA snapshots
1. Paula: sample DSKLEN, DSKSYNC, dmaen, dmaon, dskstate, trackrd, lenzero, selected_fifo_empty; count blckint and syncint pulses and last DMA state transition. rtl/paula_floppy.v already contains these signals.
2. CPU: capture true instruction-fetch progress (qualified by fetch/FC or CPU core interface); do NOT pretend generic CPU data-bus address equals PC. Count fetches and latch last 2-4 true fetch addresses; also capture halt/reset state. Inspect rtl/cpu_wrapper.v and rtl/minimig.v for the correct 68000 tap.
3. Agnus: horizontal/vertical beam progress and ERSY to distinguish CPU stalls from video hardware still running.
4. Export only versioned read-only on-demand snapshots through the existing supported FPGA-to-host channel; avoid high-frequency polling, modified floppy data, or continuous logging.
5. Matching diagnostic Main may be needed to read snapshots; if so install under a new filename and preserve the official physical Main v1.3 as stable default.

## Diagnostic decision
- DMA remains armed without block completion -> investigate Paula DMA/flux/interrupt semantics.
- DMA completed, CPU runs in tight loop -> investigate loader or copy-protection result; compare exact SPS 0884 image against Amiberry CPU registers/PC.
- CPU instruction fetch stops while beam progresses -> investigate CPU bus stalled/exception/wait state.
- CPU progresses and DMA idle, video flashes -> inspect Copper/bitplane/video state.

## Validation before deployment
- First ensure the exact uploaded SPS 0884 Disk2 IPF (not only physical Disk2) boots in Amiberry 8.5 under matching A500 settings.
- Apply only one read-only FPGA diagnostic change at a time to pinned upstream FPGA 7d5d3c2f685af4ce3eb361c22893fccd153f2d87 plus the working Rick ERSY v4 patch.
- GitHub Actions: exactly one fitter seed, both setup and hold timing passing; never pass an unverified RBF.
- Deploy a separate _Unstable diagnostic RBF; never overwrite Minimig_Rick_ERSY_v4_20261116.rbf.
- Use the released Main for normal operation. Do not commit game IPF images or Kickstart ROM files to public GitHub.

## Source reconnaissance
- rtl/paula_floppy.v: DSKSYNC, DSKLEN, DMA state machine; DISKDMA_ACTIVE completes on lenzero && selected_fifo_empty && !fifo_wr_delay and then blckint pulses in DISKDMA_INT.
- rtl/paula.v: blckint and syncint wired to interrupt controller.
- rtl/cpu_wrapper.v: 68k CPU wrapper and instruction/bus signals, requires careful selection of genuine fetch qualifiers.

**Status:** design branch and evidence-based specification only; no FPGA diagnostic binary or hardware patch has been built.
