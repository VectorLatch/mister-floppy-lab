# Bart Disk 2 — fx68k internal HALT/exception capture (v3)

## Why another diagnostic?

The same original SPS 0884 Disk 2 IPF boots correctly in Amiberry but stalls on Minimig and physical floppy. The two separate v2 on-device captures, 3 seconds apart, were bit-for-bit identical except the timestamp:

```text
SIG=B4A7 VER=2 FLAGS=C101 SYNC=FFFF LEN=6C16 TRACK=24 FIFO=0 DMASTATE=0 CPU_FETCHES=58928250 FETCH_LAST=00FFFFFE FETCH_PREV=00040006
dma_arms=39 dma_done=39 sync_irqs=6 flux_sync_events=47 dmal_cycles=33951239 dsklen_writes=149
RAW_BUS=00FFFFFE BUSFLAGS=DC4E BUSDETAIL=0E58 FETCH_OLD2=DF229C FETCH_OLD3=DF229A BUS_EVENTS=76104870
```

The fetch counter and total bus cycle counter did not change for 3 seconds; ASn and chip_ASn were high (inactive), DTACKn high (inactive), CPU reset deasserted. FX68K is the active A500 CPU; its last bus address was 0xFFFFFE, function code 110 (supervisor program). `BUSDETAIL=0E58` raw chip IPL pins are 001 (active low), meaning a pending **level-6 interrupt**. The four most recent *sampled fetch addresses* were DF229A, DF229C, 040006, FFFFFE. Those are not architectural/retired instruction PCs.

This rules out an **ongoing addressed bus wait** as the immediate state, and makes fx68k internal HALT (double fault / address error) vs STOP with masked interrupts the next discriminating question. No evidence yet shows which happened first or proves disk protection failed.

## What v3 reads

The v3 patch starts with pinned Minimig upstream `7d5d3c2f685af4ce3eb361c22893fccd153f2d87`, applies the **one-line working Rick ERSY v4 beam fix**, and layers the existing read-only v1 and v2 FPGA taps, then `scripts/patch_bart_fpga_fx68k_internal_v3.py`. It does *not* alter internal 68000 computation, microcode, exception logic, Paula disk DMA, the ROM, disk data or interrupt routing.

New FPGA read registers 40–44 (existing 0–39 are unchanged). **Protocol signature `B4A8`, version `3`**, read only upon `/tmp/bart-snapshot.req` using matching Physical-Floppy Main `MiSTer_Physical-Floppy_BartFxV3`.

- `FX_HALT` — 1 if existing fx68k `oHALTEDn` output is asserted low; this reflects the CPU's internal HALT indication, *not* a generic inactivity flag
- `FX_UADDR` — current fx68k microcode address, 10 bits (`HALT1_NMA=0x001` in pinned fx68k source); useful to understand where CPU has stopped
- `FX_PSW` — current 68000 status word. Bits 10–8 contain the interrupt priority mask, bits 15 trace, 13 supervisor
- `FX_IRD` — fx68k internal instruction decoder register. Do not assume this is the opcode at `FETCH_LAST` without correlating microstate/prefetch
- `FX_ERR` — bit7 pending group-0 `A0Err`; bit6 latched group-0 exception; bit5 latched address error; bit4 latched bus error; bit3 raw address error; bit2 bus-error latch; bit1 reset exception latch; bit0 internal halted flag

The v3 Main checks protocol signature and version before logging. Scripts: `patch_bart_main_snapshot_v1.py`, `patch_bart_main_cpu_bus_v2.py`, `patch_bart_main_fx68k_internal_v3.py`.

## Build

GitHub Actions workflow: `.github/workflows/build-bart-fx68k-internal-v3.yml`. One fitter seed **5**, upload separate FPGA and matching Main artifacts, source patches pinned and checked. The workflow has a documented experimental setup-time allowance no worse than −0.200 ns and requires nonnegative hold/recovery/removal/pulse slack. A successful workflow may therefore still be experimental and *not* strictly timing-clean; check the reported slacks. No ROM/IPF content is stored in this public repository.

The first two attempted v3 runs stopped before Quartus because the original upstream `fx68k.sv` has CRLF line endings; source patch and strict whitespace check now preserve and explicitly allow CR-at-EOL, without disabling other whitespace checks. This was build preparation only, not a functional issue with the CPU. Latest attempt: [GitHub Actions 43914758773](https://github.com/VectorLatch/mister-floppy-lab/actions/runs/43914758773). **Do not install if it has not completed successfully.**

## Installation and capture (macOS)

After *both* jobs complete successfully:

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin
git switch diagnostic/bart-fx68k-internal-v3 2>/dev/null || git switch --track origin/diagnostic/bart-fx68k-internal-v3
git pull --ff-only
bash scripts/deploy-bart-fx68k-internal-v3.sh 43914758773 mister
```

The installer validates the GitHub workflow/branch/success status, checks downloaded hashes, saves `MiSTer.ini` and any previous v3 files, puts the new `Minimig_Bart_FX68K_Internal_v3_Experimental.rbf` in `_Unstable`, and points the Minimig-specific `main=` to the paired new ARM Main. **Existing Rick FPGA and released Physical-Floppy Main executables are not overwritten.** After reboot, load the v3 core, set A500 KS1.3 512KiB Chip +512KiB Slow, boot **Disk 2 alone** of the same SPS 0884 IPF, and leave it hung. Capture:

```bash
ssh root@mister 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 3; touch /tmp/bart-snapshot.req; sleep 3; cat /tmp/bart-snapshots.txt'
scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-fx68k-internal-v3.txt"
```

Upload the v3 log. The installer prints the backup path and exact command to restore the previous `MiSTer.ini`, then reboot and load the known-working Rick core. Since the latest previous configuration might itself be diagnostic v2, restoration is to the **immediately previous** Main, not necessarily the original release.

## Interpretation

`FX_HALT=1` and `FX_UADDR` at/near HALT microcode would strongly support internal fx68k halt; correlate `FX_ERR`, which may record the root exception. If `FX_HALT=0` and interrupt mask 7 while IPL6 is pending, a masked-IRQ STOP or other inactive microcode is possible. If `FX_HALT=0` while mask under 6, investigate no-interrupt progress and other engine state. Avoid deriving a definitive cause from an incomplete single snapshot.
