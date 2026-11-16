# Bart SPS 0884 Disk 2: Last two odd-address fault-condition episodes (v5)

## Why v5?

The user ran the **timing-clean v4** FPGA + paired Physical Floppy Main with the original Bart vs Space Mutants SPS 0884 **Disk 2 booted directly** on A500/KS1.3. Two captured samples taken 3.0 seconds apart are identical apart from timestamps. Key findings:

```text
SIG=B4A9 VER=4 CPU_FETCHES=61359430 BUS_EVENTS=80119839
TRACK=24 DMASTATE=0 dma_arms=39 dma_done=39
FX_HALT=1 FX_UADDR=001 FX_PSW=2708 FX_IRD=2556 FX_ERR=61
FX_FAULT_COUNT=1143
FX_FAULT1_ADDR=0101BDDF FX_FAULT1_PC=000063A4 FX_FAULT1_PSW=2700 FX_FAULT1_IRD=4A90 FX_FAULT1_UADDR=005
FX_FAULT2_ADDR=0101BDDF FX_FAULT2_PC=0007087E FX_FAULT2_PSW=2704 FX_FAULT2_IRD=21D0 FX_FAULT2_UADDR=005
```

The v3 conclusion holds: **fx68k is in internal HALT**, microcode address `0x001` (`HALT1_NMA`), with group-0 / address-error exception flags; this is not a pending floppy DMA request or an ongoing external DTACK bus stall. Its final failure mechanism is consistent with a nested address-error exception.

**Crucial limitation:** v4 stores the **first two** odd word/long address error *condition episodes*, but its detector counted **1143** such episodes before HALT. The first two (both internal address `0x0101BDDF`, effective 24-bit `0x01BDDF`) may be benign/handled/transient or different from the fatal nested error; **1143 events must not be presented as 1143 architecturally serviced CPU exceptions.** v4 `rAddrErr` is set at `enPhi1` when `busAddrErr && addrOe`, and the v4 recorder uses exactly the same qualification with a rising-edge detector. This is a matching internal condition, but `addrOe` and microcode control timing still merit scrutiny.

`FX_FAULT1_IRD=0x4A90` is consistent with `TST.L (A0)`; `FX_FAULT2_IRD=0x21D0` also involves a memory operand through `(A0)`. The captured `IRD` and internal PC are microarchitectural register snapshots at the condition edge, not an independently verified retired instruction PC/opcode pair. No evidence yet establishes whether disk protection or corrupted data initiated the failing pointer.

## v5 design

New branch `diagnostic/bart-last-address-fault-v5`. Retains all pinned upstream sources and same Rick ERSY v4 fix, plus v1/v2/v3/v4 instrumentation. New overlay `scripts/patch_bart_fpga_last_address_fault_v5.py` replaces v4's first-two latch with a 2-entry **sliding register history of the latest two episodes**. This captures the **penultimate and final** odd address condition observed before HALT, instead of early events. Each record includes 32-bit internal address (bit0), internal PC register, PSW, IRD, and microaddress. The previously unused high bits of each UADDR register (bits13:10) also now include the fx68k sequencer's own group-0 flags *at the moment of the event*. This helps distinguish ordinary odd word/long access from an odd access during address-error exception handling.

The event detector remains `Clks.enPhi1 && (busAddrErr && addrOe) && !bart_addrerr_prev`, where `busAddrErr` in upstream fx68k is `aob0 && !bciByte`. **No functional CPU bus, exception, memory, ROM, floppy DMA, host disk reader, or interrupt code is modified.** Total event counter saturates at 65535.

SPI signature `B4AA` / version `5`. **Still only 60 words, indices 0..59**; v5 reuses existing v4 slots 45..59 and preserves v1/v2/v3 slots 0..44. Paired Main `scripts/patch_bart_main_last_address_fault_v5.py` rejects any mismatch and prints:
- `FX_ADDRERR_EPISODES` — count of observed qualified condition episodes
- `FX_PREV_ADDR/PC/PSW/IRD/UADDR/GRP0` — penultimate observed episode (if at least two)
- `FX_LAST_ADDR/PC/PSW/IRD/UADDR/GRP0` — final observed episode
- `GRP0` flags 4-bit mask `{inGrp0Exc,rExcAdrErr,rExcBusErr,rExcRst}`. A nonzero group0 active on the last event would be evidence of nested error context.

One fitter seed 5, existing setup tolerance >=−0.200ns and strict nonnegative hold/recovery/removal/pulse; verify *actual* TimeQuest margins after success. Build action: https://github.com/VectorLatch/mister-floppy-lab/actions/runs/43937913184 (started; not yet known successful).

## Deployment (only after BOTH jobs succeed and timing reviewed)

On user's Mac:

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin
git switch diagnostic/bart-last-address-fault-v5 2>/dev/null || git switch --track origin/diagnostic/bart-last-address-fault-v5
git pull --ff-only
bash scripts/deploy-bart-last-address-fault-v5.sh 43937913184 mister
```

This deploys uniquely named `_Unstable/Minimig_Bart_LastFault_v5.rbf` and `/media/fat/MiSTer_Physical-Floppy_BartFaultV5`, after verifying run success, names, branch/workflow, checksum, and backing up existing MiSTer.ini. Rick-fixed core and original Main unaffected.

Restart MiSTer. A500 KS1.3 512KB Chip + 512KB Slow, original SPS 0884 Disk 2 IPF **directly**. Leave stuck machine unreset; use:

```bash
ssh root@mister 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 3; touch /tmp/bart-snapshot.req; sleep 3; cat /tmp/bart-snapshots.txt'
scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-last-address-fault-v5.txt"
```

Upload log for diagnosis. Restore previous MiSTer.ini from `$HOME/Downloads/mister-floppy-lab/bart-last-address-fault-v5/<run-id>/remote-backup.txt` and restart. That backup may itself be from diagnostic v4, not necessarily the original release.
