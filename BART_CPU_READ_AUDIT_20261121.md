# Bart CPU/chip-RAM read-handshake audit — 2026-11-21

**Status: hypothesis rejected; NO Bart fix and NO hardware candidate build.**

## Reproducible isolated simulation

Workflow: `.github/workflows/verify-cpu-read-handshake.yml`

Passing run: https://github.com/VectorLatch/mister-floppy-lab/actions/runs/44910267930

Sources: unmodified pinned MiSTer-devel/Minimig-AGA_MiSTer commit
`7d5d3c2f685af4ce3eb361c22893fccd153f2d87`,
`rtl/minimig_m68k_bridge.v` and `rtl/amiga_clk.v`.
Testbench: `tests/tb_chipram_read.v`.

The testbench drives an artificial DMA ownership pattern `dbr = !cck`
during a CPU chip-RAM read. It models Gary's CPU read-data mux masking
the data to zero during DMA ownership.

- Without DMA: expected 0xCAFE, observed 0xCAFE.
- Artificial `dbr = !cck`: expected 0xBEEF, observed 0x0000.

**This is NOT a reproduced real Minimig failure.** It establishes only
that injecting an *invalid DMA grant pattern* into the standalone bridge
can make it capture incorrect data.

Earlier failures of the bench (undefined data even for a no-DMA control)
were due to an incorrect CPU bus stimulus/sample phase. They were fixed;
do not misinterpret those failed CI runs as chip-RAM bugs.

## Full-system source check (disqualifying evidence)

Pinned upstream RTL:

- `rtl/agnus_beamcounter.v`: `hpos[0] = cck`.
- `rtl/agnus_diskdma.v`: `dma = dmal & dmaslot & hpos[0]`.
- `rtl/agnus_refresh.v`: DMA only for hpos patterns ending in 1.
- `rtl/agnus_audiodma.v`: hpos DMA cases all end in 1.
- `rtl/agnus_bitplanedma.v`: `dma = ... && hpos[0] && ...`.
- `rtl/agnus_spritedma.v`: `reqdma` only if `hpos[1:0]==2'b01`.
- `rtl/agnus_copper.v`: `reqdma = dma_req & bus_ena & clk_ena`;
  `clk_ena = hpos[0]`.
- `rtl/agnus_blitter.v`: `reqdma = dma_req & enadma & clkena`;
  `clkena` is connected to `cck` in `rtl/agnus.v`.
- `rtl/agnus.v`: `dbr` asserted only when one of these DMA
  requests owns the bus; otherwise `dbr=0`.

Thus, for fully defined 0/1 signals in the normal source:
`dbr -> cck`, and **the test's `dbr=1 && cck=0` state cannot be
produced by the actual Agnus DMA scheduler**.

The bridge's actual data latch enable is
`~l_as & ~l_dtack & ~cck`; with `cck=0`, normal Agnus DMA is not
active. The synthetic data-latch failure therefore does not justify
a patch to the CPU bridge.

## Further source review

The real MiSTer memory backend is not asynchronous SRAM:
`Minimig.sv` feeds `minimig_sram_bridge` and `chipdma_arb` to
`sdram_ctrl` running from the 114MHz system clock. The SDRAM
controller updates `chipRD` at `sdram_state == 9` for a CHIP
read slot. No proven invalid-data/ACK overlap was found in this review.

An RTL simulation of this small component pair does **not** simulate
Bart, its self-modifying loader, disk image or exact real machine
timing. Reproducing the *exact* intermittent game problem requires a
much more complete test environment and matching game/ROM data.

## Existing captured evidence

The supplied v13 failed-versus-perfect traces differ in later Line-F
exception counts (590 vs 589), and the recorded final Line-F PC
(0x7087C vs 0x70912), but the same first Line-F at 0x7009C is present
in different visible outcomes. This difference does not itself prove
memory corruption or a DMA handshake bug.

## Engineering decision

No source change to `rtl/agnus.v`, `rtl/gary.v`,
`rtl/minimig_m68k_bridge.v`, `rtl/sdram_ctrl.v` or the physical
floppy pipeline. No speculative v19 RTL fix; preserve running MiSTer
and its backups. Any future patch must have a reachable failing
condition demonstrated against full-system invariants and the same
test must pass after a minimal correction.
