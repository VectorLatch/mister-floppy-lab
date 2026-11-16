# Bart SPS 0884 Disk 2 — first misaligned access recorder v4

## Established failure mechanism from timing-clean v3

Two independent real MiSTer on-device snapshots, ~3 seconds apart, gave:

```text
SIG=B4A8 VER=3 FX_HALT=1 FX_UADDR=001 FX_PSW=2708 FX_IRD=2556 FX_ERR=61
CPU_FETCHES=59396221 BUS_EVENTS=76808158 TRACK=24 DMASTATE=0 dma_arms=40 dma_done=40
FETCH_OLD3=DF220C FETCH_OLD2=DF220E FETCH_PREV=00DF2210 FETCH_LAST=00DF2212
```

In pinned source `rtl/fx68k/fx68k.sv`, `HALT1_NMA=0x001`; `sequencer` selects that address only when `A0Err` occurs while already handling a group-0 exception. `FX_ERR=0x61` shows group-0 active and specifically an address-error exception (no latched bus error). **The CPU has been halted by a nested group-0 address error, not by a pending disk transfer or a stalled external DTACK.** This identifies the final failure mechanism; it does **not yet prove** what corrupted the pointer/stack/flow or whether floppy protection data were misdecoded earlier.

The fx68k source forms the error signal as `busAddrErr = aob0 & ~bciByte`, for an odd address on a word/longword bus transfer. External address bus `eab[23:1]` omits A0. The v3 terminal RAW_BUS was even but is not the fault's original internal address.

## v4 diagnostic (read-only)

The v4 overlay to known-good v1/v2/v3 instrumentation exposes `excUnit`'s `{PcH,PcL}` **internal PC register** and full 32-bit `aob` internal address operand **including bit0**. On each rising CPU phase1 when `busAddrErr && addrOe` transitions from false to true, it increments a saturated counter and freezes the context of the **first two error episodes** until reset. This does not prevent the exception or change CPU control.

The new protocol is `SIG=B4A9 VER=4`, 60 read-only 16-bit words, slots 0–44 unchanged; slots 45–59 carry `FX_FAULT_COUNT` and `FX_FAULT1_ADDR/PC/PSW/IRD/UADDR`, `FX_FAULT2_ADDR/PC/PSW/IRD/UADDR`.

**Cautions:** These are internal CPU implementation registers sampled when bus address error is active; `FX_FAULT*_PC` may be prefetch-relative, not necessarily the instruction address that originated the bad access. The first two event episodes can include intentional address errors earlier in boot, though the normal game failure is reproducible. Captured 32-bit AOB can differ from externally visible 24-bit address (and includes the critical low bit). A nonzero counter is *not* proof that faulty floppy data caused the bad pointer.

## Build

Branch `diagnostic/bart-first-address-fault-v4`, single fitter seed5, pinned official upstream FPGA `7d5d3c2f685af4ce3eb361c22893fccd153f2d87` and Physical-Floppy Main `d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2`, original one-line Rick ERSY v4 beam patch retained. New scripts:
- `scripts/patch_bart_fpga_first_address_fault_v4.py`
- `scripts/patch_bart_main_first_address_fault_v4.py`
- `scripts/deploy-bart-first-address-fault-v4.sh`
- `.github/workflows/build-bart-first-address-fault-v4.yml`

Run: https://github.com/VectorLatch/mister-floppy-lab/actions/runs/43926658904

**Do not deploy before BOTH jobs complete successfully and examine actual setup/hold/recovery/removal/pulse slack.** The workflow still has an explicitly experimental setup tolerance down to −0.200ns; a passing build is not automatically timing-clean. Main compiled successfully at latest check, FPGA still running.

## Mac install and capture

After success:

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin
git switch diagnostic/bart-first-address-fault-v4 2>/dev/null || git switch --track origin/diagnostic/bart-first-address-fault-v4
git pull --ff-only
bash scripts/deploy-bart-first-address-fault-v4.sh 43926658904 mister
```

The installer confirms successful named run and branch/workflow, locates nested artifacts, verifies SHA256, backs up MiSTer.ini and existing v4 destinations, and **does not overwrite the original released Main or working Rick core**. Restart the MiSTer to activate the Main, load `_Unstable/Minimig_Bart_FirstFault_v4.rbf`, select A500 KS1.3 512K Chip+512K Slow, boot original SPS0884 **Disk 2 IPF directly** and do not reset when it halts.

```bash
ssh root@mister 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 3; touch /tmp/bart-snapshot.req; sleep 3; cat /tmp/bart-snapshots.txt'
scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-first-address-fault-v4.txt"
```

Upload the file. The install script prints the rollback command restoring its *immediately previous* MiSTer.ini (which may still be diagnostic v3) and requires a restart.
