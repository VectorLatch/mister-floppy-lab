# Upstream baseline lock — verified 2026-11-16

| Component | Authoritative source | Exact revision |
| --- | --- | --- |
| Minimig FPGA | https://github.com/MiSTer-devel/Minimig-AGA_MiSTer (`MiSTer` branch) | `7d5d3c2f685af4ce3eb361c22893fccd153f2d87` (2026-11-09) |
| Physical Floppy Linux Main | https://github.com/manfredi90/Main_MiSTer_Physical_Floppy | `v1.3` = `d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2` (2026-11-12) |
| Official v1.3 ARM executable | https://github.com/manfredi90/Main_MiSTer_Physical_Floppy/releases/tag/v1.3 | SHA-256 `4420074539883d8fcd43ac53eff7ebc6168b047356ada9a0a524f825b44d186f` |

This repository does not embed upstream source trees or proprietary Kickstart ROMs. The Actions workflow clones exact upstream commits to isolate and preserve the baseline. The FPGA build uses `ghcr.io/raetro/quartus:mister` (container tag, NOT an immutable image digest); the resolved digest is captured with the artifact for auditing. The upstream Quartus project uses seed 1. Timing must be inspected before interpreting an `.rbf` as a verified hardware-compatible build.

The `Minimig_20260907.rbf` bundled in upstream's `releases/` folder predates the October 2026 flux-mode requirements; do **not** use it as the baseline for Greaseweazle flux-mode testing.
