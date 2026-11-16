# Bart CPU bus-state diagnostic v2

## Purpose

Follow up the **SPS release 0884 Disk 2 standalone** freeze in Minimig. The first FPGA snapshot showed `CPU_FETCHES=56095723` unchanged over 3 seconds, `FETCH_LAST=00FFFFFE`, `FETCH_PREV=00040006`, Paula `DMASTATE=0`, `dma_arms=39`, `dma_done=39`, and last requested track 24. The same IPF boots in Amiberry 8.5. We need to decide whether CPU execution has entered STOP/HALT/exception handling or is stalled on a bus handshake, not retry floppy setup tests.

**The new source only adds read-only probes.** It does not change the CPU, reset, clocks, Paula DMA, disk flux decode or interrupt logic.

The two-layer patch sequence is:
- FPGA pinned `MiSTer-devel/Minimig-AGA_MiSTer` commit `7d5d3c2f685af4ce3eb361c22893fccd153f2d87`, Rick ERSY v4 one-line fix, then `patch_bart_fpga_snapshot_v1.py`, then `patch_bart_fpga_cpu_bus_v2.py`.
- Physical Floppy Main pinned commit `d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2`, `patch_bart_main_snapshot_v1.py`, then `patch_bart_main_cpu_bus_v2.py`.
- New FPGA diagnostic SPI signature `B4A7`, version `2`, 40 consecutive 16-bit registers (indices 0–39). The v2 Main rejects v1 or stock cores.
- Only one Quartus fitter seed (5) is compiled; the existing experimental setup tolerance permits setup slack down to `−0.200 ns` while rejecting negative hold/recovery/removal/pulse-width slack. **A passing experimental workflow is not a fully timing-clean hardware build.**
- A detailed TimeQuest path report is archived alongside logs; never deploy a failed workflow.

## New fields in `/tmp/bart-snapshots.txt`

- `RAW_BUS` — last sampled CPU address bus at 28 MHz; **not** the architectural PC or necessarily an instruction-fetch address.
- `BUSFLAGS`, bit 15 running reset input, 14 reset_out, 13 TG68K selected (0 means fx68k), 12 fx68k `ASn` (0=cycle active), 11 external chip `ASn`, 10 chip `DTACKn` (0=ack), 9 selected RAM route, 8 RAM ready, 7 CPU request, 6 TG enable, 5 CPU request gate, 4 chip ready, 3 fx68k R/Wn, 2:0 fx68k function code.
- `BUSDETAIL`, bits 15:14 reserved, 13:11 chip interrupt level input, 10:8 fx68k function code, 7:6 TG busstate, 5:4 selected CPU busstate, 3 ph1, 2 ph2, 1 fastchip_ready, 0 fastchip_selack.
- `FETCH_OLD2` and `FETCH_OLD3` — two fetch addresses preceding the existing FETCH_PREV/FETCH_LAST (four-address sequence total).
- `BUS_EVENTS` — count of initiated fx68k bus cycles or TG-accepted request cycles. **Not an instruction retirement counter.** Compare across snapshots.
- Existing v1 fields are preserved and read through reg 29.

## Install and capture

**Only after checking that BOTH jobs in the new v2 GitHub Actions run succeeded.** No commercial IPF or ROM is committed to GitHub.

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin
git switch --track origin/diagnostic/bart-cpu-bus-v2
bash scripts/deploy-bart-cpu-bus-v2.sh <successful-V2-run-id> mister
```

Reload MiSTer to activate the separate diagnostic Main, choose `_Unstable/Minimig_Bart_CPU_Bus_v2_Experimental.rbf`, A500 KS 1.3 512K chip+512K slow, and directly boot the same Disk 2 IPF. **Do not reset after the hang.** On the Mac:

```bash
ssh root@mister 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 3; touch /tmp/bart-snapshot.req; sleep 3; cat /tmp/bart-snapshots.txt'
scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-cpu-bus-v2.txt"
```

Upload the **text log** for analysis. Original working Rick FPGA `Minimig_Rick_ERSY_v4_20261116.rbf` and Physical Main executable are untouched by the installer. The script prints the exact rollback command for the backed-up `MiSTer.ini`. Restart MiSTer and reload the working Rick core after restoring.

## Interpretation constraints

A frozen fetch counter and `ASn=0`, with relevant `DTACKn=1` and stable bus address, support a stalled bus transaction; `ASn=1` and no bus events suggest idle/STOP/HALT, but do not prove which. If `BUS_EVENTS` continues while `CPU_FETCHES` remains static, investigate non-instruction CPU activity or the counter qualification. A strange fetch sequence is not automatically proof that an address is unmapped; `0xFFFFFE` is at the top of the Kickstart address range. All conclusions require care because the build accepts a small setup timing violation.
