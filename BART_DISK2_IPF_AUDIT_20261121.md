# Bart Cartoon Classics Disk 2 IPF: source audit (21 Nov 2026)

## Scope

Inspected the user-supplied SPS IPF 0884 privately. No original disk data, extracted tracks, or Kickstart ROM is in this public repository or its CI artifacts.

## Disc structure

The CAPS INFO record reports SPS ID 884 and 82 cylinders / two sides. All 330 record CRCs validated. Cylinder 0, side 1 uses Copylock Amiga track type 3 with eleven nonstandard sector sync patterns and a Rob Northen Comp signature. Most other tracks store a custom long data block per side rather than standard 11-sector AmigaDOS blocks.

## Source defect

Pinned Main: manfredi90/Main_MiSTer_Physical_Floppy at d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2.

Main IPFFile calls CAPS with DI_LOCK_OVLBIT: the returned track overlap is in *bits*. The source saves that value as m_overlapBit but compares it directly to m_bufferPos, an index into 8-bit trackbuf and timebuf arrays and a counter that wraps at tracklen/8. In other words, bits are compared to bytes.

The confirmed mismatch could delay the INDEX pulse eightfold or suppress it on tracks with nonzero overlap. The minimal change in patches/main/0001-ipf-overlap-bits-to-bytes.patch converts it to the nearest following byte boundary.

## Verification performed without the IPF on GitHub

Actions run: https://github.com/VectorLatch/mister-floppy-lab/actions/runs/44912642812

- Cloned exact pinned Main source and confirmed the original code.
- Applied the source patch.
- Compiled and ran C++ regression tests using the exact helper function in patched production Main. 100303 synthetic index positions tested, one INDEX each, 0–7 bitcells late.
- Built a working-format ELF 32-bit ARM Physical Floppy Main executable with the release-compatible toolchain. Artifact: Bart-IndexBits-Main-only.
- No FPGA build, no change to the installed MiSTer, no private IPF in CI.

## Limits

This establishes a source-level Main defect and validated unit correction, *not* that the defect causes Bart's intermittent crashes and corrupted playfield. The actual CAPS-decoded track overlap values from this IPF and Bart's failing execution path have not been confirmed in the current environment. The change is a candidate for an optional Main-only hardware A/B comparison, not a proven Bart gameplay fix.

Separately, the game's documented WHDLoad installer inserts 30 blitter waits, a different timing hypothesis that is not verified as the root cause on Minimig.
