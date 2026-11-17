# Bart SPS 0884 Disk 2 — CPU-visible address-error vector read probe v7

## Exact current failure

**Do not conflate with the earlier Bart Disk 1 Ocean-splash investigation.** For the *current* Bart SPS 0884 release, Disk 1 loads successfully on both Minimig and Amiberry; Disk 2 also boots independently in Amiberry, but a standalone Disk 2 boot under Minimig ends in a reproducible fx68k CPU HALT.

V3–V6 have established that fx68k enters internal HALT microcode `0x001` with a latched group-0 address-error exception; the most recent v6 real-hardware snapshot showed:

```text
SIG=B4AB VER=6 DF_TRACE_FLAGS=0007
DF_PRE0=00070876 DF_PRE1=00070878 DF_PRE2=0007087A
DF_PRE3=00072A48 DF_PRE4=0007087C DF_PRE5=0007087E
DF_FIRST=00DF21D0 DF_PC=0000000C DF_PSW=2704 DF_IRD=21D0
FX_HALT=1 FX_UADDR=001 FX_ERR=61
```

$0000000C is the 68000 vector-3 *address error handler pointer* address, and $DF21D0 is in the Amiga custom-chip register decode rather than game RAM. These observations are consistent with fetching an incorrect exception handler pointer **but do not establish where the bad value originated**.

## Focused v7 question

What 16-bit values were actually present on the **CPU input bus connected to fx68k.iEdb** when supervisor/software memory bus reads at physical 24-bit addresses **$00000C and $00000E** completed, shortly before the **first qualified program-space fetch into $DFxxxx**? Do these two 16-bit words concatenate to a 32-bit pointer whose physical low 24 bits equal that first $DF fetch?

This probe is read-only; it neither patches exception vectors nor changes fx68k control, processor timing, Paula, DMA, floppy data or real IPF contents.

Use the exact pinned FPGA source `7d5d3c2f685af4ce3eb361c22893fccd153f2d87` and pinned Physical-Floppy Main `d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2`. Start with the proven Rick ERSY v4 patch and Bart read-only v1/v2/v3/v6 overlays (NOT v4/v5 odd-access recorders). Apply:

- `scripts/patch_bart_fpga_address_vector_reads_v7.py` — CPU-side read-data/metadata capture and first-DF freeze
- `scripts/patch_bart_main_address_vector_reads_v7.py` — paired on-demand Main decoder

The FPGA's wire `cpu_din` is directly connected to `fx68k.iEdb` in `rtl/cpu_wrapper.v`. Capture at `ph2` (the same clock enable fed to fx68k `enPhi2`) when `ASn` is asserted, `eRWn` is read, both UDSn and LDSn are asserted, and the **same selected active-low DTACKn** presented to fx68k is asserted. De-duplicate bus cycles by waiting for ASn to go high again. Record all function-code variants, rather than assuming supervisor data, and disclose actual FC in the output.

**Interpretation limit:** This is CPU-input-bus data at a qualified PHI2 edge. It is not an internal logic analyser that proves the address was actually committed into a specific fx68k register. Even if assembled vector equals $00DF21D0, we must still distinguish memory contents, selection/mux timing, and instruction-core behaviour.

Freeze last qualified $C and $E samples **at first program-space fetch into $DFxxxx**; later erroneous fetches/reads cannot overwrite these. If either vector word was not observed before first DF, its count is zero and data field is not valid. Also collect bus-event serials to establish whether the two latest words are nearby and ordered.

## New SPI fields

Signature **`B4AC`**, version **7**. The old read-only on-demand E7xx FPGA SPI interface and 6-bit register selector stay the same: **64 total words**. Words 0..44 retain v1/v2/v3 diagnostics. Words 45..63 are reinterpreted using the same v6 transport registers, so use the **matching v7 Main binary**:

| Output | Meaning |
|---|---|
| `VEC_FLAGS` | bit0 frozen DF; bit1 $C read seen; bit2 $E read seen; bit3 latest C bus event before latest E; bit4 fx68k selected; bit5 low24 pointer matches DF_FIRST; bit6 both reads had FC=101 |
| `VEC_C_COUNT`, `VEC_E_COUNT` | saturated 16-bit successful sampled read-cycle counts before first DF |
| `VEC_C_DATA`, `VEC_E_DATA` | Latest 16-bit CPU input-bus samples at $C and $E |
| `VEC_ASSEMBLED` | `(C << 16) \| E` (only meaningful when both counts valid and event order relevant) |
| `VEC_C_META`, `VEC_E_META` | bits [15:13]=FC; [12:11]=RAM mux source; [10]=ramsel; [9]=ramready; [8]=chip_dtack; [7]=read; [6:5]=UDSn/LDSn; [4]=ph2; [3]=cpu_req |
| `VEC_C_PC`, `VEC_E_PC` | raw internal fx68k `{PcH,PcL}` at each last captured read, not guaranteed architectural PC |
| `VEC_C_BUS_EVT`, `VEC_E_BUS_EVT` | existing cumulative ASn/bus-event counter at capture |
| `VEC_DF_BUS_EVT`, `VEC_DF_FIRST` | bus-event counter/address at first $DFxxxx program-space fetch |

## Build and timing

Branch `diagnostic/bart-address-vector-reads-v7`. Workflow `.github/workflows/build-bart-address-vector-reads-v7.yml`. Exactly one FPGA fitter seed (**5**), pinned upstream sources and working Rick patch, build both FPGA + paired Main, **strict nonnegative worst-case slack** requirement for setup, hold, recovery, removal and minimum pulse width.

Run: https://github.com/VectorLatch/mister-floppy-lab/actions/runs/44053799182. Started Nov 17 2026; status and timing must be verified before deployment.

## Mac install and capture

**Only after both jobs succeed and timing is verified:**

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin
git switch diagnostic/bart-address-vector-reads-v7 2>/dev/null || git switch --track origin/diagnostic/bart-address-vector-reads-v7
git pull --ff-only
bash scripts/deploy-bart-address-vector-reads-v7.sh 44053799182 mister
```

The installer validates the GitHub run branch/workflow, FPGA + Main artifact names and SHA-256 checksums, backs up existing MiSTer.ini, and uses uniquely named `_Unstable/Minimig_Bart_VectorReads_v7.rbf` / `MiSTer_Physical-Floppy_BartVecV7`. The known-good Rick core and released Main are **not overwritten**.

Restart MiSTer, load the experimental core, use the established A500 KS1.3 512KB Chip/512KB Slow profile and boot **current SPS 0884 Bart Disk 2 IPF directly**, without Disk 1. Leave the crashed CPU halted and capture:

```bash
ssh root@mister '
rm -f /tmp/bart-snapshots.txt
touch /tmp/bart-snapshot.req
sleep 3
touch /tmp/bart-snapshot.req
sleep 3
cat /tmp/bart-snapshots.txt
'
scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-address-vector-reads-v7.txt"
```

Upload the file; the matching v7 Main will append `VEC_*` fields. To restore the immediately previous Main, use the backup path in `$HOME/Downloads/mister-floppy-lab/bart-address-vector-reads-v7/44053799182/remote-backup.txt` and restart MiSTer. The previous Main might itself be a diagnostic v6 build.

## Decision tree after capture

If both captured words form `$00DF21D0`, inspect where those data originated and whether the RAM handler vector at $C/$E itself became corrupt before the fetch, rather than altering fx68k's double-fault logic.

If the assembled pointer does not match the DF fetch, or either vector read was absent, investigate the internal exception microcode/data-route and read selection, including exact timing of `iEdb` sampling and possible other source of the invalid branch target. **Do not make a CPU or disk functional patch based on v7 alone.**
