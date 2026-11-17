# Bart CPU: freeze first DFxxxx qualified instruction fetch (v6)

## Rationale

Bart SPS 0884 standalone-IPF investigation shows internal fx68k CPU HALT at microcode 0x001 with group-0 address error (v3/v4/v5). The **last four qualified instruction-fetch bus addresses** have repeatedly been:

```text
DF220C -> DF220E -> DF2210 -> DF2212
```

These are inside the custom-chip register decode at `$DF0000-$DFFFFF`, not normal game code RAM. At the fatal end, `FX_HALT=1`, `FX_ERR=61`, and counters no longer advance. The v5 two-last-odd-word-access recorder supports a nested address-error sequence:

```text
FX_PREV_ADDR=00003E5F FX_PREV_PC=BDDF2212 FX_PREV_GRP0=0
FX_LAST_ADDR=22804AAD FX_LAST_PC=BDDF2212 FX_LAST_GRP0=C
```

Those addresses/PCs are *internal microarchitecture registers sampled at an event*; they do not independently prove bad disk bits or a real 68k PC. The investigation must now examine how the first fetch into the `$DFxxxx` hardware region was reached.

## What v6 captures

This is **not** a game fix. It changes no CPU microcode, exception processing, floppy DMA, disk decoding, RAM timing, or host disk read behavior.

Start from pinned FPGA `7d5d3c2f685af4ce3eb361c22893fccd153f2d87` with the proven Rick ERSY v4 one-line fix and the v1/v2/v3 *read-only* Bart taps. Do **not** layer v4/v5 (whose first/last fault recorders are no longer needed). Add `scripts/patch_bart_fpga_first_df_fetch_v6.py`.

At each original v1 `bart_fetch_evt` (fx68k program-space fetch when `ASn` falls and `FC[1:0]==2'b10`), keep a rolling history of six preceding bus fetch start addresses. **The first qualifying fetch** in physical 24-bit `$DF0000-$DFFFFF`, after a previous fetch outside the range, freezes:

- `DF_PRE0..DF_PRE5`: six preceding *program fetch bus addresses* in oldest-first order, zero where history has not been filled.
- `DF_FIRST`: the first fetch into `$DFxxxx`.
- `DF_PC`: core's *internal* 32-bit `{PcH,PcL}` register, sampled at the transition; not automatically an instruction-retirement PC.
- `DF_PSW` and `DF_IRD`: core's internal status word and decoder register at the transition.
- `DF_TRACE_FLAGS`: bit0=triggered; bit1=prior fetch existed; bit2=fx68k selected; bit3=first fetch after reset already in DF region.

The trigger can also freeze if the *first* observed fetch after reset starts in the DF region, in which case bit3 is set and earlier entries are zero. If no fetch enters the DF region, `DF_TRACE_FLAGS=0`; this is not necessarily a build failure. Once frozen, the trace does not change until core reset.

Original SPI read mux has a 6-bit register selector. V6 **fills exactly all 64 words** without changing that selector: slots 0..44 retain v1/v2/v3 diagnostics, slots 45..58 are seven 32-bit fetch addresses (low16 then high16), 59..60 internal PC, 61 PSW, 62 IRD, 63 flags. FPGA signature `B4AB`, version `6`.

Matching `scripts/patch_bart_main_first_df_fetch_v6.py` extends the on-demand Physical Floppy Main reader to 64 words (pinned Main `d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2`). It rejects a mismatched FPGA/reader signature. No additional routine SPI traffic is introduced.

## Build

Separate branch `diagnostic/bart-first-df-fetch-v6`, workflow `.github/workflows/build-bart-first-df-fetch-v6.yml`, pinned sources, exactly **one fitter seed 5**, strict **nonnegative** reported setup, hold, recovery, removal and minimum-pulse-width slack gate. If timing fails, the build must be considered unsuitable even if an FPGA artifact contains partial reports. Both FPGA and Main jobs must pass before installation.

Build: https://github.com/VectorLatch/mister-floppy-lab/actions/runs/44042279903 (started Nov 17 2026; status must be rechecked before deploying).

## Safe installation (Mac)

After **both** jobs succeed with clean timing:

```bash
cd "$HOME/Downloads/mister-floppy-lab-starter"
git fetch origin
git switch diagnostic/bart-first-df-fetch-v6 2>/dev/null || git switch --track origin/diagnostic/bart-first-df-fetch-v6
git pull --ff-only
bash scripts/deploy-bart-first-df-fetch-v6.sh 44042279903 mister
```

The installer verifies the run, branch, workflow, hashes, and backs up the current `MiSTer.ini` on MiSTer and Mac. It installs independent filenames `_Unstable/Minimig_Bart_FirstDF_Trace_v6.rbf` and `MiSTer_Physical-Floppy_BartDFTraceV6`, without overwriting the Rick-fixed FPGA or original released Main.

Restart MiSTer, select the new experimental core, use the same A500 KS1.3 512K Chip/512K Slow and same Bart original IPF that reproduced the HALT. Leave the machine unreset after the hang. On the Mac:

```bash
ssh root@mister 'rm -f /tmp/bart-snapshots.txt; touch /tmp/bart-snapshot.req; sleep 3; touch /tmp/bart-snapshot.req; sleep 3; cat /tmp/bart-snapshots.txt'
scp root@mister:/tmp/bart-snapshots.txt "$HOME/Downloads/bart-first-df-fetch-v6.txt"
```

Upload the file for analysis. The script prints the immediate pre-install `MiSTer.ini` rollback command. After restoring it, restart the MiSTer; the prior configuration may itself have been a diagnostic Main.

## What this could resolve

If the frozen fetch sequence shows a branch/jump from a valid RAM/ROM code region into `$DFxxxx`, the next comparison should target *that* control-flow change and the memory data that provided the branch target. If the trace only shows I/O-region addresses or is untriggered, refine the trigger to catch earlier control-flow conditions; **do not blindly patch Paula/disk or exception behavior based on the terminal double fault**.
